"""
User model schema for MongoDB
"""

from datetime import datetime

user_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "firebase_uid", "email", "name"],
        "properties": {
            "user_id": {
                "bsonType": "string",
                "description": "Unique user ID (Agri_1, Agri_2, ...)"
            },
            "firebase_uid": {
                "bsonType": "string",
                "description": "Firebase authentication UID"
            },
            "email": {
                "bsonType": "string",
                "description": "User email address"
            },
            "name": {
                "bsonType": "string",
                "description": "User's full name"
            },
            "phone": {
                "bsonType": "string",
                "description": "Phone number (optional)"
            },
            "role": {
                "bsonType": "string",
                "enum": ["user", "admin", "expert"],
                "description": "User role"
            },
            "farm_info": {
                "bsonType": "object",
                "properties": {
                    "district": {"bsonType": "string"},
                    "state": {"bsonType": "string"},
                    "farm_size": {"bsonType": "string"},
                    "soil_type": {"bsonType": "string"},
                    "irrigation_type": {"bsonType": "string"}
                }
            },
            "settings": {
                "bsonType": "object",
                "properties": {
                    "language": {"bsonType": "string"},
                    "notifications": {"bsonType": "bool"},
                    "theme": {"bsonType": "string"},
                    "units": {"bsonType": "string"}
                }
            },
            "is_active": {
                "bsonType": "bool",
                "description": "Account active status"
            },
            "created_at": {
                "bsonType": "date",
                "description": "Account creation date"
            },
            "updated_at": {
                "bsonType": "date",
                "description": "Last update date"
            },
            "last_login": {
                "bsonType": "date",
                "description": "Last login timestamp"
            }
        }
    }
}