"""
Crop recommendation endpoints - FastAPI APIRouter
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.common.auth import get_current_user
from services.crop_lifecycle_engine import get_lifecycle_engine
from utils.error_handler import APIError
from .recommendation import CropRecommender

logger = logging.getLogger(__name__)

router = APIRouter()
crop_recommender = CropRecommender()


class SelectCropRequest(BaseModel):
    crop_name: str
    custom_crop: bool = False


class StartFarmingRequest(BaseModel):
    start_date: Optional[str] = None


def _success(data: Optional[Dict[str, Any]] = None, message: str = "", next_step: str = ""):
    return {
        "success": True,
        "data": data or {},
        "message": message,
        "next_step": next_step,
    }


def _error(message: str):
    return {"success": False, "error": message}


def _error_response(message: str, status_code: int):
    return JSONResponse(status_code=status_code, content=_error(message))


@router.get("/recommend")
def get_recommendations(
    soil_result_id: str = Query(...),
    lang: str = Query(default="en"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get crop recommendations based on explicit soil result."""
    user_id = current_user["user_id"]

    try:
        recommendations = crop_recommender.get_recommendations(
            user_id=user_id,
            soil_result_id=soil_result_id,
            lang=lang,
        )
        return _success(
            data={
                "soil_result_id": soil_result_id,
                "recommendations": recommendations,
            },
            message="Crop recommendations ready",
            next_step="Select Crop",
        )
    except APIError as exc:
        return _error_response(exc.message, exc.status_code)
    except Exception as exc:
        logger.error("Crop recommendations error: %s", str(exc))
        return _error_response(str(exc), 500)


@router.post("/select")
def select_crop(
    payload: SelectCropRequest = Body(...),
    lang: str = Query(default="en"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Select a crop, persist selection, and generate crop image with API fallback."""
    user_id = current_user["user_id"]

    try:
        result = crop_recommender.select_crop(
            user_id=user_id,
            crop_name=payload.crop_name,
            custom_crop=payload.custom_crop,
            lang=lang,
        )
        return _success(
            data=result,
            message="Crop selected successfully",
            next_step="Start Farming",
        )
    except APIError as exc:
        return _error_response(exc.message, exc.status_code)
    except Exception as exc:
        logger.error("Crop selection error: %s", str(exc))
        return _error_response(str(exc), 500)


@router.get("/current")
def get_current_crop(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get currently selected crop."""
    user_id = current_user["user_id"]

    try:
        crop = crop_recommender.get_current_crop(user_id)
        return _success(
            data={"current_crop": crop},
            message="Current crop fetched",
            next_step="Start Farming" if crop else "",
        )
    except Exception as exc:
        logger.error("Get current crop error: %s", str(exc))
        return _error_response(str(exc), 500)


@router.post("/start-farming")
def start_farming(
    payload: Optional[StartFarmingRequest] = Body(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Start farming lifecycle explicitly after crop selection."""
    user_id = current_user["user_id"]

    try:
        lifecycle = get_lifecycle_engine(user_id)
        start_date = payload.start_date if payload else None
        result = lifecycle.start_growth(start_date=start_date)
        if not result.get("success"):
            status_code = int(result.get("status_code", 400))
            return _error_response(result.get("error", "Could not start farming"), status_code)

        return _success(
            data=result,
            message="Farming started successfully",
            next_step=result.get("next_step", "Track Growth"),
        )
    except Exception as exc:
        logger.error("Start farming error: %s", str(exc))
        return _error_response("Farming initialization failed", 503)


@router.get("/lifecycle")
def get_lifecycle(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get lifecycle context for the current crop."""
    user_id = current_user["user_id"]

    try:
        lifecycle = get_lifecycle_engine(user_id)
        lifecycle_data = lifecycle.get_unified_crop_context()
        next_action = lifecycle_data.get("dashboard_data", {}).get("next_action", "")

        return _success(
            data=lifecycle_data,
            message="Crop lifecycle fetched",
            next_step=next_action,
        )
    except Exception as exc:
        logger.error("Lifecycle error: %s", str(exc))
        return _error_response(str(exc), 500)
