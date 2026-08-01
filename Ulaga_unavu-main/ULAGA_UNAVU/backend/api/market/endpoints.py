"""
Market endpoints for ULAGA_UNAVU (FastAPI).
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel

from api.common.auth import get_current_user
from api.common.responses import error_response
from services.local_storage import db_service
from .decision import MarketDecisionEngine

logger = logging.getLogger(__name__)

router = APIRouter()
market_engine = MarketDecisionEngine()


class MarketDecisionRequest(BaseModel):
    crop_name: Optional[str] = None
    quantity: Optional[float] = 0.0
    harvest_date: Optional[str] = None
    storage_type: Optional[str] = "normal"
    lang: Optional[str] = "en"


class MarketActionRequest(BaseModel):
    action: str
    crop_name: Optional[str] = None
    sale_price: Optional[float] = None
    sale_quantity: Optional[float] = None
    buyer_type: Optional[str] = "Mandi"
    notes: Optional[str] = ""


class ShelfLifeRequest(BaseModel):
    crop_name: str
    harvest_date: str
    storage_type: Optional[str] = "normal"


@router.get("/")
def market_info():
    """Get market module information."""
    return {
        "module": "Market Intelligence",
        "endpoints": {
            "prices": "/prices (GET, auth)",
            "decision": "/decision (POST, auth)",
            "trends": "/trends (GET, auth)",
            "snapshot": "/snapshot (GET, auth)",
        },
    }


@router.get("/prices")
def get_market_prices(
    crop: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get market prices for crops."""
    try:
        user_id = current_user["user_id"]
        crop_name = crop
        user = db_service.find_one("users", {"user_id": user_id}) or {}
        farm_info = user.get("farm_info", {})

        if not state or not district:
            state = state or farm_info.get("state")
            district = district or farm_info.get("district")

        if not crop_name:
            crop_doc = db_service.find_one("crop_selections", {"user_id": user_id, "is_active": True})
            if crop_doc:
                crop_name = crop_doc["crop_name"]
            else:
                primary_crop = farm_info.get("primary_crop") or farm_info.get("primary_crops")
                if isinstance(primary_crop, list):
                    primary_crop = primary_crop[0] if primary_crop else None
                crop_name = primary_crop
                if not crop_name:
                    return error_response("Crop not selected", 400)

        if not state and not district:
            return error_response("Farm location not configured", 400)

        prices = market_engine.get_mandi_prices(crop_name, state or "Tamil Nadu", district)
        if prices.get("error"):
            return error_response(prices.get("error"), int(prices.get("status_code", 503)))

        return {"success": True, "prices": prices}
    except Exception as e:
        logger.error("Market prices error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/broker-prices")
def get_broker_prices(
    crop: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get local broker prices."""
    try:
        user_id = current_user["user_id"]
        crop_name = crop

        if not crop_name:
            crop_collection = db_service.get_collection("crop_selections")
            crop_doc = crop_collection.find_one(
                {"user_id": user_id, "is_active": True},
                projection={"crop_name": 1},
            )
            if crop_doc:
                crop_name = crop_doc["crop_name"]
            else:
                return error_response("No crop specified", 400)

        if not district:
            user_collection = db_service.get_collection("users")
            user = user_collection.find_one(
                {"user_id": user_id},
                projection={"farm_info.district": 1},
            )
            if user:
                district = user.get("farm_info", {}).get("district")
        if not district:
            return error_response("District context required", 400)

        broker_prices = market_engine.get_broker_prices(crop_name, district)
        if broker_prices.get("error"):
            return error_response(broker_prices.get("error"), int(broker_prices.get("status_code", 503)))

        return {"success": True, "broker_prices": broker_prices}
    except Exception as e:
        logger.error("Broker prices error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/decision")
def get_market_decision(
    payload: Optional[MarketDecisionRequest] = Body(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get SELL/WAIT decision for crop."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump() if payload else {}
        if not data:
            return error_response("Request data required", 400)

        crop_name = data.get("crop_name")
        quantity = float(data.get("quantity", 0) or 0)
        harvest_date = data.get("harvest_date")
        storage_type = data.get("storage_type", "normal")

        if not crop_name:
            crop_collection = db_service.get_collection("crop_selections")
            crop_doc = crop_collection.find_one(
                {"user_id": user_id, "is_active": True},
                projection={"crop_name": 1, "harvest_date": 1},
            )
            if crop_doc:
                crop_name = crop_doc["crop_name"]
                if not harvest_date and "harvest_date" in crop_doc:
                    harvest_date = crop_doc["harvest_date"]
            else:
                return error_response("No crop specified", 400)

        if not harvest_date:
            return error_response("Harvest date required", 400)

        user_collection = db_service.get_collection("users")
        user = user_collection.find_one(
            {"user_id": user_id},
            projection={"farm_info.district": 1},
        )
        location = user.get("farm_info", {}).get("district") if user else None
        if not location:
            return error_response("District context required", 400)

        lang = data.get("lang", "en")
        decision = market_engine.get_market_decision(
            user_id=user_id,
            crop_name=crop_name,
            quantity=quantity,
            harvest_date=harvest_date,
            storage_type=storage_type,
            location=location,
            lang=lang,
        )
        if decision.get("error") or decision.get("decision") in {"UNAVAILABLE", None}:
            return error_response(decision.get("error", "Market decision unavailable"), int(decision.get("status_code", 503)))

        _save_market_decision(user_id, decision)
        return {"success": True, "decision": decision}
    except Exception as e:
        logger.error("Market decision error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/history")
def get_market_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get user's market decision history."""
    try:
        user_id = current_user["user_id"]
        collection = db_service.get_collection("market_snapshots")
        history = list(
            collection.find(
                {"user_id": user_id},
                sort=[("captured_at", -1)],
                limit=20,
                projection={
                    "_id": 0,
                    "crop_name": 1,
                    "market_decision": 1,
                    "price_data.mandi_price": 1,
                    "captured_at": 1,
                    "farmer_action.action_taken": 1,
                },
            )
        )
        return {"success": True, "history": history}
    except Exception as e:
        logger.error("Market history error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/action")
def record_market_action(
    payload: MarketActionRequest = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Record farmer's market action."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump()
        action = data["action"]

        collection = db_service.get_collection("market_snapshots")
        snapshot = collection.find_one(
            {"user_id": user_id, "is_active": True},
            sort=[("captured_at", -1)],
        )

        if not snapshot:
            return error_response("No active market snapshot found", 404)

        snapshot["farmer_action"] = {
            "action_taken": action,
            "action_date": datetime.utcnow(),
            "sale_price": data.get("sale_price"),
            "sale_quantity": data.get("sale_quantity"),
            "buyer_type": data.get("buyer_type", "Mandi"),
            "notes": data.get("notes", ""),
        }
        if action in ["Sold", "Partial Sale"]:
            snapshot["is_active"] = False

        snapshot["updated_at"] = datetime.utcnow()
        collection.update_one({"_id": snapshot["_id"]}, {"$set": snapshot})

        return {"success": True, "message": "Market action recorded", "action": action}
    except Exception as e:
        logger.error("Record action error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/trends/{crop_name}")
def get_price_trends(
    crop_name: str,
    state: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
):
    """Get price trends for crop (public endpoint)."""
    try:
        state = state or "Tamil Nadu"
        if not district and not state:
            return error_response("State or district context required", 400)

        trends = market_engine.market_service.get_crop_market_data(crop_name, district, state)
        if trends.get("error"):
            return error_response(trends.get("error"), int(trends.get("status_code", 503)))

        return {"success": True, "crop": crop_name, "trends": trends}
    except Exception as e:
        logger.error("Price trends error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/shelf-life")
def check_shelf_life(
    payload: ShelfLifeRequest = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Check shelf life for crop."""
    try:
        data = payload.model_dump()
        shelf_life = market_engine.calculate_shelf_life_risk(
            data["crop_name"],
            data["harvest_date"],
            data.get("storage_type", "normal"),
        )
        return {"success": True, "shelf_life": shelf_life}
    except Exception as e:
        logger.error("Shelf life error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/snapshot")
@router.get("/snapshot/")
def get_market_snapshot(
    crop: Optional[str] = Query(default=None),
    lang: str = Query(default="en"),
    state: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get real-time market snapshot for user's location."""
    try:
        user_id = current_user["user_id"]
        crop_name = crop
        user = db_service.find_one("users", {"user_id": user_id}) or {}
        farm_info = user.get("farm_info", {})
        state = farm_info.get("state") or state
        district = farm_info.get("district") or district

        if not crop_name:
            crop_doc = db_service.find_one("crop_selections", {"user_id": user_id, "is_active": True})
            if crop_doc:
                crop_name = crop_doc["crop_name"]
            else:
                primary_crop = farm_info.get("primary_crop") or farm_info.get("primary_crops")
                if isinstance(primary_crop, list):
                    primary_crop = primary_crop[0] if primary_crop else None
                crop_name = primary_crop
                if not crop_name:
                    return error_response("No crop specified", 400)

        if not state and not district:
            return error_response("State or district context required", 400)

        snapshot = market_engine.get_market_snapshot(user_id, crop_name, state or "Tamil Nadu", district, lang=lang)
        if snapshot.get("error"):
            return error_response(snapshot.get("error", "Real-time market prices unavailable"), int(snapshot.get("status_code", 503)))

        return {"success": True, "snapshot": snapshot}
    except Exception as e:
        logger.error("Market snapshot error: %s", str(e))
        return error_response(str(e), 500)


def _save_market_decision(user_id: str, decision_data: Dict):
    """Save market decision to history."""
    try:
        collection = db_service.get_collection("market_snapshots")
        snapshot = {
            "user_id": user_id,
            "crop_name": decision_data.get("crop"),
            "quantity": decision_data.get("quantity", 0),
            "harvest_date": decision_data.get("harvest_date"),
            "storage_type": decision_data.get("storage_type", "normal"),
            "price_data": {
                "mandi_price": decision_data.get("prices", {}).get("mandi", 0),
                "broker_price": decision_data.get("prices", {}).get("broker", 0),
                "price_trend": decision_data.get("price_trend", {}).get("trend", "STABLE"),
            },
            "market_decision": {
                "decision": decision_data.get("decision", "WAIT"),
                "reasoning": decision_data.get("reasoning", []),
                "confidence": decision_data.get("confidence", 0.5),
                "priority": "High" if decision_data.get("decision") in ["SELL", "DO NOT SELL"] else "Medium",
            },
            "shelf_life_analysis": decision_data.get("shelf_life", {}),
            "comparison_analysis": {
                "best_option": decision_data.get("comparison", {}).get("best_option", "MANDI"),
                "price_difference": decision_data.get("prices", {}).get("difference", 0),
            },
            "financial_projections": decision_data.get("expected_value", {}),
            "captured_at": datetime.utcnow(),
            "location": decision_data.get("location", ""),
            "farmer_action": {"action_taken": "No Action"},
            "is_active": True,
            "notes": "",
        }
        collection.insert_one(snapshot)
        logger.info("Market decision saved for user %s", user_id)
    except Exception as e:
        logger.error("Save market decision error: %s", str(e))
