import requests
import json
import time
import concurrent.futures
import sys
import jwt

BASE_URL = "http://127.0.0.1:5000"
USER_ID = "Agri_1" # Default test user
SECRET = "ulaga-unavu-jwt-secret-2024"

def generate_token(user_id):
    payload = {
        "user_id": user_id,
        "email": "test@example.com",
        "exp": time.time() + 3600
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")

AUTH_TOKEN = generate_token(USER_ID)

def test_soil_analysis_and_retrieval():
    print("\n--- Testing Soil Analysis and Retrieval ---")
    
    # 1. Manual analysis
    url = f"{BASE_URL}/api/soil/analyze-manual"
    payload = {"soil_name": "Black", "lang": "en"}
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            print(f"FAILED: Initial analysis. Status: {response.status_code}, Body: {response.text}")
            return None
        
        result = response.json()
        # The API returns 'analysis_id' in data
        analysis_id = result.get("data", {}).get("analysis_id")
        if not analysis_id:
             analysis_id = result.get("data", {}).get("result", {}).get("result_id")
             
        print(f"SUCCESS: Created analysis with ID: {analysis_id}")
        
        # 2. Retrieve the result
        result_url = f"{BASE_URL}/api/soil/result/{analysis_id}"
        get_response = requests.get(result_url, headers=headers)
        if get_response.status_code != 200:
            print(f"FAILED: Retrieving analysis {analysis_id}. Status: {get_response.status_code}")
            return None
        
        print(f"SUCCESS: Retrieved analysis {analysis_id}")
        return analysis_id
    except Exception as e:
        print(f"ERROR in soil test: {e}")
        return None

def test_crop_recommendation(soil_result_id):
    if not soil_result_id:
        return
    
    print("\n--- Testing Crop Recommendation ---")
    url = f"{BASE_URL}/api/crop/recommend"
    params = {"soil_result_id": soil_result_id, "lang": "en"}
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json().get("data", {})
            recs = data.get("recommendations", [])
            print(f"SUCCESS: Crop recommendation fetched successfully. Found {len(recs)} Suggestions.")
        else:
            print(f"FAILED: Crop recommendation. Status: {response.status_code}, Body: {response.text}")
    except Exception as e:
        print(f"ERROR in crop test: {e}")

def pressure_test_storage():
    print("\n--- Pressure Testing Storage for Data Loss (Parallel Writes) ---")
    url = f"{BASE_URL}/api/soil/analyze-manual"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    def send_request(i):
        # alternate soils
        soil = "Red" if i % 2 == 0 else "Alluvial"
        resp = requests.post(url, json={"soil_name": soil}, headers=headers)
        return resp.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(send_request, range(10)))
    
    success_count = results.count(200)
    print(f"Parallel Write Results: {success_count}/10 successful.")
    
    history_url = f"{BASE_URL}/api/soil/history"
    hist_resp = requests.get(history_url, headers=headers)
    if hist_resp.status_code == 200:
        history = hist_resp.json().get("data", {}).get("history", [])
        print(f"History verification: {len(history)} items present.")
    else:
        print(f"FAILED: History check. Status: {hist_resp.status_code}")

if __name__ == "__main__":
    sid = test_soil_analysis_and_retrieval()
    if sid:
        test_crop_recommendation(sid)
        pressure_test_storage()
    else:
        print("Initial test failed. Check server logs.")
