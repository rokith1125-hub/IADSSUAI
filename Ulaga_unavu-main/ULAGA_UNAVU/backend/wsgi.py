"""
WSGI entry point is deprecated.
Use ASGI: `python -m uvicorn asgi:app --host 127.0.0.1 --port 5000`
"""

from asgi import app as application  # Exposed for tooling compatibility


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("asgi:app", host="127.0.0.1", port=5000, reload=False)
