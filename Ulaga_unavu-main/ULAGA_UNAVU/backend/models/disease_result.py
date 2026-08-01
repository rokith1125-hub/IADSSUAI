"""
Disease result model for MongoDB
"""

from datetime import datetime

disease_result_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "disease_name", "created_at"],
        "properties": {
            "user_id": {
                "bsonType": "string",
                "description": "User ID (Agri_1, Agri_2, ...)"
            },
            "disease_name": {
                "bsonType": "string",
                "description": "Name of the detected disease"
            },
            "tamil_name": {
                "bsonType": "string",
                "description": "Disease name in Tamil"
            },
            "scientific_name": {
                "bsonType": "string",
                "description": "Scientific name of disease/pathogen"
            },
            "affected_crop": {
                "bsonType": "string",
                "description": "Crop affected by disease"
            },
            "confidence": {
                "bsonType": ["double", "int"],
                "minimum": 0,
                "maximum": 1,
                "description": "Confidence score (0-1)"
            },
            "detection_method": {
                "bsonType": "string",
                "enum": ["CNN", "Manual"],
                "description": "Method used for detection"
            },
            "severity_level": {
                "bsonType": "string",
                "enum": ["Low", "Medium", "High", "Critical"],
                "description": "Severity of disease"
            },
            "symptoms": {
                "bsonType": "array",
                "items": {"bsonType": "string"},
                "description": "Observed symptoms"
            },
            "causes": {
                "bsonType": "array",
                "items": {"bsonType": "string"},
                "description": "Possible causes"
            },
            "treatment": {
                "bsonType": "object",
                "properties": {
                    "organic": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "chemical": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "prevention": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "safety_notes": {
                        "bsonType": "string",
                        "description": "Safety precautions"
                    }
                }
            },
            "weather_conditions": {
                "bsonType": "string",
                "description": "Weather that favors disease"
            },
            "risk_period": {
                "bsonType": "string",
                "description": "High-risk period for disease"
            },
            "spread_speed": {
                "bsonType": "string",
                "enum": ["Slow", "Moderate", "Rapid", "Very Rapid"]
            },
            "contagious": {
                "bsonType": "bool",
                "description": "Whether disease is contagious"
            },
            "plant_image_url": {
                "bsonType": "string",
                "description": "URL of affected plant image"
            },
            "weather_warning": {
                "bsonType": "string",
                "description": "Weather-based spraying warning"
            },
            "recommended_action": {
                "bsonType": "string",
                "description": "Immediate recommended action"
            },
            "consultation_advised": {
                "bsonType": "bool",
                "description": "Whether to consult agriculture officer"
            },
            "created_at": {
                "bsonType": "date",
                "description": "Detection timestamp"
            },
            "updated_at": {
                "bsonType": "date",
                "description": "Last update timestamp"
            },
            "treatment_applied": {
                "bsonType": "bool",
                "description": "Whether treatment was applied"
            },
            "treatment_date": {
                "bsonType": "date",
                "description": "When treatment was applied"
            },
            "treatment_notes": {
                "bsonType": "string",
                "description": "Notes about treatment"
            },
            "recovery_status": {
                "bsonType": "string",
                "enum": ["Not Treated", "In Progress", "Recovered", "Not Recovered"]
            },
            "is_active": {
                "bsonType": "bool",
                "description": "Whether this is an active disease case"
            }
        }
    }
}

def create_disease_result(user_id, disease_name, confidence, severity_level, affected_crop=None):
    """Create a disease result document"""
    return {
        "user_id": user_id,
        "disease_name": disease_name,
        "confidence": confidence,
        "severity_level": severity_level,
        "affected_crop": affected_crop,
        "detection_method": "CNN",
        "symptoms": [],
        "causes": [],
        "treatment": {
            "organic": [],
            "chemical": [],
            "prevention": []
        },
        "weather_conditions": "",
        "risk_period": "",
        "spread_speed": "Moderate",
        "contagious": True,
        "consultation_advised": severity_level in ["High", "Critical"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "treatment_applied": False,
        "recovery_status": "Not Treated",
        "is_active": True
    }

def mark_treatment_applied(disease_result, treatment_notes=""):
    """Mark treatment as applied"""
    disease_result["treatment_applied"] = True
    disease_result["treatment_date"] = datetime.utcnow()
    disease_result["treatment_notes"] = treatment_notes
    disease_result["recovery_status"] = "In Progress"
    disease_result["updated_at"] = datetime.utcnow()
    return disease_result

def update_recovery_status(disease_result, status, notes=""):
    """Update recovery status"""
    allowed_statuses = ["In Progress", "Recovered", "Not Recovered"]
    if status not in allowed_statuses:
        raise ValueError(f"Status must be one of: {allowed_statuses}")
    
    disease_result["recovery_status"] = status
    if notes:
        disease_result["treatment_notes"] = notes
    disease_result["updated_at"] = datetime.utcnow()
    
    if status == "Recovered":
        disease_result["is_active"] = False
    
    return disease_result