"""
User settings endpoints for ULAGA_UNAVU (FastAPI).
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, UploadFile
from pydantic import BaseModel

from api.common.auth import get_current_user
from api.common.responses import error_response
from app.firebase_config import delete_firebase_user
from services.local_storage import db_service
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter()
notification_service = NotificationService()


class UpdateSettingsRequest(BaseModel):
    settings: Optional[Dict[str, Any]] = None
    profile: Optional[Dict[str, Any]] = None


class MarkNotificationReadRequest(BaseModel):
    notification_id: Optional[str] = None


class DeleteAccountRequest(BaseModel):
    confirm: str


@router.get("/")
@router.get("")
def get_settings(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get user settings."""
    try:
        user_id = current_user["user_id"]
        user_collection = db_service.get_collection("users")
        user = user_collection.find_one(
            {"user_id": user_id},
            projection={
                "_id": 0,
                "settings": 1,
                "farm_info": 1,
                "name": 1,
                "email": 1,
                "phone": 1,
                "photo_url": 1,
            },
        )
        if not user:
            return error_response("User not found", 404)

        return {
            "success": True,
            "settings": user.get("settings", {}),
            "profile": {
                "name": user.get("name", ""),
                "email": user.get("email", ""),
                "phone": user.get("phone", ""),
                "farm_info": user.get("farm_info", {}),
                "photo_url": user.get("photo_url", "/static/images/default-avatar.png"),
            },
        }
    except Exception as e:
        logger.error("Get settings error: %s", str(e))
        return error_response(str(e), 500)


@router.put("/update")
def update_settings(
    payload: UpdateSettingsRequest = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update user settings."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump(exclude_none=True)
        if not data:
            return error_response("No data provided", 400)

        update_data = {}
        profile_update = {}

        if "settings" in data:
            update_data["settings"] = data["settings"]

        if "profile" in data:
            profile = data["profile"] or {}
            if "name" in profile:
                profile_update["name"] = profile["name"]
            if "phone" in profile:
                profile_update["phone"] = profile["phone"]
            if "farm_info" in profile:
                profile_update["farm_info"] = profile["farm_info"]
            if "email" in profile:
                logger.warning("User %s attempted to update email via settings endpoint. Ignored.", user_id)

        user_collection = db_service.get_collection("users")
        update_query = {"$set": {"updated_at": datetime.utcnow()}}
        if update_data:
            update_query["$set"].update(update_data)
        if profile_update:
            update_query["$set"].update(profile_update)

        result = user_collection.update_one({"user_id": user_id}, update_query)
        if result.modified_count == 0:
            return error_response("No changes made", 400)

        if "settings" in data:
            user = user_collection.find_one({"user_id": user_id}, projection={"settings": 1})
            if user:
                notification_service.schedule_notifications(user_id, user.get("settings", {}))

        return {"success": True, "message": "Settings updated successfully"}
    except Exception as e:
        logger.error("Update settings error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/profile-picture")
async def upload_profile_pic(
    profile_pic: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Upload profile picture."""
    try:
        user_id = current_user["user_id"]
        if not profile_pic.filename:
            return error_response("No selected file", 400)

        static_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "static",
            "profile_pics",
        )
        os.makedirs(static_dir, exist_ok=True)

        ext = os.path.splitext(profile_pic.filename)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            return error_response("Invalid file type. Use JPG, PNG, or WEBP.", 400)

        filename = f"profile_{user_id}{ext}"
        filepath = os.path.join(static_dir, filename)
        content = await profile_pic.read()
        with open(filepath, "wb") as f:
            f.write(content)

        photo_url = f"/static/profile_pics/{filename}"
        user_collection = db_service.get_collection("users")
        user_collection.update_one(
            {"user_id": user_id},
            {"$set": {"photo_url": photo_url, "updated_at": datetime.utcnow()}},
        )

        return {"success": True, "message": "Profile picture updated", "photo_url": photo_url}
    except Exception as e:
        logger.error("Profile pic upload error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/notifications")
def get_notifications(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get user notifications."""
    try:
        user_id = current_user["user_id"]
        notifications = notification_service.get_user_notifications(user_id, unread_only=False, limit=50)
        return {
            "success": True,
            "notifications": notifications,
            "unread_count": notification_service.get_unread_count(user_id),
        }
    except Exception as e:
        logger.error("Get notifications error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/notifications/read")
def mark_notifications_read(
    payload: Optional[MarkNotificationReadRequest] = Body(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Mark notifications as read."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump(exclude_none=True) if payload else {}
        if data and "notification_id" in data:
            notification_id = data["notification_id"]
            success = notification_service.mark_as_read(notification_id, user_id)
            if not success:
                return error_response("Notification not found", 404)
            return {"success": True, "message": "Notification marked as read"}

        count = notification_service.mark_all_as_read(user_id)
        return {"success": True, "message": f"Marked {count} notifications as read"}
    except Exception as e:
        logger.error("Mark notifications read error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/notifications/clear")
def clear_notifications(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Clear all notifications."""
    try:
        user_id = current_user["user_id"]
        collection = db_service.get_collection("notifications")
        result = collection.delete_many({"user_id": user_id})
        logger.info("Cleared %s notifications for user %s", result.deleted_count, user_id)
        return {"success": True, "message": f"Cleared {result.deleted_count} notifications"}
    except Exception as e:
        logger.error("Clear notifications error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/account/change-password")
def change_password(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Change password (handled by Firebase on frontend)."""
    return {
        "success": True,
        "message": "Use Firebase Authentication on frontend to change password",
    }


@router.post("/account/logout-all")
def logout_all_devices(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Logout from all devices."""
    try:
        user_id = current_user["user_id"]
        logger.info("User %s logged out from all devices", user_id)
        return {"success": True, "message": "Logged out from all devices"}
    except Exception as e:
        logger.error("Logout all error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/account/delete")
def delete_account(
    payload: DeleteAccountRequest = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete user account."""
    try:
        user_id = current_user["user_id"]
        firebase_uid = current_user.get("uid") or current_user.get("firebase_uid")
        if payload.confirm != "DELETE":
            return error_response("Confirmation required. Send {'confirm': 'DELETE'} to delete account.", 400)

        if firebase_uid and not str(firebase_uid).startswith("local_"):
            try:
                delete_firebase_user(firebase_uid)
            except Exception as firebase_error:
                logger.error("Firebase delete error: %s", str(firebase_error))

        user_collection = db_service.get_collection("users")
        user_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "is_active": False,
                    "deleted_at": datetime.utcnow(),
                    "email": f"deleted_{user_id}@ulagau.com",
                    "name": "Deleted User",
                    "phone": "",
                }
            },
        )

        notification_service.cleanup_old_notifications(days_old=7)
        logger.info("Account deleted for user %s", user_id)
        return {"success": True, "message": "Account deleted successfully"}
    except Exception as e:
        logger.error("Delete account error: %s", str(e))
        return error_response(str(e), 500)
