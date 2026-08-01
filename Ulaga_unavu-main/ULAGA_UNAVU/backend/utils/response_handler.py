"""
Standardized API Response Handler
Ensures all API responses follow consistent envelope format
"""

from datetime import datetime
from typing import Any, Optional, Dict


def success_response(
    data: Any = None,
    message: str = "Success",
    meta: Optional[Dict] = None,
    status_code: int = 200
):
    """
    Create a standardized success response
    
    Args:
        data: The response payload
        message: Success message
        meta: Optional metadata
        status_code: HTTP status code
    
    Returns:
        tuple: (response_dict, status_code)
    """
    response = {
        "status": "success",
        "message": message,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    if data is not None:
        response["data"] = data
    
    if meta:
        response["meta"] = meta
    
    return response, status_code


def error_response(
    error: str,
    code: int = 400,
    details: Optional[Dict] = None
):
    """
    Create a standardized error response
    
    Args:
        error: Error message
        code: Error code
        details: Optional error details
    
    Returns:
        tuple: (response_dict, status_code)
    """
    response = {
        "status": "error",
        "message": error,
        "code": code,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    if details:
        response["details"] = details
    
    return response, code


def paginated_response(
    data: list,
    page: int = 1,
    per_page: int = 20,
    total: int = None
):
    """
    Create a standardized paginated response
    
    Args:
        data: List of items
        page: Current page
        per_page: Items per page
        total: Total items
    
    Returns:
        tuple: (response_dict, status_code)
    """
    if total is None:
        total = len(data)
    
    return success_response(
        data=data,
        meta={
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page
            }
        }
    )


class ResponseBuilder:
    """Builder class for complex responses"""
    
    def __init__(self):
        self._data = None
        self._message = "Success"
        self._meta = {}
        self._status_code = 200
    
    def set_data(self, data: Any) -> 'ResponseBuilder':
        self._data = data
        return self
    
    def set_message(self, message: str) -> 'ResponseBuilder':
        self._message = message
        return self
    
    def add_meta(self, key: str, value: Any) -> 'ResponseBuilder':
        self._meta[key] = value
        return self
    
    def set_status_code(self, code: int) -> 'ResponseBuilder':
        self._status_code = code
        return self
    
    def build(self):
        return success_response(
            data=self._data,
            message=self._message,
            meta=self._meta if self._meta else None,
            status_code=self._status_code
        )
