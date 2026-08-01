"""
Compatibility wrapper for model loader access from services namespace.
"""

from ai_models.model_loader import ModelLoader, ModelNotAvailableError, get_model_loader

__all__ = ["ModelLoader", "ModelNotAvailableError", "get_model_loader"]
