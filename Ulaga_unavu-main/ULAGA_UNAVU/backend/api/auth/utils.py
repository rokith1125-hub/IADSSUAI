"""
Authentication utility functions
"""

import secrets
import string
import hashlib
import jwt
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)
JWT_SECRET = (
    os.environ.get("JWT_SECRET_KEY")
    or os.environ.get("JWT_SECRET")
    or "ulaga_unavu_local_secret_key_2026"
)

def generate_api_key(length=32):
    """Generate a secure API key"""
    alphabet = string.ascii_letters + string.digits
    api_key = ''.join(secrets.choice(alphabet) for _ in range(length))
    return api_key

def hash_password(password):
    """Hash password (though Firebase handles this)"""
    return hashlib.sha256(password.encode()).hexdigest()

def generate_reset_token(user_id, expires_in=3600):
    """Generate password reset token"""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'type': 'reset'
    }
    
    token = jwt.encode(
        payload,
        JWT_SECRET,
        algorithm='HS256'
    )
    
    return token

def verify_reset_token(token):
    """Verify password reset token"""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=['HS256']
        )
        
        if payload.get('type') != 'reset':
            return None
        
        return payload.get('user_id')
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def validate_session(token):
    """Validate user session token"""
    try:
        # This is a placeholder for session validation logic
        # In production, you might use Redis or database sessions
        return True
    except Exception as e:
        logger.error(f"Session validation error: {str(e)}")
        return False

def cleanup_expired_sessions():
    """Clean up expired sessions"""
    # This would clean up sessions from database or cache
    # Placeholder implementation
    pass

def get_user_roles(user_id):
    """Get roles for a user"""
    # This could fetch from database
    # For now, return default role
    return ['user']

def has_permission(user_role, required_permission):
    """Check if user has required permission"""
    # Simple role-based permission check
    permissions = {
        'admin': ['read', 'write', 'delete', 'admin'],
        'user': ['read', 'write'],
        'viewer': ['read']
    }
    
    user_perms = permissions.get(user_role, ['read'])
    return required_permission in user_perms
