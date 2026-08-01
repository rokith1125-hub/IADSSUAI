"""
Growth timeline model for MongoDB
"""

from datetime import datetime, timedelta

growth_timeline_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "crop_name", "start_date", "stages"],
        "properties": {
            "user_id": {
                "bsonType": "string",
                "description": "User ID (Agri_1, Agri_2, ...)"
            },
            "crop_name": {
                "bsonType": "string",
                "description": "Name of the crop"
            },
            "start_date": {
                "bsonType": "date",
                "description": "Growth start date"
            },
            "expected_end_date": {
                "bsonType": "date",
                "description": "Expected harvest date"
            },
            "actual_end_date": {
                "bsonType": "date",
                "description": "Actual harvest date"
            },
            "total_days": {
                "bsonType": "int",
                "minimum": 30,
                "maximum": 365
            },
            "stages": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["name", "duration_days"],
                    "properties": {
                        "name": {
                            "bsonType": "string",
                            "description": "Stage name (e.g., 'Germination')"
                        },
                        "tamil_name": {
                            "bsonType": "string",
                            "description": "Stage name in Tamil"
                        },
                        "duration_days": {
                            "bsonType": "int",
                            "minimum": 1,
                            "maximum": 100
                        },
                        "start_day": {
                            "bsonType": "int",
                            "minimum": 0
                        },
                        "end_day": {
                            "bsonType": "int",
                            "minimum": 1
                        },
                        "critical_actions": {
                            "bsonType": "array",
                            "items": {"bsonType": "string"}
                        },
                        "irrigation_need": {
                            "bsonType": "string",
                            "enum": ["Low", "Medium", "High", "Critical"]
                        },
                        "temperature_range": {
                            "bsonType": "string",
                            "description": "Optimal temperature for stage"
                        },
                        "monitoring_focus": {
                            "bsonType": "string",
                            "description": "What to monitor in this stage"
                        },
                        "is_completed": {
                            "bsonType": "bool",
                            "description": "Whether stage is completed"
                        },
                        "completed_date": {
                            "bsonType": "date",
                            "description": "When stage was completed"
                        },
                        "notes": {
                            "bsonType": "string",
                            "description": "Farmer notes for this stage"
                        }
                    }
                }
            },
            "current_stage": {
                "bsonType": "string",
                "description": "Current growth stage"
            },
            "current_stage_index": {
                "bsonType": "int",
                "minimum": 0,
                "description": "Index of current stage"
            },
            "days_completed": {
                "bsonType": "int",
                "minimum": 0,
                "description": "Number of days since start"
            },
            "days_remaining": {
                "bsonType": "int",
                "minimum": 0,
                "description": "Days until expected harvest"
            },
            "progress_percent": {
                "bsonType": ["double", "int"],
                "minimum": 0,
                "maximum": 100,
                "description": "Overall progress percentage"
            },
            "today_message": {
                "bsonType": "string",
                "description": "Daily advice/message"
            },
            "harvest_status": {
                "bsonType": "string",
                "enum": ["Not Ready", "Approaching", "Ready", "Overdue", "Harvested"]
            },
            "harvest_guidance": {
                "bsonType": "object",
                "properties": {
                    "cut_timing": {"bsonType": "string"},
                    "cleaning_method": {"bsonType": "string"},
                    "bag_filling": {"bsonType": "string"},
                    "transport_tips": {"bsonType": "string"},
                    "storage_advice": {"bsonType": "string"}
                }
            },
            "growth_conditions": {
                "bsonType": "object",
                "properties": {
                    "temperature_optimal": {"bsonType": "bool"},
                    "rainfall_adequate": {"bsonType": "bool"},
                    "soil_moisture": {"bsonType": "string"},
                    "pest_risk": {"bsonType": "string"}
                }
            },
            "yield_estimate": {
                "bsonType": "object",
                "properties": {
                    "estimated_yield": {"bsonType": "string"},
                    "confidence": {"bsonType": "string"},
                    "factors": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    }
                }
            },
            "created_at": {
                "bsonType": "date",
                "description": "Timeline creation timestamp"
            },
            "updated_at": {
                "bsonType": "date",
                "description": "Last update timestamp"
            },
            "is_active": {
                "bsonType": "bool",
                "description": "Whether this timeline is active"
            },
            "farmer_notes": {
                "bsonType": "string",
                "description": "General farmer notes"
            }
        }
    }
}

def create_growth_timeline(user_id, crop_name, start_date, stages_data, total_days):
    """Create a growth timeline document"""
    # Calculate stage days
    current_day = 0
    for i, stage in enumerate(stages_data):
        stage["start_day"] = current_day
        stage["end_day"] = current_day + stage["duration_days"]
        stage["is_completed"] = False
        current_day = stage["end_day"]
    
    # Calculate expected end date
    expected_end_date = start_date + timedelta(days=total_days)
    
    # Calculate initial progress
    today = datetime.utcnow().date()
    start_date_date = start_date.date() if isinstance(start_date, datetime) else start_date
    days_completed = max(0, (today - start_date_date).days)
    days_remaining = max(0, total_days - days_completed)
    progress_percent = min(100, (days_completed / total_days * 100) if total_days > 0 else 0)
    
    # Determine current stage
    current_stage = "Not Started"
    current_stage_index = 0
    for i, stage in enumerate(stages_data):
        if days_completed >= stage["start_day"] and days_completed < stage["end_day"]:
            current_stage = stage["name"]
            current_stage_index = i
            break
    if days_completed >= total_days:
        current_stage = "Harvest"
        current_stage_index = len(stages_data)
    
    return {
        "user_id": user_id,
        "crop_name": crop_name,
        "start_date": start_date,
        "expected_end_date": expected_end_date,
        "total_days": total_days,
        "stages": stages_data,
        "current_stage": current_stage,
        "current_stage_index": current_stage_index,
        "days_completed": days_completed,
        "days_remaining": days_remaining,
        "progress_percent": progress_percent,
        "today_message": "",
        "harvest_status": "Not Ready",
        "harvest_guidance": {},
        "growth_conditions": {},
        "yield_estimate": {},
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
        "farmer_notes": ""
    }

def update_growth_progress(timeline):
    """Update growth progress based on current date"""
    today = datetime.utcnow().date()
    
    if isinstance(timeline["start_date"], datetime):
        start_date = timeline["start_date"].date()
    else:
        start_date = timeline["start_date"]
    
    total_days = timeline["total_days"]
    days_completed = max(0, (today - start_date).days)
    days_remaining = max(0, total_days - days_completed)
    progress_percent = min(100, (days_completed / total_days * 100) if total_days > 0 else 0)
    
    # Update basic progress
    timeline["days_completed"] = days_completed
    timeline["days_remaining"] = days_remaining
    timeline["progress_percent"] = progress_percent
    
    # Update current stage
    current_stage = "Not Started"
    current_stage_index = 0
    
    for i, stage in enumerate(timeline["stages"]):
        if days_completed >= stage["start_day"] and days_completed < stage["end_day"]:
            current_stage = stage["name"]
            current_stage_index = i
            break
    
    if days_completed >= total_days:
        current_stage = "Harvest"
        current_stage_index = len(timeline["stages"])
        timeline["harvest_status"] = "Ready"
    
    timeline["current_stage"] = current_stage
    timeline["current_stage_index"] = current_stage_index
    
    # Update stage completion status
    for stage in timeline["stages"]:
        if days_completed >= stage["end_day"] and not stage.get("is_completed"):
            stage["is_completed"] = True
            stage["completed_date"] = datetime.utcnow()
    
    timeline["updated_at"] = datetime.utcnow()
    
    return timeline

def mark_stage_completed(timeline, stage_index, notes=""):
    """Mark a specific stage as completed"""
    if 0 <= stage_index < len(timeline["stages"]):
        timeline["stages"][stage_index]["is_completed"] = True
        timeline["stages"][stage_index]["completed_date"] = datetime.utcnow()
        if notes:
            timeline["stages"][stage_index]["notes"] = notes
        
        timeline["updated_at"] = datetime.utcnow()
    
    return timeline

def mark_as_harvested(timeline, actual_end_date=None, yield_amount="", notes=""):
    """Mark timeline as harvested"""
    timeline["actual_end_date"] = actual_end_date or datetime.utcnow()
    timeline["harvest_status"] = "Harvested"
    timeline["is_active"] = False
    timeline["progress_percent"] = 100
    timeline["current_stage"] = "Harvested"
    
    if yield_amount:
        timeline["yield_estimate"]["actual_yield"] = yield_amount
    
    if notes:
        timeline["farmer_notes"] = notes
    
    timeline["updated_at"] = datetime.utcnow()
    
    return timeline