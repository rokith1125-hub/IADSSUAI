"""
Shared FastAPI response helpers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse


def success_response(
    data: Optional[Dict[str, Any]] = None,
    message: str = "",
    next_step: str = "",
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data or {},
            "message": message,
            "next_step": next_step,
        },
    )


def error_response(error: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": error,
        },
    )


def api_error_response(exc: Exception, default_status: int = 500) -> JSONResponse:
    status_code = int(getattr(exc, "status_code", default_status))
    message = str(getattr(exc, "message", str(exc)))
    return error_response(message, status_code=status_code)
