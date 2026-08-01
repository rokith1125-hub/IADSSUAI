"""
Disease Detection Endpoints - FastAPI router.
"""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.common.auth import get_current_user
from api.common.responses import error_response
from .detection import DiseaseDetectionError, get_disease_detector

logger = logging.getLogger(__name__)

router = APIRouter()
MAX_UPLOAD_MB = 5


class ManualDiseaseRequest(BaseModel):
    disease_name: str
    crop_name: Optional[str] = None
    lang: Optional[str] = "en"


def _success(data: Optional[Dict[str, Any]] = None, message: str = "", next_step: str = "") -> Dict[str, Any]:
    return {
        "success": True,
        "data": data or {},
        "message": message,
        "next_step": next_step,
    }


def _build_disease_data(result: Dict[str, Any]) -> Dict[str, Any]:
    # Extract prediction data (Step 0 from USER)
    primary_name = result.get("disease_name")
    prediction_label = result.get("prediction") or primary_name
    confidence = result.get("confidence")
    alternatives = result.get("alternatives", [])
    warning = result.get("warning") or result.get("confidence_warning")

    return {
        "type": "disease_analysis",
        "analysis_id": result.get("analysis_id") or result.get("result_id") or result.get("_id"),
        "prediction": {
            "primary": primary_name,
            "disease_name": primary_name,
            "label": prediction_label,
            "confidence": confidence,
            "severity": result.get("severity"),
            "is_healthy": result.get("is_healthy"),
        },
        "alternatives": alternatives,
        "warning": warning,
        "confidence_percentage": result.get("confidence_percentage"),
        "weather_context": result.get("weather_context"),
        "spray_recommendation": result.get("spray_recommendation"),
        "treatment_plan": result.get("treatment_plan"),
        "llm_explanation": result.get("llm_explanation"),
        "created_at": result.get("created_at"),
        # Keep compatibility with existing frontend that expects `res.result`.
        "result": result,
    }


@router.get("/")
def disease_info():
    """Get disease module information and model status."""
    detector = get_disease_detector()
    model_status = detector.get_model_status()
    return {
        "module": "Disease Detection",
        "version": "2.0-production",
        "model_status": model_status,
        "endpoints": {
            "detect": "POST /detect - Detect disease from image",
            "manual": "POST /manual - Manual disease selection",
            "history": "GET /history - Get detection history",
            "result": "GET /result/<id> - Get specific result",
            "types": "GET /types - List known diseases",
            "treatment": "GET /treatment/<name> - Get treatment info",
            "model_status": "GET /model-status - Check CNN model status",
        },
    }


@router.get("/model-status")
def model_status():
    """Get CNN model availability status."""
    detector = get_disease_detector()
    status = detector.get_model_status()
    http_code = 200 if status.get("available") else 503
    return JSONResponse(
        status_code=http_code,
        content={
            "model": "disease_cnn",
            "status": status,
        },
    )


@router.post("/detect")
@router.post("/analyze")
async def detect_disease(
    image: Optional[UploadFile] = File(default=None),
    plant_image: Optional[UploadFile] = File(default=None),
    crop_name: Optional[str] = Form(default=None),
    ui_mode: Optional[str] = Query(default=None),
    lang: str = Query(default="en"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Detect disease from uploaded plant image.
    """
    try:
        user_id = current_user["user_id"]
        detector = get_disease_detector()

        image_file = image or plant_image
        if not image_file:
            return error_response("Image file required for disease detection", 400)
        if not image_file.filename:
            return error_response("No image file selected", 400)

        allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
        file_ext = os.path.splitext(image_file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return error_response(f"Invalid file type: {file_ext}", 400)

        image_bytes = await image_file.read()
        image_size_mb = len(image_bytes) / (1024 * 1024)
        if image_size_mb > MAX_UPLOAD_MB:
            return error_response(
                f"Image too large ({image_size_mb:.1f}MB). Maximum allowed: {MAX_UPLOAD_MB}MB",
                400,
            )

        result = detector.detect(
            user_id=user_id,
            image_bytes=image_bytes,
            crop_name=crop_name,
            lang=lang,
            ui_mode=ui_mode,
        )
        return _success(
            data=_build_disease_data(result),
            message="Disease detection completed",
            next_step="Review treatment plan",
        )

    except DiseaseDetectionError as e:
        logger.error("Disease detection error for user %s: %s", current_user.get("user_id", "unknown"), e.message)
        return error_response(e.message, e.code)
    except Exception as e:
        logger.error("Unexpected detection error: %s", str(e))
        return error_response("Disease detection failed unexpectedly", 500)


@router.post("/manual")
def manual_detection(
    payload: ManualDiseaseRequest = Body(...),
    ui_mode: Optional[str] = Query(default=None),
    lang: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Record disease with manual selection."""
    try:
        user_id = current_user["user_id"]
        detector = get_disease_detector()
        selected_lang = lang or payload.lang or "en"

        result = detector.detect(
            user_id=user_id,
            disease_name=payload.disease_name,
            crop_name=payload.crop_name,
            lang=selected_lang,
            ui_mode=ui_mode,
        )
        return _success(
            data=_build_disease_data(result),
            message="Manual disease detection completed",
            next_step="Review treatment plan",
        )
    except DiseaseDetectionError as e:
        logger.error("Manual detection error: %s", e.message)
        return error_response(e.message, e.code)
    except Exception as e:
        logger.error("Manual detection error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/history")
def get_disease_history(
    limit: int = Query(default=10),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get user's disease detection history."""
    try:
        user_id = current_user["user_id"]
        detector = get_disease_detector()
        safe_limit = min(max(limit, 1), 50)
        history = detector.get_history(user_id, limit=safe_limit)
        return _success(
            data={
                "count": len(history),
                "history": history,
                "results": history,
            },
            message="Disease history fetched",
            next_step="",
        )
    except Exception as e:
        logger.error("Disease history error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/history/{analysis_id}")
def get_disease_result(analysis_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get specific disease detection result."""
    try:
        user_id = current_user["user_id"]
        detector = get_disease_detector()
        result = detector.get_result_by_id(user_id, analysis_id)
        if not result:
            return error_response("Result not found or access denied", 404)
        return _success(
            data={
                "analysis_id": result.get("analysis_id") or result.get("result_id"),
                "result": result,
            },
            message="Disease result fetched",
            next_step="",
        )
    except Exception as e:
        logger.error("Disease result error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/result/{result_id}")
def get_disease_result_alias(result_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Backward-compatible alias for legacy frontend route."""
    return get_disease_result(result_id, current_user)


@router.get("/types")
def get_disease_types():
    """Get list of known diseases for manual selection (public endpoint)."""
    try:
        detector = get_disease_detector()
        diseases = detector.get_disease_types()
        return {"success": True, "count": len(diseases), "diseases": diseases}
    except Exception as e:
        logger.error("Disease types error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/treatment/{disease_name}")
def get_treatment(disease_name: str):
    """Get treatment information for a specific disease (public endpoint)."""
    try:
        detector = get_disease_detector()
        treatment = detector.get_treatment_info(disease_name)
        if not treatment:
            return error_response(f"Disease '{disease_name}' not found", 404)
        return {"success": True, "treatment": treatment}
    except Exception as e:
        logger.error("Treatment info error: %s", str(e))
        return error_response(str(e), 500)
