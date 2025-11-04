import os
import secrets
import string
import csv
import io
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session as flask_session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import qrcode
from io import BytesIO
import base64

from database import init_db, get_db, get_setting, set_setting
from models import User
from timezone_utils import now as tz_now, format_datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'change-this-to-a-random-secret-key')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize database
init_db()

# Create upload directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Register timezone template filter
@app.template_filter('format_datetime')
def format_datetime_filter(dt, format_str='%Y-%m-%d %H:%M:%S'):
    """Format datetime to local timezone in templates"""
    return format_datetime(dt, format_str)

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('需要管理员权限', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def password_change_required(f):
    """Decorator to require password change if needed"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and current_user.must_change_password:
            if request.endpoint != 'change_password' and request.endpoint != 'logout':
                flash('首次登录必须修改密码', 'warning')
                return redirect(url_for('change_password'))
        return f(*args, **kwargs)
    return decorated_function

def generate_activity_code():
    """Generate 6-character activity code"""
    chars = string.ascii_letters + string.digits
    while True:
        code = ''.join(secrets.choice(chars) for _ in range(6))
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM attendance_sessions WHERE activity_code = ?', (code,))
        if not cursor.fetchone():
            conn.close()
            return code
        conn.close()

def generate_qr_token():
    """Generate secure QR token"""
    return secrets.token_urlsafe(32)

@app.route('/')
@login_required
@password_change_required
def index():
    """User home page"""
    system_title = get_setting('system_title', '签到系统')
    total_points = current_user.get_points()
    points_history = current_user.get_points_history()

    # Get pending leave requests
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT lr.*, ats.activity_code
        FROM leave_requests lr
        LEFT JOIN attendance_sessions ats ON lr.session_id = ats.id
        WHERE lr.user_id = ?
        ORDER BY lr.created_at DESC
    ''', (current_user.id,))
    leave_requests = cursor.fetchall()
    conn.close()

    return render_template('index.html',
                         system_title=system_title,
                         total_points=total_points,
                         points_history=points_history,
                         leave_requests=leave_requests)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    system_title = get_setting('system_title', '签到系统')

    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        user = User.get_by_student_id(student_id)

        if user and user.check_password(password):
            login_user(user, remember=True)

            # Check if this is a QR code scan login
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/checkin/'):
                flask_session['pending_checkin'] = next_page
                return redirect(url_for('complete_checkin'))

            return redirect(url_for('index'))
        else:
            flash('学工号或密码错误', 'error')

    return render_template('login.html', system_title=system_title)

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    return redirect(url_for('login'))

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password"""
    system_title = get_setting('system_title', '签到系统')

    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_user.check_password(current_password):
            flash('当前密码错误', 'error')
        elif len(new_password) < 6:
            flash('新密码长度至少6位', 'error')
        elif new_password != confirm_password:
            flash('两次输入的新密码不一致', 'error')
        elif current_password == new_password:
            flash('新密码不能与旧密码相同', 'error')
        elif new_password == current_user.student_id:
            flash('密码不能和账号相同', 'error')
        else:
            current_user.set_password(new_password)

            # Check if user was trying to check in via QR code
            had_pending_checkin = flask_session.pop('pending_checkin', None)

            if had_pending_checkin:
                # Clear the pending checkin and show rescan message
                return redirect(url_for('password_changed_rescan'))
            else:
                flash('密码修改成功。如果您正在签到，请重新扫描二维码以完成签到。', 'success')
                return redirect(url_for('index'))

    return render_template('change_password.html', system_title=system_title)

@app.route('/password-changed-rescan')
@login_required
def password_changed_rescan():
    """Show message to rescan QR code after password change"""
    system_title = get_setting('system_title', '签到系统')
    return render_template('password_changed_rescan.html', system_title=system_title)

@app.route('/checkin/<qr_token>')
def checkin(qr_token):
    """Check-in via QR code"""
    if not current_user.is_authenticated:
        return redirect(url_for('login', next=request.url))

    if current_user.must_change_password:
        flash('请先修改密码', 'warning')
        return redirect(url_for('change_password'))

    # Verify QR token - 仅验证时效性和会话状态，不检查 is_used
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT qr.*, ats.activity_code
        FROM qr_codes qr
        JOIN attendance_sessions ats ON qr.session_id = ats.id
        WHERE qr.qr_token = ? AND qr.expires_at > ?
        AND ats.is_active = 1
    ''', (qr_token, tz_now()))
    qr_code_row = cursor.fetchone()

    if not qr_code_row:
        conn.close()
        return render_template('checkin_result.html',
                             success=False,
                             message='二维码已过期或签到活动已结束',
                             system_title=get_setting('system_title', '签到系统'))

    session_id = qr_code_row['session_id']

    # Check if already checked in
    cursor.execute('''
        SELECT id FROM attendance_records
        WHERE session_id = ? AND user_id = ?
    ''', (session_id, current_user.id))

    if cursor.fetchone():
        conn.close()
        return render_template('checkin_result.html',
                             success=True,
                             message='您已完成签到，无需重复操作',
                             system_title=get_setting('system_title', '签到系统'))

    # Get session info to check if it has paired checkout
    cursor.execute('''
        SELECT session_type, paired_session_id,
               (SELECT id FROM attendance_sessions WHERE paired_session_id = ats.id) as checkout_session_id
        FROM attendance_sessions ats
        WHERE id = ?
    ''', (session_id,))
    session_info = cursor.fetchone()

    session_type = session_info['session_type'] if session_info else 'checkin'
    has_checkout = session_info and (session_info['checkout_session_id'] is not None)

    # Record attendance
    cursor.execute('''
        INSERT INTO attendance_records (session_id, user_id, status)
        VALUES (?, ?, 'present')
    ''', (session_id, current_user.id))

    # 加分逻辑：只有在配对活动中签到和签退都完成才加分
    should_add_points = False

    if session_type == 'checkout':
        # 这是签退会话 - 检查用户是否完成了配对的签到
        paired_checkin_id = session_info['paired_session_id']
        if paired_checkin_id:
            cursor.execute('''
                SELECT id FROM attendance_records
                WHERE session_id = ? AND user_id = ? AND status = 'present'
            ''', (paired_checkin_id, current_user.id))
            if cursor.fetchone():
                # 用户签到和签退都完成了，加分
                should_add_points = True
    elif not has_checkout:
        # 独立签到活动（无配对签退），立即加分
        should_add_points = True
    # 如果是有配对签退的签到活动，不加分（等签退完成后再加）

    if should_add_points:
        checkin_points = float(get_setting('checkin_points', '1'))
        if checkin_points != 0:
            cursor.execute('''
                INSERT INTO points_records (user_id, points, reason, record_type, session_id)
                VALUES (?, ?, '签到成功', 'checkin', ?)
            ''', (current_user.id, checkin_points, session_id))

    conn.commit()
    conn.close()

    return render_template('checkin_result.html',
                         success=True,
                         message='签到成功！',
                         system_title=get_setting('system_title', '签到系统'))

@app.route('/complete-checkin')
@login_required
@password_change_required
def complete_checkin():
    """Complete check-in after login"""
    pending_checkin = flask_session.pop('pending_checkin', None)
    if pending_checkin:
        return redirect(pending_checkin)
    return redirect(url_for('index'))

@app.route('/leave/request', methods=['GET', 'POST'])
@login_required
@password_change_required
def request_leave():
    """Request leave"""
    system_title = get_setting('system_title', '签到系统')

    if request.method == 'POST':
        leave_type = request.form.get('leave_type')
        reason = request.form.get('reason', '').strip()

        if not leave_type or leave_type not in ['public', 'personal', 'sick']:
            flash('请选择请假类型', 'error')
            return redirect(url_for('request_leave'))

        if not reason:
            flash('请填写请假原因', 'error')
            return redirect(url_for('request_leave'))

        # Create leave request
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO leave_requests (user_id, leave_type, reason, status)
            VALUES (?, ?, ?, 'pending')
        ''', (current_user.id, leave_type, reason))
        leave_request_id = cursor.lastrowid

        # Handle file uploads
        files = request.files.getlist('attachments')
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                timestamp = tz_now().strftime('%Y%m%d%H%M%S')
                unique_filename = f"{timestamp}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)

                cursor.execute('''
                    INSERT INTO leave_attachments (leave_request_id, filename, filepath)
                    VALUES (?, ?, ?)
                ''', (leave_request_id, filename, filepath))

        conn.commit()
        conn.close()

        flash('请假申请已提交', 'success')
        return redirect(url_for('index'))

    return render_template('request_leave.html', system_title=system_title)

@app.route('/admin')
@login_required
@admin_required
@password_change_required
def admin_dashboard():
    """Admin dashboard"""
    system_title = get_setting('system_title', '签到系统')

    conn = get_db()
    cursor = conn.cursor()

    # Get statistics
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_admin = 0')
    total_users = cursor.fetchone()['count']

    cursor.execute('SELECT COUNT(*) as count FROM attendance_sessions')
    total_sessions = cursor.fetchone()['count']

    cursor.execute('SELECT COUNT(*) as count FROM leave_requests WHERE status = "pending"')
    pending_leaves = cursor.fetchone()['count']

    conn.close()

    return render_template('admin/dashboard.html',
                         system_title=system_title,
                         total_users=total_users,
                         total_sessions=total_sessions,
                         pending_leaves=pending_leaves)

@app.route('/admin/users')
@login_required
@admin_required
@password_change_required
def admin_users():
    """Admin user management"""
    system_title = get_setting('system_title', '签到系统')
    users = User.get_all_users()
    return render_template('admin/users.html', system_title=system_title, users=users)

@app.route('/admin/users/template')
@login_required
@admin_required
def download_user_template():
    """Download CSV template for user import"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['学工号', '姓名'])
    writer.writerow(['20230001', '张三'])
    writer.writerow(['20230002', '李四'])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='用户导入模板.csv'
    )

@app.route('/admin/users/import', methods=['POST'])
@login_required
@admin_required
def import_users():
    """Import users from CSV"""
    if 'file' not in request.files:
        flash('请选择文件', 'error')
        return redirect(url_for('admin_users'))

    file = request.files['file']
    if file.filename == '':
        flash('请选择文件', 'error')
        return redirect(url_for('admin_users'))

    if not file.filename.endswith('.csv'):
        flash('只支持CSV文件', 'error')
        return redirect(url_for('admin_users'))

    try:
        stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
        csv_reader = csv.DictReader(stream)

        success_count = 0
        error_count = 0

        for row in csv_reader:
            student_id = row.get('学工号', '').strip()
            name = row.get('姓名', '').strip()

            if student_id and name:
                if User.create_user(student_id, name):
                    success_count += 1
                else:
                    error_count += 1
            else:
                error_count += 1

        if success_count > 0:
            flash(f'成功导入{success_count}个用户', 'success')
        if error_count > 0:
            flash(f'{error_count}个用户导入失败（可能已存在）', 'warning')

    except Exception as e:
        flash(f'导入失败: {str(e)}', 'error')

    return redirect(url_for('admin_users'))

@app.route('/admin/users/delete', methods=['POST'])
@login_required
@admin_required
def delete_users():
    """Delete multiple users"""
    user_ids = request.form.getlist('user_ids')

    if not user_ids:
        flash('请选择要删除的用户', 'error')
        return redirect(url_for('admin_users'))

    conn = get_db()
    cursor = conn.cursor()

    for user_id in user_ids:
        cursor.execute('DELETE FROM users WHERE id = ? AND is_admin = 0', (user_id,))

    conn.commit()
    conn.close()

    flash(f'成功删除{len(user_ids)}个用户', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_user_password(user_id):
    """Reset user password"""
    user = User.get(user_id)
    if user and not user.is_admin:
        user.reset_password()
        flash(f'已重置用户 {user.name} 的密码为学工号', 'success')
    else:
        flash('用户不存在或无法重置', 'error')

    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/rename', methods=['POST'])
@login_required
@admin_required
def rename_user(user_id):
    """Rename user"""
    user = User.get(user_id)
    if not user or user.is_admin:
        flash('用户不存在或无法更名', 'error')
        return redirect(url_for('admin_users'))

    new_name = request.form.get('new_name', '').strip()
    if not new_name:
        flash('新姓名不能为空', 'error')
        return redirect(url_for('admin_users'))

    if user.rename_user(new_name):
        flash(f'用户姓名已从 "{user.name}" 更新为 "{new_name}"', 'success')
    else:
        flash('更新失败', 'error')

    return redirect(url_for('admin_users'))

# Import and register additional routes
from app_attendance import register_attendance_routes
from app_leave_points import register_leave_points_routes

register_attendance_routes(app, admin_required, password_change_required, generate_activity_code, generate_qr_token)
register_leave_points_routes(app, admin_required, password_change_required)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
