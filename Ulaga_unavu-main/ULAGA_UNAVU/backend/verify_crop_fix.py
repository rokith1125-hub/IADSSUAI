
import requests
import json
import time
import jwt

BASE_URL = "http://127.0.0.1:5000/api"
USER_ID = "Agri_1" # Existing user from data/users.json
JWT_SECRET = "ulaga-unavu-jwt-secret-2024"

def generate_token(user_id):
    payload = {
        "user_id": user_id,
        "email": "testuser@example.com",
        "exp": int(time.time()) + 3600
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def test_crop_fix():
    print("=" * 60)
    print("ULAGA_UNAVU - Crop Recommendation Fix Verification")
    print("=" * 60)

    token = generate_token(USER_ID)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Manual Soil Analysis
    print("\n[1] Performing Manual Soil Analysis (Black Soil)...")
    payload = {
        "user_id": USER_ID,
        "soil_name": "Black Soil",
        "lang": "en"
    }
    resp = requests.post(f"{BASE_URL}/soil/analyze-manual", json=payload, headers=headers)
    if resp.status_code != 200:
        print(f"FAILED: Manual analysis returned {resp.status_code}")
        print(resp.text)
        return

    full_resp = resp.json()
    # The response is like: {"success": true, "data": {"result": {...}}, "message": "..."}
    data_payload = full_resp.get('data', {})
    result_obj = data_payload.get('result', {})
    
    result_id = result_obj.get('result_id')
    suitable_crops = result_obj.get('suitable_crops')
    
    if result_id:
        print(f"    Success: result_id={result_id}")
    else:
        print(f"    FAILED: result_id missing in response")
        print(json.dumps(full_resp, indent=2))
        return

    if suitable_crops and isinstance(suitable_crops, list) and len(suitable_crops) > 0:
        print(f"    Success: persisted suitable_crops={suitable_crops}")
    else:
        print(f"    FAILED: suitable_crops missing or empty in result object")
        print(json.dumps(result_obj, indent=2))
        return

    # 2. Get Recommendations
    print("\n[2] Fetching Crop Recommendations...")
    params = {
        "soil_result_id": result_id,
        "user_id": USER_ID,
        "lang": "en"
    }
    resp = requests.get(f"{BASE_URL}/crop/recommend", params=params, headers=headers)
    
    if resp.status_code != 200:
        print(f"FAILED: Recommendation returned {resp.status_code}")
        print(resp.text)
        return

    full_recs_resp = resp.json()
    # The recommender returns the list directly or wrapped in data?
    # endpoints.py: return recommendations (a list)
    recs = full_recs_resp
    
    if not isinstance(recs, list):
         print(f"    FAILED: Expected list of recommendations, got {type(recs)}")
         print(json.dumps(recs, indent=2))
         return

    print(f"    Success: Received {len(recs)} recommendations")
    
    # Check if any have "selection_method": "adaptive_ai" (dataset match)
    methods = [r.get('selection_method') for r in recs]
    print(f"    Methods used: {set(methods)}")
    
    if "adaptive_ai" in methods:
        print("    Success: Dataset-based recommendations generated (Adaptive AI)")
    else:
        print("    WARNING: No dataset-based recommendations. Checked LLM fallback?")
        methods_list = list(set(methods))
        if "llm_fallback" in methods_list:
             print("    Detected LLM Fallback (Check if LLM keys are valid if this was expected)")

    print("\n" + "=" * 60)
    print("Verification complete!")
    print("=" * 60)

if __name__ == "__main__":
    test_crop_fix()
