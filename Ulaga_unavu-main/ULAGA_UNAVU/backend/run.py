#!/usr/bin/env python
"""
ULAGA_UNAVU backend launcher.

Primary runtime: FastAPI (ASGI) with mounted Flask modules.
"""

import logging
import os
import sys

import uvicorn

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from asgi import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Backward compatibility for deployment tools that look for `application`
application = app


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    reload_enabled = os.getenv("RELOAD", os.getenv("FLASK_DEBUG", "true")).lower() == "true"

    print("\n" + "=" * 60)
    print("ULAGA_UNAVU - Agriculture AI Backend")
    print("=" * 60)
    print(f"Server: http://localhost:{port}")
    print("Runtime: FastAPI (ASGI) + mounted Flask modules")
    print("Health: http://localhost:{}/healthz".format(port))
    print("Legacy API: http://localhost:{}/api/health".format(port))
    print("Storage: Local JSON (data/ folder)")
    print("Firebase: Enabled (existing flow retained)")
    print("=" * 60 + "\n")

    logger.info("Starting FastAPI server with legacy Flask mount")
    uvicorn.run("asgi:app", host=host, port=port, reload=reload_enabled)
