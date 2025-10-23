import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'database.db')

def get_db():
    """Get database connection"""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with tables"""
    conn = get_db()
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT 0,
            must_change_password BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # System settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Attendance sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_code TEXT UNIQUE NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            session_type TEXT DEFAULT 'checkin',
            paired_session_id INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id),
            FOREIGN KEY (paired_session_id) REFERENCES attendance_sessions(id)
        )
    ''')

    # Attendance records table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            checked_in_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'present',
            FOREIGN KEY (session_id) REFERENCES attendance_sessions(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(session_id, user_id)
        )
    ''')

    # Leave requests table
    # Status: pending(待审批), rejected(未通过), approved(已批准待使用), used(已使用)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id INTEGER,
            paired_session_id INTEGER,
            leave_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            approved_by INTEGER,
            approved_at TIMESTAMP,
            used_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (session_id) REFERENCES attendance_sessions(id),
            FOREIGN KEY (paired_session_id) REFERENCES attendance_sessions(id),
            FOREIGN KEY (approved_by) REFERENCES users(id)
        )
    ''')

    # Leave attachments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leave_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            leave_request_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (leave_request_id) REFERENCES leave_requests(id) ON DELETE CASCADE
        )
    ''')

    # Points records table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS points_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            points REAL NOT NULL,
            reason TEXT NOT NULL,
            record_type TEXT NOT NULL,
            session_id INTEGER,
            leave_request_id INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_deleted BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (session_id) REFERENCES attendance_sessions(id),
            FOREIGN KEY (leave_request_id) REFERENCES leave_requests(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    ''')

    # QR codes table for security
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS qr_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            qr_token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            is_used BOOLEAN DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES attendance_sessions(id)
        )
    ''')

    # Initialize default admin user if not exists
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
    if cursor.fetchone()[0] == 0:
        admin_username = os.getenv('ADMIN_USERNAME', 'admin')
        admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
        cursor.execute('''
            INSERT INTO users (student_id, name, password_hash, is_admin, must_change_password)
            VALUES (?, ?, ?, 1, 1)
        ''', (admin_username, '系统管理员', generate_password_hash(admin_password)))

    # Initialize default system settings
    default_settings = {
        'system_title': os.getenv('SYSTEM_TITLE', '签到系统'),
        'qr_refresh_interval': os.getenv('QR_REFRESH_INTERVAL', '15'),
        'checkin_points': '1',
        'public_leave_points': '0',
        'personal_leave_points': '-1',
        'sick_leave_points': '-0.5',
        'absent_points': '-2'
    }

    for key, value in default_settings.items():
        cursor.execute('''
            INSERT OR IGNORE INTO system_settings (key, value)
            VALUES (?, ?)
        ''', (key, value))

    conn.commit()
    conn.close()

def get_setting(key, default=None):
    """Get system setting value"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM system_settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    """Set system setting value"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO system_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (key, value))
    conn.commit()
    conn.close()
