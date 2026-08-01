"""
ULAGA_UNAVU - FastAPI launcher module.
"""

import logging
import os
import sys

import uvicorn

# Ensure backend root is importable when running `python app/main.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from asgi import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    reload_enabled = os.getenv("RELOAD", os.getenv("FLASK_DEBUG", "true")).lower() == "true"

    logger.info("Starting ULAGA_UNAVU FastAPI server")
    uvicorn.run("asgi:app", host=host, port=port, reload=reload_enabled)
