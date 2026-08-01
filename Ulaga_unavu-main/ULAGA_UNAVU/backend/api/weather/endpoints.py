"""
Weather data endpoints (FastAPI).
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from api.common.auth import get_current_user
from api.common.responses import error_response
from utils.error_handler import APIError
from .openmeteo import WeatherEngine

logger = logging.getLogger(__name__)

router = APIRouter()
weather_engine = WeatherEngine()


@router.get("/")
def weather_info():
    """Get weather module information."""
    return {
        "module": "Weather Service",
        "endpoints": {
            "current": "/current (GET, auth)",
            "forecast": "/forecast (GET, auth)",
            "farming": "/farming (GET, auth)",
        },
    }


@router.get("/current")
def get_current_weather(
    lang: str = Query(default="en"),
    location: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get current weather for user's location."""
    try:
        user_id = current_user["user_id"]
        weather = weather_engine.get_user_weather(user_id, lang=lang, location_override=location)
        return {"success": True, "weather": weather}
    except Exception as e:
        logger.error("Get current weather error: %s", str(e))
        if isinstance(e, APIError):
            return error_response(e.message, e.status_code)
        return error_response("Weather service unavailable", 503)


@router.get("/forecast")
def get_weather_forecast(
    days: int = Query(default=3),
    location: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get weather forecast."""
    try:
        user_id = current_user["user_id"]
        forecast = weather_engine.get_forecast(user_id, days, location_override=location)
        return {"success": True, "forecast": forecast}
    except Exception as e:
        logger.error("Get forecast error: %s", str(e))
        if isinstance(e, APIError):
            return error_response(e.message, e.status_code)
        return error_response("Weather service unavailable", 503)


@router.get("/farming")
def get_farming_weather(
    lang: str = Query(default="en"),
    location: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get weather with farming-specific insights."""
    try:
        user_id = current_user["user_id"]
        farming_weather = weather_engine.get_farming_weather(user_id, lang=lang, location_override=location)
        return {"success": True, "farming_weather": farming_weather}
    except Exception as e:
        logger.error("Get farming weather error: %s", str(e))
        if isinstance(e, APIError):
            return error_response(e.message, e.status_code)
        return error_response("Weather service unavailable", 503)


@router.get("/alerts")
def get_weather_alerts(
    location: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get weather alerts for farming."""
    try:
        user_id = current_user["user_id"]
        alerts = weather_engine.get_weather_alerts(user_id, location_override=location)
        return {"success": True, "alerts": alerts}
    except Exception as e:
        logger.error("Get weather alerts error: %s", str(e))
        if isinstance(e, APIError):
            return error_response(e.message, e.status_code)
        return error_response("Weather service unavailable", 503)


@router.get("/locations")
def get_supported_locations():
    """Get list of supported locations."""
    try:
        locations = weather_engine.get_supported_locations()
        return {"success": True, "locations": locations}
    except Exception as e:
        logger.error("Get locations error: %s", str(e))
        return error_response("Locations temporarily unavailable", 500)
