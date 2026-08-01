import os
import json
import numpy as np
import tensorflow as tf
from pathlib import Path

def debug_disease_model():
    # Use absolute paths
    base_dir = Path(r"c:\Users\Murasolimaran\OneDrive\Desktop\Ungal_nanban\ULAGA_UNAVU\backend")
    model_path = base_dir / "ai_models" / "disease_cnn.h5"
    config_path = base_dir / "ai_models" / "disease_cnn.json"
    
    print(f"--- Model Debug Report ---")
    print(f"Model Path: {model_path} (Exists: {model_path.exists()})")
    print(f"Config Path: {config_path} (Exists: {config_path.exists()})")
    
    if not model_path.exists():
        print("ERROR: Model file missing")
        return
        
    try:
        # Load labels
        with open(config_path, 'r') as f:
            labels = json.load(f)
        print(f"Labels loaded: {len(labels)} classes")
        
        # Load model metadata only first if possible, or just load model
        print("Loading model (this may take a moment)...")
        model = tf.keras.models.load_model(str(model_path), compile=False)
        
        input_shape = model.input_shape
        output_shape = model.output_shape
        print(f"Model Input Shape: {input_shape}")
        print(f"Model Output Shape: {output_shape}")
        
        # check if labels match output shape
        if len(labels) != output_shape[-1]:
            print(f"CRITICAL MISMATCH: JSON has {len(labels)} labels, but Model has {output_shape[-1]} outputs!")
        else:
            print(f"CONFIRMED: JSON and Model labels count match ({len(labels)})")
            
        # Test with random noise to see if it's biased towards index 11 (Grape Black Rot)
        print("\nTesting with 10 random inputs...")
        predictions_history = []
        for i in range(10):
            dummy_input = np.random.rand(1, input_shape[1], input_shape[2], 3).astype(np.float32)
            preds = model.predict(dummy_input, verbose=0)
            idx = np.argmax(preds[0])
            conf = preds[0][idx]
            label = labels.get(str(idx), "Unknown")
            print(f"Test {i+1}: Predicted Index {idx} ({label}) with {conf*100:.2f}% confidence")
            predictions_history.append(idx)
            
        if all(x == predictions_history[0] for x in predictions_history):
            print(f"\nWARNING: Model predicted the SAME index ({predictions_history[0]}) for all 10 random inputs.")
            print("This suggests the model might be collapsed or require specific normalization.")
        else:
            print("\nModel produces varied outputs for random noise.")

    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    debug_disease_model()
