"""
python -m uvicorn asgi:app --host 127.0.0.1 --port 5000

FastAPI ASGI entry point for ULAGA_UNAVU.

Migration strategy:
- FastAPI is the primary server/runtime.
- All API modules are registered as FastAPI routers.
- JSON file storage and Firebase integration remain unchanged.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

# Add project root to import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment before importing app modules/services.
load_dotenv()

from api.router_registry import api_router
from app.config import Config
from app.firebase_config import is_firebase_ready
from services.local_storage import db_service

BACKEND_ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = (BACKEND_ROOT.parent / "frontend" / "dist").resolve()
_frontend_override = os.getenv("FRONTEND_DIR", "").strip()
FRONTEND_DIR = Path(_frontend_override) if _frontend_override else (FRONTEND_DIST if FRONTEND_DIST.exists() else BACKEND_ROOT / "app" / "static" / "frontend")
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
FRONTEND_SW = FRONTEND_DIR / "service-worker.js"
FRONTEND_ICON = FRONTEND_DIR / "icons" / "icon-192.png"

_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _file_response(path: Path, media_type: str | None = None, cache_headers: dict | None = None) -> FileResponse:
    headers = cache_headers or {}
    return FileResponse(str(path), media_type=media_type, headers=headers)


def _resolve_cors_origins():
    origins = [origin.strip() for origin in (Config.CORS_ORIGINS or []) if origin.strip()]
    return origins or ["*"]


def create_app() -> FastAPI:
    app = FastAPI(
        title="ULAGA_UNAVU API",
        version=Config.APP_VERSION,
        description="FastAPI server for ULAGA_UNAVU API",
    )

    cors_origins = _resolve_cors_origins()
    allow_all = "*" in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def warm_models():
        try:
            try:
                from services.model_loader import get_model_loader
            except Exception:
                from ai_models.model_loader import get_model_loader
            loader = get_model_loader()
            # Warm up both critical models to prevent memory spikes on first request
            loader.load_soil_model()
            loader.load_disease_model()
            from services.cnn_service import get_cnn_service
            cnn_service = get_cnn_service()
            cnn_service.load_model("soil")
            cnn_service.load_model("disease")
            print("âœ… AI Models warmed up at startup")
        except Exception as e:
            print("âš ï¸ AI Models not fully loaded at startup:", e)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": str(exc.detail),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": "Invalid request payload",
                "details": exc.errors(),
            },
        )

    @app.get("/", tags=["meta"])
    def root():
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return {
            "message": "ULAGA_UNAVU API is running on FastAPI",
            "version": Config.APP_VERSION,
            "docs": "/docs",
            "legacy_api_prefix": "/api",
        }

    @app.get("/app", include_in_schema=False)
    def app_ui():
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/healthz", tags=["meta"])
    def healthz():
        storage_status = db_service.get_status()
        return {
            "status": "healthy",
            "framework": "fastapi",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "services": {
                "storage": storage_status.get("type", "local_storage"),
                "firebase_ready": is_firebase_ready(),
            },
        }

    @app.get("/service-worker.js", include_in_schema=False)
    def service_worker():
        if FRONTEND_SW.exists():
            return _file_response(FRONTEND_SW, media_type="application/javascript", cache_headers=_NO_CACHE_HEADERS)
        # Fallback worker that unregisters any previous service worker.
        content = (
            "self.addEventListener('install', () => self.skipWaiting());"
            "self.addEventListener('activate', (event) => {"
            "event.waitUntil(self.registration.unregister().then(() => self.clients.matchAll())"
            ".then((clients) => { clients.forEach((client) => client.navigate(client.url)); }));"
            "});"
        )
        return Response(content=content, media_type="application/javascript", headers=_NO_CACHE_HEADERS)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        if FRONTEND_ICON.exists():
            return _file_response(FRONTEND_ICON, media_type="image/png", cache_headers=_NO_CACHE_HEADERS)
        # Return empty response when no favicon asset exists.
        return Response(status_code=204)

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon_svg():
        # Fallback inline icon to avoid frontend 404 noise when SVG favicon is requested.
        content = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
            "<rect width='64' height='64' rx='14' fill='#2E7D32'/>"
            "<path d='M19 38c11-1 18-7 24-20 2 12-5 25-19 27-4 0-7-2-5-7z' fill='#FDD835'/>"
            "</svg>"
        )
        return Response(content=content, media_type="image/svg+xml", headers=_NO_CACHE_HEADERS)

    # Serve individual asset files explicitly.
    FRONTEND_ASSETS = FRONTEND_DIR / "assets"
    
    @app.get("/assets/{path:path}", include_in_schema=False)
    def serve_assets(path: str):
        asset_path = FRONTEND_ASSETS / path
        if asset_path.exists() and asset_path.is_file():
            media_type = "application/javascript" if path.endswith(".js") else "text/css" if path.endswith(".css") else "application/octet-stream"
            return _file_response(asset_path, media_type=media_type, cache_headers=_NO_CACHE_HEADERS)
        return Response("Asset not found", status_code=404)

    # SPA routes - serve index.html for all frontend routes.
    @app.get("/dashboard", include_in_schema=False)
    @app.get("/dashboard/{path:path}", include_in_schema=False)
    def dashboard_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/soil-analysis", include_in_schema=False)
    @app.get("/soil-analysis/{path:path}", include_in_schema=False)
    def soil_analysis_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/disease-detection", include_in_schema=False)
    @app.get("/disease-detection/{path:path}", include_in_schema=False)
    @app.get("/disease-detect", include_in_schema=False)
    @app.get("/disease-detect/{path:path}", include_in_schema=False)
    def disease_detection_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/crop-recommend", include_in_schema=False)
    @app.get("/crop-recommend/{path:path}", include_in_schema=False)
    def crop_recommend_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/crop-select", include_in_schema=False)
    @app.get("/crop-select/{path:path}", include_in_schema=False)
    def crop_select_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/start-farming", include_in_schema=False)
    @app.get("/start-farming/{path:path}", include_in_schema=False)
    def start_farming_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/crop-selection", include_in_schema=False)
    @app.get("/crop-selection/{path:path}", include_in_schema=False)
    def crop_selection_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/growth-tracking", include_in_schema=False)
    @app.get("/growth-tracking/{path:path}", include_in_schema=False)
    def growth_tracking_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/fertilizer", include_in_schema=False)
    @app.get("/fertilizer/{path:path}", include_in_schema=False)
    def fertilizer_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/market", include_in_schema=False)
    @app.get("/market/{path:path}", include_in_schema=False)
    def market_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/weather", include_in_schema=False)
    @app.get("/weather/{path:path}", include_in_schema=False)
    def weather_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/chatbot", include_in_schema=False)
    @app.get("/chatbot/{path:path}", include_in_schema=False)
    def chatbot_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/news", include_in_schema=False)
    @app.get("/news/{path:path}", include_in_schema=False)
    def news_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/settings", include_in_schema=False)
    @app.get("/settings/{path:path}", include_in_schema=False)
    def settings_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/login", include_in_schema=False)
    def login_route():
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/forgot-password", include_in_schema=False)
    @app.get("/forgot-password/{path:path}", include_in_schema=False)
    def forgot_password_route(path: str = ""):
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    @app.get("/register", include_in_schema=False)
    def register_route():
        if FRONTEND_INDEX.exists():
            return _file_response(FRONTEND_INDEX, media_type="text/html", cache_headers=_NO_CACHE_HEADERS)
        return Response("Frontend not found", status_code=404)

    app.include_router(api_router)

    return app


app = create_app()
