"""
Timezone utilities for proper timezone handling
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# Get timezone from environment variable
TIMEZONE = os.getenv('TZ', 'Asia/Shanghai')

def get_timezone():
    """Get the configured timezone"""
    return ZoneInfo(TIMEZONE)

def now():
    """Get current time in configured timezone"""
    return datetime.now(get_timezone())

def to_local_time(dt):
    """Convert datetime to local timezone"""
    if dt is None:
        return None

    # If datetime is naive (no timezone), assume it's UTC from SQLite
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo('UTC'))

    # Convert to local timezone
    return dt.astimezone(get_timezone())

def format_datetime(dt, format_str='%Y-%m-%d %H:%M:%S'):
    """Format datetime to string in local timezone"""
    if dt is None:
        return ''

    if isinstance(dt, str):
        # Try to parse string datetime
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt

    # Convert to local time if needed
    local_dt = to_local_time(dt)
    return local_dt.strftime(format_str)
