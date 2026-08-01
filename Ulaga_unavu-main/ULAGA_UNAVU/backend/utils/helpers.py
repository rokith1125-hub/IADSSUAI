"""
General helper functions
"""

import os
import json
import hashlib
import random
import string
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def generate_id(prefix='', length=8):
    """Generate a unique ID"""
    chars = string.ascii_letters + string.digits
    random_part = ''.join(random.choice(chars) for _ in range(length))
    return f"{prefix}{random_part}"

def format_date(date_obj, format_str="%d %b %Y"):
    """Format date object to string"""
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
        except:
            return date_obj
    
    if isinstance(date_obj, datetime):
        return date_obj.strftime(format_str)
    
    return str(date_obj)

def calculate_days_between(start_date, end_date):
    """Calculate days between two dates"""
    if isinstance(start_date, str):
        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    if isinstance(end_date, str):
        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    
    return (end_date - start_date).days

def validate_image_file(filename):
    """Validate image file extension"""
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_uploaded_file(file, upload_folder='uploads'):
    """Save uploaded file"""
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
    
    filename = f"{generate_id('img_')}.{file.filename.rsplit('.', 1)[1].lower()}"
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)
    
    return filename, filepath

def calculate_percentage(value, total):
    """Calculate percentage"""
    if total == 0:
        return 0
    return round((value / total) * 100, 2)

def parse_json_safe(data, default=None):
    """Safely parse JSON"""
    try:
        if isinstance(data, str):
            return json.loads(data)
        return data
    except:
        return default

def get_file_hash(filepath):
    """Calculate file hash"""
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def clean_text(text, max_length=500):
    """Clean and truncate text"""
    if not text:
        return ""
    
    text = str(text).strip()
    if len(text) > max_length:
        text = text[:max_length] + "..."
    
    return text

def generate_progress_color(percentage):
    """Generate color based on percentage"""
    if percentage >= 70:
        return "#10B981"  # Green
    elif percentage >= 40:
        return "#F59E0B"  # Yellow
    else:
        return "#EF4444"  # Red

def get_season_from_date(date_obj=None):
    """Get season based on date"""
    if not date_obj:
        date_obj = datetime.now()
    
    month = date_obj.month
    
    if month in [12, 1, 2]:
        return "Winter"
    elif month in [3, 4, 5]:
        return "Summer"
    elif month in [6, 7, 8, 9]:
        return "Monsoon"
    else:
        return "Post-Monsoon"