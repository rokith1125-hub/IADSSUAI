"""
Chat history model for MongoDB
"""

from datetime import datetime

chat_history_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "messages", "created_at"],
        "properties": {
            "user_id": {
                "bsonType": "string",
                "description": "User ID (Agri_1, Agri_2, ...)"
            },
            "session_id": {
                "bsonType": "string",
                "description": "Unique session identifier"
            },
            "messages": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["role", "content", "timestamp"],
                    "properties": {
                        "role": {
                            "bsonType": "string",
                            "enum": ["user", "assistant", "system"]
                        },
                        "content": {
                            "bsonType": "string",
                            "description": "Message content"
                        },
                        "timestamp": {
                            "bsonType": "date",
                            "description": "When message was sent"
                        },
                        "metadata": {
                            "bsonType": "object",
                            "properties": {
                                "source": {
                                    "bsonType": "string",
                                    "enum": ["RAG", "Dataset", "LLM", "Fallback"]
                                },
                                "tokens_used": {
                                    "bsonType": "int",
                                    "minimum": 0
                                },
                                "response_time_ms": {
                                    "bsonType": "int",
                                    "minimum": 0
                                },
                                "context_used": {
                                    "bsonType": "bool",
                                    "description": "Whether RAG context was used"
                                },
                                "agriculture_related": {
                                    "bsonType": "bool",
                                    "description": "Whether query was agriculture-related"
                                },
                                "language": {
                                    "bsonType": "string",
                                    "description": "Language of response"
                                }
                            }
                        }
                    }
                }
            },
            "chat_context": {
                "bsonType": "object",
                "properties": {
                    "crop_context": {
                        "bsonType": "string",
                        "description": "Current crop context"
                    },
                    "soil_context": {
                        "bsonType": "string",
                        "description": "Soil context"
                    },
                    "location_context": {
                        "bsonType": "string",
                        "description": "Location context"
                    },
                    "season_context": {
                        "bsonType": "string",
                        "description": "Season context"
                    },
                    "last_activity": {
                        "bsonType": "string",
                        "description": "Last user activity mentioned"
                    }
                }
            },
            "summary": {
                "bsonType": "object",
                "properties": {
                    "total_messages": {
                        "bsonType": "int",
                        "minimum": 0
                    },
                    "user_messages": {
                        "bsonType": "int",
                        "minimum": 0
                    },
                    "assistant_messages": {
                        "bsonType": "int",
                        "minimum": 0
                    },
                    "total_tokens": {
                        "bsonType": "int",
                        "minimum": 0
                    },
                    "agriculture_queries": {
                        "bsonType": "int",
                        "minimum": 0
                    },
                    "non_agriculture_queries": {
                        "bsonType": "int",
                        "minimum": 0
                    },
                    "average_response_time": {
                        "bsonType": ["double", "int"],
                        "minimum": 0
                    },
                    "common_topics": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"}
                    }
                }
            },
            "session_start": {
                "bsonType": "date",
                "description": "When session started"
            },
            "session_end": {
                "bsonType": "date",
                "description": "When session ended"
            },
            "session_duration_seconds": {
                "bsonType": "int",
                "minimum": 0
            },
            "is_active": {
                "bsonType": "bool",
                "description": "Whether session is active"
            },
            "created_at": {
                "bsonType": "date",
                "description": "Session creation timestamp"
            },
            "updated_at": {
                "bsonType": "date",
                "description": "Last update timestamp"
            },
            "feedback": {
                "bsonType": "object",
                "properties": {
                    "rating": {
                        "bsonType": "int",
                        "minimum": 1,
                        "maximum": 5
                    },
                    "helpful": {
                        "bsonType": "bool"
                    },
                    "comments": {
                        "bsonType": "string"
                    },
                    "submitted_at": {
                        "bsonType": "date"
                    }
                }
            },
            "tags": {
                "bsonType": "array",
                "items": {"bsonType": "string"},
                "description": "Tags for categorization"
            }
        }
    }
}

def create_chat_session(user_id, session_id=None):
    """Create a new chat session"""
    import uuid
    
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
    
    now = datetime.utcnow()
    
    return {
        "user_id": user_id,
        "session_id": session_id,
        "messages": [],
        "chat_context": {},
        "summary": {
            "total_messages": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "total_tokens": 0,
            "agriculture_queries": 0,
            "non_agriculture_queries": 0,
            "average_response_time": 0,
            "common_topics": []
        },
        "session_start": now,
        "session_end": None,
        "session_duration_seconds": 0,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "feedback": {},
        "tags": []
    }

def add_message(session, role, content, metadata=None):
    """Add a message to chat session"""
    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow(),
        "metadata": metadata or {}
    }
    
    session["messages"].append(message)
    
    # Update summary
    if role == "user":
        session["summary"]["user_messages"] += 1
        
        # Check if agriculture related
        if metadata and metadata.get("agriculture_related", True):
            session["summary"]["agriculture_queries"] += 1
        else:
            session["summary"]["non_agriculture_queries"] += 1
            
    elif role == "assistant":
        session["summary"]["assistant_messages"] += 1
        
        # Update tokens and response time
        if metadata:
            tokens = metadata.get("tokens_used", 0)
            response_time = metadata.get("response_time_ms", 0)
            
            session["summary"]["total_tokens"] += tokens
            
            # Update average response time
            current_avg = session["summary"]["average_response_time"]
            total_assistant = session["summary"]["assistant_messages"]
            session["summary"]["average_response_time"] = (
                (current_avg * (total_assistant - 1) + response_time) / total_assistant
            )
    
    session["summary"]["total_messages"] = len(session["messages"])
    session["updated_at"] = datetime.utcnow()
    
    return session

def end_session(session, feedback=None):
    """End a chat session"""
    session["is_active"] = False
    session["session_end"] = datetime.utcnow()
    
    # Calculate session duration
    if session["session_start"] and session["session_end"]:
        duration = (session["session_end"] - session["session_start"]).total_seconds()
        session["session_duration_seconds"] = int(duration)
    
    if feedback:
        session["feedback"] = {
            "rating": feedback.get("rating", 0),
            "helpful": feedback.get("helpful", True),
            "comments": feedback.get("comments", ""),
            "submitted_at": datetime.utcnow()
        }
    
    # Update common topics
    session = _update_common_topics(session)
    
    session["updated_at"] = datetime.utcnow()
    
    return session

def _update_common_topics(session):
    """Update common topics from chat messages"""
    topics = []
    
    # Simple topic extraction from messages
    agriculture_keywords = {
        "soil": ["soil", "man", "fertility", "pH", "drainage"],
        "crop": ["crop", "plant", "seed", "sowing", "harvest"],
        "fertilizer": ["fertilizer", "manure", "nutrient", "NPK"],
        "disease": ["disease", "pest", "insect", "spray", "treatment"],
        "weather": ["weather", "rain", "temperature", "monsoon", "irrigation"],
        "market": ["price", "market", "sell", "mandi", "broker"],
        "government": ["scheme", "subsidy", "loan", "government", "policy"]
    }
    
    for message in session["messages"]:
        if message["role"] == "user":
            content_lower = message["content"].lower()
            
            for topic, keywords in agriculture_keywords.items():
                if any(keyword in content_lower for keyword in keywords):
                    if topic not in topics:
                        topics.append(topic)
    
    session["summary"]["common_topics"] = topics[:5]  # Top 5 topics
    
    return session

def get_session_summary(session):
    """Get summary of chat session"""
    return {
        "session_id": session["session_id"],
        "total_messages": session["summary"]["total_messages"],
        "user_messages": session["summary"]["user_messages"],
        "assistant_messages": session["summary"]["assistant_messages"],
        "agriculture_queries": session["summary"]["agriculture_queries"],
        "non_agriculture_queries": session["summary"]["non_agriculture_queries"],
        "common_topics": session["summary"]["common_topics"],
        "session_duration": f"{session['session_duration_seconds']} seconds",
        "is_active": session["is_active"],
        "feedback": session.get("feedback", {})
    }

def add_feedback(session, rating, helpful=True, comments=""):
    """Add feedback to chat session"""
    session["feedback"] = {
        "rating": rating,
        "helpful": helpful,
        "comments": comments,
        "submitted_at": datetime.utcnow()
    }
    
    session["updated_at"] = datetime.utcnow()
    
    return session