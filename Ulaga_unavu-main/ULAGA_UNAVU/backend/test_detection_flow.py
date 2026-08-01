import os
import sys
import json
import numpy as np
import tensorflow as tf
from pathlib import Path

# Add backend to path
sys.path.append(os.getcwd())

from api.disease.detection import get_disease_detector

def test_full_detection_flow():
    detector = get_disease_detector()
    
    # Create two different dummy images (random noise)
    img1 = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
    img2 = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
    
    import io
    from PIL import Image
    
    def to_bytes(arr):
        img = Image.fromarray(arr)
        bio = io.BytesIO()
        img.save(bio, format='JPEG')
        return bio.getvalue()
        
    bytes1 = to_bytes(img1)
    bytes2 = to_bytes(img2)
    
    print("--- Test 1 (Random Image A) ---")
    res1 = detector.detect(user_id="Agri_Test", image_bytes=bytes1)
    print(f"Result: {res1.get('disease_name')} (Confidence: {res1.get('confidence')})")
    
    print("\n--- Test 2 (Random Image B) ---")
    res2 = detector.detect(user_id="Agri_Test", image_bytes=bytes2)
    print(f"Result: {res2.get('disease_name')} (Confidence: {res2.get('confidence')})")
    
    if res1.get('confidence') == res2.get('confidence'):
        print("\nCRITICAL: BOTH TESTS GAVE IDENTICAL CONFIDENCE!")
    else:
        print("\nSUCCESS: Predictions varied between images.")

if __name__ == "__main__":
    test_full_detection_flow()
