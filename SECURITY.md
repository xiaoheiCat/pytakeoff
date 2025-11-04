# Security Guide

This document outlines the security measures implemented in the pytakeoff attendance system and provides guidance for secure deployment.

## Security Features Implemented

### 🔐 Authentication & Authorization
- **Strong Password Requirements**: Minimum 8 characters, must include uppercase, lowercase, numbers, and special characters
- **Password Hashing**: Uses Werkzeug's PBKDF2-SHA256 with salt
- **Session Management**: Secure session handling with 8-hour timeout
- **Role-Based Access Control**: Admin-only routes protected with decorators
- **Forced Password Change**: Users must change default passwords on first login

### 🛡️ CSRF Protection
- **Flask-WTF Integration**: All forms protected with CSRF tokens
- **Automatic Token Validation**: CSRF tokens validated on all state-changing requests
- **Secure Token Generation**: Cryptographically secure random tokens

### 📝 Input Validation & Sanitization
- **Student ID Validation**: Alphanumeric characters only, length restrictions
- **Text Input Sanitization**: XSS prevention and SQL injection pattern detection
- **File Upload Security**: Extension whitelisting, MIME type validation, content verification
- **Image Validation**: PIL-based image content verification

### 🔒 QR Code Security
- **One-Time Use Tokens**: QR tokens marked as used after successful check-in
- **Token Expiration**: Time-limited QR codes with configurable refresh intervals
- **Session Binding**: Tokens only valid for active attendance sessions

### 🌐 Web Security Headers
- **X-Content-Type-Options**: Prevents MIME-type sniffing
- **X-Frame-Options**: Clickjacking protection
- **X-XSS-Protection**: XSS attack prevention
- **Content-Security-Policy**: Controls resource loading
- **Strict-Transport-Security**: HTTPS enforcement in production

### 🔐 Secret Key Management
- **Automatic Generation**: Secure random keys generated if not provided
- **Environment Variable Support**: Production keys should be set via environment variables
- **Warning System**: Alerts when using auto-generated keys in production

## Secure Deployment Checklist

### ✅ Pre-Deployment
- [ ] Generate a secure `FLASK_SECRET_KEY` using `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] Change default admin credentials to strong, unique passwords
- [ ] Set `FLASK_ENV=production` in production environment
- [ ] Configure HTTPS with valid SSL certificates
- [ ] Set up reverse proxy (nginx/Apache) with security headers
- [ ] Configure firewall to restrict database access
- [ ] Set up regular database backups
- [ ] Enable application logging and monitoring

### 🚀 Production Configuration
```bash
# Environment variables
export FLASK_SECRET_KEY="your-32-byte-hex-key-here"
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="your-secure-password-here"
export FLASK_ENV="production"
export TZ="Asia/Shanghai"

# Database security
chmod 600 data/database.db
chown www-data:www-data data/database.db

# Uploads directory
chmod 755 uploads/
chown www-data:www-data uploads/
```

### 🔍 Security Monitoring
- [ ] Monitor failed login attempts
- [ ] Track unusual file upload patterns
- [ ] Monitor QR code generation patterns
- [ ] Review system logs regularly
- [ ] Set up alerts for security events

## Password Security Requirements

Passwords must meet the following criteria:
- **Minimum length**: 8 characters
- **Maximum length**: 128 characters
- **Required characters**: At least one uppercase letter, one lowercase letter, one number, one special character
- **Forbidden patterns**: Common passwords, sequential characters, repeated characters

## File Upload Security

### Allowed File Types
- **Documents**: PDF (.pdf), Word (.doc, .docx)
- **Images**: JPEG (.jpg, .jpeg), PNG (.png), GIF (.gif)

### Security Measures
- File extension validation
- MIME type verification
- Content validation for images
- Filename sanitization
- Size limitations (16MB max)
- Automatic timestamp prefixing

## Database Security

### Connection Security
- Parameterized queries prevent SQL injection
- Connection isolation with thread safety
- Automatic connection closing

### Data Protection
- Passwords hashed, never stored in plain text
- Soft deletes for audit trails
- Role-based data access

## Session Security

### Session Configuration
- 8-hour session timeout
- Secure cookie settings
- Session regeneration on login
- Automatic cleanup of expired sessions

## Security Recommendations

### Regular Maintenance
1. **Update Dependencies**: Keep Flask and all packages updated
2. **Security Patches**: Apply security patches promptly
3. **Password Audits**: Regularly review and update admin passwords
4. **Log Review**: Monitor access logs for suspicious activity
5. **Backup Security**: Secure backup storage and test restore procedures

### Network Security
1. **HTTPS Only**: Always use HTTPS in production
2. **Firewall Configuration**: Restrict database and admin access
3. **VPN Access**: Use VPN for remote admin access
4. **DDoS Protection**: Implement rate limiting and DDoS protection

### Incident Response
1. **Security Incident Plan**: Have a response plan ready
2. **Contact Information**: Maintain emergency contact list
3. **Backup Procedures**: Regular, tested backup procedures
4. ** forensic Analysis**: Log analysis capabilities

## Vulnerability Reporting

If you discover a security vulnerability, please report it responsibly:
- Do not disclose publicly
- Send details to the security team
- Include steps to reproduce
- Allow time for patching before disclosure

## Security Updates

This security guide is updated regularly. Check for updates and review security practices periodically.