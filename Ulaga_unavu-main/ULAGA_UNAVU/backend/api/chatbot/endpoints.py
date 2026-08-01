"""
Chatbot endpoints for ULAGA_UNAVU (FastAPI).
"""

import logging
import json
import time
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, Form, Query, Request, UploadFile
from pydantic import BaseModel

from api.common.auth import get_current_user
from api.common.responses import error_response
from api.disease.detection import DiseaseDetector
from api.soil.analysis import SoilAnalysisEngine
from services.crop_lifecycle_engine import get_lifecycle_engine
from services.image_service import get_image_service
from services.local_storage import db_service
from .rag_engine import AgriNambanChatbot

logger = logging.getLogger(__name__)

router = APIRouter()
chatbot_engine = AgriNambanChatbot()


class AskRequest(BaseModel):
    question: Optional[str] = None
    message: Optional[str] = None
    session_id: Optional[str] = None
    language: Optional[str] = "mixed"


class FeedbackRequest(BaseModel):
    session_id: str
    rating: int
    helpful: Optional[bool] = True
    comments: Optional[str] = ""


@router.get("/")
def chatbot_info():
    """Get chatbot module information."""
    return {
        "module": "AgriNamban Chatbot",
        "status": "active",
        "description": "RAG-powered agriculture assistant",
        "endpoints": {
            "ask": "/ask (POST)",
            "init": "/init (GET)",
            "sessions": "/sessions (GET)",
            "history": "/session/<id> (GET)",
            "feedback": "/feedback (POST)",
        },
    }


@router.get("/init")
def chatbot_init(
    lang: str = Query(default="mixed"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get initial chatbot state and suggestions."""
    try:
        user_id = current_user["user_id"]
        user_context = _get_user_context(user_id)
        last_question = _get_last_user_question(user_id)

        if last_question:
            suggestions = chatbot_engine.get_followup_suggestions(last_question, user_context, lang)
        else:
            suggestions = chatbot_engine.get_initial_suggestions(user_context, lang)

        greeting = chatbot_engine.generate_welcome_message(user_context, lang)
        crops = user_context.get("crops") or []
        active_crop = crops[0] if crops else "None"

        return {
            "success": True,
            "suggestions": suggestions,
            "greeting": greeting,
            "user_context": {
                "active_crop": active_crop,
                "location": user_context.get("location", "Unknown"),
            },
        }
    except Exception as e:
        logger.error("Chatbot init error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/ask")
async def ask_question(
    request: Request,
    payload: Optional[AskRequest] = Body(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Ask question to agriculture chatbot (JSON)."""
    try:
        user_id = current_user["user_id"]

        question_raw = None
        payload_language = None
        payload_session_id = None

        if payload is not None:
            question_raw = payload.question or payload.message
            payload_language = payload.language
            payload_session_id = payload.session_id

        if not question_raw:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    parsed = json.loads(body_bytes.decode("utf-8"))
                    if isinstance(parsed, dict):
                        question_raw = parsed.get("question") or parsed.get("message")
                        payload_language = parsed.get("language") or payload_language
                        payload_session_id = parsed.get("session_id") or payload_session_id
            except Exception:
                # Leave question_raw as-is and use normal validation path.
                pass

        if question_raw is None:
            return error_response("Question is required", 400)

        question = str(question_raw).strip()
        session_id = payload_session_id
        language = (payload_language or "mixed").strip() or "mixed"
        if not question:
            return error_response("Question cannot be empty", 400)

        user_context = _get_user_context(user_id)
        response = chatbot_engine.get_response(
            user_id=user_id,
            question=question,
            session_id=session_id,
            user_context=user_context,
            language_preference=language,
        )

        _save_chat_history(user_id, session_id, question, response)
        return {
            "success": True,
            "response": response["answer"],
            "session_id": response["session_id"],
            "source": response["source"],
            "agriculture_related": response["agriculture_related"],
            "tokens_used": response.get("tokens_used", 0),
            "response_time_ms": response.get("response_time_ms", 0),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error("Chatbot error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/ask-image")
async def ask_question_image(
    image: UploadFile = File(...),
    analysis_type: str = Form(default="auto"),
    language: str = Form(default="mixed"),
    session_id: Optional[str] = Form(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Ask question to chatbot using image analysis (multipart/form-data)."""
    try:
        user_id = current_user["user_id"]
        analysis_result = _analyze_image_for_chatbot(user_id, image, analysis_type, language)
        session_id_value = session_id or f"session_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        response = {
            "answer": analysis_result["message"],
            "session_id": session_id_value,
            "source": "CNN_ANALYSIS",
            "agriculture_related": True,
            "language": language,
            "analysis_result": analysis_result,
            "tokens_used": 0,
            "response_time_ms": analysis_result.get("response_time_ms", 0),
        }

        _save_chat_history(user_id, session_id_value, f"[Image Analysis: {analysis_type}]", response)
        return {
            "success": True,
            "response": response["answer"],
            "session_id": response["session_id"],
            "source": response["source"],
            "agriculture_related": response["agriculture_related"],
            "analysis_result": response["analysis_result"],
            "tokens_used": response.get("tokens_used", 0),
            "response_time_ms": response.get("response_time_ms", 0),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error("Chatbot image error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/sessions")
def get_sessions(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get user's chat sessions."""
    try:
        user_id = current_user["user_id"]
        collection = db_service.get_collection("chat_sessions")
        sessions = list(
            collection.find(
                {"user_id": user_id},
                sort=[("updated_at", -1)],
                limit=10,
                projection={
                    "_id": 0,
                    "session_id": 1,
                    "summary": 1,
                    "session_start": 1,
                    "session_end": 1,
                    "is_active": 1,
                },
            )
        )
        return {"success": True, "sessions": sessions}
    except Exception as e:
        logger.error("Get sessions error: %s", str(e))
        return error_response(str(e), 500)


@router.get("/session/{session_id}")
def get_session_history(session_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get chat history for specific session."""
    try:
        user_id = current_user["user_id"]
        collection = db_service.get_collection("chat_sessions")
        session = collection.find_one({"user_id": user_id, "session_id": session_id})
        if not session:
            return error_response("Session not found", 404)

        if "_id" in session:
            session["session_id"] = str(session.pop("_id"))
        return {"success": True, "session": session}
    except Exception as e:
        logger.error("Get session error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/session/{session_id}/end")
def end_session(session_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """End a chat session."""
    try:
        user_id = current_user["user_id"]
        collection = db_service.get_collection("chat_sessions")
        result = collection.update_one(
            {"user_id": user_id, "session_id": session_id, "is_active": True},
            {"$set": {"is_active": False, "session_end": datetime.utcnow(), "updated_at": datetime.utcnow()}},
        )
        if result.modified_count == 0:
            return error_response("Session not found or already ended", 404)
        return {"success": True, "message": "Session ended successfully"}
    except Exception as e:
        logger.error("End session error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/feedback")
def submit_feedback(
    payload: FeedbackRequest = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Submit feedback for chatbot response."""
    try:
        user_id = current_user["user_id"]
        data = payload.model_dump()
        if not 1 <= data["rating"] <= 5:
            return error_response("Rating must be between 1 and 5", 400)

        collection = db_service.get_collection("chat_sessions")
        result = collection.update_one(
            {"user_id": user_id, "session_id": data["session_id"]},
            {
                "$set": {
                    "feedback": {
                        "rating": data["rating"],
                        "helpful": data.get("helpful", True),
                        "comments": data.get("comments", ""),
                        "submitted_at": datetime.utcnow(),
                    },
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        if result.modified_count == 0:
            return error_response("Session not found", 404)
        return {"success": True, "message": "Feedback submitted successfully"}
    except Exception as e:
        logger.error("Feedback error: %s", str(e))
        return error_response(str(e), 500)


@router.post("/clear")
def clear_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Clear user's chat history."""
    try:
        user_id = current_user["user_id"]
        collection = db_service.get_collection("chat_sessions")
        result = collection.delete_many({"user_id": user_id})
        logger.info("Cleared %s chat sessions for user %s", result.deleted_count, user_id)
        return {"success": True, "message": f"Cleared {result.deleted_count} chat sessions"}
    except Exception as e:
        logger.error("Clear history error: %s", str(e))
        return error_response(str(e), 500)


def _get_user_context(user_id):
    """Get user context for chatbot."""
    try:
        context = {
            "crops": [],
            "soil": "",
            "location": "",
            "season": "",
            "current_crop": "",
            "growth_stage": "",
            "soil_result": {},
        }

        user_collection = db_service.get_collection("users")
        user = user_collection.find_one({"user_id": user_id}, projection={"farm_info": 1, "settings": 1})
        if user:
            farm_info = user.get("farm_info", {})
            context["location"] = farm_info.get("district", "")

            crop_collection = db_service.get_collection("crop_selections")
            crop = crop_collection.find_one({"user_id": user_id, "is_active": True})
            if crop:
                crop_name = crop.get("crop_name", "")
                context["crops"] = [crop_name] if crop_name else []
                context["current_crop"] = crop_name
                context["growth_stage"] = crop.get("growth_timeline", {}).get("current_stage") or ""

            try:
                lifecycle = get_lifecycle_engine(user_id)
                lifecycle_stage = lifecycle.get_current_stage_info()
                stage_name = lifecycle_stage.get("stage")
                if stage_name:
                    context["growth_stage"] = stage_name
            except Exception:
                pass

            soil_collection = db_service.get_collection("soil_results")
            soil = soil_collection.find_one({"user_id": user_id}, sort=[("created_at", -1)])
            if soil:
                context["soil"] = soil.get("soil_name", "")
                context["soil_result"] = {
                    "soil_name": soil.get("soil_name", ""),
                    "ph_range": (soil.get("soil_properties", {}) or {}).get("ph_range"),
                    "created_at": soil.get("created_at", ""),
                }
        return context
    except Exception as e:
        logger.error("Get user context error: %s", str(e))
        return {}


def _get_last_user_question(user_id):
    """Fetch the most recent user question from chat history."""
    try:
        collection = db_service.get_collection("chat_sessions")
        session = collection.find_one({"user_id": user_id}, sort=[("updated_at", -1)])
        if not session:
            return None

        messages = session.get("messages", []) or []
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return str(msg.get("content", "")).strip() if msg.get("content") else msg.get("content", "")
        return None
    except Exception as e:
        logger.error("Get last question error: %s", str(e))
        return None


def _save_chat_history(user_id, session_id, question, response):
    """Save chat to history."""
    try:
        collection = db_service.get_collection("chat_sessions")
        session_data = {
            "user_id": user_id,
            "session_id": session_id or f"session_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "updated_at": datetime.utcnow(),
        }

        user_message = {
            "role": "user",
            "content": question,
            "timestamp": datetime.utcnow(),
            "metadata": {"agriculture_related": response.get("agriculture_related", True)},
        }
        assistant_message = {
            "role": "assistant",
            "content": response["answer"],
            "timestamp": datetime.utcnow(),
            "metadata": {
                "source": response["source"],
                "tokens_used": response.get("tokens_used", 0),
                "response_time_ms": response.get("response_time_ms", 0),
                "context_used": response.get("context_used", False),
            },
        }
        message_data = {
            "$push": {"messages": {"$each": [user_message, assistant_message]}},
            "$inc": {
                "summary.total_messages": 2,
                "summary.user_messages": 1,
                "summary.assistant_messages": 1,
                "summary.total_tokens": response.get("tokens_used", 0),
            },
        }
        if response.get("agriculture_related", True):
            message_data["$inc"]["summary.agriculture_queries"] = 1
        else:
            message_data["$inc"]["summary.non_agriculture_queries"] = 1

        collection.update_one(
            {"user_id": user_id, "session_id": session_data["session_id"]},
            {
                "$setOnInsert": {
                    "session_start": datetime.utcnow(),
                    "is_active": True,
                    "created_at": datetime.utcnow(),
                    "summary": {
                        "total_messages": 0,
                        "user_messages": 0,
                        "assistant_messages": 0,
                        "total_tokens": 0,
                        "agriculture_queries": 0,
                        "non_agriculture_queries": 0,
                        "average_response_time": 0,
                        "common_topics": [],
                    },
                    "chat_context": {},
                    "messages": [],
                },
                **message_data,
            },
            upsert=True,
        )
    except Exception as e:
        logger.error("Save chat history error: %s", str(e))


def _analyze_image_for_chatbot(user_id, image_file, analysis_type, language):
    """Analyze image for chatbot using CNN models."""
    start_time = time.time()
    try:
        image_service = get_image_service()
        filename, image_path = image_service.save_image(image_file)
        result = {
            "image_filename": filename,
            "analysis_type": analysis_type,
            "message": "",
            "details": {},
            "response_time_ms": 0,
        }

        if analysis_type in {"soil", "auto"}:
            try:
                soil_analyzer = SoilAnalysisEngine()
                soil_result = soil_analyzer.analyze(user_id=user_id, image_path=image_path, lang=language)
                if soil_result:
                    result["details"] = soil_result
                    result["message"] = _format_soil_analysis_message(soil_result, language)
                    result["analysis_type"] = "soil"
                elif analysis_type == "soil":
                    result["message"] = "Soil analysis failed. Please try again."
                    return result
            except Exception as e:
                logger.error("Soil analysis error: %s", str(e))
                if analysis_type == "soil":
                    result["message"] = "Soil analysis failed. Please try again."
                    return result

        if analysis_type == "disease" or (analysis_type == "auto" and not result["details"]):
            try:
                disease_detector = DiseaseDetector()
                disease_result = disease_detector.detect(user_id=user_id, image_path=image_path, lang=language)
                if disease_result:
                    result["details"] = disease_result
                    result["message"] = _format_disease_analysis_message(disease_result, language)
                    result["analysis_type"] = "disease"
                elif analysis_type == "disease":
                    result["message"] = "Disease detection failed. Please try again."
                    return result
            except Exception as e:
                logger.error("Disease detection error: %s", str(e))
                if analysis_type == "disease":
                    result["message"] = "Disease detection failed. Please try again."
                    return result

        if analysis_type == "auto" and not result["details"]:
            result["message"] = "Could not analyze the image. Please ensure it's a soil or disease image."

        result["response_time_ms"] = int((time.time() - start_time) * 1000)
        return result
    except Exception as e:
        logger.error("Image analysis error: %s", str(e))
        return {
            "image_filename": None,
            "analysis_type": analysis_type,
            "message": "Error analyzing image. Please try again.",
            "details": {},
            "response_time_ms": int((time.time() - start_time) * 1000),
        }


def _format_soil_analysis_message(soil_result, language):
    """Format soil analysis result for chatbot."""
    soil_name = soil_result.get("soil_name", "Unknown")
    confidence = soil_result.get("confidence", 0)
    if language == "ta":
        return f"மண் பகுப்பு முடிந்தது! இது {soil_name} மண்ணாகத் தெரிகிறது. நம்பகத்தன்மை: {confidence}%"
    return f"Soil analysis complete! This appears to be {soil_name} soil. Confidence: {confidence}%"


def _format_disease_analysis_message(disease_result, language):
    """Format disease analysis result for chatbot."""
    disease_name = disease_result.get("disease_name", "Unknown")
    confidence = disease_result.get("confidence", 0)
    affected_crop = disease_result.get("affected_crop", "Unknown crop")
    if language == "ta":
        return f"நோய் கண்டறிதல் முடிந்தது! {affected_crop}-ல் {disease_name} நோய் கண்டறியப்பட்டது. நம்பகத்தன்மை: {confidence}%"
    return f"Disease detection complete! {disease_name} detected in {affected_crop}. Confidence: {confidence}%"
