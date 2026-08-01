"""
Dashboard endpoints for ULAGA_UNAVU (FastAPI).
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query

from api.common.auth import get_current_user
from api.common.responses import error_response
from .logic import DashboardAggregator

logger = logging.getLogger(__name__)

router = APIRouter()
dashboard_aggregator = DashboardAggregator()


@router.get("/")
@router.get("")
def get_dashboard(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get complete dashboard data for user."""
    try:
        user_id = current_user["user_id"]
        dashboard_data = dashboard_aggregator.get_dashboard_data(user_id)
        return {
            "success": True,
            "dashboard": dashboard_data,
            "timestamp": dashboard_aggregator.get_current_timestamp(),
        }
    except Exception as e:
        logger.error("Dashboard error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/summary")
def get_summary(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get quick summary for dashboard."""
    try:
        user_id = current_user["user_id"]
        summary = dashboard_aggregator.get_quick_summary(user_id)
        return {
            "success": True,
            "summary": summary,
        }
    except Exception as e:
        logger.error("Dashboard summary error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/cards/{card_type}")
def get_card_data(card_type: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get specific card data."""
    try:
        user_id = current_user["user_id"]
        card_data = dashboard_aggregator.get_card_data(user_id, card_type)
        return {
            "success": True,
            "card_type": card_type,
            "data": card_data,
        }
    except Exception as e:
        logger.error("Card data error for %s: %s", card_type, str(e))
        return error_response(str(e), 500)


@router.post("/refresh")
def refresh_dashboard(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Force refresh dashboard data."""
    try:
        user_id = current_user["user_id"]
        dashboard_aggregator.clear_cache(user_id)
        dashboard_data = dashboard_aggregator.get_dashboard_data(user_id, force_refresh=True)
        return {
            "success": True,
            "message": "Dashboard refreshed",
            "dashboard": dashboard_data,
        }
    except Exception as e:
        logger.error("Dashboard refresh error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/alerts")
def get_alerts(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get active alerts for user."""
    try:
        user_id = current_user["user_id"]
        alerts = dashboard_aggregator.get_alerts(user_id)
        return {
            "success": True,
            "alerts": alerts,
        }
    except Exception as e:
        logger.error("Alerts error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/next-step")
def get_next_step(
    lang: str = Query(default="en"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get prioritized next steps for the mandatory flow."""
    try:
        user_id = current_user["user_id"]
        steps = dashboard_aggregator.get_next_steps(user_id, lang=lang)
        return {
            "success": True,
            "steps": steps,
            "count": len(steps),
        }
    except Exception as e:
        logger.error("Next-step error: %s", str(e))
        return error_response(str(e), 500)
