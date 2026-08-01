import os
import sys
import json
import numpy as np
import tensorflow as tf
from pathlib import Path

# Add backend to path
sys.path.append(os.getcwd())

from services.cnn_service import get_cnn_service

def test_real_image_prediction():
    cnn = get_cnn_service()
    img_path = r"c:\Users\Murasolimaran\OneDrive\Desktop\Ungal_nanban\ULAGA_UNAVU\backend\sample_image\test_blueberry_healthy.jpg"
    
    print(f"--- Testing Real Image: {img_path} ---")
    res = cnn.predict_disease(image_path=img_path)
    
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    test_real_image_prediction()
