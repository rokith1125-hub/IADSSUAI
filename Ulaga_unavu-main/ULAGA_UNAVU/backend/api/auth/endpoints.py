"""
Authentication Endpoints - FastAPI router.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

import jwt
import requests
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from api.common.auth import get_current_user, verify_local_jwt
from api.common.responses import error_response
from app.firebase_config import verify_firebase_token
from services.local_storage import db_service
from utils.localization import get_message
from utils.validators import validate_email, validate_password

logger = logging.getLogger(__name__)

router = APIRouter()

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "")
LOCAL_JWT_SECRET = (
    os.getenv("JWT_SECRET_KEY")
    or os.getenv("JWT_SECRET")
    or "ulaga_unavu_local_secret_key_2026"
)
LOCAL_AUTH_ENABLED = os.getenv("LOCAL_AUTH", "true").lower() == "true"


class AuthError(Exception):
    def __init__(self, message, code=401):
        self.message = message
        self.code = code
        super().__init__(message)


class RegisterRequest(BaseModel):
    email: str
    password: Optional[str] = ""
    uid: Optional[str] = None
    name: Optional[str] = ""
    displayName: Optional[str] = ""
    phone: Optional[str] = ""
    location: Optional[str] = ""
    farm_size: Optional[str] = ""
    primary_crops: Optional[List[str]] = None


class LoginRequest(BaseModel):
    email: Optional[str] = ""
    password: Optional[str] = ""
    token: Optional[str] = None
    firebase_token: Optional[str] = None
    id_token: Optional[str] = None
    displayName: Optional[str] = ""


class ForgotPasswordRequest(BaseModel):
    email: str


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    displayName: Optional[str] = None
    phone: Optional[str] = None
    farm_info: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None


class LocalRegisterRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = ""
    phone: Optional[str] = ""


class LocalLoginRequest(BaseModel):
    email: str
    password: str


class LocalResetPasswordRequest(BaseModel):
    email: str
    new_password: str
    confirm_password: str


class VerifyTokenRequest(BaseModel):
    token: str


@router.post("/register")
def register(payload: RegisterRequest = Body(...)):
    """Register new user."""
    try:
        data = payload.model_dump()
        email = data.get("email", "").strip()
        password = data.get("password", "") or ""
        uid = data.get("uid")
        name = (data.get("name") or data.get("displayName") or "").strip()
        phone = data.get("phone", "") or ""
        location = data.get("location", "") or ""
        farm_size = data.get("farm_size", "") or ""
        primary_crops = data.get("primary_crops", []) or []

        if not email:
            raise AuthError("Email is required", 400)
        if not validate_email(email):
            raise AuthError("Invalid email format", 400)

        firebase_uid = None
        id_token = None

        if uid:
            firebase_uid = uid
            logger.info("Syncing existing Firebase user: %s", uid)
        elif password:
            if not validate_password(password):
                raise AuthError("Password must be at least 6 characters", 400)
            if not FIREBASE_API_KEY:
                raise AuthError("Firebase registration is not configured", 503)

            firebase_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
            response = requests.post(
                firebase_url,
                json={"email": email, "password": password, "returnSecureToken": True},
                timeout=20,
            )

            if response.status_code != 200:
                error_data = response.json()
                error_message = error_data.get("error", {}).get("message", "Registration failed")
                error_translations = {
                    "EMAIL_EXISTS": "User with this email already exists. Please login.",
                    "INVALID_EMAIL": "Invalid email format.",
                    "WEAK_PASSWORD": "Password is too weak. Use at least 6 characters.",
                    "OPERATION_NOT_ALLOWED": "Email/password registration is disabled.",
                }
                raise AuthError(error_translations.get(error_message, error_message), 400)

            firebase_response = response.json()
            id_token = firebase_response.get("idToken")
            firebase_uid = firebase_response.get("localId")
            logger.info("Created new Firebase user: %s", firebase_uid)
        else:
            raise AuthError("Either Firebase UID or password is required", 400)

        existing_user = db_service.find_one("users", {"firebase_uid": firebase_uid})
        if existing_user:
            return {
                "success": True,
                "message": "User already registered",
                "user": {
                    "user_id": existing_user["user_id"],
                    "name": existing_user["name"],
                    "email": existing_user["email"],
                    "created_at": existing_user.get("created_at", ""),
                },
                "token": id_token,
            }

        user_profile = _create_user_profile(firebase_uid, email, name or email.split("@")[0], phone)
        if location:
            user_profile["farm_info"]["location"] = location
        if farm_size:
            user_profile["farm_info"]["farm_size"] = farm_size
        if primary_crops:
            user_profile["farm_info"]["primary_crops"] = primary_crops

        db_service.insert_one("users", user_profile)
        logger.info("Registered user: %s", user_profile["user_id"])
        return {
            "success": True,
            "message": "User registered successfully",
            "user": {
                "user_id": user_profile["user_id"],
                "email": email,
                "name": user_profile["name"],
                "created_at": user_profile["created_at"],
            },
            "token": id_token,
        }
    except AuthError as e:
        logger.error("Registration error: %s", e.message)
        return error_response(e.message, e.code)
    except Exception as e:
        logger.error("Registration error: %s", str(e))
        error_msg = str(e).lower()
        if "already in use" in error_msg or "already exists" in error_msg:
            return error_response("User with this email already exists. Please login.", 400)
        return error_response(str(e), 400)


@router.post("/dev-register")
def dev_register(payload: RegisterRequest = Body(...)):
    """Development/Postman register with Firebase REST API."""
    try:
        email = payload.email.strip()
        password = payload.password or ""
        name = (payload.name or payload.displayName or "").strip()

        if not email:
            return error_response("Email is required", 400)
        if not password:
            return error_response("Password is required", 400)
        if len(password) < 6:
            return error_response("Password must be at least 6 characters", 400)
        if not FIREBASE_API_KEY:
            return error_response("Firebase registration is not configured", 503)

        firebase_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
        response = requests.post(
            firebase_url,
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=20,
        )

        if response.status_code != 200:
            error_data = response.json()
            error_message = error_data.get("error", {}).get("message", "Registration failed")
            error_translations = {
                "EMAIL_EXISTS": "User with this email already exists. Use /api/auth/dev-login instead.",
                "INVALID_EMAIL": "Invalid email format.",
                "WEAK_PASSWORD": "Password is too weak. Use at least 6 characters.",
                "OPERATION_NOT_ALLOWED": "Email/password registration is disabled.",
            }
            return error_response(error_translations.get(error_message, error_message), 400)

        firebase_response = response.json()
        id_token = firebase_response.get("idToken")
        firebase_uid = firebase_response.get("localId")
        user_name = name or email.split("@")[0]
        user_profile = _create_user_profile(firebase_uid, email, user_name, "")
        db_service.insert_one("users", user_profile)
        logger.info("Dev-registered user: %s", user_profile["user_id"])

        return {
            "success": True,
            "message": "User registered successfully",
            "token": id_token,
            "expires_in": 3600,
            "user": {
                "user_id": user_profile["user_id"],
                "email": email,
                "name": user_name,
                "firebase_uid": firebase_uid,
            },
            "usage": {
                "header": "Authorization: Bearer <token>",
                "description": "Use the 'token' value in Authorization header for all protected endpoints",
            },
        }
    except Exception as e:
        logger.error("Dev registration error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/login")
def login(payload: LoginRequest = Body(...)):
    """Login user with email/password or Firebase token."""
    try:
        data = payload.model_dump()
        email = (data.get("email") or "").strip()
        password = data.get("password", "") or ""
        firebase_token = data.get("token") or data.get("firebase_token") or data.get("id_token")

        firebase_uid = None
        id_token = None

        if email and password:
            logger.info("Login attempt with email: %s", email)
            if not FIREBASE_API_KEY:
                raise AuthError("Firebase login is not configured", 503)
            firebase_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
            response = requests.post(
                firebase_url,
                json={"email": email, "password": password, "returnSecureToken": True},
                timeout=20,
            )
            if response.status_code != 200:
                error_data = response.json()
                error_message = error_data.get("error", {}).get("message", "Authentication failed")
                error_translations = {
                    "EMAIL_NOT_FOUND": "User not found. Please register first.",
                    "INVALID_PASSWORD": "Invalid password.",
                    "INVALID_LOGIN_CREDENTIALS": "Invalid email or password.",
                    "USER_DISABLED": "This account has been disabled.",
                    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many failed attempts. Try again later.",
                }
                raise AuthError(error_translations.get(error_message, error_message), 401)
            firebase_response = response.json()
            id_token = firebase_response.get("idToken")
            firebase_uid = firebase_response.get("localId")
        elif firebase_token:
            logger.info("Login attempt with Firebase token")
            decoded_token = verify_firebase_token(firebase_token)
            if not decoded_token or "uid" not in decoded_token:
                raise AuthError("Invalid Firebase token", 401)
            firebase_uid = decoded_token["uid"]
            email = decoded_token.get("email", "")
            id_token = firebase_token
        else:
            raise AuthError("Email/password or Firebase token required", 400)

        user = db_service.find_one("users", {"firebase_uid": firebase_uid})
        if not user:
            user = _create_user_profile(
                firebase_uid,
                email,
                data.get("displayName", email.split("@")[0] if email else "User"),
            )
            db_service.insert_one("users", user)
            logger.info("Auto-created user profile: %s", user["user_id"])

        db_service.update_one(
            "users",
            {"firebase_uid": firebase_uid},
            {"$set": {"last_login": datetime.utcnow().isoformat()}},
        )

        user_response = {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "role": user.get("role", "user"),
            "settings": user.get("settings", {}),
            "farm_info": user.get("farm_info", {}),
        }
        lang = user.get("settings", {}).get("language", "en")
        return {
            "success": True,
            "message": get_message("login_success", lang),
            "user": user_response,
            "token": id_token,
            "expires_in": 86400,
        }
    except AuthError as e:
        logger.error("Login error: %s", e.message)
        return error_response(e.message, e.code)
    except Exception as e:
        logger.error("Login error: %s", str(e))
        return error_response("Authentication failed. Please try again.", 401)


@router.post("/dev-login")
def dev_login(payload: LocalLoginRequest = Body(...)):
    """Development/Postman login with Firebase REST API."""
    try:
        email = payload.email.strip()
        password = payload.password
        if not email:
            return error_response("Email is required", 400)
        if not password:
            return error_response("Password is required", 400)
        if not FIREBASE_API_KEY:
            return error_response("Firebase login is not configured", 503)

        firebase_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
        response = requests.post(
            firebase_url,
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=20,
        )
        if response.status_code != 200:
            error_data = response.json()
            error_message = error_data.get("error", {}).get("message", "Authentication failed")
            error_translations = {
                "EMAIL_NOT_FOUND": "User not found. Please register first.",
                "INVALID_PASSWORD": "Invalid password.",
                "INVALID_LOGIN_CREDENTIALS": "Invalid email or password.",
                "USER_DISABLED": "This account has been disabled.",
                "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many failed attempts. Try again later.",
            }
            return error_response(error_translations.get(error_message, error_message), 401)

        firebase_response = response.json()
        id_token = firebase_response.get("idToken")
        refresh_token = firebase_response.get("refreshToken")
        expires_in = firebase_response.get("expiresIn", "3600")
        firebase_uid = firebase_response.get("localId")

        user = db_service.find_one("users", {"firebase_uid": firebase_uid})
        if not user:
            user = _create_user_profile(firebase_uid, email, firebase_response.get("displayName", email.split("@")[0]))
            db_service.insert_one("users", user)
            logger.info("Auto-created user profile: %s", user["user_id"])

        db_service.update_one(
            "users",
            {"firebase_uid": firebase_uid},
            {"$set": {"last_login": datetime.utcnow().isoformat()}},
        )
        return {
            "success": True,
            "message": "Login successful",
            "token": id_token,
            "refresh_token": refresh_token,
            "expires_in": int(expires_in),
            "user": {
                "user_id": user["user_id"],
                "email": email,
                "name": user.get("name", ""),
                "firebase_uid": firebase_uid,
            },
            "usage": {
                "header": "Authorization: Bearer <token>",
                "description": "Use the 'token' value in Authorization header for all protected endpoints",
            },
        }
    except Exception as e:
        logger.error("Dev login error: %s", str(e))
        return error_response(str(e), 500)


@router.api_route("/verify", methods=["GET", "POST"])
def verify_token(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Verify token and get user info."""
    try:
        user_id = current_user["user_id"]
        user = db_service.find_one("users", {"user_id": user_id}) or db_service.find_one(
            "users", {"firebase_uid": current_user.get("uid")}
        )
        if not user:
            return error_response("User account not found", 404)

        user_response = {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "role": user.get("role", "user"),
            "settings": user.get("settings", {}),
            "farm_info": user.get("farm_info", {}),
        }
        return {"success": True, "user": user_response}
    except Exception as e:
        logger.error("Token verification error: %s", str(e))
        return error_response(str(e), 401)


@router.get("/profile")
@router.get("/profile/{uid}")
def get_profile(uid: Optional[str] = None, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get user profile."""
    try:
        target_uid = uid or current_user.get("uid") or current_user.get("firebase_uid")
        user = db_service.find_one("users", {"firebase_uid": target_uid})
        if not user:
            return error_response("User not found", 404)
        user.pop("_id", None)
        return {"success": True, "profile": user, "user": user}
    except Exception as e:
        logger.error("Get profile error: %s", str(e))
        return error_response(str(e), 500)


@router.put("/profile")
def update_profile(
    payload: ProfileUpdateRequest = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update user profile."""
    try:
        data = payload.model_dump(exclude_none=True)
        if not data:
            raise AuthError("No data provided", 400)

        allowed_fields = ["name", "displayName", "phone", "farm_info", "settings"]
        update_data = {}
        for field in allowed_fields:
            if field in data:
                if field == "displayName":
                    update_data["name"] = data[field]
                else:
                    update_data[field] = data[field]

        if not update_data:
            raise AuthError("No valid fields to update", 400)

        update_data["updated_at"] = datetime.utcnow().isoformat()
        db_service.update_one(
            "users",
            {"user_id": current_user["user_id"]},
            {"$set": update_data},
        )

        lang = current_user.get("settings", {}).get("language", "en")
        return {"success": True, "message": get_message("profile_updated", lang)}
    except AuthError as e:
        return error_response(e.message, e.code)
    except Exception as e:
        logger.error("Update profile error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/logout")
def logout():
    return {"success": True, "message": "Logout successful"}


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest = Body(...)):
    """Initiate password reset via Firebase Identity Toolkit."""
    try:
        email = payload.email.strip()
        if not email:
            return error_response("Email is required", 400)
        if not validate_email(email):
            return error_response("Invalid email format", 400)
        if not FIREBASE_API_KEY:
            logger.error("FIREBASE_API_KEY is missing for forgot-password")
            return error_response("Password reset service is not configured", 503)

        firebase_url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={FIREBASE_API_KEY}"
        response = requests.post(
            firebase_url,
            json={"requestType": "PASSWORD_RESET", "email": email},
            timeout=15,
        )

        if response.status_code == 200:
            return {"success": True, "message": "If this email is registered, a password reset link has been sent."}

        try:
            error_message = (response.json() or {}).get("error", {}).get("message", "")
        except Exception:
            error_message = ""

        if error_message == "EMAIL_NOT_FOUND":
            return {"success": True, "message": "If this email is registered, a password reset link has been sent."}

        error_map = {"INVALID_EMAIL": "Invalid email format", "MISSING_EMAIL": "Email is required"}
        return error_response(error_map.get(error_message, "Password reset request failed"), 400)
    except requests.RequestException as e:
        logger.error("Forgot password network error: %s", str(e))
        return error_response("Password reset service temporarily unavailable", 503)
    except Exception as e:
        logger.error("Forgot password error: %s", str(e))
        return error_response("Password reset failed", 500)


@router.post("/local-register")
def local_register(payload: LocalRegisterRequest = Body(...)):
    """LOCAL register (no Firebase required)."""
    if not LOCAL_AUTH_ENABLED:
        return error_response("Local auth is disabled. Use Firebase auth.", 400)
    try:
        email = payload.email.strip().lower()
        password = payload.password
        name = payload.name.strip() if payload.name else ""
        phone = payload.phone or ""

        if not email:
            return error_response("Email is required", 400)
        if not validate_email(email):
            return error_response("Invalid email format", 400)
        if not password:
            return error_response("Password is required", 400)
        if len(password) < 6:
            return error_response("Password must be at least 6 characters", 400)

        existing_user = db_service.find_one("users", {"email": email})
        if existing_user:
            return error_response("User with this email already exists. Use /api/auth/local-login", 400)

        local_uid = f"local_{secrets.token_hex(12)}"
        user_id = db_service.get_next_user_id()
        user_profile = {
            "firebase_uid": local_uid,
            "user_id": user_id,
            "email": email,
            "name": name or email.split("@")[0],
            "phone": phone,
            "password_hash": _hash_password(password),
            "auth_type": "local",
            "role": "user",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "last_login": datetime.utcnow().isoformat(),
            "settings": {
                "language": "en",
                "notifications": True,
                "theme": "light",
                "units": "metric",
                "dashboard_layout": "standard",
            },
            "farm_info": {
                "district": "",
                "state": "Tamil Nadu",
                "farm_size": "",
                "soil_type": "",
                "primary_crop": "",
            },
            "photo_url": "/static/images/default-avatar.png",
            "is_active": True,
        }
        db_service.insert_one("users", user_profile)
        token = _generate_local_token(user_id, email)
        logger.info("Local registered user: %s", user_id)
        return {
            "success": True,
            "message": "User registered successfully (local auth)",
            "user": {"user_id": user_id, "email": email, "name": user_profile["name"]},
            "token": token,
            "auth_type": "local",
            "expires_in": 86400,
        }
    except Exception as e:
        logger.error("Local registration error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/local-login")
def local_login(payload: LocalLoginRequest = Body(...)):
    """LOCAL login (no Firebase required)."""
    if not LOCAL_AUTH_ENABLED:
        return error_response("Local auth is disabled. Use Firebase auth.", 400)
    try:
        email = payload.email.strip().lower()
        password = payload.password
        if not email:
            return error_response("Email is required", 400)
        if not password:
            return error_response("Password is required", 400)

        user = db_service.find_one("users", {"email": email})
        if not user:
            return error_response("User not found. Please register first.", 401)
        if user.get("auth_type") != "local":
            return error_response("This account uses Firebase auth. Use /api/auth/login instead.", 400)
        if not _verify_password(password, user.get("password_hash", "")):
            return error_response("Invalid password", 401)

        db_service.update_one("users", {"email": email}, {"$set": {"last_login": datetime.utcnow().isoformat()}})
        token = _generate_local_token(user["user_id"], email)
        logger.info("Local login: %s", user["user_id"])
        return {
            "success": True,
            "message": "Login successful (local auth)",
            "user": {
                "user_id": user["user_id"],
                "name": user["name"],
                "email": user["email"],
                "role": user.get("role", "user"),
                "settings": user.get("settings", {}),
                "farm_info": user.get("farm_info", {}),
            },
            "token": token,
            "auth_type": "local",
            "expires_in": 86400,
        }
    except Exception as e:
        logger.error("Local login error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/local-reset-password")
def local_reset_password(payload: LocalResetPasswordRequest = Body(...)):
    """Reset password for locally authenticated users."""
    if not LOCAL_AUTH_ENABLED:
        return error_response("Local auth is disabled. Use Firebase password reset.", 400)
    try:
        email = (payload.email or "").strip().lower()
        new_password = payload.new_password or ""
        confirm_password = payload.confirm_password or ""

        if not email:
            return error_response("Email is required", 400)
        if not validate_email(email):
            return error_response("Invalid email format", 400)
        if not new_password:
            return error_response("New password is required", 400)
        if not validate_password(new_password):
            return error_response("Password must be at least 6 characters", 400)
        if new_password != confirm_password:
            return error_response("Password confirmation does not match", 400)

        user = db_service.find_one("users", {"email": email})
        if not user:
            return error_response("User not found. Please register first.", 404)
        if user.get("auth_type") != "local":
            return error_response("This account uses Firebase auth. Use /api/auth/forgot-password instead.", 400)

        db_service.update_one(
            "users",
            {"email": email},
            {
                "$set": {
                    "password_hash": _hash_password(new_password),
                    "updated_at": datetime.utcnow().isoformat(),
                }
            },
        )
        logger.info("Local password reset successful for user: %s", user.get("user_id", "unknown"))
        return {
            "success": True,
            "message": "Password reset successful. Please login with your new password.",
        }
    except Exception as e:
        logger.error("Local password reset error: %s", str(e))
        return error_response("Password reset failed", 500)


@router.post("/verify-token")
def verify_token_endpoint(payload: VerifyTokenRequest = Body(...)):
    """Verify any token (Firebase or Local)."""
    try:
        token = payload.token
        if not token:
            return error_response("Token is required", 400)

        local_payload = verify_local_jwt(token)
        if local_payload:
            return {
                "valid": True,
                "user_id": local_payload.get("user_id"),
                "email": local_payload.get("email"),
                "type": "local",
            }

        try:
            decoded = verify_firebase_token(token)
            if decoded:
                return {
                    "valid": True,
                    "uid": decoded.get("uid"),
                    "email": decoded.get("email"),
                    "type": "firebase",
                }
        except Exception:
            pass

        return error_response("Invalid token", 401)
    except Exception as e:
        return error_response(str(e), 500)


def _create_user_profile(firebase_uid, email, name, phone=""):
    user_id = db_service.get_next_user_id()
    return {
        "firebase_uid": firebase_uid,
        "user_id": user_id,
        "email": email,
        "name": name,
        "phone": phone,
        "role": "user",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "last_login": datetime.utcnow().isoformat(),
        "settings": {
            "language": "en",
            "notifications": True,
            "theme": "light",
            "units": "metric",
            "dashboard_layout": "standard",
        },
        "farm_info": {
            "district": "",
            "state": "Tamil Nadu",
            "farm_size": "",
            "soil_type": "",
            "primary_crop": "",
        },
        "photo_url": "/static/images/default-avatar.png",
        "is_active": True,
    }


def _hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}${hashed}"


def _verify_password(password, stored_hash):
    if "$" not in stored_hash:
        return False
    salt, hashed = stored_hash.split("$", 1)
    check_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return check_hash == hashed


def _generate_local_token(user_id, email):
    payload = {
        "user_id": user_id,
        "email": email,
        "iat": datetime.utcnow().timestamp(),
        "exp": datetime.utcnow().timestamp() + 86400,
        "type": "local",
    }
    return jwt.encode(payload, LOCAL_JWT_SECRET, algorithm="HS256")
