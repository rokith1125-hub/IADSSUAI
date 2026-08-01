"""
Shared FastAPI authentication dependency for API routers.
Supports local JWT and Firebase ID token verification.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import jwt
from fastapi import Header, HTTPException

from app.firebase_config import is_firebase_ready, verify_firebase_token
from services.local_storage import db_service

logger = logging.getLogger(__name__)

LOCAL_JWT_SECRET = (
    os.environ.get("JWT_SECRET_KEY")
    or os.environ.get("JWT_SECRET")
    or "ulaga_unavu_local_secret_key_2026"
)
LOCAL_AUTH_ENABLED = os.environ.get("LOCAL_AUTH", "true").lower() == "true"


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
    else:
        token = authorization.strip()
    return token or None


def verify_local_jwt(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, LOCAL_JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Dict[str, Any]:
    """
    Authenticate request and return user context.
    Raises HTTPException on failure.
    """
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authorization header is missing or empty.")

    if LOCAL_AUTH_ENABLED:
        local_payload = verify_local_jwt(token)
        if local_payload and local_payload.get("user_id"):
            user_id = local_payload.get("user_id")
            email = local_payload.get("email", "")
            user = db_service.find_one("users", {"user_id": user_id})
            if not user and email:
                user = db_service.find_one("users", {"email": email})

            if user:
                if not user.get("is_active", True):
                    raise HTTPException(status_code=403, detail="User account is deactivated.")
                return {
                    "user_id": user.get("user_id"),
                    "uid": user.get("firebase_uid"),
                    "firebase_uid": user.get("firebase_uid"),
                    "email": user.get("email", ""),
                    "name": user.get("name", ""),
                    "role": user.get("role", "user"),
                    "settings": user.get("settings", {}),
                    "farm_info": user.get("farm_info", {}),
                    "auth_type": "local",
                }

    if not is_firebase_ready():
        raise HTTPException(status_code=401, detail="Invalid token")

    try:
        decoded_token = verify_firebase_token(token)
        if not decoded_token or "uid" not in decoded_token:
            raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Firebase auth error: %s", str(exc))
        raise HTTPException(status_code=401, detail="Invalid token provided")

    firebase_uid = decoded_token["uid"]
    user = db_service.get_user_by_firebase_uid(firebase_uid)

    if not user:
        user = db_service.create_user(
            firebase_uid=firebase_uid,
            email=decoded_token.get("email", ""),
            name=decoded_token.get("name", decoded_token.get("email", "").split("@")[0]),
        )
    else:
        db_service.update_user(
            user["user_id"],
            {"last_login": datetime.utcnow().isoformat()},
        )

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="User account is deactivated.")

    return {
        "uid": firebase_uid,
        "firebase_uid": firebase_uid,
        "user_id": user["user_id"],
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "role": user.get("role", "user"),
        "profile": user.get("profile", {}),
        "settings": user.get("settings", {}),
        "farm_info": user.get("farm_info", {}),
        "auth_type": "firebase",
    }
