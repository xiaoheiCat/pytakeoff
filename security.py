"""
Security configuration and validation utilities
"""
import os
import secrets
import re
from flask import request
from werkzeug.security import check_password_hash


def validate_password_strength(password):
    """
    Validate password strength according to security best practices

    Args:
        password (str): Password to validate

    Returns:
        tuple: (is_valid, error_messages)
    """
    errors = []

    if len(password) < 8:
        errors.append("密码长度至少8位")

    if len(password) > 128:
        errors.append("密码长度不能超过128位")

    if not re.search(r'[A-Z]', password):
        errors.append("密码必须包含至少一个大写字母")

    if not re.search(r'[a-z]', password):
        errors.append("密码必须包含至少一个小写字母")

    if not re.search(r'\d', password):
        errors.append("密码必须包含至少一个数字")

    # Special characters (excluding common problematic ones)
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:"\\|,.<>\/?]', password):
        errors.append("密码必须包含至少一个特殊字符")

    # Check for common patterns
    common_patterns = [
        r'123456', r'password', r'qwerty', r'abc123', r'admin',
        r'letmein', r'welcome', r'monkey', r'dragon', r'football'
    ]

    password_lower = password.lower()
    for pattern in common_patterns:
        if re.search(pattern, password_lower):
            errors.append(f"密码不能包含常见模式: {pattern}")
            break

    # Check for sequential characters
    if re.search(r'(.)\1{2,}', password):  # 3+ repeated characters
        errors.append("密码不能包含连续重复字符")

    return len(errors) == 0, errors


def validate_student_id(student_id):
    """
    Validate student ID format

    Args:
        student_id (str): Student ID to validate

    Returns:
        tuple: (is_valid, error_message)
    """
    if not student_id or not student_id.strip():
        return False, "学工号不能为空"

    student_id = student_id.strip()

    # Allow alphanumeric characters, dash, underscore
    if not re.match(r'^[a-zA-Z0-9\-_]+$', student_id):
        return False, "学工号只能包含字母、数字、连字符和下划线"

    if len(student_id) < 3 or len(student_id) > 50:
        return False, "学工号长度必须在3-50字符之间"

    return True, None


def sanitize_input(text, max_length=1000):
    """
    Sanitize text input to prevent XSS and injection attacks

    Args:
        text (str): Input text to sanitize
        max_length (int): Maximum allowed length

    Returns:
        str: Sanitized text
    """
    if not text:
        return ""

    text = str(text).strip()

    # Limit length
    if len(text) > max_length:
        text = text[:max_length]

    # Remove potentially dangerous characters for HTML output
    dangerous_chars = ['<', '>', '&', '"', "'", '\x00', '\n', '\r', '\t']
    for char in dangerous_chars:
        text = text.replace(char, '')

    # Remove potential SQL injection patterns
    sql_patterns = [
        r'(union|select|insert|update|delete|drop|create|alter|exec|execute)\s',
        r'(--|#|/\*|\*/)',
        r'(\b(or|and)\s+\w+\s*=\s*\w+)',
        r'(1\s*=\s*1|1\s*=\s*1\s*--)',
    ]

    text_lower = text.lower()
    for pattern in sql_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            # Replace suspicious content with safe placeholder
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    return text.strip()


def is_secure_request():
    """
    Check if the request is secure (HTTPS in production)

    Returns:
        bool: True if request is secure
    """
    # Check for HTTPS
    if request.is_secure:
        return True

    # Check for common headers indicating HTTPS (behind reverse proxy)
    secure_headers = [
        'X-Forwarded-Proto',
        'X-Forwarded-Ssl',
        'X-Url-Scheme'
    ]

    for header in secure_headers:
        if request.headers.get(header, '').lower() in ['https', 'ssl', 'on']:
            return True

    # Allow insecure requests in development
    return os.getenv('FLASK_ENV', 'production') == 'development'


def generate_secure_secret():
    """
    Generate a cryptographically secure secret key

    Returns:
        str: Secure secret key
    """
    return secrets.token_hex(32)


def validate_file_upload(file, allowed_extensions=None, allowed_mimetypes=None, max_size_mb=16):
    """
    Validate uploaded file for security

    Args:
        file: File object from request
        allowed_extensions (set): Set of allowed file extensions
        allowed_mimetypes (set): Set of allowed MIME types
        max_size_mb (int): Maximum file size in MB

    Returns:
        tuple: (is_valid, error_message)
    """
    if not file or not file.filename:
        return False, "文件不能为空"

    # Default allowed extensions if not specified
    if allowed_extensions is None:
        allowed_extensions = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif'}

    # Default allowed MIME types if not specified
    if allowed_mimetypes is None:
        allowed_mimetypes = {
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'image/jpeg',
            'image/png',
            'image/gif'
        }

    filename = file.filename.lower()

    # Check file extension
    file_ext = os.path.splitext(filename)[1]
    if file_ext not in allowed_extensions:
        return False, f"不支持的文件类型: {file_ext}"

    # Check MIME type
    if file.mimetype not in allowed_mimetypes:
        return False, f"不支持的MIME类型: {file.mimetype}"

    # Check file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        return False, f"文件大小超过限制 ({max_size_mb}MB)"

    # Check for dangerous filenames
    dangerous_patterns = [
        r'\.\./',  # Directory traversal
        r'\.exe$', r'\.bat$', r'\.cmd$', r'\.scr$',  # Executables
        r'\.php$', r'\.jsp$', r'\.asp$',  # Server scripts
        r'^\.ht',  # Apache config files
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, filename, re.IGNORECASE):
            return False, "文件名包含不允许的字符"

    return True, None


def secure_headers():
    """
    Return a dictionary of security headers for HTTP responses

    Returns:
        dict: Security headers
    """
    return {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self';",
        'Referrer-Policy': 'strict-origin-when-cross-origin'
    }