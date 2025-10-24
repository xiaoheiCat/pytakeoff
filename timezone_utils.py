"""
Timezone utilities for proper timezone handling
"""
import os
from datetime import datetime

# Try to use zoneinfo (Python 3.9+), fallback to pytz
try:
    from zoneinfo import ZoneInfo
    USE_ZONEINFO = True
except ImportError:
    import pytz
    USE_ZONEINFO = False

# Get timezone from environment variable
TIMEZONE = os.getenv('TZ', 'Asia/Shanghai')

def get_timezone():
    """Get the configured timezone"""
    if USE_ZONEINFO:
        return ZoneInfo(TIMEZONE)
    else:
        return pytz.timezone(TIMEZONE)

def now():
    """Get current time in configured timezone"""
    if USE_ZONEINFO:
        return datetime.now(get_timezone())
    else:
        # For pytz, use utcnow + localize
        return datetime.now(pytz.UTC).astimezone(get_timezone())

def to_local_time(dt):
    """Convert datetime to local timezone"""
    if dt is None:
        return None

    if USE_ZONEINFO:
        # If datetime is naive (no timezone), assume it's UTC from SQLite
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo('UTC'))

        # Convert to local timezone
        return dt.astimezone(get_timezone())
    else:
        # For pytz
        if dt.tzinfo is None:
            # Assume UTC
            dt = pytz.UTC.localize(dt)

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
