"""
Market snapshot model for MongoDB
"""

from datetime import datetime

market_snapshot_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "crop_name", "captured_at"],
        "properties": {
            "user_id": {
                "bsonType": "string",
                "description": "User ID (Agri_1, Agri_2, ...)"
            },
            "crop_name": {
                "bsonType": "string",
                "description": "Name of the crop"
            },
            "quantity": {
                "bsonType": ["double", "int"],
                "minimum": 0,
                "description": "Quantity available (in quintals)"
            },
            "harvest_date": {
                "bsonType": "date",
                "description": "When crop was harvested"
            },
            "storage_type": {
                "bsonType": "string",
                "enum": ["normal", "cold", "silo", "warehouse"]
            },
            "price_data": {
                "bsonType": "object",
                "properties": {
                    "mandi_price": {
                        "bsonType": ["double", "int"],
                        "minimum": 0
                    },
                    "broker_price": {
                        "bsonType": ["double", "int"],
                        "minimum": 0
                    },
                    "yesterday_price": {
                        "bsonType": ["double", "int"],
                        "minimum": 0
                    },
                    "week_average": {
                        "bsonType": ["double", "int"],
                        "minimum": 0
                    },
                    "month_average": {
                        "bsonType": ["double", "int"],
                        "minimum": 0
                    },
                    "price_change_percent": {
                        "bsonType": ["double", "int"],
                        "description": "Percentage change from yesterday"
                    },
                    "price_trend": {
                        "bsonType": "string",
                        "enum": ["UP", "DOWN", "STABLE"]
                    },
                    "source": {
                        "bsonType": "string",
                        "description": "Source of price data"
                    }
                }
            },
            "market_decision": {
                "bsonType": "object",
                "properties": {
                    "decision": {
                        "bsonType": "string",
                        "enum": ["SELL", "WAIT", "HOLD", "DO NOT SELL", "SELL_IN_PARTS", "SELL_TO_BROKER"]
                    },
                    "reasoning": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    },
                    "confidence": {
                        "bsonType": ["double", "int"],
                        "minimum": 0,
                        "maximum": 1
                    },
                    "priority": {
                        "bsonType": "string",
                        "enum": ["Low", "Medium", "High", "Urgent"]
                    }
                }
            },
            "shelf_life_analysis": {
                "bsonType": "object",
                "properties": {
                    "days_remaining": {
                        "bsonType": "int",
                        "description": "Days until spoilage"
                    },
                    "risk_level": {
                        "bsonType": "string",
                        "enum": ["Low", "Medium", "High", "Critical"]
                    },
                    "storage_advice": {
                        "bsonType": "string"
                    },
                    "spoilage_date": {
                        "bsonType": "date",
                        "description": "Estimated spoilage date"
                    }
                }
            },
            "comparison_analysis": {
                "bsonType": "object",
                "properties": {
                    "best_option": {
                        "bsonType": "string",
                        "enum": ["MANDI", "BROKER", "WAIT"]
                    },
                    "price_difference": {
                        "bsonType": ["double", "int"]
                    },
                    "transport_cost": {
                        "bsonType": ["double", "int"]
                    },
                    "effective_price_mandi": {
                        "bsonType": ["double", "int"]
                    },
                    "effective_price_broker": {
                        "bsonType": ["double", "int"]
                    },
                    "recommendation": {
                        "bsonType": "string"
                    }
                }
            },
            "financial_projections": {
                "bsonType": "object",
                "properties": {
                    "expected_revenue": {
                        "bsonType": ["double", "int"]
                    },
                    "expected_profit": {
                        "bsonType": ["double", "int"]
                    },
                    "best_case_scenario": {
                        "bsonType": ["double", "int"]
                    },
                    "worst_case_scenario": {
                        "bsonType": ["double", "int"]
                    },
                    "risk_adjusted_value": {
                        "bsonType": ["double", "int"]
                    }
                }
            },
            "short_outlook": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "properties": {
                        "day": {"bsonType": "string"},
                        "price_estimate": {"bsonType": ["double", "int"]},
                        "confidence": {"bsonType": "string"}
                    }
                }
            },
            "captured_at": {
                "bsonType": "date",
                "description": "When snapshot was taken"
            },
            "location": {
                "bsonType": "string",
                "description": "Location for market data"
            },
            "market_conditions": {
                "bsonType": "object",
                "properties": {
                    "demand_level": {
                        "bsonType": "string",
                        "enum": ["Low", "Medium", "High"]
                    },
                    "supply_level": {
                        "bsonType": "string",
                        "enum": ["Low", "Medium", "High"]
                    },
                    "arrival_trend": {
                        "bsonType": "string",
                        "enum": ["Decreasing", "Stable", "Increasing"]
                    },
                    "festival_impact": {
                        "bsonType": "bool",
                        "description": "Whether festival season affects prices"
                    },
                    "government_intervention": {
                        "bsonType": "bool",
                        "description": "Whether government policies affect prices"
                    }
                }
            },
            "farmer_action": {
                "bsonType": "object",
                "properties": {
                    "action_taken": {
                        "bsonType": "string",
                        "enum": ["Sold", "Held", "Partial Sale", "No Action"]
                    },
                    "action_date": {"bsonType": "date"},
                    "sale_price": {"bsonType": ["double", "int"]},
                    "sale_quantity": {"bsonType": ["double", "int"]},
                    "buyer_type": {
                        "bsonType": "string",
                        "enum": ["Mandi", "Broker", "Direct", "Contract"]
                    },
                    "notes": {"bsonType": "string"}
                }
            },
            "is_active": {
                "bsonType": "bool",
                "description": "Whether this snapshot is current"
            },
            "notes": {
                "bsonType": "string",
                "description": "Additional notes"
            }
        }
    }
}

def create_market_snapshot(user_id, crop_name, quantity, harvest_date, price_data=None):
    """Create a market snapshot document"""
    return {
        "user_id": user_id,
        "crop_name": crop_name,
        "quantity": quantity,
        "harvest_date": harvest_date,
        "storage_type": "normal",
        "price_data": price_data or {},
        "market_decision": {
            "decision": "WAIT",
            "reasoning": ["Initial analysis pending"],
            "confidence": 0.5,
            "priority": "Medium"
        },
        "shelf_life_analysis": {
            "days_remaining": 30,
            "risk_level": "Low",
            "storage_advice": "Store in dry place"
        },
        "comparison_analysis": {
            "best_option": "MANDI",
            "price_difference": 0,
            "transport_cost": 0
        },
        "financial_projections": {
            "expected_revenue": 0,
            "expected_profit": 0
        },
        "short_outlook": [],
        "captured_at": datetime.utcnow(),
        "location": "",
        "market_conditions": {
            "demand_level": "Medium",
            "supply_level": "Medium"
        },
        "farmer_action": {
            "action_taken": "No Action"
        },
        "is_active": True,
        "notes": ""
    }

def update_market_decision(snapshot, decision, reasoning, confidence, price_data=None):
    """Update market decision in snapshot"""
    snapshot["market_decision"]["decision"] = decision
    snapshot["market_decision"]["reasoning"] = reasoning
    snapshot["market_decision"]["confidence"] = confidence
    
    # Update priority based on decision
    if decision in ["SELL", "DO NOT SELL"]:
        snapshot["market_decision"]["priority"] = "High"
    elif decision == "WAIT":
        snapshot["market_decision"]["priority"] = "Medium"
    else:
        snapshot["market_decision"]["priority"] = "Low"
    
    if price_data:
        snapshot["price_data"].update(price_data)
    
    snapshot["captured_at"] = datetime.utcnow()
    
    return snapshot

def record_farmer_action(snapshot, action, sale_price=None, sale_quantity=None, buyer_type="Mandi", notes=""):
    """Record farmer's market action"""
    snapshot["farmer_action"]["action_taken"] = action
    snapshot["farmer_action"]["action_date"] = datetime.utcnow()
    
    if sale_price is not None:
        snapshot["farmer_action"]["sale_price"] = sale_price
    
    if sale_quantity is not None:
        snapshot["farmer_action"]["sale_quantity"] = sale_quantity
    
    snapshot["farmer_action"]["buyer_type"] = buyer_type
    snapshot["farmer_action"]["notes"] = notes
    
    # Mark as inactive if sold
    if action in ["Sold", "Partial Sale"]:
        snapshot["is_active"] = False
    
    snapshot["captured_at"] = datetime.utcnow()
    
    return snapshot

def calculate_expected_revenue(snapshot):
    """Calculate expected revenue based on current data"""
    quantity = snapshot.get("quantity", 0)
    price = snapshot["price_data"].get("mandi_price", 0)
    
    if quantity and price:
        expected_revenue = quantity * price
        
        snapshot["financial_projections"]["expected_revenue"] = expected_revenue
        
        # Simple profit calculation (assume 70% of revenue as profit)
        snapshot["financial_projections"]["expected_profit"] = expected_revenue * 0.7
    
    return snapshot