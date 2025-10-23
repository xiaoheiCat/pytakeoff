# Attendance management routes (to be imported into app.py)

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import qrcode
from io import BytesIO
import base64

from database import get_db, get_setting
from models import User

def generate_qr_code_image(data):
    """Generate QR code image as base64"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return base64.b64encode(buffer.getvalue()).decode()

def register_attendance_routes(app, admin_required, password_change_required, generate_activity_code, generate_qr_token):
    """Register attendance-related routes"""

    @app.route('/admin/attendance')
    @login_required
    @admin_required
    @password_change_required
    def admin_attendance():
        """Admin attendance management"""
        system_title = get_setting('system_title', '签到系统')

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ats.*, u.name as created_by_name,
                   COUNT(DISTINCT ar.id) as checked_in_count,
                   (SELECT COUNT(*) FROM users WHERE is_admin = 0) as total_users
            FROM attendance_sessions ats
            LEFT JOIN users u ON ats.created_by = u.id
            LEFT JOIN attendance_records ar ON ats.id = ar.session_id
            GROUP BY ats.id
            ORDER BY ats.created_at DESC
        ''')
        sessions = cursor.fetchall()
        conn.close()

        return render_template('admin/attendance.html',
                             system_title=system_title,
                             sessions=sessions)

    @app.route('/admin/attendance/create', methods=['POST'])
    @login_required
    @admin_required
    def create_attendance_session():
        """Create new attendance session"""
        start_time_str = request.form.get('start_time', '').strip()
        end_time_str = request.form.get('end_time', '').strip()

        # Parse times
        if not start_time_str:
            start_time = datetime.now()
        else:
            try:
                start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('开始时间格式错误', 'error')
                return redirect(url_for('admin_attendance'))

        if not end_time_str:
            end_time = start_time + timedelta(minutes=10)
        else:
            try:
                end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('结束时间格式错误', 'error')
                return redirect(url_for('admin_attendance'))

        if end_time <= start_time:
            flash('结束时间必须晚于开始时间', 'error')
            return redirect(url_for('admin_attendance'))

        # Generate activity code
        activity_code = generate_activity_code()

        # Create session
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO attendance_sessions (activity_code, start_time, end_time, created_by, is_active)
            VALUES (?, ?, ?, ?, 1)
        ''', (activity_code, start_time, end_time, current_user.id))
        conn.commit()
        conn.close()

        flash(f'签到活动已创建，活动码：{activity_code}', 'success')
        return redirect(url_for('admin_attendance'))

    @app.route('/admin/attendance/<int:session_id>/end', methods=['POST'])
    @login_required
    @admin_required
    def end_attendance_session(session_id):
        """End attendance session"""
        conn = get_db()
        cursor = conn.cursor()

        # Check for pending leave requests
        cursor.execute('''
            SELECT COUNT(*) as count FROM leave_requests
            WHERE status = 'pending'
        ''')
        pending_count = cursor.fetchone()['count']

        if pending_count > 0:
            conn.close()
            flash(f'还有{pending_count}个待审批的请假申请，请先审批', 'warning')
            return redirect(url_for('admin_leave_approval', session_id=session_id))

        # Mark session as inactive
        cursor.execute('UPDATE attendance_sessions SET is_active = 0 WHERE id = ?', (session_id,))

        # Get all users who didn't check in and don't have approved leave
        cursor.execute('''
            SELECT u.id, u.name, u.student_id
            FROM users u
            WHERE u.is_admin = 0
            AND u.id NOT IN (
                SELECT ar.user_id FROM attendance_records ar WHERE ar.session_id = ?
            )
            AND u.id NOT IN (
                SELECT lr.user_id FROM leave_requests lr
                WHERE lr.session_id = ? AND lr.status = 'approved'
            )
        ''', (session_id, session_id))
        absent_users = cursor.fetchall()

        # Record absences and deduct points
        absent_points = float(get_setting('absent_points', '-2'))
        for user in absent_users:
            # Record absence
            cursor.execute('''
                INSERT INTO attendance_records (session_id, user_id, status)
                VALUES (?, ?, 'absent')
            ''', (session_id, user['id']))

            # Deduct points
            cursor.execute('''
                INSERT INTO points_records (user_id, points, reason, record_type, session_id, created_by)
                VALUES (?, ?, ?, 'absence', ?, ?)
            ''', (user['id'], absent_points, '缺勤', session_id, current_user.id))

        conn.commit()
        conn.close()

        flash(f'签到活动已结束，{len(absent_users)}人缺勤', 'success')
        return redirect(url_for('admin_attendance'))

    @app.route('/qr')
    @login_required
    @admin_required
    @password_change_required
    def qr_screen():
        """QR code display screen"""
        system_title = get_setting('system_title', '签到系统')
        return render_template('qr_screen.html', system_title=system_title)

    @app.route('/api/qr/start', methods=['POST'])
    @login_required
    @admin_required
    def start_qr_display():
        """Start QR code display"""
        data = request.get_json()
        activity_code = data.get('activity_code', '').strip()

        if not activity_code:
            return jsonify({'success': False, 'message': '请输入活动码'})

        # Verify activity code
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, end_time, is_active
            FROM attendance_sessions
            WHERE activity_code = ?
        ''', (activity_code,))
        session = cursor.fetchone()

        if not session:
            conn.close()
            return jsonify({'success': False, 'message': '活动码不存在'})

        if not session['is_active']:
            conn.close()
            return jsonify({'success': False, 'message': '该签到活动已结束'})

        # Check if session has expired
        end_time = datetime.strptime(session['end_time'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() > end_time:
            conn.close()
            return jsonify({'success': False, 'message': '该签到活动已过期'})

        conn.close()

        return jsonify({
            'success': True,
            'session_id': session['id'],
            'activity_code': activity_code
        })

    @app.route('/api/qr/generate/<int:session_id>')
    @login_required
    @admin_required
    def generate_qr_api(session_id):
        """Generate new QR code for session"""
        conn = get_db()
        cursor = conn.cursor()

        # Verify session exists and is active
        cursor.execute('''
            SELECT id, end_time, is_active
            FROM attendance_sessions
            WHERE id = ?
        ''', (session_id,))
        session = cursor.fetchone()

        if not session or not session['is_active']:
            conn.close()
            return jsonify({'success': False, 'message': '签到活动不存在或已结束'})

        # Generate QR token
        qr_token = generate_qr_token()
        qr_refresh_interval = int(get_setting('qr_refresh_interval', '15'))
        expires_at = datetime.now() + timedelta(seconds=qr_refresh_interval + 5)

        # Save QR code
        cursor.execute('''
            INSERT INTO qr_codes (session_id, qr_token, expires_at)
            VALUES (?, ?, ?)
        ''', (session_id, qr_token, expires_at))
        conn.commit()
        conn.close()

        # Generate QR code image
        checkin_url = url_for('checkin', qr_token=qr_token, _external=True)
        qr_image = generate_qr_code_image(checkin_url)

        return jsonify({
            'success': True,
            'qr_image': qr_image,
            'refresh_interval': qr_refresh_interval
        })

    @app.route('/api/qr/status/<int:session_id>')
    @login_required
    @admin_required
    def qr_status_api(session_id):
        """Get attendance status for QR display"""
        conn = get_db()
        cursor = conn.cursor()

        # Get checked-in users
        cursor.execute('''
            SELECT u.id, u.name, u.student_id, ar.checked_in_at
            FROM attendance_records ar
            JOIN users u ON ar.user_id = u.id
            WHERE ar.session_id = ?
            ORDER BY ar.checked_in_at DESC
        ''', (session_id,))
        checked_in = [dict(row) for row in cursor.fetchall()]

        # Get users who haven't checked in (excluding approved leaves)
        cursor.execute('''
            SELECT u.id, u.name, u.student_id
            FROM users u
            WHERE u.is_admin = 0
            AND u.id NOT IN (
                SELECT ar.user_id FROM attendance_records ar WHERE ar.session_id = ?
            )
            AND u.id NOT IN (
                SELECT lr.user_id FROM leave_requests lr
                WHERE (lr.session_id = ? OR lr.session_id IS NULL) AND lr.status = 'approved'
            )
            ORDER BY u.student_id
        ''', (session_id, session_id))
        not_checked_in = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return jsonify({
            'success': True,
            'checked_in': checked_in,
            'not_checked_in': not_checked_in,
            'checked_in_count': len(checked_in),
            'not_checked_in_count': len(not_checked_in)
        })
