"""
News endpoints for ULAGA_UNAVU (FastAPI).
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel

from api.common.auth import get_current_user
from api.common.responses import error_response
from services.local_storage import db_service
from services.market_service import MarketService
from services.weather_service import WeatherService
from utils.error_handler import APIError
from .aggregator import NewsAggregator

logger = logging.getLogger(__name__)

router = APIRouter()
news_aggregator = NewsAggregator()
weather_service = WeatherService()
market_service = MarketService()


class MarkReadRequest(BaseModel):
    title: str
    source: Optional[str] = "Unknown"
    category: Optional[str] = "general"
    url: Optional[str] = ""


@router.get("/")
def news_info():
    """Get news module information."""
    return {
        "module": "Agriculture News",
        "endpoints": {
            "today": "/today (GET, auth)",
            "search": "/search (GET, auth)",
            "categories": "/categories (GET)",
            "trending": "/trending (GET)",
        },
    }


@router.get("/today")
def get_today_news(
    lang: str = Query(default="en"),
    limit: int = Query(default=10),
    category: Optional[str] = Query(default=None),
    refresh: bool = Query(default=False),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get ranked agriculture news with location and crop awareness."""
    try:
        user_id = current_user["user_id"]
        user_context = _get_user_context(user_id)
        location = user_context.get("location", "")
        crop_name = user_context.get("crop", "")
        severe_weather = _is_severe_weather(location) if location else False
        market_drop = _has_market_drop(crop_name, location) if crop_name and location else False

        category_key = (category or "all").strip().lower()
        cache_key = (
            f"ranked_news:{lang}:{limit}:{category_key}:"
            f"{location or 'na'}:{crop_name or 'na'}:{int(severe_weather)}:{int(market_drop)}"
        )

        if not refresh:
            cached = db_service.find_one(
                "news_cache",
                {"cache_key": cache_key, "cache_type": "ranked_news"},
                sort=[("created_at", -1)],
            )
            if cached and _is_cache_valid(cached.get("expires_at")):
                return {
                    "success": True,
                    "news": (cached.get("news") or [])[:limit],
                    "cache_used": True,
                }

        raw_items = news_aggregator.get_todays_news_with_lang(
            lang=lang,
            limit=max(limit * 4, 40),
            refresh=refresh,
        )
        if not raw_items:
            raise APIError("News service unavailable", 503)

        ranked_news = []
        for item in raw_items:
            title = str(item.get("title", "")).strip()
            summary = str(item.get("summary", "")).strip()
            text_blob = f"{title} {summary}".lower()

            if any(term in text_blob for term in {"politics", "film", "crime", "sports"}):
                continue

            normalized_category = _normalize_news_category(item.get("category"), text_blob)
            if category and normalized_category != category.lower():
                continue

            relevance_score = _compute_news_relevance(
                item=item,
                crop_name=crop_name,
                severe_weather=severe_weather,
                market_drop=market_drop,
                normalized_category=normalized_category,
            )

            ranked_news.append(
                {
                    "title": title,
                    "description": summary,
                    "source": item.get("source", "Unknown"),
                    "published_at": item.get("published_at") or item.get("date") or "",
                    "url": item.get("url", ""),
                    "relevance_score": relevance_score,
                    "category": normalized_category,
                }
            )

        ranked_news.sort(
            key=lambda row: (float(row.get("relevance_score", 0) or 0), str(row.get("published_at", ""))),
            reverse=True,
        )
        ranked_news = ranked_news[:limit]
        if not ranked_news:
            raise APIError("News service unavailable", 503)

        db_service.insert_one(
            "news_cache",
            {
                "cache_key": cache_key,
                "cache_type": "ranked_news",
                "news": ranked_news,
                "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            },
        )

        _save_news_history(user_id, ranked_news[:5])
        return {"success": True, "news": ranked_news, "cache_used": False}
    except APIError as e:
        logger.error("Today news error: %s", str(e))
        return error_response(e.message, e.status_code)
    except Exception as e:
        logger.error("Today news error: %s", str(e))
        return error_response("News service unavailable", 503)


@router.get("/personalized")
def get_personalized_news(
    limit: int = Query(default=5),
    lang: str = Query(default="en"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get personalized news based on user's crops and location."""
    try:
        user_id = current_user["user_id"]
        user_context = _get_user_context(user_id)
        news_items = news_aggregator.get_news_for_farmers(
            location=user_context.get("location"),
            crop=user_context.get("crop"),
            lang=lang,
        )
        return {
            "success": True,
            "personalized_for": {
                "location": user_context.get("location", ""),
                "crop": user_context.get("crop", ""),
            },
            "news": news_items[:limit],
        }
    except Exception as e:
        logger.error("Personalized news error: %s", str(e))
        return error_response("News service unavailable", 503)


@router.get("/summary")
def get_news_summary(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get summary of today's agriculture news."""
    try:
        summary = news_aggregator.get_news_summary()
        return {"success": True, "summary": summary}
    except Exception as e:
        logger.error("News summary error: %s", str(e))
        return error_response("News service unavailable", 503)


@router.get("/categories")
def get_news_categories():
    """Get available news categories."""
    categories = [
        {"id": "crop", "name": "Crop", "icon": "crop"},
        {"id": "market", "name": "Market", "icon": "market"},
        {"id": "weather", "name": "Weather", "icon": "weather"},
        {"id": "government", "name": "Government Schemes", "icon": "government"},
        {"id": "pest", "name": "Pest Alerts", "icon": "pest"},
        {"id": "policy", "name": "Agriculture Policy", "icon": "policy"},
    ]
    return {"success": True, "categories": categories}


@router.get("/trending")
def get_trending_news(
    limit: int = Query(default=5),
    lang: str = Query(default="en"),
    refresh: bool = Query(default=False),
):
    """Get trending agriculture news (public endpoint)."""
    try:
        if refresh:
            news_aggregator.clear_cache()
        trending = news_aggregator.get_trending_news(limit=limit, lang=lang)
        return {"success": True, "trending": trending, "updated_at": datetime.now().isoformat()}
    except Exception as e:
        logger.error("Trending news error: %s", str(e))
        return error_response("News service unavailable", 503)


@router.get("/history")
def get_news_history(
    days: int = Query(default=7),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get user's news reading history."""
    try:
        user_id = current_user["user_id"]
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        collection = db_service.get_collection("news_history")
        history = list(
            collection.find(
                {"user_id": user_id, "read_at": {"$gte": cutoff_date}},
                sort=[("read_at", -1)],
                projection={
                    "_id": 0,
                    "title": 1,
                    "source": 1,
                    "category": 1,
                    "read_at": 1,
                },
            )
        )
        return {"success": True, "history": history}
    except Exception as e:
        logger.error("News history error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/mark-read")
def mark_news_read(
    payload: MarkReadRequest = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Mark news article as read."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump()
        title = data["title"]
        source = data.get("source", "Unknown")
        category = data.get("category", "general")
        url = data.get("url", "")

        collection = db_service.get_collection("news_history")
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        existing = collection.find_one(
            {"user_id": user_id, "title": title, "read_at": {"$gte": today_start}}
        )

        if not existing:
            now_iso = datetime.utcnow().isoformat()
            news_item = {
                "user_id": user_id,
                "title": title,
                "source": source,
                "category": category,
                "url": url,
                "read_at": now_iso,
                "created_at": now_iso,
            }
            collection.insert_one(news_item)

        return {"success": True, "message": "News marked as read"}
    except Exception as e:
        logger.error("Mark read error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/clear-history")
def clear_news_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Clear user's news history."""
    try:
        user_id = current_user["user_id"]
        collection = db_service.get_collection("news_history")
        result = collection.delete_many({"user_id": user_id})
        logger.info("Cleared %s news items for user %s", result.deleted_count, user_id)
        return {"success": True, "message": f"Cleared {result.deleted_count} news items"}
    except Exception as e:
        logger.error("Clear history error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/important")
def get_important_news(
    lang: str = Query(default="en"),
    limit: int = Query(default=5),
    refresh: bool = Query(default=False),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get important/breaking news."""
    try:
        all_news = news_aggregator.get_todays_news_with_lang(lang=lang, limit=20, refresh=refresh)
        important_news = []
        for item in all_news:
            category = item.get("category", "")
            relevance_score = float(item.get("relevance_score", 0) or 0)
            if relevance_score > 0.75 or category in ["market", "weather", "pest"]:
                important_news.append(item)

        important_news.sort(
            key=lambda x: (float(x.get("relevance_score", 0) or 0), x.get("published_at", "")),
            reverse=True,
        )
        return {"success": True, "important_news": important_news[:limit]}
    except Exception as e:
        logger.error("Important news error: %s", str(e))
        return error_response("News service unavailable", 503)


def _get_user_context(user_id: str) -> Dict:
    """Get user context for personalized news."""
    try:
        context = {"location": "", "crop": ""}
        user_collection = db_service.get_collection("users")
        user = user_collection.find_one({"user_id": user_id}, projection={"farm_info.district": 1})
        if user:
            context["location"] = user.get("farm_info", {}).get("district", "")

        crop_collection = db_service.get_collection("crop_selections")
        crop = crop_collection.find_one(
            {"user_id": user_id, "is_active": True},
            projection={"crop_name": 1},
        )
        if crop:
            context["crop"] = crop.get("crop_name", "")
        return context
    except Exception as e:
        logger.error("Get user context error: %s", str(e))
        return {}


def _save_news_history(user_id: str, news_items: List[Dict]):
    """Save news to user's reading history."""
    try:
        if not news_items:
            return

        collection = db_service.get_collection("news_history")
        for item in news_items:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            existing = collection.find_one(
                {"user_id": user_id, "title": item.get("title"), "read_at": {"$gte": today_start}}
            )
            if not existing:
                now_iso = datetime.utcnow().isoformat()
                news_record = {
                    "user_id": user_id,
                    "news_id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "summary": item.get("summary", item.get("description", "")),
                    "source": item.get("source", ""),
                    "category": item.get("category", "crop"),
                    "url": item.get("url", ""),
                    "image_url": item.get("image_url", ""),
                    "published_at": item.get("published_at", ""),
                    "relevance_score": float(item.get("relevance_score", 0) or 0),
                    "is_important": bool(item.get("is_important", False)),
                    "importance": item.get("importance", "normal"),
                    "read_at": now_iso,
                    "created_at": now_iso,
                }
                collection.insert_one(news_record)
    except Exception as e:
        logger.error("Save news history error: %s", str(e))


def _is_cache_valid(expires_at: str) -> bool:
    try:
        if not expires_at:
            return False
        return datetime.fromisoformat(str(expires_at)) > datetime.utcnow()
    except Exception:
        return False


def _normalize_news_category(category: str, text_blob: str) -> str:
    cat = str(category or "").strip().lower()
    if cat in {"crop", "market", "weather", "government", "pest", "policy"}:
        return cat
    if cat == "disease":
        return "pest"
    if any(word in text_blob for word in ["policy", "regulation", "bill", "act"]):
        return "policy"
    if any(word in text_blob for word in ["scheme", "subsidy", "pm-kisan", "government"]):
        return "government"
    if any(word in text_blob for word in ["disease", "pest", "insect", "blight"]):
        return "pest"
    if any(word in text_blob for word in ["weather", "rain", "monsoon", "flood", "drought"]):
        return "weather"
    if any(word in text_blob for word in ["market", "price", "mandi", "msp", "demand"]):
        return "market"
    return "crop"


def _compute_news_relevance(item: Dict, crop_name: str, severe_weather: bool, market_drop: bool, normalized_category: str) -> float:
    base_score = float(item.get("relevance_score", 0) or 0) * 100.0
    title = str(item.get("title", "")).lower()
    summary = str(item.get("summary", "")).lower()
    text_blob = f"{title} {summary}"

    if crop_name and crop_name.lower() in text_blob:
        base_score += 20.0
    if severe_weather and normalized_category == "weather":
        base_score += 15.0
        if "alert" in text_blob:
            base_score += 5.0
    if market_drop and normalized_category == "market":
        base_score += 15.0
        if "price" in text_blob or "drop" in text_blob:
            base_score += 5.0

    return round(min(100.0, max(0.0, base_score)), 2)


def _is_severe_weather(location: str) -> bool:
    try:
        weather = weather_service.get_current_weather(location)
        alerts = weather.get("alerts", []) or []
        return any(
            str(alert.get("severity", "")).lower() == "high"
            for alert in alerts
            if isinstance(alert, dict)
        )
    except Exception as e:
        logger.warning("Weather boost signal unavailable: %s", str(e))
        return False


def _has_market_drop(crop_name: str, district: str) -> bool:
    try:
        market_snapshot = market_service.get_mandi_snapshot(crop_name, "Tamil Nadu", district)
        if market_snapshot.get("error"):
            return False
        trend = str(market_snapshot.get("trend", "STABLE")).upper()
        change = float(market_snapshot.get("day_change_percent", market_snapshot.get("change_percent", 0)) or 0)
        return trend == "DOWN" and change <= -2
    except Exception as e:
        logger.warning("Market boost signal unavailable: %s", str(e))
        return False
