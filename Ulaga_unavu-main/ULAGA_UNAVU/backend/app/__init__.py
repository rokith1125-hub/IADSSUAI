"""
Flask bootstrap has been deprecated.
Use ASGI app from `asgi.py`.
"""


def create_app():
    raise RuntimeError(
        "Flask bootstrap is deprecated. Start the service with: "
        "python -m uvicorn asgi:app --host 127.0.0.1 --port 5000"
    )
