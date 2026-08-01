"""
Crop selection model for MongoDB
"""

from datetime import datetime

crop_selection_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "crop_name", "selected_at"],
        "properties": {
            "user_id": {
                "bsonType": "string",
                "description": "User ID (Agri_1, Agri_2, ...)"
            },
            "crop_name": {
                "bsonType": "string",
                "description": "Name of the selected crop"
            },
            "tamil_name": {
                "bsonType": "string",
                "description": "Crop name in Tamil"
            },
            "scientific_name": {
                "bsonType": "string",
                "description": "Scientific name of the crop"
            },
            "selection_method": {
                "bsonType": "string",
                "enum": ["Recommended", "Custom", "Manual"],
                "description": "How the crop was selected"
            },
            "recommendation_score": {
                "bsonType": ["double", "int"],
                "minimum": 0,
                "maximum": 100,
                "description": "Suitability score if recommended"
            },
            "crop_details": {
                "bsonType": "object",
                "properties": {
                    "growing_season": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "season_months": {
                        "bsonType": "string",
                        "description": "Month range for cultivation"
                    },
                    "soil_compatibility": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "water_requirement": {
                        "bsonType": "string",
                        "enum": ["Very Low", "Low", "Medium", "High", "Very High"]
                    },
                    "growth_days": {
                        "bsonType": "int",
                        "minimum": 30,
                        "maximum": 365
                    },
                    "temperature_range": {
                        "bsonType": "string",
                        "description": "Optimal temperature range"
                    },
                    "rainfall_needed": {
                        "bsonType": "string",
                        "description": "Required rainfall"
                    },
                    "yield_per_acre": {
                        "bsonType": "string",
                        "description": "Expected yield"
                    },
                    "market_price_range": {
                        "bsonType": "string",
                        "description": "Typical market price range"
                    },
                    "risk_level": {
                        "bsonType": "string",
                        "enum": ["Low", "Medium", "High"]
                    },
                    "special_notes": {
                        "bsonType": "string",
                        "description": "Special considerations"
                    }
                }
            },
            "growth_timeline": {
                "bsonType": "object",
                "properties": {
                    "start_date": {"bsonType": "date"},
                    "expected_end_date": {"bsonType": "date"},
                    "current_stage": {"bsonType": "string"},
                    "progress_percent": {
                        "bsonType": ["double", "int"],
                        "minimum": 0,
                        "maximum": 100
                    }
                }
            },
            "image_url": {
                "bsonType": "string",
                "description": "URL of crop image"
            },
            "explanation": {
                "bsonType": "object",
                "properties": {
                    "why_suitable": {"bsonType": "string"},
                    "benefits": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "risks": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "special_requirements": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    }
                }
            },
            "fertilizer_plan_id": {
                "bsonType": "string",
                "description": "Reference to fertilizer plan"
            },
            "selected_at": {
                "bsonType": "date",
                "description": "When crop was selected"
            },
            "is_active": {
                "bsonType": "bool",
                "description": "Whether this is the current active crop"
            },
            "harvested": {
                "bsonType": "bool",
                "description": "Whether crop has been harvested"
            },
            "harvest_date": {
                "bsonType": "date",
                "description": "Actual harvest date"
            },
            "notes": {
                "bsonType": "string",
                "description": "Additional farmer notes"
            }
        }
    }
}

def create_crop_selection(user_id, crop_name, selection_method="Recommended", crop_details=None):
    """Create a crop selection document"""
    return {
        "user_id": user_id,
        "crop_name": crop_name,
        "selection_method": selection_method,
        "crop_details": crop_details or {},
        "growth_timeline": {
            "start_date": datetime.utcnow(),
            "current_stage": "Planning",
            "progress_percent": 0
        },
        "selected_at": datetime.utcnow(),
        "is_active": True,
        "harvested": False,
        "notes": ""
    }

def update_crop_progress(crop_selection, progress_percent, current_stage):
    """Update crop progress"""
    crop_selection["growth_timeline"]["progress_percent"] = progress_percent
    crop_selection["growth_timeline"]["current_stage"] = current_stage
    crop_selection["growth_timeline"]["updated_at"] = datetime.utcnow()
    return crop_selection

def mark_as_harvested(crop_selection, harvest_date=None):
    """Mark crop as harvested"""
    crop_selection["harvested"] = True
    crop_selection["harvest_date"] = harvest_date or datetime.utcnow()
    crop_selection["is_active"] = False
    crop_selection["growth_timeline"]["progress_percent"] = 100
    crop_selection["growth_timeline"]["current_stage"] = "Harvested"
    return crop_selection