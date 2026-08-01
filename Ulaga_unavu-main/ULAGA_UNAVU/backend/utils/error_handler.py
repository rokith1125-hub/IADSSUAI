"""
Error handling utilities
"""

import traceback
import logging

logger = logging.getLogger(__name__)

class APIError(Exception):
    """Custom API error class"""
    
    def __init__(self, message, status_code=400, error_code=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
    
    def to_dict(self):
        """Convert error to dictionary"""
        error_dict = {
            "error": self.message,
            "status_code": self.status_code
        }
        
        if self.error_code:
            error_dict["error_code"] = self.error_code
        
        return error_dict

def handle_api_error(error):
    """Handle API errors"""
    if isinstance(error, APIError):
        logger.warning(f"API Error: {error.message} (Status: {error.status_code})")
        return error.to_dict(), error.status_code
    
    # Log unexpected errors
    logger.error(f"Unexpected error: {str(error)}")
    logger.error(traceback.format_exc())
    
    return {
        "error": "An unexpected error occurred",
        "status_code": 500
    }, 500

def validate_request_data(required_fields, data):
    """Validate request data has required fields"""
    missing_fields = []
    
    for field in required_fields:
        if field not in data or data[field] in [None, ""]:
            missing_fields.append(field)
    
    if missing_fields:
        raise APIError(f"Missing required fields: {', '.join(missing_fields)}", 400)
    
    return True

def check_resource_exists(collection, query, resource_name):
    """Check if resource exists"""
    result = collection.find_one(query)
    if not result:
        raise APIError(f"{resource_name} not found", 404)
    return result

def handle_database_error(error):
    """Handle database errors"""
    logger.error(f"Database error: {str(error)}")
    raise APIError("Database operation failed", 500, "DB_ERROR")

def handle_external_api_error(service_name, error):
    """Handle external API errors"""
    logger.error(f"{service_name} API error: {str(error)}")
    raise APIError(f"{service_name} service unavailable", 503, "EXT_API_ERROR")

def log_and_raise(error_message, status_code=500):
    """Log error and raise APIError"""
    logger.error(error_message)
    raise APIError(error_message, status_code)
