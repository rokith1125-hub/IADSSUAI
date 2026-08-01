import os
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.append(os.getcwd())

def verify_all_mappings():
    # Use absolute paths
    base_dir = Path(r"c:\Users\Murasolimaran\OneDrive\Desktop\Ungal_nanban\ULAGA_UNAVU\backend")
    cnn_json_path = base_dir / "ai_models" / "disease_cnn.json"
    dataset_path = base_dir / "datasets" / "disease_data.json"
    
    with open(cnn_json_path, 'r') as f:
        cnn_labels = json.load(f)
        
    with open(dataset_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)
        
    dataset_names = {d['disease_name'].lower() for d in dataset}
    
    # We need to initialize the detector to use its mapping logic
    from api.disease.detection import get_disease_detector
    detector = get_disease_detector()
    
    print(f"--- Mapping Verification Report ---")
    print(f"Total CNN Labels: {len(cnn_labels)}")
    
    missing = []
    for idx, raw_label in cnn_labels.items():
        # Simulate mapping
        mapped = detector._map_cnn_class_to_dataset(raw_label, raw_label)
        if mapped:
            print(f"Index {idx:2}: {raw_label:50} -> {mapped.get('disease_name')}")
        else:
            print(f"Index {idx:2}: {raw_label:50} -> MISSING! (Threshold Blocked)")
            missing.append(raw_label)
            
    print(f"\nSummary:")
    print(f"Successfully mapped: {len(cnn_labels) - len(missing)}/{len(cnn_labels)}")
    if missing:
        print(f"Missing mappings: {len(missing)}")
        for m in missing:
            print(f" - {m}")
    else:
        print("PERFECT: All labels map correctly to dataset!")

if __name__ == "__main__":
    verify_all_mappings()
