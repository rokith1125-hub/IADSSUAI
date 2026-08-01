"""
Date and time utility functions
"""

from datetime import datetime, timedelta
import calendar

def get_current_timestamp():
    """Get current UTC timestamp"""
    return datetime.utcnow()

def format_timestamp(timestamp, format_str="%Y-%m-%d %H:%M:%S"):
    """Format timestamp to string"""
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except:
            return timestamp
    
    if isinstance(timestamp, datetime):
        return timestamp.strftime(format_str)
    
    return str(timestamp)

def format_date(date_obj=None, format_str="%d %b %Y"):
    """Format date to readable string"""
    if date_obj is None:
        date_obj = datetime.now()
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
        except:
            return date_obj
    if isinstance(date_obj, datetime):
        return date_obj.strftime(format_str)
    return str(date_obj)

def get_current_season():
    """Get current agricultural season"""
    month = datetime.now().month
    
    if month in [6, 7, 8, 9, 10]:
        return "Kharif"
    elif month in [11, 12, 1, 2, 3]:
        return "Rabi"
    else:
        return "Zaid"

def calculate_days_remaining(end_date):
    """Calculate days remaining until end date"""
    if isinstance(end_date, str):
        try:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except:
            return 0
    
    if not isinstance(end_date, datetime):
        return 0
    
    today = datetime.utcnow()
    if end_date < today:
        return 0
    
    return (end_date - today).days

def calculate_growth_stage(start_date, total_days, stages):
    """Calculate current growth stage"""
    if isinstance(start_date, str):
        try:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        except:
            return "Unknown"
    
    if not isinstance(start_date, datetime):
        return "Unknown"
    
    elapsed_days = (datetime.utcnow() - start_date).days
    
    if elapsed_days < 0:
        return "Not started"
    
    if elapsed_days >= total_days:
        return "Harvest"
    
    # Calculate stage based on elapsed days
    cumulative_days = 0
    for stage in stages:
        stage_days = stage.get('duration_days', 0)
        cumulative_days += stage_days
        
        if elapsed_days < cumulative_days:
            return stage.get('stage', 'Unknown')
    
    return "Unknown"

def get_next_monday():
    """Get next Monday date"""
    today = datetime.now()
    days_ahead = 0 - today.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    return today + timedelta(days=days_ahead)

def is_weekend(date_obj=None):
    """Check if date is weekend"""
    if not date_obj:
        date_obj = datetime.now()
    
    return date_obj.weekday() >= 5  # 5=Saturday, 6=Sunday

def add_days_to_date(start_date, days):
    """Add days to date"""
    if isinstance(start_date, str):
        try:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        except:
            return start_date
    
    if isinstance(start_date, datetime):
        return start_date + timedelta(days=days)
    
    return start_date

def get_month_name(month_number):
    """Get month name from number"""
    try:
        return calendar.month_name[month_number]
    except:
        return "Unknown"

def get_quarter_from_date(date_obj=None):
    """Get financial quarter from date"""
    if not date_obj:
        date_obj = datetime.now()
    
    month = date_obj.month
    if month in [4, 5, 6]:
        return "Q1"
    elif month in [7, 8, 9]:
        return "Q2"
    elif month in [10, 11, 12]:
        return "Q3"
    else:
        return "Q4"

def time_ago(timestamp):
    """Get human-readable time ago string"""
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except:
            return timestamp
    
    if not isinstance(timestamp, datetime):
        return "Unknown time"
    
    now = datetime.utcnow()
    diff = now - timestamp
    
    if diff.days > 365:
        years = diff.days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
    elif diff.days > 30:
        months = diff.days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"