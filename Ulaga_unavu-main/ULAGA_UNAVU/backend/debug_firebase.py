import os
import sys

print(f"Python executable: {sys.executable}")
print(f"Current working directory: {os.getcwd()}")

try:
    import firebase_admin
    from firebase_admin import credentials
    print("✅ firebase-admin imported successfully")
except ImportError as e:
    print(f"❌ Failed to import firebase-admin: {e}")
    sys.exit(1)

# Replicate path logic
SERVICE_ACCOUNT_FILE = "ulagaunavu-firebase-adminsdk-fbsvc-7195d378c3.json"
# We are currently in backend/, so we don't need the complex path logic if we run from here
# But let's replicate the app's logic assuming this file is in app/
backend_dir = os.getcwd()
json_path = os.path.join(backend_dir, SERVICE_ACCOUNT_FILE)

print(f"Looking for JSON at: {json_path}")
if os.path.exists(json_path):
    print("✅ JSON file found")
    try:
        cred = credentials.Certificate(json_path)
        print("✅ Credentials object created successfully from JSON")
    except Exception as e:
        print(f"❌ Failed to create credentials from JSON: {e}")
else:
    print("❌ JSON file NOT found")

# Check .env
from dotenv import load_dotenv
load_dotenv()

p_key = os.getenv('FIREBASE_PRIVATE_KEY')
if p_key:
    print("✅ FIREBASE_PRIVATE_KEY found in env")
    # mimicking formatting
    formatted_key = p_key.replace('\\n', '\n')
    print(f"Key starts with: {formatted_key[:30]}...")
    
    try:
        firebase_config = {
            "type": "service_account",
            "project_id": os.getenv('FIREBASE_PROJECT_ID'),
            "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
            "private_key": formatted_key,
            "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
            "client_id": os.getenv('FIREBASE_CLIENT_ID'),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_X509_CERT_URL')
        }
        cred_env = credentials.Certificate(firebase_config)
        print("✅ Credentials object created successfully from ENV")
    except Exception as e:
        print(f"❌ Failed to create credentials from ENV: {e}")
else:
    print("❌ FIREBASE_PRIVATE_KEY NOT found in env")
