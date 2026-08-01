"""
Fertilizer schedule model for MongoDB
"""

from datetime import datetime, timedelta

fertilizer_schedule_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "crop_name", "schedule", "created_at"],
        "properties": {
            "user_id": {
                "bsonType": "string",
                "description": "User ID (Agri_1, Agri_2, ...)"
            },
            "crop_name": {
                "bsonType": "string",
                "description": "Crop for which schedule is created"
            },
            "soil_type": {
                "bsonType": "string",
                "description": "Soil type for which schedule is optimized"
            },
            "schedule": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["stage", "fertilizer", "date"],
                    "properties": {
                        "stage": {
                            "bsonType": "string",
                            "description": "Growth stage (e.g., 'Basal', 'Vegetative')"
                        },
                        "fertilizer": {
                            "bsonType": "string",
                            "description": "Fertilizer name/type"
                        },
                        "tamil_name": {
                            "bsonType": "string",
                            "description": "Fertilizer name in Tamil"
                        },
                        "date": {
                            "bsonType": "date",
                            "description": "Scheduled application date"
                        },
                        "actual_date": {
                            "bsonType": "date",
                            "description": "Actual application date"
                        },
                        "quantity": {
                            "bsonType": "string",
                            "description": "Recommended quantity (e.g., '100 kg/acre')"
                        },
                        "method": {
                            "bsonType": "string",
                            "enum": ["Basal", "Top Dressing", "Foliar", "Fertigation"]
                        },
                        "purpose": {
                            "bsonType": "string",
                            "description": "Purpose of application"
                        },
                        "best_time": {
                            "bsonType": "string",
                            "enum": ["Morning", "Evening", "Anytime"]
                        },
                        "weather_dependent": {
                            "bsonType": "bool",
                            "description": "Whether application depends on weather"
                        },
                        "safety_notes": {
                            "bsonType": "array",
                            "items": {"bsonType": "string"}
                        },
                        "status": {
                            "bsonType": "string",
                            "enum": ["Pending", "Applied", "Skipped", "Postponed"]
                        },
                        "notes": {
                            "bsonType": "string",
                            "description": "Farmer notes"
                        }
                    }
                }
            },
            "total_stages": {
                "bsonType": "int",
                "minimum": 1,
                "maximum": 10
            },
            "current_stage_index": {
                "bsonType": "int",
                "minimum": 0,
                "description": "Index of current stage in schedule"
            },
            "next_application": {
                "bsonType": "object",
                "properties": {
                    "date": {"bsonType": "date"},
                    "fertilizer": {"bsonType": "string"},
                    "days_until": {"bsonType": "int"}
                }
            },
            "weather_aware": {
                "bsonType": "bool",
                "description": "Whether schedule adjusts for weather"
            },
            "created_at": {
                "bsonType": "date",
                "description": "Schedule creation timestamp"
            },
            "updated_at": {
                "bsonType": "date",
                "description": "Last update timestamp"
            },
            "is_active": {
                "bsonType": "bool",
                "description": "Whether this is the active schedule"
            },
            "completed": {
                "bsonType": "bool",
                "description": "Whether all applications are completed"
            },
            "completion_date": {
                "bsonType": "date",
                "description": "When schedule was completed"
            },
            "performance_notes": {
                "bsonType": "string",
                "description": "Notes on fertilizer performance"
            }
        }
    }
}

def create_fertilizer_schedule(user_id, crop_name, soil_type, schedule_data):
    """Create a fertilizer schedule document"""
    # Calculate next application
    today = datetime.utcnow()
    next_app = None
    
    for stage in schedule_data:
        stage_date = stage.get("date")
        if stage_date and stage_date >= today:
            next_app = {
                "date": stage_date,
                "fertilizer": stage.get("fertilizer"),
                "days_until": (stage_date - today).days
            }
            break
    
    return {
        "user_id": user_id,
        "crop_name": crop_name,
        "soil_type": soil_type,
        "schedule": schedule_data,
        "total_stages": len(schedule_data),
        "current_stage_index": 0,
        "next_application": next_app,
        "weather_aware": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
        "completed": False,
        "performance_notes": ""
    }

def mark_application_completed(schedule, stage_index, actual_date=None, notes=""):
    """Mark a fertilizer application as completed"""
    if 0 <= stage_index < len(schedule["schedule"]):
        schedule["schedule"][stage_index]["status"] = "Applied"
        schedule["schedule"][stage_index]["actual_date"] = actual_date or datetime.utcnow()
        if notes:
            schedule["schedule"][stage_index]["notes"] = notes
        
        # Update current stage index
        schedule["current_stage_index"] = stage_index + 1
        
        # Update next application
        today = datetime.utcnow()
        next_app = None
        
        for i in range(schedule["current_stage_index"], len(schedule["schedule"])):
            stage = schedule["schedule"][i]
            stage_date = stage.get("date")
            if stage_date and stage_date >= today:
                next_app = {
                    "date": stage_date,
                    "fertilizer": stage.get("fertilizer"),
                    "days_until": (stage_date - today).days
                }
                break
        
        schedule["next_application"] = next_app
        
        # Check if all completed
        all_completed = all(
            stage.get("status") == "Applied" 
            for stage in schedule["schedule"]
        )
        
        if all_completed:
            schedule["completed"] = True
            schedule["completion_date"] = datetime.utcnow()
            schedule["is_active"] = False
        
        schedule["updated_at"] = datetime.utcnow()
    
    return schedule

def postpone_application(schedule, stage_index, new_date, reason=""):
    """Postpone a fertilizer application"""
    if 0 <= stage_index < len(schedule["schedule"]):
        schedule["schedule"][stage_index]["status"] = "Postponed"
        schedule["schedule"][stage_index]["date"] = new_date
        if reason:
            schedule["schedule"][stage_index]["notes"] = f"Postponed: {reason}"
        
        schedule["updated_at"] = datetime.utcnow()
    
    return schedule

def get_todays_action(schedule):
    """Get today's fertilizer action"""
    today = datetime.utcnow().date()
    
    for stage in schedule["schedule"]:
        stage_date = stage.get("date")
        if isinstance(stage_date, datetime):
            stage_date = stage_date.date()
        
        if stage_date == today and stage.get("status") == "Pending":
            return {
                "action": "APPLY",
                "stage": stage.get("stage"),
                "fertilizer": stage.get("fertilizer"),
                "method": stage.get("method"),
                "quantity": stage.get("quantity"),
                "best_time": stage.get("best_time")
            }
    
    return {"action": "NONE", "message": "No fertilizer application scheduled for today"}