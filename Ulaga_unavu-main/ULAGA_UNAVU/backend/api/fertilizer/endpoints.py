"""
Fertilizer schedule endpoints (FastAPI).
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel

from api.common.auth import get_current_user
from api.common.responses import error_response
from .scheduler import FertilizerScheduler

logger = logging.getLogger(__name__)

router = APIRouter()
fertilizer_scheduler = FertilizerScheduler()


class ApplyRequest(BaseModel):
    stage_index: Optional[int] = None
    actual_date: Optional[str] = None
    notes: Optional[str] = ""


class PostponeRequest(BaseModel):
    stage_index: Optional[int] = None
    new_date: Optional[str] = None
    reason: Optional[str] = ""


@router.get("/")
def fertilizer_info():
    """Get fertilizer module information."""
    return {
        "module": "Fertilizer Scheduling",
        "endpoints": {
            "plan": "/plan (GET)",
            "today": "/today (GET)",
            "apply": "/apply (POST)",
            "postpone": "/postpone (POST)",
            "types": "/types (GET)",
        },
    }


@router.get("/plan")
def get_fertilizer_plan(
    lang: str = Query(default="en"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get fertilizer plan for current crop."""
    try:
        user_id = current_user["user_id"]
        plan = fertilizer_scheduler.get_fertilizer_plan(user_id, lang=lang)
        return {"success": True, "plan": plan}
    except Exception as e:
        logger.error("Get fertilizer plan error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/today")
def get_today_action(
    lang: str = Query(default="en"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get today's fertilizer action."""
    try:
        user_id = current_user["user_id"]
        action = fertilizer_scheduler.get_today_action(user_id, lang=lang)
        return {"success": True, "action": action}
    except Exception as e:
        logger.error("Get today action error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/apply")
def mark_applied(
    payload: Optional[ApplyRequest] = Body(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Mark fertilizer as applied."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump() if payload else {}
        result = fertilizer_scheduler.mark_applied(
            user_id=user_id,
            stage_index=data.get("stage_index"),
            actual_date=data.get("actual_date"),
            notes=data.get("notes", ""),
        )
        return {
            "success": True,
            "message": "Fertilizer application recorded",
            "result": result,
        }
    except Exception as e:
        logger.error("Mark applied error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/postpone")
def postpone_application(
    payload: Optional[PostponeRequest] = Body(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Postpone fertilizer application."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump() if payload else {}
        result = fertilizer_scheduler.postpone_application(
            user_id=user_id,
            stage_index=data.get("stage_index"),
            new_date=data.get("new_date"),
            reason=data.get("reason", ""),
        )
        return {
            "success": True,
            "message": "Application postponed",
            "result": result,
        }
    except Exception as e:
        logger.error("Postpone application error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/types")
def get_fertilizer_types():
    """Get list of fertilizer types (public)."""
    try:
        fertilizers = fertilizer_scheduler.get_fertilizer_types()
        return {"success": True, "fertilizers": fertilizers}
    except Exception as e:
        logger.error("Get fertilizer types error: %s", str(e))
        return error_response(str(e), 500)
