"""
Firebase service for ULAGA_UNAVU
"""

import firebase_admin
from firebase_admin import auth, credentials
from firebase_admin.exceptions import FirebaseError
import logging
from typing import Dict, Optional, List
import os

logger = logging.getLogger(__name__)

class FirebaseService:
    """Service for Firebase authentication operations"""
    
    def __init__(self):
        self.app = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            # Check if already initialized
            if not firebase_admin._apps:
                # Get Firebase credentials from environment
                firebase_config = {
                    "type": "service_account",
                    "project_id": os.getenv('FIREBASE_PROJECT_ID'),
                    "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
                    "private_key": os.getenv('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n'),
                    "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
                    "client_id": os.getenv('FIREBASE_CLIENT_ID'),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_X509_CERT_URL')
                }
                
                # Validate required fields
                required_fields = ['project_id', 'private_key', 'client_email']
                for field in required_fields:
                    if not firebase_config.get(field):
                        raise ValueError(f"Missing Firebase configuration: {field}")
                
                # Initialize Firebase
                cred = credentials.Certificate(firebase_config)
                self.app = firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK initialized successfully")
            else:
                self.app = firebase_admin.get_app()
                logger.info("Firebase Admin SDK already initialized")
                
        except Exception as e:
            logger.error(f"Firebase initialization failed: {str(e)}")
            self.app = None
    
    def verify_id_token(self, id_token: str) -> Dict:
        """Verify Firebase ID token"""
        if not self.app:
            raise FirebaseError("Firebase not initialized", "firebase_not_initialized")
        
        try:
            decoded_token = auth.verify_id_token(id_token)
            return decoded_token
        except auth.ExpiredIdTokenError:
            raise FirebaseError("Token has expired", "token_expired")
        except auth.InvalidIdTokenError:
            raise FirebaseError("Invalid token", "invalid_token")
        except auth.RevokedIdTokenError:
            raise FirebaseError("Token has been revoked", "token_revoked")
        except Exception as e:
            raise FirebaseError(f"Token verification failed: {str(e)}", "verification_failed")
    
    def get_user(self, uid: str) -> Optional[Dict]:
        """Get user by UID"""
        if not self.app:
            return None
        
        try:
            user = auth.get_user(uid)
            return self._format_user_data(user)
        except auth.UserNotFoundError:
            logger.warning(f"User not found: {uid}")
            return None
        except Exception as e:
            logger.error(f"Error getting user {uid}: {str(e)}")
            return None
    
    def create_user(self, email: str, password: str, display_name: str = "", phone: str = "") -> Optional[str]:
        """Create new user"""
        if not self.app:
            return None
        
        try:
            user_args = {
                'email': email,
                'password': password,
                'email_verified': False,
                'disabled': False
            }
            
            if display_name:
                user_args['display_name'] = display_name
            
            if phone:
                user_args['phone_number'] = phone
            
            user = auth.create_user(**user_args)
            logger.info(f"Firebase user created: {user.uid}")
            return user.uid
        except auth.EmailAlreadyExistsError:
            raise FirebaseError("Email already exists", "email_exists")
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            raise FirebaseError(f"User creation failed: {str(e)}", "creation_failed")
    
    def update_user(self, uid: str, **kwargs) -> bool:
        """Update user profile"""
        if not self.app:
            return False
        
        try:
            auth.update_user(uid, **kwargs)
            logger.info(f"Firebase user updated: {uid}")
            return True
        except auth.UserNotFoundError:
            logger.warning(f"User not found for update: {uid}")
            return False
        except Exception as e:
            logger.error(f"Error updating user {uid}: {str(e)}")
            return False
    
    def delete_user(self, uid: str) -> bool:
        """Delete user"""
        if not self.app:
            return False
        
        try:
            auth.delete_user(uid)
            logger.info(f"Firebase user deleted: {uid}")
            return True
        except auth.UserNotFoundError:
            logger.warning(f"User not found for deletion: {uid}")
            return False
        except Exception as e:
            logger.error(f"Error deleting user {uid}: {str(e)}")
            return False
    
    def set_custom_claims(self, uid: str, claims: Dict) -> bool:
        """Set custom claims for user"""
        if not self.app:
            return False
        
        try:
            auth.set_custom_user_claims(uid, claims)
            logger.info(f"Custom claims set for user {uid}: {claims}")
            return True
        except Exception as e:
            logger.error(f"Error setting claims for user {uid}: {str(e)}")
            return False
    
    def list_users(self, max_results: int = 100) -> List[Dict]:
        """List users (for admin)"""
        if not self.app:
            return []
        
        try:
            users = []
            page = auth.list_users(max_results=max_results)
            
            for user in page.users:
                users.append(self._format_user_data(user))
            
            while page.next_page_token:
                page = auth.list_users(max_results=max_results, page_token=page.next_page_token)
                for user in page.users:
                    users.append(self._format_user_data(user))
            
            return users
        except Exception as e:
            logger.error(f"Error listing users: {str(e)}")
            return []
    
    def send_email_verification(self, uid: str) -> bool:
        """Send email verification (handled by Firebase client SDK)"""
        # Note: Firebase Admin SDK doesn't directly send verification emails
        # This is handled by Firebase Client SDK on frontend
        logger.info(f"Email verification requested for user {uid}")
        return True
    
    def send_password_reset_email(self, email: str) -> bool:
        """Send password reset email"""
        if not self.app:
            return False
        
        try:
            link = auth.generate_password_reset_link(email)
            # In production, you would send this link via email service
            logger.info(f"Password reset link generated for {email}: {link[:50]}...")
            return True
        except auth.UserNotFoundError:
            logger.warning(f"User not found for password reset: {email}")
            return False
        except Exception as e:
            logger.error(f"Error sending password reset: {str(e)}")
            return False
    
    def revoke_refresh_tokens(self, uid: str) -> bool:
        """Revoke all refresh tokens for user"""
        if not self.app:
            return False
        
        try:
            auth.revoke_refresh_tokens(uid)
            logger.info(f"Refresh tokens revoked for user {uid}")
            return True
        except Exception as e:
            logger.error(f"Error revoking tokens for user {uid}: {str(e)}")
            return False
    
    def _format_user_data(self, user) -> Dict:
        """Format Firebase user data"""
        return {
            'uid': user.uid,
            'email': user.email,
            'email_verified': user.email_verified,
            'display_name': user.display_name,
            'phone_number': user.phone_number,
            'photo_url': user.photo_url,
            'disabled': user.disabled,
            'provider_data': [
                {
                    'provider_id': provider.provider_id,
                    'uid': provider.uid,
                    'display_name': provider.display_name,
                    'email': provider.email,
                    'phone_number': provider.phone_number,
                    'photo_url': provider.photo_url
                }
                for provider in user.provider_data
            ],
            'created_at': user.user_metadata.creation_timestamp,
            'last_login_at': user.user_metadata.last_sign_in_timestamp,
            'last_refresh_at': user.user_metadata.last_refresh_timestamp if hasattr(user.user_metadata, 'last_refresh_timestamp') else None
        }
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user by email"""
        if not self.app:
            return None
        
        try:
            user = auth.get_user_by_email(email)
            return self._format_user_data(user)
        except auth.UserNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error getting user by email {email}: {str(e)}")
            return None
    
    def get_user_by_phone(self, phone: str) -> Optional[Dict]:
        """Get user by phone number"""
        if not self.app:
            return None
        
        try:
            user = auth.get_user_by_phone_number(phone)
            return self._format_user_data(user)
        except auth.UserNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error getting user by phone {phone}: {str(e)}")
            return None
    
    def create_custom_token(self, uid: str, additional_claims: Dict = None) -> Optional[str]:
        """Create custom token for user"""
        if not self.app:
            return None
        
        try:
            token = auth.create_custom_token(uid, additional_claims)
            return token.decode('utf-8') if isinstance(token, bytes) else token
        except Exception as e:
            logger.error(f"Error creating custom token for {uid}: {str(e)}")
            return None
    
    def batch_delete_users(self, uids: List[str]) -> Dict:
        """Batch delete users"""
        if not self.app:
            return {"success_count": 0, "failure_count": len(uids), "errors": []}
        
        try:
            result = auth.delete_users(uids)
            logger.info(f"Batch deleted {result.success_count} users, {result.failure_count} failed")
            
            errors = []
            for error in result.errors:
                errors.append({
                    'index': error.index,
                    'uid': uids[error.index],
                    'reason': error.reason
                })
            
            return {
                'success_count': result.success_count,
                'failure_count': result.failure_count,
                'errors': errors
            }
        except Exception as e:
            logger.error(f"Error batch deleting users: {str(e)}")
            return {"success_count": 0, "failure_count": len(uids), "errors": [{"reason": str(e)}]}
    
    def is_initialized(self) -> bool:
        """Check if Firebase is initialized"""
        return self.app is not None