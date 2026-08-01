"""
Smart Mandi endpoints (FastAPI).
"""

import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel

from api.common.auth import get_current_user
from services.llm_service import LLMService
from services.local_storage import db_service
from services.smart_mandi.prediction_engine import PredictionEngine
from services.smart_mandi.price_fetcher import PriceFetcher
from services.smart_mandi.profit_calculator import ProfitCalculator
from services.smart_mandi.sell_score import SellScoreEngine
from services.smart_mandi.storage import MarketHistoryStorage

logger = logging.getLogger(__name__)

router = APIRouter()
price_fetcher = PriceFetcher()
predictor = PredictionEngine()
sell_score_engine = SellScoreEngine()
profit_calculator = ProfitCalculator()
history_storage = MarketHistoryStorage()
llm_service = LLMService()

SNAPSHOT_CACHE = {}
SNAPSHOT_CACHE_TTL_SECONDS = 600
KNOWN_CROPS = [
    "paddy",
    "rice",
    "maize",
    "groundnut",
    "sugarcane",
    "wheat",
    "cotton",
    "turmeric",
    "chilli",
    "onion",
    "tomato",
    "banana",
    "coconut",
]


class ProfitRequest(BaseModel):
    crop: Optional[str] = None
    quantity: float = 0
    transport_cost: float = 0
    district: Optional[str] = None
    state: Optional[str] = None


def _normalize_location_value(value):
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple, set)):
        return None
    text = str(value).strip()
    if text.lower() in {"[object object]", "object object", "undefined", "null", "none"}:
        return None
    return text or None


def _cache_get(cache_key):
    item = SNAPSHOT_CACHE.get(cache_key)
    if not item:
        return None
    if time.time() - item.get("ts", 0) > SNAPSHOT_CACHE_TTL_SECONDS:
        SNAPSHOT_CACHE.pop(cache_key, None)
        return None
    return item.get("value")


def _cache_set(cache_key, value):
    SNAPSHOT_CACHE[cache_key] = {"ts": time.time(), "value": value}


def _get_user_location(user_id):
    user = db_service.find_one("users", {"user_id": user_id}) or {}
    farm_info = user.get("farm_info", {}) or {}
    return {
        "district": farm_info.get("district") or "",
        "state": farm_info.get("state") or "Tamil Nadu",
        "lat": farm_info.get("latitude") or None,
        "lon": farm_info.get("longitude") or None,
    }


def _get_primary_crop(user_id):
    crop = db_service.find_one("crop_selections", {"user_id": user_id, "is_active": True})
    if crop and crop.get("crop_name"):
        return crop["crop_name"]
    user = db_service.find_one("users", {"user_id": user_id}) or {}
    farm_info = user.get("farm_info", {}) or {}
    primary = farm_info.get("primary_crop") or farm_info.get("primary_crops")
    if isinstance(primary, list):
        return primary[0] if primary else None
    return primary


def _normalize_crop_name(raw_crop: str) -> str:
    if not raw_crop:
        return ""
    value = str(raw_crop).strip().lower()
    if value in KNOWN_CROPS:
        return value
    try:
        from difflib import get_close_matches

        matches = get_close_matches(value, KNOWN_CROPS, n=1, cutoff=0.6)
        if matches:
            return matches[0]
    except Exception:
        pass

    try:
        prompt = f"""
        Correct the crop name spelling. Choose only one from this list:
        {', '.join(KNOWN_CROPS)}
        Input: {value}
        Reply with only the corrected crop name.
        """
        response = llm_service.generate_response(prompt, max_tokens=20, temperature=0.0, language="english")
        cleaned = str(response).strip().lower()
        if cleaned in KNOWN_CROPS:
            return cleaned
    except Exception:
        pass
    return value


@router.get("/get-price")
def get_price(
    crop: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        user_id = current_user["user_id"]
        crop_input = crop or _get_primary_crop(user_id) or "paddy"
        crop = _normalize_crop_name(crop_input) or "paddy"
        loc = _get_user_location(user_id)
        district = _normalize_location_value(district) or _normalize_location_value(loc.get("district"))
        state = _normalize_location_value(state) or _normalize_location_value(loc.get("state")) or "Tamil Nadu"

        data = price_fetcher.get_current_prices(crop, state, district)
        if not data or data.get("error"):
            logger.warning(
                "Mandi API failed for crop=%s district=%s: %s",
                crop,
                district,
                data.get("error") if data else "empty response",
            )
            return {
                "success": False,
                "message": "Live mandi data temporarily unavailable",
                "crop": crop,
                "normalized_crop": crop,
                "location": {
                    "district": district or "Unknown",
                    "state": state,
                    "lat": loc.get("lat"),
                    "lon": loc.get("lon"),
                },
                "prices": [],
                "series": [],
                "source": "Unavailable",
            }

        history_storage.append_daily_price(crop, state, district, data)
        return {
            "success": True,
            "location": {
                "district": data.get("district") or district,
                "state": data.get("state") or state,
                "lat": loc.get("lat"),
                "lon": loc.get("lon"),
            },
            "crop": data.get("crop"),
            "normalized_crop": crop,
            "prices": data.get("prices") or [],
            "series": data.get("series") or [],
            "source": data.get("source") or "Government Mandi API",
        }
    except Exception as e:
        logger.error("Smart mandi get-price error: %s", str(e))
        return {
            "success": False,
            "message": "Market service temporarily unavailable",
            "crop": "paddy",
            "normalized_crop": "paddy",
            "prices": [],
            "series": [],
        }


@router.get("/snapshot")
@router.get("/snapshot/")
def snapshot(
    crop: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    lang: str = Query(default="en"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Single-call snapshot endpoint for price + forecast + sell-score."""
    try:
        user_id = current_user["user_id"]
        crop_input = crop or _get_primary_crop(user_id) or "paddy"
        crop = _normalize_crop_name(crop_input) or "paddy"
        loc = _get_user_location(user_id)
        district = _normalize_location_value(district) or _normalize_location_value(loc.get("district"))
        state = _normalize_location_value(state) or _normalize_location_value(loc.get("state")) or "Tamil Nadu"

        cache_key = f"{crop}:{state}:{district}:{lang}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        price_payload = price_fetcher.get_current_prices(crop, state, district)
        if not price_payload or price_payload.get("error"):
            response = {
                "success": False,
                "message": "Live mandi data temporarily unavailable",
                "snapshot": {
                    "crop": crop,
                    "normalized_crop": crop,
                    "location": {
                        "district": district or "Unknown",
                        "state": state,
                        "lat": loc.get("lat"),
                        "lon": loc.get("lon"),
                    },
                    "source": "Unavailable",
                    "prices": [],
                    "series": [],
                    "prediction": {
                        "forecasts": [],
                        "moving_average": [],
                        "trend": "STABLE",
                        "confidence": 40,
                    },
                    "sell_score": {
                        "score": 50,
                        "label": "HOLD",
                        "trend": "STABLE",
                        "confidence": 40,
                        "weather_impact": "neutral",
                        "recommendation": {"text": "Live mandi data temporarily unavailable."},
                    },
                    "current_price": None,
                    "min_price": None,
                    "max_price": None,
                },
            }
            _cache_set(cache_key, response)
            return response

        series = price_payload.get("series") or []
        prediction = predictor.generate_forecasts(series)
        score = sell_score_engine.generate_sell_score(crop, price_payload, prediction, loc)
        recommendation = sell_score_engine.generate_tamil_recommendation(score, lang=lang)
        score["recommendation"] = recommendation

        latest = (price_payload.get("prices") or [{}])[0]
        snapshot_payload = {
            "crop": price_payload.get("crop", crop),
            "normalized_crop": crop,
            "location": {
                "district": price_payload.get("district") or district or "Unknown",
                "state": price_payload.get("state") or state,
                "lat": loc.get("lat"),
                "lon": loc.get("lon"),
            },
            "source": price_payload.get("source") or "Government Mandi API",
            "prices": price_payload.get("prices") or [],
            "series": series[-30:],
            "prediction": prediction,
            "sell_score": score,
            "current_price": latest.get("modal_price"),
            "min_price": latest.get("min_price"),
            "max_price": latest.get("max_price"),
        }
        response = {"success": True, "snapshot": snapshot_payload}
        _cache_set(cache_key, response)
        return response
    except Exception as e:
        logger.error("Smart mandi snapshot error: %s", str(e))
        return {
            "success": False,
            "message": "Market service temporarily unavailable",
            "snapshot": {
                "crop": "paddy",
                "normalized_crop": "paddy",
                "location": {"district": "Unknown", "state": "Tamil Nadu"},
                "prices": [],
                "series": [],
                "prediction": {"forecasts": [], "moving_average": [], "trend": "STABLE", "confidence": 40},
                "sell_score": {"score": 50, "label": "HOLD", "trend": "STABLE", "confidence": 40},
                "current_price": None,
                "min_price": None,
                "max_price": None,
            },
        }


@router.get("/predict")
def predict(
    crop: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        user_id = current_user["user_id"]
        crop_input = crop or _get_primary_crop(user_id) or "paddy"
        crop = _normalize_crop_name(crop_input) or "paddy"
        loc = _get_user_location(user_id)
        district = _normalize_location_value(district) or _normalize_location_value(loc.get("district"))
        state = _normalize_location_value(state) or _normalize_location_value(loc.get("state")) or "Tamil Nadu"

        series = price_fetcher.get_series(crop, state, district)
        prediction = predictor.generate_forecasts(series)
        if prediction.get("error"):
            return {
                "success": False,
                "message": "Prediction unavailable for current market data",
                "prediction": prediction,
                "normalized_crop": crop,
            }
        return {"success": True, "prediction": prediction, "normalized_crop": crop}
    except Exception as e:
        logger.error("Smart mandi predict error: %s", str(e))
        return {
            "success": False,
            "message": "Prediction unavailable",
            "prediction": {"forecasts": [], "moving_average": [], "trend": "STABLE", "confidence": 40},
        }


@router.get("/sell-score")
def sell_score(
    crop: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    lang: str = Query(default="ta"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        user_id = current_user["user_id"]
        crop_input = crop or _get_primary_crop(user_id) or "paddy"
        crop = _normalize_crop_name(crop_input) or "paddy"
        loc = _get_user_location(user_id)
        district = _normalize_location_value(district) or _normalize_location_value(loc.get("district"))
        state = _normalize_location_value(state) or _normalize_location_value(loc.get("state")) or "Tamil Nadu"

        price_payload = price_fetcher.get_current_prices(crop, state, district)
        series = price_fetcher.get_series(crop, state, district)
        prediction = predictor.generate_forecasts(series)
        score = sell_score_engine.generate_sell_score(crop, price_payload, prediction, loc)
        tamil_explanation = sell_score_engine.generate_tamil_recommendation(score, lang=lang)

        return {
            "success": True,
            "score": score,
            "recommendation": tamil_explanation,
            "normalized_crop": crop,
        }
    except Exception as e:
        logger.error("Smart mandi sell-score error: %s", str(e))
        return {
            "success": False,
            "message": "Sell score unavailable",
            "score": {"score": 50, "label": "HOLD", "trend": "STABLE", "confidence": 40},
        }


@router.post("/calculate-profit")
def calculate_profit(
    payload: ProfitRequest = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump()
        crop_input = data.get("crop") or _get_primary_crop(user_id) or "paddy"
        crop = _normalize_crop_name(crop_input) or "paddy"
        quantity = float(data.get("quantity", 0) or 0)
        transport_cost = float(data.get("transport_cost", 0) or 0)

        if quantity <= 0:
            return {"success": False, "message": "Quantity must be greater than 0"}
        if transport_cost < 0:
            return {"success": False, "message": "Transport cost cannot be negative"}

        loc = _get_user_location(user_id)
        district = _normalize_location_value(data.get("district")) or _normalize_location_value(loc.get("district"))
        state = _normalize_location_value(data.get("state")) or _normalize_location_value(loc.get("state")) or "Tamil Nadu"

        price_payload = price_fetcher.get_current_prices(crop, state, district)
        result = profit_calculator.calculate(price_payload.get("prices", []), quantity, transport_cost)
        return {"success": True, "profit": result, "normalized_crop": crop}
    except Exception as e:
        logger.error("Smart mandi calculate-profit error: %s", str(e))
        return {"success": False, "message": "Profit calculation unavailable"}


@router.get("/get-history")
def get_history(
    crop: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        user_id = current_user["user_id"]
        crop_input = crop or _get_primary_crop(user_id) or "paddy"
        crop = _normalize_crop_name(crop_input) or "paddy"
        loc = _get_user_location(user_id)
        district = _normalize_location_value(district) or _normalize_location_value(loc.get("district"))
        state = _normalize_location_value(state) or _normalize_location_value(loc.get("state")) or "Tamil Nadu"

        history = history_storage.get_history(crop, state, district)
        return {"success": True, "history": history, "normalized_crop": crop}
    except Exception as e:
        logger.error("Smart mandi get-history error: %s", str(e))
        return {"success": False, "message": "History unavailable", "history": []}
