import sys
import os
import requests
import random
import string

BASE_URL = "http://127.0.0.1:5000"

def get_random_string(length=6):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

def run_simulation():
    print("Starting Full Farmer Journey Simulation (Live HTTP Test)...")
    
    # Check health first
    try:
        health = requests.get(f"{BASE_URL}/healthz")
        if health.status_code != 200:
            print("Server not ready!")
            return
        print("Server Health: OK")
    except Exception as e:
        print(f"Failed to connect to server: {e}")
        return

    # 1. Registration
    print("\n[Step 1] User Registration")
    rand_suffix = get_random_string()
    reg_data = {
        "email": f"farmer_sim_{rand_suffix}@example.com",
        "password": "Password123!",
        "name": f"Simulated Farmer {rand_suffix}"
    }
    response = requests.post(f"{BASE_URL}/api/auth/local-register", json=reg_data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    # If 400 (already exists), try login
    res_json = response.json() if response.status_code == 200 else {}
    if not res_json:
        login_data = {"email": reg_data["email"], "password": "Password123!"}
        response = requests.post(f"{BASE_URL}/api/auth/local-login", json=login_data)
        print(f"Login Response: {response.text}")
        res_json = response.json() if response.status_code == 200 else {}
        
    token = res_json.get("token", "") or res_json.get("access_token", "")
    user = res_json.get("user", {})
    user_id = user.get("user_id", "Agri_1")
    
    print(f"User ID: {user_id}, Got Token: {'Yes' if token else 'No'}")
    
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # 2. Soil Analysis Simulation
    print("\n[Step 2] Soil Analysis Check")
    response = requests.get(f"{BASE_URL}/api/soil/model-status", headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Soil Service Availability: {response.json()}")

    # 3. Smart Mandi Check
    print("\n[Step 3] Smart Mandi Price Check")
    response = requests.get(f"{BASE_URL}/api/smart-mandi/snapshot?crop=Tomato", headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        res_data = response.json()
        prices = res_data.get("prices", [])
        if prices:
            print(f"Top Price: {prices[0].get('modal_price')} at {prices[0].get('market')}")
            # Verify sorting
            if len(prices) > 1:
                is_sorted = float(prices[0].get('modal_price', 0)) >= float(prices[-1].get('modal_price', 0))
                print(f"Is Sorted High->Low: {is_sorted}")
        else:
            print("No prices returned.")
    else:
        print(f"Error: {response.text}")

    # 4. Chatbot Interaction
    print("\n[Step 4] Chatbot Advice")
    chat_data = {
        "message": "Ennoda tomato sedi la karuppu pulli iruku, enna panradhu?",
        "user_id": user_id,
        "language": "mixed"
    }
    response = requests.post(f"{BASE_URL}/api/chatbot/ask", json=chat_data, headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        resp_text = response.json().get('response', '')
        snippet = resp_text[:100] + "..." if len(resp_text) > 100 else resp_text
        print(f"Bot Response Snippet: {snippet}")
    else:
         print(f"Error: {response.text}")

    print("\nSimulation Complete!")

if __name__ == "__main__":
    run_simulation()
