import sqlite3
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db

class User(UserMixin):
    def __init__(self, id, student_id, name, password_hash, is_admin, must_change_password):
        self.id = id
        self.student_id = student_id
        self.name = name
        self.password_hash = password_hash
        self.is_admin = is_admin
        self.must_change_password = must_change_password

    @staticmethod
    def get(user_id):
        """Get user by ID"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return User(
                id=row['id'],
                student_id=row['student_id'],
                name=row['name'],
                password_hash=row['password_hash'],
                is_admin=bool(row['is_admin']),
                must_change_password=bool(row['must_change_password'])
            )
        return None

    @staticmethod
    def get_by_student_id(student_id):
        """Get user by student ID"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE student_id = ?', (student_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return User(
                id=row['id'],
                student_id=row['student_id'],
                name=row['name'],
                password_hash=row['password_hash'],
                is_admin=bool(row['is_admin']),
                must_change_password=bool(row['must_change_password'])
            )
        return None

    def check_password(self, password):
        """Check if password is correct"""
        return check_password_hash(self.password_hash, password)

    def set_password(self, password):
        """Set new password"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?',
            (generate_password_hash(password), self.id)
        )
        conn.commit()
        conn.close()
        self.must_change_password = False

    def reset_password(self):
        """Reset password to default (student_id)"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?',
            (generate_password_hash(self.student_id), self.id)
        )
        conn.commit()
        conn.close()

    def rename_user(self, new_name):
        """Update user's name"""
        if not new_name or not new_name.strip():
            return False

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE users SET name = ? WHERE id = ?',
            (new_name.strip(), self.id)
        )
        conn.commit()
        conn.close()

        # Update object's name
        self.name = new_name.strip()
        return True

    @staticmethod
    def create_user(student_id, name, password=None):
        """Create new user"""
        if password is None:
            password = student_id

        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO users (student_id, name, password_hash, is_admin, must_change_password) VALUES (?, ?, ?, 0, 1)',
                (student_id, name, generate_password_hash(password))
            )
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return user_id
        except sqlite3.IntegrityError:
            conn.close()
            return None

    @staticmethod
    def delete_user(user_id):
        """Delete user by ID"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE id = ? AND is_admin = 0', (user_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_all_users():
        """Get all non-admin users"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE is_admin = 0 ORDER BY student_id')
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_points(self):
        """Get user's total points"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COALESCE(SUM(points), 0) as total_points
            FROM points_records
            WHERE user_id = ? AND is_deleted = 0
        ''', (self.id,))
        row = cursor.fetchone()
        conn.close()
        return row['total_points'] if row else 0

    def get_points_history(self):
        """Get user's points history"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT pr.*, u.name as created_by_name
            FROM points_records pr
            LEFT JOIN users u ON pr.created_by = u.id
            WHERE pr.user_id = ? AND pr.is_deleted = 0
            ORDER BY pr.created_at DESC
        ''', (self.id,))
        rows = cursor.fetchall()
        conn.close()
        return rows
