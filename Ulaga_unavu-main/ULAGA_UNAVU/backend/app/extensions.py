"""
Extensions initialization for Flask app
Uses Firebase for auth, Local JSON storage for data
"""

import logging
import os

logger = logging.getLogger(__name__)

# Global storage instance
_local_storage = None

def init_extensions(app):
    """Initialize all Flask extensions"""
    global _local_storage
    
    # Initialize Local Storage
    try:
        from services.local_storage import LocalStorageService
        data_dir = os.getenv('DATA_DIR', app.config.get('DATA_DIR', 'data'))
        _local_storage = LocalStorageService(data_dir)
        logger.info(f"Local JSON Storage initialized - Data directory: {data_dir}")
    except Exception as e:
        logger.error(f"Local storage initialization failed: {str(e)}")
    
    logger.info("Extensions initialized")

def get_storage():
    """Get local storage instance"""
    global _local_storage
    
    if _local_storage is None:
        try:
            from services.local_storage import LocalStorageService
            data_dir = os.getenv('DATA_DIR', 'data')
            _local_storage = LocalStorageService(data_dir)
        except Exception as e:
            logger.error(f"Storage initialization failed: {str(e)}")
            return None
    
    return _local_storage

# Backward compatibility aliases
def get_local_storage():
    """Alias for get_storage()"""
    return get_storage()

