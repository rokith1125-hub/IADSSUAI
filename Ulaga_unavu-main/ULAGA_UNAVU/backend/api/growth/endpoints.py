"""
Growth tracking endpoints (FastAPI).
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel

from api.common.auth import get_current_user
from api.common.responses import error_response
from .tracker import GrowthTracker

logger = logging.getLogger(__name__)

router = APIRouter()
growth_tracker = GrowthTracker()


class StartTrackingRequest(BaseModel):
    start_date: Optional[str] = None
    lang: Optional[str] = "en"


class UpdateStageRequest(BaseModel):
    stage_index: Optional[int] = None
    notes: Optional[str] = ""
    lang: Optional[str] = "en"


class HarvestRequest(BaseModel):
    actual_date: Optional[str] = None
    yield_amount: Optional[str] = ""
    notes: Optional[str] = ""
    lang: Optional[str] = "en"


@router.get("/")
def growth_info():
    """Get growth tracking module information."""
    return {
        "module": "Growth Tracking",
        "endpoints": {
            "timeline": "/timeline (GET)",
            "start": "/start (POST)",
            "update": "/update (POST)",
            "harvest": "/harvest (POST)",
            "status": "/status (GET)",
        },
    }


@router.get("/timeline")
def get_growth_timeline(
    lang: str = Query(default="en"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get growth timeline for current crop."""
    try:
        user_id = current_user["user_id"]
        timeline = growth_tracker.get_growth_timeline(user_id, lang=lang)
        return {"success": True, "timeline": timeline}
    except Exception as e:
        logger.error("Get growth timeline error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/start")
def start_growth_tracking(
    payload: Optional[StartTrackingRequest] = Body(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Start growth tracking for crop."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump() if payload else {}
        timeline = growth_tracker.start_tracking(
            user_id,
            data.get("start_date"),
            lang=data.get("lang", "en"),
        )
        return {
            "success": True,
            "message": "Growth tracking started",
            "timeline": timeline,
        }
    except Exception as e:
        logger.error("Start growth tracking error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/update")
def update_growth_stage(
    payload: Optional[UpdateStageRequest] = Body(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update growth stage manually."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump() if payload else {}
        result = growth_tracker.update_stage(
            user_id=user_id,
            stage_index=data.get("stage_index"),
            notes=data.get("notes", ""),
            lang=data.get("lang", "en"),
        )
        return {
            "success": True,
            "message": "Growth stage updated",
            "result": result,
        }
    except Exception as e:
        logger.error("Update growth stage error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/harvest")
def mark_harvested(
    payload: Optional[HarvestRequest] = Body(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Mark crop as harvested."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump() if payload else {}
        result = growth_tracker.mark_harvested(
            user_id=user_id,
            actual_date=data.get("actual_date"),
            yield_amount=data.get("yield_amount", ""),
            notes=data.get("notes", ""),
            lang=data.get("lang", "en"),
        )
        return {
            "success": True,
            "message": "Harvest recorded",
            "result": result,
        }
    except Exception as e:
        logger.error("Mark harvested error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/status")
def get_growth_status(
    lang: str = Query(default="en"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get current growth status."""
    try:
        user_id = current_user["user_id"]
        status = growth_tracker.get_current_status(user_id, lang=lang)
        return {"success": True, "status": status}
    except Exception as e:
        logger.error("Get growth status error: %s", str(e))
        return error_response(str(e), 500)
