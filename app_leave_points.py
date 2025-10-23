# Leave and points management routes (to be imported into app.py)

from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from datetime import datetime
import csv
import io

from database import get_db, get_setting, set_setting
from models import User

def register_leave_points_routes(app, admin_required, password_change_required):
    """Register leave and points management routes"""

    @app.route('/admin/leave')
    @login_required
    @admin_required
    @password_change_required
    def admin_leave():
        """Admin leave management"""
        system_title = get_setting('system_title', '签到系统')

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT lr.*, u.name as user_name, u.student_id,
                   ats.activity_code,
                   approver.name as approved_by_name
            FROM leave_requests lr
            JOIN users u ON lr.user_id = u.id
            LEFT JOIN attendance_sessions ats ON lr.session_id = ats.id
            LEFT JOIN users approver ON lr.approved_by = approver.id
            ORDER BY lr.created_at DESC
        ''')
        leave_requests = cursor.fetchall()
        conn.close()

        return render_template('admin/leave.html',
                             system_title=system_title,
                             leave_requests=leave_requests)

    @app.route('/admin/leave/<int:session_id>/approval')
    @login_required
    @admin_required
    @password_change_required
    def admin_leave_approval(session_id):
        """Approve leave requests for a session"""
        system_title = get_setting('system_title', '签到系统')

        conn = get_db()
        cursor = conn.cursor()

        # Get session info
        cursor.execute('SELECT * FROM attendance_sessions WHERE id = ?', (session_id,))
        session = cursor.fetchone()

        if not session:
            flash('签到活动不存在', 'error')
            return redirect(url_for('admin_attendance'))

        # Get pending leave requests
        cursor.execute('''
            SELECT lr.*, u.name as user_name, u.student_id
            FROM leave_requests lr
            JOIN users u ON lr.user_id = u.id
            WHERE lr.status = 'pending'
            ORDER BY lr.created_at
        ''')
        pending_requests = cursor.fetchall()

        conn.close()

        return render_template('admin/leave_approval.html',
                             system_title=system_title,
                             session=session,
                             pending_requests=pending_requests)

    @app.route('/admin/leave/<int:leave_id>/attachments')
    @login_required
    @admin_required
    def view_leave_attachments(leave_id):
        """View leave request attachments"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM leave_attachments
            WHERE leave_request_id = ?
        ''', (leave_id,))
        attachments = cursor.fetchall()
        conn.close()

        return jsonify({
            'success': True,
            'attachments': [dict(att) for att in attachments]
        })

    @app.route('/admin/leave/<int:leave_id>/approve', methods=['POST'])
    @login_required
    @admin_required
    def approve_leave(leave_id):
        """Approve leave request"""
        action = request.form.get('action')  # 'approve' or 'reject'
        session_id = request.form.get('session_id')

        if action not in ['approve', 'reject']:
            flash('无效的操作', 'error')
            return redirect(url_for('admin_leave'))

        conn = get_db()
        cursor = conn.cursor()

        # Get leave request
        cursor.execute('SELECT * FROM leave_requests WHERE id = ?', (leave_id,))
        leave_request = cursor.fetchone()

        if not leave_request:
            conn.close()
            flash('请假申请不存在', 'error')
            return redirect(url_for('admin_leave'))

        # Update leave request status
        new_status = 'approved' if action == 'approve' else 'rejected'
        cursor.execute('''
            UPDATE leave_requests
            SET status = ?, approved_by = ?, approved_at = CURRENT_TIMESTAMP, session_id = ?
            WHERE id = ?
        ''', (new_status, current_user.id, session_id, leave_id))

        # If approved, add points based on leave type
        if action == 'approve':
            leave_type = leave_request['leave_type']
            points_map = {
                'public': float(get_setting('public_leave_points', '0')),
                'personal': float(get_setting('personal_leave_points', '-1')),
                'sick': float(get_setting('sick_leave_points', '-0.5'))
            }
            points = points_map.get(leave_type, 0)

            leave_type_names = {
                'public': '公假',
                'personal': '事假',
                'sick': '病假'
            }

            cursor.execute('''
                INSERT INTO points_records (user_id, points, reason, record_type, session_id, leave_request_id, created_by)
                VALUES (?, ?, ?, 'leave', ?, ?, ?)
            ''', (leave_request['user_id'], points, f'{leave_type_names[leave_type]}审批通过',
                  session_id, leave_id, current_user.id))

        conn.commit()
        conn.close()

        flash(f'请假申请已{new_status}', 'success')

        # Redirect back to approval page if session_id provided
        if session_id:
            return redirect(url_for('admin_leave_approval', session_id=session_id))
        return redirect(url_for('admin_leave'))

    @app.route('/admin/attendance/<int:session_id>/manual-status', methods=['POST'])
    @login_required
    @admin_required
    def update_manual_status(session_id):
        """Manually update attendance status"""
        user_id = request.form.get('user_id')
        status = request.form.get('status')  # 'public', 'personal', 'sick'

        if not user_id or not status or status not in ['public', 'personal', 'sick']:
            flash('参数错误', 'error')
            return redirect(url_for('admin_attendance'))

        conn = get_db()
        cursor = conn.cursor()

        # Update or create attendance record
        cursor.execute('''
            INSERT INTO attendance_records (session_id, user_id, status)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id, user_id) DO UPDATE SET status = ?
        ''', (session_id, user_id, status, status))

        # Add points
        points_map = {
            'public': float(get_setting('public_leave_points', '0')),
            'personal': float(get_setting('personal_leave_points', '-1')),
            'sick': float(get_setting('sick_leave_points', '-0.5'))
        }
        points = points_map.get(status, 0)

        status_names = {
            'public': '公假（手动标记）',
            'personal': '事假（手动标记）',
            'sick': '病假（手动标记）'
        }

        cursor.execute('''
            INSERT INTO points_records (user_id, points, reason, record_type, session_id, created_by)
            VALUES (?, ?, ?, 'manual_leave', ?, ?)
        ''', (user_id, points, status_names[status], session_id, current_user.id))

        conn.commit()
        conn.close()

        flash('状态已更新', 'success')
        return redirect(url_for('admin_attendance'))

    @app.route('/admin/points')
    @login_required
    @admin_required
    @password_change_required
    def admin_points():
        """Admin points management"""
        system_title = get_setting('system_title', '签到系统')

        conn = get_db()
        cursor = conn.cursor()

        # Get all users with their points
        cursor.execute('''
            SELECT u.id, u.student_id, u.name,
                   COALESCE(SUM(CASE WHEN pr.is_deleted = 0 THEN pr.points ELSE 0 END), 0) as total_points
            FROM users u
            LEFT JOIN points_records pr ON u.id = pr.user_id
            WHERE u.is_admin = 0
            GROUP BY u.id
            ORDER BY u.student_id
        ''')
        users_points = cursor.fetchall()

        conn.close()

        return render_template('admin/points.html',
                             system_title=system_title,
                             users_points=users_points)

    @app.route('/admin/points/add', methods=['POST'])
    @login_required
    @admin_required
    def add_points():
        """Add or deduct points manually"""
        user_id = request.form.get('user_id')
        points = request.form.get('points', '').strip()
        reason = request.form.get('reason', '').strip()

        if not user_id or not points or not reason:
            flash('请填写完整信息', 'error')
            return redirect(url_for('admin_points'))

        try:
            points = float(points)
        except ValueError:
            flash('分数格式错误', 'error')
            return redirect(url_for('admin_points'))

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO points_records (user_id, points, reason, record_type, created_by)
            VALUES (?, ?, ?, 'manual', ?)
        ''', (user_id, points, reason, current_user.id))
        conn.commit()
        conn.close()

        flash('积分已更新', 'success')
        return redirect(url_for('admin_points'))

    @app.route('/admin/points/<int:record_id>/revoke', methods=['POST'])
    @login_required
    @admin_required
    def revoke_points(record_id):
        """Revoke points record"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE points_records SET is_deleted = 1 WHERE id = ?', (record_id,))
        conn.commit()
        conn.close()

        flash('积分记录已撤销', 'success')
        return redirect(url_for('admin_points'))

    @app.route('/admin/points/user/<int:user_id>')
    @login_required
    @admin_required
    def view_user_points(user_id):
        """View user points history"""
        user = User.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': '用户不存在'})

        points_history = user.get_points_history()

        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'name': user.name,
                'student_id': user.student_id
            },
            'points_history': [dict(record) for record in points_history],
            'total_points': user.get_points()
        })

    @app.route('/admin/export/leave-history')
    @login_required
    @admin_required
    def export_leave_history():
        """Export leave history and points"""
        conn = get_db()
        cursor = conn.cursor()

        # Get all users with their points breakdown
        cursor.execute('''
            SELECT
                u.student_id as '学工号',
                u.name as '姓名',
                COALESCE(SUM(CASE WHEN pr.record_type = 'leave' AND pr.leave_request_id IN
                    (SELECT id FROM leave_requests WHERE leave_type = 'public') AND pr.is_deleted = 0
                    THEN pr.points ELSE 0 END), 0) as '公假分值',
                COALESCE(SUM(CASE WHEN pr.record_type = 'leave' AND pr.leave_request_id IN
                    (SELECT id FROM leave_requests WHERE leave_type = 'personal') AND pr.is_deleted = 0
                    THEN pr.points ELSE 0 END), 0) as '事假分值',
                COALESCE(SUM(CASE WHEN pr.record_type = 'leave' AND pr.leave_request_id IN
                    (SELECT id FROM leave_requests WHERE leave_type = 'sick') AND pr.is_deleted = 0
                    THEN pr.points ELSE 0 END), 0) as '病假分值',
                COALESCE(SUM(CASE WHEN pr.record_type = 'absence' AND pr.is_deleted = 0
                    THEN pr.points ELSE 0 END), 0) as '缺勤分值',
                COALESCE(SUM(CASE WHEN pr.record_type = 'manual' AND pr.points > 0 AND pr.is_deleted = 0
                    THEN pr.points ELSE 0 END), 0) as '手动加分',
                COALESCE(SUM(CASE WHEN pr.record_type = 'manual' AND pr.points < 0 AND pr.is_deleted = 0
                    THEN pr.points ELSE 0 END), 0) as '手动扣分',
                COALESCE(SUM(CASE WHEN pr.is_deleted = 0 THEN pr.points ELSE 0 END), 0) as '总分'
            FROM users u
            LEFT JOIN points_records pr ON u.id = pr.user_id
            WHERE u.is_admin = 0
            GROUP BY u.id
            ORDER BY u.student_id
        ''')
        data = cursor.fetchall()
        conn.close()

        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['学工号', '姓名', '公假分值', '事假分值', '病假分值', '缺勤分值', '手动加分', '手动扣分', '总分'])

        # Write data
        for row in data:
            writer.writerow([
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]
            ])

        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'积分统计_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )

    @app.route('/admin/settings', methods=['GET', 'POST'])
    @login_required
    @admin_required
    @password_change_required
    def admin_settings():
        """Admin system settings"""
        system_title = get_setting('system_title', '签到系统')

        if request.method == 'POST':
            # Update settings
            set_setting('system_title', request.form.get('system_title', '签到系统'))
            set_setting('qr_refresh_interval', request.form.get('qr_refresh_interval', '15'))
            set_setting('public_leave_points', request.form.get('public_leave_points', '0'))
            set_setting('personal_leave_points', request.form.get('personal_leave_points', '-1'))
            set_setting('sick_leave_points', request.form.get('sick_leave_points', '-0.5'))
            set_setting('absent_points', request.form.get('absent_points', '-2'))

            flash('设置已保存', 'success')
            return redirect(url_for('admin_settings'))

        settings = {
            'system_title': get_setting('system_title', '签到系统'),
            'qr_refresh_interval': get_setting('qr_refresh_interval', '15'),
            'public_leave_points': get_setting('public_leave_points', '0'),
            'personal_leave_points': get_setting('personal_leave_points', '-1'),
            'sick_leave_points': get_setting('sick_leave_points', '-0.5'),
            'absent_points': get_setting('absent_points', '-2')
        }

        return render_template('admin/settings.html',
                             system_title=system_title,
                             settings=settings)
