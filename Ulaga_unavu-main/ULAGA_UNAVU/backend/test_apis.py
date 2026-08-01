#!/usr/bin/env python3
"""
ULAGA_UNAVU Backend API Testing Script
Tests all endpoints to ensure they work properly
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:5000"

def test_health():
    """Test health endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/api/health")
        print(f"Health Check: {response.status_code}")
        if response.status_code == 200:
            print("✅ Health endpoint working")
            return True
        else:
            print("❌ Health endpoint failed")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_auth_endpoints():
    """Test auth endpoints"""
    print("\n--- Testing Auth Endpoints ---")

    # Test signup
    signup_data = {
        "email": "test@example.com",
        "password": "testpass123",
        "confirm_password": "testpass123"
    }

    try:
        response = requests.post(f"{BASE_URL}/api/auth/signup", json=signup_data)
        print(f"Signup: {response.status_code}")
        if response.status_code in [200, 201]:
            print("✅ Signup endpoint working")
        else:
            print(f"❌ Signup failed: {response.text}")
    except Exception as e:
        print(f"❌ Signup error: {e}")

def test_soil_endpoints():
    """Test soil endpoints"""
    print("\n--- Testing Soil Endpoints ---")

    # Test soil types
    try:
        response = requests.get(f"{BASE_URL}/api/soil/types")
        print(f"Soil Types: {response.status_code}")
        if response.status_code == 200:
            print("✅ Soil types endpoint working")
        else:
            print(f"❌ Soil types failed: {response.text}")
    except Exception as e:
        print(f"❌ Soil types error: {e}")

def test_crop_endpoints():
    """Test crop endpoints"""
    print("\n--- Testing Crop Endpoints ---")

    # Test crop types
    try:
        response = requests.get(f"{BASE_URL}/api/crop/types")
        print(f"Crop Types: {response.status_code}")
        if response.status_code == 200:
            print("✅ Crop types endpoint working")
        else:
            print(f"❌ Crop types failed: {response.text}")
    except Exception as e:
        print(f"❌ Crop types error: {e}")

def test_weather_endpoints():
    """Test weather endpoints"""
    print("\n--- Testing Weather Endpoints ---")

    # Test weather
    try:
        response = requests.get(f"{BASE_URL}/api/weather/current?location=Chennai")
        print(f"Weather: {response.status_code}")
        if response.status_code == 200:
            print("✅ Weather endpoint working")
        else:
            print(f"❌ Weather failed: {response.text}")
    except Exception as e:
        print(f"❌ Weather error: {e}")

def test_news_endpoints():
    """Test news endpoints"""
    print("\n--- Testing News Endpoints ---")

    # Test news
    try:
        response = requests.get(f"{BASE_URL}/api/news/today")
        print(f"News: {response.status_code}")
        if response.status_code == 200:
            print("✅ News endpoint working")
        else:
            print(f"❌ News failed: {response.text}")
    except Exception as e:
        print(f"❌ News error: {e}")

def test_market_endpoints():
    """Test market endpoints"""
    print("\n--- Testing Market Endpoints ---")

    # Test market prices
    try:
        response = requests.get(f"{BASE_URL}/api/market/prices?crop=rice&location=Chennai")
        print(f"Market Prices: {response.status_code}")
        if response.status_code == 200:
            print("✅ Market prices endpoint working")
        else:
            print(f"❌ Market prices failed: {response.text}")
    except Exception as e:
        print(f"❌ Market prices error: {e}")

def main():
    """Run all tests"""
    print("🚀 Starting ULAGA_UNAVU Backend API Tests")
    print("=" * 50)

    # Wait for server to be ready
    time.sleep(2)

    tests = [
        test_health,
        test_auth_endpoints,
        test_soil_endpoints,
        test_crop_endpoints,
        test_weather_endpoints,
        test_news_endpoints,
        test_market_endpoints
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1

    print("\n" + "=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Backend is ready.")
    else:
        print("⚠️ Some tests failed. Check the logs above.")

if __name__ == "__main__":
    main()
