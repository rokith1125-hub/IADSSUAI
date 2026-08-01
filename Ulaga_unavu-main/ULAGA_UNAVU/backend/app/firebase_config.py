"""
Firebase configuration and initialization for ULAGA_UNAVU
Project: ulagaunavu
"""

try:
    import firebase_admin
    from firebase_admin import credentials, auth
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    firebase_admin = None
    credentials = None
    auth = None

# Flask request decorators are deprecated after FastAPI cutover.
request = None


def jsonify(payload):
    return payload
import json
import os
from functools import wraps
import logging

logger = logging.getLogger(__name__)

firebase_app = None

# Your Firebase Service Account JSON file (in backend folder)
SERVICE_ACCOUNT_FILE = "ulagaunavu-firebase-adminsdk-fbsvc-7195d378c3.json"


def is_firebase_ready():
    """Check if Firebase is properly initialized and ready to use."""
    return FIREBASE_AVAILABLE and firebase_app is not None


def init_firebase(app):
    """Initialize Firebase Admin SDK"""
    global firebase_app
    
    if not FIREBASE_AVAILABLE:
        logger.warning("⚠️ firebase-admin package not installed. Auth features disabled.")
        return
    
    # Skip if already initialized
    if firebase_admin._apps:
        firebase_app = firebase_admin.get_app()
        logger.info("✅ Firebase already initialized")
        return
    
    try:
        cred = None
        
        # Calculate path relative to this file's location
        this_file_dir = os.path.dirname(os.path.abspath(__file__))  # app/
        backend_dir = os.path.dirname(this_file_dir)  # backend/
        json_path = os.path.join(backend_dir, SERVICE_ACCOUNT_FILE)
        
        logger.info(f"Looking for Firebase credentials at: {json_path}")
        
        if os.path.exists(json_path):
            cred = credentials.Certificate(json_path)
            logger.info(f"Loading Firebase credentials from: {SERVICE_ACCOUNT_FILE}")
        
        # Option 2: Fallback to environment variables
        elif app.config.get('FIREBASE_PROJECT_ID'):
            firebase_config = {
                "type": "service_account",
                "project_id": app.config['FIREBASE_PROJECT_ID'],
                "private_key_id": app.config.get('FIREBASE_PRIVATE_KEY_ID', ''),
                "private_key": app.config.get('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n'),
                "client_email": app.config.get('FIREBASE_CLIENT_EMAIL', ''),
                "client_id": app.config.get('FIREBASE_CLIENT_ID', ''),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": app.config.get('FIREBASE_CLIENT_X509_CERT_URL', '')
            }
            cred = credentials.Certificate(firebase_config)
            logger.info("Loading Firebase credentials from environment variables")
        
        # Initialize Firebase
        if cred:
            firebase_app = firebase_admin.initialize_app(cred)
            logger.info("✅ Firebase Admin SDK initialized successfully (Project: ulagaunavu)")
        else:
            logger.warning("⚠️ Firebase configuration not found. Auth features disabled.")
            
    except Exception as e:
        logger.error(f"❌ Firebase initialization failed: {str(e)}")
        firebase_app = None

def verify_firebase_token(token):
    """Verify Firebase ID token"""
    if not FIREBASE_AVAILABLE or not firebase_app:
        raise Exception("Firebase not initialized")
    
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except auth.ExpiredIdTokenError:
        raise Exception("Token expired")
    except auth.InvalidIdTokenError:
        raise Exception("Invalid token")
    except Exception as e:
        raise Exception(f"Token verification failed: {str(e)}")


# Local JWT verification (for local auth)
import jwt
LOCAL_JWT_SECRET = (
    os.environ.get('JWT_SECRET_KEY')
    or os.environ.get('JWT_SECRET')
    or 'ulaga_unavu_local_secret_key_2026'
)

def verify_local_token(token):
    """Verify local JWT token"""
    try:
        payload = jwt.decode(token, LOCAL_JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def firebase_auth_required(f):
    """Decorator to require authentication - Supports both Firebase and Local tokens"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request is None:
            raise RuntimeError("firebase_auth_required is deprecated in FastAPI runtime")
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({"error": "No authorization header", "success": False}), 401
        
        try:
            # Expecting "Bearer {token}"
            if auth_header.startswith('Bearer '):
                token = auth_header.split('Bearer ')[1]
            else:
                token = auth_header
            
            # Try 1: Verify as local JWT token first (faster)
            local_payload = verify_local_token(token)
            if local_payload:
                # Local token is valid
                request.user_id = local_payload.get('user_id')
                request.user_email = local_payload.get('email', '')
                request.user_name = local_payload.get('name', '')
                request.auth_type = 'local'
                logger.info(f"Auth: Local token verified for {request.user_id}")
                return f(*args, **kwargs)
            
            # Try 2: Verify as Firebase token
            if is_firebase_ready():
                decoded_token = verify_firebase_token(token)
                request.user_id = decoded_token['uid']
                request.user_email = decoded_token.get('email', '')
                request.user_name = decoded_token.get('name', '')
                request.auth_type = 'firebase'
                logger.info(f"Auth: Firebase token verified for {request.user_id}")
                return f(*args, **kwargs)
            else:
                return jsonify({
                    "error": "Invalid token provided",
                    "message": "Invalid Firebase token.",
                    "success": False
                }), 401
            
        except IndexError:
            return jsonify({"error": "Invalid authorization header format", "success": False}), 401
        except Exception as e:
            logger.error(f"Auth error: {str(e)}")
            return jsonify({
                "error": "Invalid token provided",
                "message": str(e),
                "success": False
            }), 401
    
    return decorated_function

def get_firebase_user(uid):
    """Get user from Firebase by UID"""
    if not firebase_app:
        return None
    
    try:
        user = auth.get_user(uid)
        return {
            'uid': user.uid,
            'email': user.email,
            'display_name': user.display_name,
            'photo_url': user.photo_url,
            'email_verified': user.email_verified,
            'disabled': user.disabled,
            'created_at': user.user_metadata.creation_timestamp if hasattr(user.user_metadata, 'creation_timestamp') else None
        }
    except Exception as e:
        logger.error(f"Error getting Firebase user {uid}: {str(e)}")
        return None

def create_firebase_user(email, password, display_name=""):
    """Create new user in Firebase"""
    if not firebase_app:
        raise Exception("Firebase not initialized")
    
    try:
        user = auth.create_user(
            email=email,
            password=password,
            display_name=display_name
        )
        return user.uid
    except Exception as e:
        logger.error(f"Error creating Firebase user: {str(e)}")
        raise

def delete_firebase_user(uid):
    """Delete user from Firebase"""
    if not firebase_app:
        raise Exception("Firebase not initialized")
    
    try:
        auth.delete_user(uid)
        return True
    except Exception as e:
        logger.error(f"Error deleting Firebase user: {str(e)}")
        raise
