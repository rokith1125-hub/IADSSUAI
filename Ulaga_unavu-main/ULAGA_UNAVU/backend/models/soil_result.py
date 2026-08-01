"""
Soil result model for MongoDB
"""

from datetime import datetime

soil_result_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "soil_name", "created_at"],
        "properties": {
            "user_id": {
                "bsonType": "string",
                "description": "User ID (Agri_1, Agri_2, ...)"
            },
            "soil_name": {
                "bsonType": "string",
                "description": "Name of the soil type"
            },
            "tamil_name": {
                "bsonType": "string",
                "description": "Soil name in Tamil"
            },
            "confidence": {
                "bsonType": ["double", "int", "string"],
                "minimum": 0,
                "maximum": 1,
                "description": "Confidence score (0-1) or 'Manual'"
            },
            "analysis_method": {
                "bsonType": "string",
                "enum": ["CNN", "Manual"],
                "description": "Method used for analysis"
            },
            "soil_properties": {
                "bsonType": "object",
                "properties": {
                    "hardness": {
                        "bsonType": "string",
                        "enum": ["Very Soft", "Soft", "Medium", "Hard", "Very Hard"]
                    },
                    "fertility": {
                        "bsonType": "string",
                        "enum": ["Very Low", "Low", "Medium", "High", "Very High"]
                    },
                    "water_retention": {
                        "bsonType": "string",
                        "enum": ["Very Low", "Low", "Medium", "High", "Very High"]
                    },
                    "drainage": {
                        "bsonType": "string",
                        "enum": ["Poor", "Fair", "Good", "Excellent"]
                    },
                    "ph_range": {
                        "bsonType": "string",
                        "description": "pH range (e.g., '5.5-7.0')"
                    },
                    "suitable_crops": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "color": {
                        "bsonType": "string",
                        "description": "Soil color hex code"
                    },
                    "region": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    }
                }
            },
            "explanation": {
                "bsonType": "object",
                "properties": {
                    "summary": {"bsonType": "string"},
                    "dos": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "donts": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "practices": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    }
                }
            },
            "recommendations": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "properties": {
                        "type": {"bsonType": "string"},
                        "action": {"bsonType": "string"},
                        "priority": {
                            "bsonType": "string",
                            "enum": ["Low", "Medium", "High"]
                        }
                    }
                }
            },
            "image_url": {
                "bsonType": "string",
                "description": "URL of soil image (if uploaded)"
            },
            "result_summary": {
                "bsonType": "string",
                "description": "One-line summary of result"
            },
            "created_at": {
                "bsonType": "date",
                "description": "Analysis timestamp"
            },
            "updated_at": {
                "bsonType": "date",
                "description": "Last update timestamp"
            },
            "is_active": {
                "bsonType": "bool",
                "description": "Whether this result is currently active"
            }
        }
    }
}

# Helper functions
def create_soil_result(user_id, soil_name, confidence, analysis_method, soil_properties, explanation=None):
    """Create a soil result document"""
    return {
        "user_id": user_id,
        "soil_name": soil_name,
        "confidence": confidence,
        "analysis_method": analysis_method,
        "soil_properties": soil_properties,
        "explanation": explanation or {},
        "result_summary": f"{soil_name} soil analyzed with {confidence:.1%} confidence",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True
    }

def validate_soil_result(data):
    """Validate soil result data"""
    required_fields = ["user_id", "soil_name", "soil_properties"]
    
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
    
    # Validate soil properties
    required_props = ["hardness", "fertility", "water_retention", "drainage"]
    soil_props = data.get("soil_properties", {})
    
    for prop in required_props:
        if prop not in soil_props:
            return False, f"Missing soil property: {prop}"
    
    return True, "Valid"