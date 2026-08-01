"""
Input validation functions
"""

import re
from datetime import datetime

def validate_email(email):
    """Validate email address"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 6:
        return False
    return True

def validate_phone(phone):
    """Validate phone number"""
    pattern = r'^[0-9]{10}$'
    return re.match(pattern, phone) is not None

def validate_date(date_str, format_str="%Y-%m-%d"):
    """Validate date string"""
    try:
        datetime.strptime(date_str, format_str)
        return True
    except ValueError:
        return False

def validate_coordinates(lat, lng):
    """Validate latitude and longitude"""
    try:
        lat = float(lat)
        lng = float(lng)
        return -90 <= lat <= 90 and -180 <= lng <= 180
    except:
        return False

def validate_file_size(file, max_size_mb=10):
    """Validate file size"""
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Seek back to start
    return size <= max_size_mb * 1024 * 1024

def validate_crop_name(crop_name):
    """Validate crop name"""
    if not crop_name or len(crop_name.strip()) < 2:
        return False
    return True

def validate_soil_type(soil_type):
    """Validate soil type"""
    valid_types = ['Red Soil', 'Black Soil', 'Alluvial Soil', 'Sandy Soil', 
                  'Clay Soil', 'Loamy Soil', 'Laterite Soil', 'Peaty Soil',
                  'Saline Soil', 'Mountain Soil']
    return soil_type in valid_types

def validate_percentage(value):
    """Validate percentage value"""
    try:
        value = float(value)
        return 0 <= value <= 100
    except:
        return False

def validate_integer(value, min_val=None, max_val=None):
    """Validate integer value"""
    try:
        num = int(value)
        if min_val is not None and num < min_val:
            return False
        if max_val is not None and num > max_val:
            return False
        return True
    except:
        return False