import os

def get_backend_root():
    """
    Get the absolute path to the backend directory.
    This works regardless of where the script is launched from.
    """
    # This file is in backend/utils/, so its parent's parent is backend/
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def get_dataset_path(filename):
    """
    Get the absolute path to a dataset file in the backend/datasets/ directory.
    """
    return os.path.join(get_backend_root(), 'datasets', filename)

def get_model_path(filename, model_type=None):
    """
    Get the absolute path to an AI model file.
    """
    if model_type:
        return os.path.join(get_backend_root(), 'ai_models', model_type, filename)
    return os.path.join(get_backend_root(), 'ai_models', filename)
