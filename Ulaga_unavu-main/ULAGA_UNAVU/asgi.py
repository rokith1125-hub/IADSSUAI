"""
Compatibility ASGI entrypoint for running uvicorn from project root.

Example:
    python -m uvicorn asgi:app --host 127.0.0.1 --port 5000
"""

from backend.asgi import app, create_app  # re-export

