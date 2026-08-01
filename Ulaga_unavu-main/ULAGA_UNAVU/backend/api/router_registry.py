"""
Central FastAPI router registry for all API modules.
"""

from datetime import datetime

from fastapi import APIRouter

from services.local_storage import db_service

from .auth.endpoints import router as auth_router
from .chatbot.endpoints import router as chatbot_router
from .crop.endpoints import router as crop_router
from .dashboard.endpoints import router as dashboard_router
from .disease.endpoints import router as disease_router
from .fertilizer.endpoints import router as fertilizer_router
from .growth.endpoints import router as growth_router
from .market.endpoints import router as market_router
from .news.endpoints import router as news_router
from .pdf.endpoints import router as pdf_router
from .settings.endpoints import router as settings_router
from .smart_mandi.endpoints import router as smart_mandi_router
from .soil.endpoints import router as soil_router
from .weather.endpoints import router as weather_router

api_router = APIRouter(prefix="/api")


@api_router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "services": {
            "database": "online",
            "storage": db_service.get_status().get("type", "local_storage"),
        },
    }


@api_router.get("/version")
def version():
    return {
        "api_version": "v1",
        "backend_version": "1.0.0",
        "last_updated": "2026-02-27",
    }


@api_router.get("/status")
def status():
    storage_status = db_service.get_status()
    return {
        "api_version": "1.0.0",
        "uptime": "active",
        "storage": {
            "type": storage_status.get("type", "local_storage"),
            "path": storage_status.get("path", "data/"),
            "status": "online",
        },
        "services": {
            "database": "online",
            "firebase": "configured",
            "llm": "available",
        },
    }


api_router.include_router(auth_router, prefix="/auth")
api_router.include_router(dashboard_router, prefix="/dashboard")
api_router.include_router(soil_router, prefix="/soil")
api_router.include_router(crop_router, prefix="/crop")
api_router.include_router(disease_router, prefix="/disease")
api_router.include_router(fertilizer_router, prefix="/fertilizer")
api_router.include_router(growth_router, prefix="/growth")
api_router.include_router(weather_router, prefix="/weather")
api_router.include_router(market_router, prefix="/market")
api_router.include_router(smart_mandi_router, prefix="/smart-mandi")
api_router.include_router(chatbot_router, prefix="/chatbot")
api_router.include_router(news_router, prefix="/news")
api_router.include_router(settings_router, prefix="/settings")
api_router.include_router(pdf_router, prefix="/pdf")
