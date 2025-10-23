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

    @app.route('/admin/attendance/<int:session_id>/records')
    @login_required
    @admin_required
    @password_change_required
    def attendance_records(session_id):
        """View attendance records for a session"""
        system_title = get_setting('system_title', '签到系统')

        conn = get_db()
        cursor = conn.cursor()

        # Get session info
        cursor.execute('''
            SELECT ats.*, u.name as created_by_name
            FROM attendance_sessions ats
            LEFT JOIN users u ON ats.created_by = u.id
            WHERE ats.id = ?
        ''', (session_id,))
        session = cursor.fetchone()

        if not session:
            conn.close()
            flash('签到活动不存在', 'error')
            return redirect(url_for('admin_attendance'))

        # Get all attendance records
        cursor.execute('''
            SELECT ar.*, u.name, u.student_id
            FROM attendance_records ar
            JOIN users u ON ar.user_id = u.id
            WHERE ar.session_id = ?
            ORDER BY
                CASE WHEN ar.checked_in_at IS NULL THEN 1 ELSE 0 END,
                ar.checked_in_at DESC
        ''', (session_id,))
        records = cursor.fetchall()

        # Get users who haven't checked in
        cursor.execute('''
            SELECT u.id, u.name, u.student_id
            FROM users u
            WHERE u.is_admin = 0
            AND u.id NOT IN (
                SELECT ar.user_id FROM attendance_records ar WHERE ar.session_id = ?
            )
            ORDER BY u.student_id
        ''', (session_id,))
        not_checked_in = cursor.fetchall()

        conn.close()

        return render_template('admin/attendance_records.html',
                             system_title=system_title,
                             session=session,
                             records=records,
                             not_checked_in=not_checked_in)

    @app.route('/admin/attendance/record/<int:record_id>/update', methods=['POST'])
    @login_required
    @admin_required
    def update_attendance_status(record_id):
        """Update attendance record status"""
        new_status = request.form.get('status', '').strip()

        valid_statuses = ['present', 'absent', 'public_leave', 'personal_leave', 'sick_leave']
        if new_status not in valid_statuses:
            flash('无效的状态', 'error')
            return redirect(url_for('admin_attendance'))

        conn = get_db()
        cursor = conn.cursor()

        # Get current record info
        cursor.execute('''
            SELECT ar.*, u.name, u.student_id
            FROM attendance_records ar
            JOIN users u ON ar.user_id = u.id
            WHERE ar.id = ?
        ''', (record_id,))
        record = cursor.fetchone()

        if not record:
            conn.close()
            flash('签到记录不存在', 'error')
            return redirect(url_for('admin_attendance'))

        old_status = record['status']
        session_id = record['session_id']
        user_id = record['user_id']

        # If status unchanged, do nothing
        if old_status == new_status:
            conn.close()
            flash('状态未改变', 'warning')
            return redirect(url_for('attendance_records', session_id=session_id))

        # Update attendance record status
        cursor.execute('''
            UPDATE attendance_records
            SET status = ?
            WHERE id = ?
        ''', (new_status, record_id))

        # Soft delete old points records for this session and user
        cursor.execute('''
            UPDATE points_records
            SET is_deleted = 1
            WHERE session_id = ? AND user_id = ? AND is_deleted = 0
        ''', (session_id, user_id))

        # Add new points record based on new status
        points = 0
        reason = ''
        record_type = 'manual'

        if new_status == 'present':
            # Present: no points change
            points = 0
            reason = '管理员标记为已签到'
        elif new_status == 'absent':
            points = float(get_setting('absent_points', '-2'))
            reason = '管理员标记为缺勤'
            record_type = 'absence'
        elif new_status == 'public_leave':
            points = float(get_setting('public_leave_points', '0'))
            reason = '管理员标记为公假'
            record_type = 'manual_leave'
        elif new_status == 'personal_leave':
            points = float(get_setting('personal_leave_points', '-1'))
            reason = '管理员标记为事假'
            record_type = 'manual_leave'
        elif new_status == 'sick_leave':
            points = float(get_setting('sick_leave_points', '-0.5'))
            reason = '管理员标记为病假'
            record_type = 'manual_leave'

        # Insert new points record if points != 0
        if points != 0:
            cursor.execute('''
                INSERT INTO points_records (user_id, points, reason, record_type, session_id, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, points, reason, record_type, session_id, current_user.id))

        conn.commit()
        conn.close()

        status_names = {
            'present': '已签到',
            'absent': '缺勤',
            'public_leave': '公假',
            'personal_leave': '事假',
            'sick_leave': '病假'
        }
        flash(f'已将 {record["name"]} 的状态修改为：{status_names[new_status]}', 'success')
        return redirect(url_for('attendance_records', session_id=session_id))

    @app.route('/admin/attendance/<int:session_id>/add_record', methods=['POST'])
    @login_required
    @admin_required
    def add_attendance_record(session_id):
        """Manually add attendance record for a user"""
        user_id = request.form.get('user_id', '').strip()
        status = request.form.get('status', 'present').strip()

        valid_statuses = ['present', 'absent', 'public_leave', 'personal_leave', 'sick_leave']
        if status not in valid_statuses:
            flash('无效的状态', 'error')
            return redirect(url_for('attendance_records', session_id=session_id))

        conn = get_db()
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute('SELECT id, name FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()

        if not user:
            conn.close()
            flash('用户不存在', 'error')
            return redirect(url_for('attendance_records', session_id=session_id))

        # Check if record already exists
        cursor.execute('''
            SELECT id FROM attendance_records
            WHERE session_id = ? AND user_id = ?
        ''', (session_id, user_id))
        existing = cursor.fetchone()

        if existing:
            conn.close()
            flash(f'{user["name"]} 已有签到记录', 'warning')
            return redirect(url_for('attendance_records', session_id=session_id))

        # Insert attendance record
        cursor.execute('''
            INSERT INTO attendance_records (session_id, user_id, status, checked_in_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (session_id, user_id, status))

        # Add points record based on status
        points = 0
        reason = ''
        record_type = 'manual'

        if status == 'present':
            points = 0
            reason = '管理员手动添加签到'
        elif status == 'absent':
            points = float(get_setting('absent_points', '-2'))
            reason = '管理员标记为缺勤'
            record_type = 'absence'
        elif status == 'public_leave':
            points = float(get_setting('public_leave_points', '0'))
            reason = '管理员标记为公假'
            record_type = 'manual_leave'
        elif status == 'personal_leave':
            points = float(get_setting('personal_leave_points', '-1'))
            reason = '管理员标记为事假'
            record_type = 'manual_leave'
        elif status == 'sick_leave':
            points = float(get_setting('sick_leave_points', '-0.5'))
            reason = '管理员标记为病假'
            record_type = 'manual_leave'

        if points != 0:
            cursor.execute('''
                INSERT INTO points_records (user_id, points, reason, record_type, session_id, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, points, reason, record_type, session_id, current_user.id))

        conn.commit()
        conn.close()

        status_names = {
            'present': '已签到',
            'absent': '缺勤',
            'public_leave': '公假',
            'personal_leave': '事假',
            'sick_leave': '病假'
        }
        flash(f'已为 {user["name"]} 添加签到记录：{status_names[status]}', 'success')
        return redirect(url_for('attendance_records', session_id=session_id))

    @app.route('/admin/attendance/<int:session_id>/delete', methods=['POST'])
    @login_required
    @admin_required
    def delete_attendance_session(session_id):
        """Delete entire attendance session with all related data"""
        conn = get_db()
        cursor = conn.cursor()

        try:
            # Get session info
            cursor.execute('SELECT * FROM attendance_sessions WHERE id = ?', (session_id,))
            session = cursor.fetchone()

            if not session:
                flash('签到活动不存在', 'error')
                return redirect(url_for('admin_attendance'))

            # Soft delete all related points records
            cursor.execute('''
                UPDATE points_records
                SET is_deleted = 1
                WHERE session_id = ? AND is_deleted = 0
            ''', (session_id,))

            # Delete all QR codes for this session
            cursor.execute('DELETE FROM qr_codes WHERE session_id = ?', (session_id,))

            # Delete all attendance records for this session
            cursor.execute('DELETE FROM attendance_records WHERE session_id = ?', (session_id,))

            # Update leave requests to remove session_id reference
            cursor.execute('''
                UPDATE leave_requests
                SET session_id = NULL
                WHERE session_id = ?
            ''', (session_id,))

            # Delete the session itself
            cursor.execute('DELETE FROM attendance_sessions WHERE id = ?', (session_id,))

            conn.commit()
            flash(f'签到活动（活动码：{session["activity_code"]}）已删除', 'success')

        except Exception as e:
            conn.rollback()
            flash(f'删除失败: {str(e)}', 'error')
        finally:
            conn.close()

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

        # 获取所有未签到的用户
        cursor.execute('''
            SELECT u.id, u.name, u.student_id
            FROM users u
            WHERE u.is_admin = 0
            AND u.id NOT IN (
                SELECT ar.user_id FROM attendance_records ar WHERE ar.session_id = ?
            )
        ''', (session_id,))
        not_checked_in_users = cursor.fetchall()

        # 获取所有已批准待使用的请假
        cursor.execute('''
            SELECT id, user_id, leave_type
            FROM leave_requests
            WHERE status = 'approved'
            ORDER BY approved_at
        ''')
        approved_leaves = cursor.fetchall()

        # 创建一个字典存储已批准请假的用户
        leave_dict = {leave['user_id']: leave for leave in approved_leaves}

        # 积分和请假类型映射
        points_map = {
            'public': float(get_setting('public_leave_points', '0')),
            'personal': float(get_setting('personal_leave_points', '-1')),
            'sick': float(get_setting('sick_leave_points', '-0.5'))
        }
        leave_type_names = {
            'public': '公假',
            'personal': '事假',
            'sick': '病假'
        }

        absent_count = 0
        used_leave_count = 0

        # 处理每个未签到的用户
        for user in not_checked_in_users:
            user_id = user['id']

            # 检查该用户是否有已批准的请假
            if user_id in leave_dict:
                leave = leave_dict[user_id]
                leave_type = leave['leave_type']

                # 标记请假为已使用
                cursor.execute('''
                    UPDATE leave_requests
                    SET status = 'used', session_id = ?, used_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (session_id, leave['id']))

                # 添加积分记录
                points = points_map.get(leave_type, 0)
                if points != 0:
                    cursor.execute('''
                        INSERT INTO points_records (user_id, points, reason, record_type, session_id, leave_request_id, created_by)
                        VALUES (?, ?, ?, 'leave', ?, ?, ?)
                    ''', (user_id, points, f'{leave_type_names[leave_type]}', session_id, leave['id'], current_user.id))

                used_leave_count += 1
            else:
                # 无请假，标记为缺勤
                cursor.execute('''
                    INSERT INTO attendance_records (session_id, user_id, status, checked_in_at)
                    VALUES (?, ?, 'absent', CURRENT_TIMESTAMP)
                ''', (session_id, user_id))

                # 扣除缺勤积分
                absent_points = float(get_setting('absent_points', '-2'))
                cursor.execute('''
                    INSERT INTO points_records (user_id, points, reason, record_type, session_id, created_by)
                    VALUES (?, ?, ?, 'absence', ?, ?)
                ''', (user_id, absent_points, '缺勤', session_id, current_user.id))

                absent_count += 1

        conn.commit()
        conn.close()

        flash(f'签到活动已结束，{absent_count}人缺勤，{used_leave_count}人使用请假', 'success')
        return redirect(url_for('admin_attendance'))

    @app.route('/qr')
    def qr_screen():
        """QR code display screen"""
        system_title = get_setting('system_title', '签到系统')
        return render_template('qr_screen.html', system_title=system_title)

    @app.route('/api/qr/start', methods=['POST'])
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
        end_time_str = session['end_time']
        # Handle both formats: with and without microseconds
        try:
            end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S')

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
    def qr_status_api(session_id):
        """Get attendance status for QR display"""
        conn = get_db()
        cursor = conn.cursor()

        # Get session status
        cursor.execute('''
            SELECT is_active
            FROM attendance_sessions
            WHERE id = ?
        ''', (session_id,))
        session = cursor.fetchone()

        if not session:
            conn.close()
            return jsonify({'success': False, 'message': '签到活动不存在'})

        is_active = session['is_active']

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
            'is_active': is_active,
            'checked_in': checked_in,
            'not_checked_in': not_checked_in,
            'checked_in_count': len(checked_in),
            'not_checked_in_count': len(not_checked_in)
        })
