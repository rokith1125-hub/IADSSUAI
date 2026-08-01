"""
Soil Analysis Endpoints - FastAPI Router
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.common.auth import get_current_user
from services.weather_service import WeatherService
from .analysis import SoilAnalysisError, get_soil_analyzer

logger = logging.getLogger(__name__)

router = APIRouter()
weather_service = WeatherService()
MAX_UPLOAD_MB = 5


class ManualSoilAnalyzeRequest(BaseModel):
    soil_name: Optional[str] = None
    lang: Optional[str] = "en"


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


def _season_context() -> Dict[str, str]:
    month_index = datetime.utcnow().month
    month_name = datetime.utcnow().strftime("%B")
    if month_index in [6, 7, 8, 9, 10]:
        season = "Kharif"
    elif month_index in [11, 12, 1, 2, 3]:
        season = "Rabi"
    else:
        season = "Zaid"
    return {"current_month": month_name, "season": season}


def _safe_weather_note(current_user: Dict[str, Any]) -> Dict[str, Any]:
    farm_info = (current_user or {}).get("farm_info", {}) or {}
    location = None
    lat = farm_info.get("latitude")
    lon = farm_info.get("longitude")
    if lat is not None and lon is not None:
        try:
            location = f"{float(lat)},{float(lon)}"
        except Exception:
            location = None
    if not location:
        location = farm_info.get("district") or farm_info.get("state")

    if not location:
        return {
            "rain_expected_today": None,
            "two_line_report": "Weather context unavailable. Farm location is not configured.",
        }

    try:
        weather = weather_service.get_current_weather(location)
        current = weather.get("current", {}) or {}
        hourly = weather.get("forecast", {}).get("hourly", []) or []
        probs = [
            item.get("precipitation_probability")
            for item in hourly[:24]
            if isinstance(item.get("precipitation_probability"), (int, float))
        ]
        rain_probability = max(probs) if probs else None
        rain_now = float(current.get("rain", 0) or current.get("showers", 0) or 0)
        rain_expected = bool(rain_now > 0 or (rain_probability is not None and rain_probability > 40))

        temp = current.get("temperature")
        humidity = current.get("humidity")
        wind_speed = current.get("wind_speed")
        line_1 = (
            f"Today weather: {temp if temp is not None else 'N/A'}C, "
            f"humidity {humidity if humidity is not None else 'N/A'}%, "
            f"wind {wind_speed if wind_speed is not None else 'N/A'} km/h."
        )
        line_2 = (
            "Rain expected today. Plan soil work and irrigation accordingly."
            if rain_expected
            else "No significant rain expected today. Field operations can continue."
        )
        return {
            "rain_expected_today": rain_expected,
            "two_line_report": f"{line_1} {line_2}",
        }
    except Exception as exc:
        logger.warning("Weather note unavailable for soil analysis: %s", str(exc))
        return {
            "rain_expected_today": None,
            "two_line_report": "Weather service unavailable for today.",
        }


def _build_soil_data_payload(result: Dict[str, Any], current_user: Dict[str, Any]) -> Dict[str, Any]:
    confidence_value = result.get("confidence_value")
    confidence_ratio = None
    confidence_percentage = None
    if isinstance(confidence_value, (int, float)):
        normalized = float(confidence_value)
        confidence_ratio = round(normalized / 100.0 if normalized > 1 else normalized, 4)
        confidence_percentage = f"{round(normalized, 2)}%"
    elif result.get("confidence_label"):
        confidence_percentage = result.get("confidence_label")

    analysis_id = result.get("result_id") or result.get("_id")
    return {
        "type": "soil_analysis",
        "analysis_id": analysis_id,
        "prediction": {
            "soil_name": result.get("soil_name", ""),
            "confidence": confidence_ratio,
        },
        "confidence_percentage": confidence_percentage,
        "analysis_method": result.get("analysis_method", "CNN"),
        "season_context": _season_context(),
        "weather_note": _safe_weather_note(current_user),
        "soil_properties": result.get("soil_properties", {}),
        "explanation": result.get("explanation", {}),
        "created_at": result.get("created_at"),
        "result": get_soil_analyzer().to_public_report(result),
        "unlock_crop_module": True,
    }


@router.get("/")
def soil_info():
    """Get soil module information and model status."""
    try:
        analyzer = get_soil_analyzer()
        model_status = analyzer.get_model_status()
        return _success(
            data={
                "module": "Soil Analysis",
                "version": "2.0-production",
                "model_status": model_status,
                "endpoints": {
                    "analyze": "POST /analyze - Analyze soil from image",
                    "analyze_manual": "POST /analyze-manual - Manual soil selection",
                    "history": "GET /history - Get analysis history",
                    "result": "GET /result/{id} - Get specific result",
                    "types": "GET /types - List available soil types",
                    "model_status": "GET /model-status - Check CNN model status",
                },
            },
            message="Soil module info fetched",
            next_step="",
        )
    except Exception as exc:
        logger.error("Soil info error: %s", str(exc))
        return _error_response(str(exc), 500)


@router.get("/model-status")
def model_status():
    """Get CNN model availability status."""
    try:
        analyzer = get_soil_analyzer()
        status = analyzer.get_model_status()
        http_code = 200 if status.get("available") else 503
        payload = _success(
            data={"model": "soil_cnn", "status": status},
            message="Model status fetched",
            next_step="",
        )
        return JSONResponse(status_code=http_code, content=payload)
    except Exception as exc:
        logger.error("Model status error: %s", str(exc))
        return _error_response(str(exc), 500)


@router.post("/analyze")
async def analyze_soil(
    image: Optional[UploadFile] = File(default=None),
    soil_image: Optional[UploadFile] = File(default=None),
    lang: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Analyze soil from uploaded image.

    CRITICAL: If CNN model unavailable, returns 503 error.
    NEVER returns fake predictions.
    """
    user_id = current_user["user_id"]

    analyzer = get_soil_analyzer()
    selected_lang = lang or "en"
    image_file = image or soil_image

    if not image_file:
        return _error_response("Image file required for soil analysis", 400)
    if not image_file.filename:
        return _error_response("No image file selected", 400)

    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    file_ext = os.path.splitext(image_file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        return _error_response(f"Invalid file type: {file_ext}", 400)

    try:
        image_bytes = await image_file.read()
        image_size_mb = len(image_bytes) / (1024 * 1024)
        if image_size_mb > MAX_UPLOAD_MB:
            return _error_response(
                f"Image too large ({image_size_mb:.1f}MB). Maximum allowed: {MAX_UPLOAD_MB}MB",
                400
            )
        result = analyzer.analyze(
            user_id=user_id,
            image_bytes=image_bytes,
            lang=selected_lang,
        )
        data_payload = _build_soil_data_payload(result, current_user)

        payload = _success(
            data=data_payload,
            message="Soil analysis completed",
            next_step="Proceed to Crop Recommendation",
        )
        return payload

    except SoilAnalysisError as exc:
        logger.error("Soil analysis error for user %s: %s", user_id, exc.message)
        return _error_response(exc.message, exc.code)
    except Exception as exc:
        logger.error("Unexpected soil analysis error: %s", str(exc))
        return _error_response("Soil analysis failed unexpectedly", 500)


@router.post("/analyze-manual")
def analyze_soil_manual(
    payload: Optional[ManualSoilAnalyzeRequest] = Body(default=None),
    lang: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Analyze soil with manual selection.
    """
    user_id = current_user["user_id"]

    analyzer = get_soil_analyzer()
    if not payload or not payload.soil_name:
        return _error_response("soil_name is required", 400)

    selected_lang = lang or payload.lang or "en"

    try:
        result = analyzer.analyze(
            user_id=user_id,
            soil_name=payload.soil_name,
            lang=selected_lang,
        )
        data_payload = _build_soil_data_payload(result, current_user)

        response_payload = _success(
            data=data_payload,
            message="Soil analysis completed",
            next_step="Proceed to Crop Recommendation",
        )
        return response_payload
    except SoilAnalysisError as exc:
        logger.error("Manual soil error: %s", exc.message)
        return _error_response(exc.message, exc.code)
    except Exception as exc:
        logger.error("Manual soil error: %s", str(exc))
        return _error_response(str(exc), 500)


@router.get("/history")
def get_soil_history(
    limit: int = Query(default=10),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get user's soil analysis history."""
    user_id = current_user["user_id"]

    try:
        analyzer = get_soil_analyzer()
        safe_limit = min(max(limit, 1), 50)
        history = analyzer.get_history(user_id, limit=safe_limit)
        return _success(
            data={"count": len(history), "history": history},
            message="Soil history fetched",
            next_step="",
        )
    except Exception as exc:
        logger.error("Soil history error: %s", str(exc))
        return _error_response(str(exc), 500)


@router.get("/result/{result_id}")
def get_soil_result(
    result_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get specific soil analysis result."""
    user_id = current_user["user_id"]

    try:
        analyzer = get_soil_analyzer()
        result = analyzer.get_result_by_id(user_id, result_id)

        if not result:
            return _error_response("Result not found or access denied", 404)

        return _success(
            data={"result": analyzer.to_public_report(result)},
            message="Soil result fetched",
            next_step="",
        )
    except Exception as exc:
        logger.error("Soil result error: %s", str(exc))
        return _error_response(str(exc), 500)


@router.get("/types")
def get_soil_types():
    """
    Get list of available soil types for manual selection.

    Public endpoint - no auth required.
    """
    try:
        analyzer = get_soil_analyzer()
        soil_types = analyzer.get_soil_types()
        return _success(
            data={"count": len(soil_types), "soil_types": soil_types},
            message="Soil types fetched",
            next_step="",
        )
    except Exception as exc:
        logger.error("Soil types error: %s", str(exc))
        return _error_response(str(exc), 500)
