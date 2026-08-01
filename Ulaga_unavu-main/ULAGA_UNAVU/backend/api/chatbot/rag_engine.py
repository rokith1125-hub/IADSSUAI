"""
RAG + LLM engine for agriculture chatbot
"""

import logging
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import time
import re
from utils.path_utils import get_dataset_path
from difflib import get_close_matches

try:
    from services.llm_service import LLMService
    from services.news_service import NewsService
    from services.weather_service import WeatherService
    from services.market_service import MarketService
    from services.local_storage import db_service
    from utils.error_handler import APIError
except ImportError:
    from services.llm_service import LLMService
    from services.news_service import NewsService
    from services.weather_service import WeatherService
    from services.market_service import MarketService
    from services.local_storage import db_service
    from utils.error_handler import APIError

logger = logging.getLogger(__name__)

# Language-specific responses (Prioritizing Tanglish/English)
LANGUAGE_RESPONSES = {
    "tamil": {
        "non_agri": "This system supports agriculture-related queries only.",
        "greeting": "Hello! Naan ULAGA_UNAVU - Smart Agriculture AI Assistant. Ungaluku eppadi help panna?",
        "thanks": "Nandri! Farming queries-ku help pannuren.",
        "error": "⚠️ Konjam issue irukku. Meendum try pannunga."
    },
    "english": {
        "non_agri": "This system supports agriculture-related queries only.",
        "greeting": "**Hello!** I'm ULAGA_UNAVU - Smart Agriculture AI Assistant.",
        "thanks": "**Thanks!** Happy to help with farming.",
        "error": "**Error:** Please try again."
    },
    "tanglish": {
        "non_agri": "This system supports agriculture-related queries only.",
        "greeting": "**Hello!** Naan ULAGA_UNAVU - Smart Agriculture AI Assistant.",
        "thanks": "**Thanks!** Farming queries-ku help pannuren.",
        "error": "**Error:** Konjam issue irukku. Try again."
    }
}

NON_AGRI_REPLY = "This system supports agriculture-related queries only."

SUPPORTED_INTENTS = [
    "greeting",
    "crop_info",
    "crop_benefits",
    "best_crop",
    "soil_testing",
    "fertilizer_advice",
    "disease_help",
    "weather_check",
    "market_price",
    "government_scheme",
    "news_summary",
    "utility_date",
    "utility_time",
    "unsupported"
]

INTENTS_REQUIRING_LOCATION = {"weather_check", "market_price"}
INTENTS_REQUIRING_CROP = {"market_price"}
DECISION_CRITICAL_INTENTS = {"weather_check", "market_price", "fertilizer_advice", "disease_help"}

ORCHESTRATOR_V20_PROMPT = """
🌾 ULAGA_UNAVU - FULL SMART FARMING ORCHESTRATION PROMPT (V20 - DEEP PRODUCTION)
SYSTEM ROLE:
You are ULAGA_UNAVU - Smart Farming Orchestrator AI.
You DO NOT directly predict images.
You DO NOT simulate CNN.
You DO NOT fabricate data.
You orchestrate structured outputs from CNN results, dataset engine, weather API, market API, fertilizer scheduler, growth tracker, and profit logic.
Operate in STRICT PIPELINE MODE.

SECTION 1 - CNN IMAGE ANALYSIS RULES (.h5 + .json)
- Soil model: soil_cnn.h5 + soil_cnn.json
- Disease model: disease_cnn.h5 + disease_cnn.json
- If .h5 missing: "Model unavailable. Please deploy trained model."
- If .json missing: "Label configuration missing."
- CNN returns ONLY: class_name, confidence, all_predictions
- CNN NEVER explains soil, recommends crop, or suggests fertilizer
- LLM handles reasoning separately

SECTION 2-9 PIPELINE CONTRACT
- Soil intelligence: soil_class_name + confidence + location + season -> soil health + compatibility
- Crop recommendation: use soil/season/location/weather/market with score breakdown
- Crop selection event auto-generates fertilizer plan, growth timeline, market snapshot, profit projection, and report placeholders
- Fertilizer engine adjusts by weather, never gives fixed dosage without soil report
- Growth tracker recalculates progress and harvest date on updates
- Market intelligence returns live-only summary; never simulate prices
- Sell engine returns sell score with trace
- Harvest completion stores actual yield/date/profit/sold price and final summary

SECTION 10 - CONFIDENCE METER
- CNN: >80 High, 60-80 Medium, <60 Low
- Crop recommendation: score consistency based
- Market: data completeness based
- Always show confidence

SECTION 11 - STRICT OUTPUT FORMAT
🌾 Title
📌 Key Info:
• Bullet
• Bullet
📊 Score:
...
🔎 Why:
• Reason
⚠ Risk:
...
🎯 Action:
...
📈 Confidence:
...

SECTION 12 - NO HALLUCINATION
- Never generate fake rainfall
- Never generate fake mandi price
- Never guess missing soil data
- Never simulate CNN output
- Never override backend authentication
- If missing data, respond exactly: "Required data unavailable."
"""

INTEGRATION_V30_PROMPT = """
🌐 ULAGA_UNAVU - FULL BACKEND ↔ FRONTEND CONNECTION CONTROL PROMPT (V30)
SYSTEM ROLE:
You are ULAGA_UNAVU System Integration Controller.
You enforce API consistency and prevent undefined, nested mismatch, and 502-style failures.
You do NOT generate farming advice.

MASTER API RESPONSE (MANDATORY):
{
  "success": true/false,
  "module": "soil|crop|fertilizer|weather|market|growth|sell|report",
  "data": { ... } or null,
  "meta": {
    "confidence": number|null,
    "confidence_level": "High|Medium|Low"|null,
    "source": "cnn|ml_model|api|rule_engine|llm",
    "timestamp": "ISO_DATETIME"
  },
  "error": null|string
}

RULES:
- Never return raw array/string as top-level payload.
- Never return nested duplicate objects (example: weather.weather).
- Never expose Mongo _id.
- External API failure must return success:false with safe error payload.
- Keep Firebase auth separate from AI logic.
- LLM may explain; it must not change numeric values from CNN/API/model.
- If required data missing, return "Required data unavailable."
"""

REALTIME_SMART_MODE_PROMPT = """
ULAGA_UNAVU - Smart Agriculture AI (Realtime Conversational Mode)

SYSTEM ROLE:
You are a realtime agriculture assistant.
Reply naturally like a modern conversational AI (ChatGPT-style).
Avoid rigid templates unless absolutely necessary for safety.

RESPONSE BEHAVIOR RULES:
1) Greeting intent:
- Reply in 1-2 short lines.
- Do not use section blocks.

2) Simple explain intent (crop, soil, scheme, news):
- Give a natural paragraph or compact bullets only when useful.
- Avoid Risk/Action/Intent/Confidence headings.

3) Decision-critical intent (weather, market, fertilizer, disease):
- Provide clear recommendation and key risk in normal prose.
- Use short paragraphs or bullets only if it improves clarity.
- Do not force a fixed template.

4) Never always include intent labels, traces, or confidence lines.
   Include them only when helpful and concise.

5) Keep responses dynamic and non-repetitive.

6) Agriculture-only:
If unrelated, reply exactly:
"This system supports agriculture-related queries only."

7) Never hallucinate:
- no fake mandi prices
- no fake weather/rainfall
- no fake CNN output
- no fake scheme benefits
If live data is missing, say clearly what input is required.

8) Tone:
Professional, helpful, concise, and practical.

9) Follow-up continuity:
Continue the conversation naturally.
Do not reset with a greeting unless user greets.
"""

class AgriNambanChatbot:
    """Agriculture chatbot engine with RAG capabilities
    
    Supports Tamil, English, and Tanglish (mixed) languages.
    Uses LLM service for intelligent responses with agriculture-specific knowledge.
    """
    
    # Supported languages
    SUPPORTED_LANGUAGES = ['tamil', 'english', 'tanglish', 'mixed']
    
    def __init__(self):
        self.llm_service = LLMService()
        self.news_service = NewsService()
        self.weather_service = WeatherService()
        self.market_service = MarketService()
        self.enable_llm_intent_parsing = os.getenv("ENABLE_LLM_CHAT_INTENT", "false").lower() == "true"
        self.memory_store = {}
        self.memory_collection = "chat_memory"
        
        # Agriculture knowledge base
        self.knowledge_base = self._load_knowledge_base()
    
    def _get_language_response(self, response_type: str, language: str = 'tanglish') -> str:
        """Get language-specific response"""
        lang = language.lower() if language else 'tanglish'
        if lang == 'mixed':
            lang = 'tanglish'
        if lang not in LANGUAGE_RESPONSES:
            lang = 'tanglish'
        return LANGUAGE_RESPONSES[lang].get(response_type, LANGUAGE_RESPONSES['english'][response_type])

    def _simple_response(self, language: str, english: str, tanglish: str = None, tamil: str = None) -> str:
        lang = str(language or "tanglish").strip().lower()
        if lang == "ta":
            lang = "tamil"
        if lang == "en":
            lang = "english"
        if lang == "mixed":
            lang = "tanglish"
        if lang == "tamil":
            return tamil or tanglish or english
        if lang == "english":
            return english
        return tanglish or english
    
    def _load_knowledge_base(self) -> Dict:
        """Load agriculture knowledge base"""
        try:
            # Load from datasets
            knowledge = {
                "crops": [],
                "diseases": [],
                "fertilizers": [],
                "practices": [],
                "schemes": []
            }
            
            # Load crop data
            crop_path = get_dataset_path('crop_data.json')
            if os.path.exists(crop_path):
                with open(crop_path, 'r', encoding='utf-8') as f:
                    knowledge["crops"] = json.load(f)
            
            # Load disease data
            disease_path = get_dataset_path('disease_data.json')
            if os.path.exists(disease_path):
                with open(disease_path, 'r', encoding='utf-8') as f:
                    knowledge["diseases"] = json.load(f)
            
            # Load fertilizer data
            fertilizer_path = get_dataset_path('fertilizer_data.json')
            if os.path.exists(fertilizer_path):
                with open(fertilizer_path, 'r', encoding='utf-8') as f:
                    knowledge["fertilizers"] = json.load(f)
            
            # Government schemes
            knowledge["schemes"] = [
                {
                    "name": "PM-KISAN",
                    "description": "â‚¹6,000 per year to farmers in three equal installments",
                    "eligibility": "All landholding farmer families",
                    "link": "https://pmkisan.gov.in"
                },
                {
                    "name": "Pradhan Mantri Fasal Bima Yojana",
                    "description": "Crop insurance against natural calamities",
                    "eligibility": "All farmers including sharecroppers and tenant farmers",
                    "link": "https://pmfby.gov.in"
                },
                {
                    "name": "Soil Health Card Scheme",
                    "description": "Free soil testing and recommendations",
                    "eligibility": "All farmers",
                    "link": "https://soilhealth.dac.gov.in"
                }
            ]
            
            logger.info("Agriculture knowledge base loaded")
            return knowledge
            
        except Exception as e:
            logger.error(f"Error loading knowledge base: {str(e)}")
            return {}
    
    def get_response(self, user_id: str, question: str, session_id: str = None, 
                    user_context: Dict = None, language_preference: str = 'mixed') -> Dict:
        """Get chatbot response for question
        
        Args:
            user_id: User identifier
            question: User's question
            session_id: Session identifier for conversation tracking
            user_context: Additional context (location, crops, etc.)
            language_preference: 'tamil' | 'english' | 'tanglish' | 'mixed'
        
        Returns:
            Dict with answer, session_id, source, and metadata
        """
        start_time = time.time()
        user_context = dict(user_context or {})

        question = self._correct_spelling(question or "")
        if not question.strip():
            return {
                "answer": "Please type your farming question.",
                "session_id": session_id,
                "source": "SYSTEM",
                "agriculture_related": True,
                "language": language_preference or "mixed",
                "tokens_used": 0,
                "response_time_ms": int((time.time() - start_time) * 1000)
            }

        question_parts = [part.strip() for part in re.split(r"\n+", question) if part.strip()]
        if len(question_parts) > 1:
            combined_answers = []
            total_tokens = 0
            for part in question_parts:
                sub = self.get_response(
                    user_id=user_id,
                    question=part,
                    session_id=session_id,
                    user_context=user_context,
                    language_preference=language_preference,
                )
                combined_answers.append(sub.get("answer", ""))
                total_tokens += int(sub.get("tokens_used", 0) or 0)
            return {
                "answer": "\n\n".join([a for a in combined_answers if a]),
                "session_id": session_id or f"session_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "source": "MULTI_INTENT",
                "agriculture_related": True,
                "language": self._normalize_language(language_preference),
                "context_used": True,
                "tokens_used": total_tokens,
                "response_time_ms": int((time.time() - start_time) * 1000),
            }

        tagged_crop, clean_question = self._extract_tagged_crop(question)
        if tagged_crop and clean_question:
            question = clean_question

        language = self._normalize_language(language_preference)
        memory = self._get_memory(user_id)

        try:
            intent = self._classify_intent_ml(question, language)
            is_followup = self._is_followup_question(question)
            if intent == "unsupported" and is_followup and memory.get("last_intent"):
                intent = memory.get("last_intent")

            entities = self._extract_entities_ml(question, language)
            if tagged_crop:
                verified_crop = self._verify_crop_name(tagged_crop)
                if verified_crop:
                    entities["crop_name"] = verified_crop

            runtime_context = self._merge_user_context(
                user_context,
                memory,
                entities,
                language,
                use_memory_location=is_followup,
            )

            if intent == "unsupported":
                self._update_memory(
                    user_id,
                    {
                        "last_intent": intent,
                        "language_preference": language,
                    },
                )
                return {
                    "answer": NON_AGRI_REPLY,
                    "session_id": session_id,
                    "source": "SYSTEM",
                    "agriculture_related": False,
                    "language": language,
                    "tokens_used": 0,
                    "response_time_ms": int((time.time() - start_time) * 1000)
                }

            utility_response = self._handle_utility_intent(intent, language)
            if utility_response:
                self._update_memory(
                    user_id,
                    {
                        "last_intent": intent,
                        "language_preference": language,
                        "last_crop": (runtime_context.get("crops") or [None])[0],
                        "last_location": runtime_context.get("location"),
                        "last_state": runtime_context.get("state"),
                        "last_district": runtime_context.get("district"),
                    },
                )
                return {
                    "answer": utility_response,
                    "session_id": session_id or f"session_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    "source": "SYSTEM",
                    "agriculture_related": True,
                    "language": language,
                    "context_used": False,
                    "tokens_used": 0,
                    "response_time_ms": int((time.time() - start_time) * 1000)
                }

            state_response = self._handle_user_state_query(question, runtime_context, language)
            if state_response:
                self._update_memory(
                    user_id,
                    {
                        "last_intent": intent,
                        "language_preference": language,
                        "last_crop": (runtime_context.get("crops") or [None])[0],
                        "last_location": runtime_context.get("location"),
                        "last_state": runtime_context.get("state"),
                        "last_district": runtime_context.get("district"),
                    },
                )
                return {
                    "answer": state_response,
                    "session_id": session_id or f"session_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    "source": "DATASTORE",
                    "agriculture_related": True,
                    "language": language,
                    "context_used": True,
                    "tokens_used": 0,
                    "response_time_ms": int((time.time() - start_time) * 1000),
                }

            if intent in INTENTS_REQUIRING_LOCATION and not runtime_context.get("location"):
                answer = self._simple_response(
                    language,
                    english="I need your district or state to fetch live weather or market data. Please share it.",
                    tanglish="Live weather/market pakkanum na district/state venum. Please share pannunga.",
                    tamil="District/state thevai. Please share pannunga.",
                )
                self._update_memory(
                    user_id,
                    {
                        "last_intent": intent,
                        "language_preference": language,
                        "last_crop": (runtime_context.get("crops") or [None])[0],
                    },
                )
                return {
                    "answer": answer,
                    "session_id": session_id or f"session_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    "source": "SYSTEM",
                    "agriculture_related": True,
                    "language": language,
                    "context_used": False,
                    "tokens_used": 0,
                    "response_time_ms": int((time.time() - start_time) * 1000)
                }

            if intent in INTENTS_REQUIRING_CROP and not runtime_context.get("crops"):
                answer = self._simple_response(
                    language,
                    english="Please share the crop name (example: paddy, maize) to check market prices.",
                    tanglish="Market price paaka crop name venum (ex: paddy, maize). Please share pannunga.",
                    tamil="Crop name thevai (ud: paddy, maize). Please share pannunga.",
                )
                self._update_memory(
                    user_id,
                    {
                        "last_intent": intent,
                        "language_preference": language,
                        "last_location": runtime_context.get("location"),
                        "last_state": runtime_context.get("state"),
                        "last_district": runtime_context.get("district"),
                    },
                )
                return {
                    "answer": answer,
                    "session_id": session_id or f"session_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    "source": "SYSTEM",
                    "agriculture_related": True,
                    "language": language,
                    "context_used": False,
                    "tokens_used": 0,
                    "response_time_ms": int((time.time() - start_time) * 1000)
                }

            context = self._get_relevant_context(
                question,
                runtime_context,
                intent=intent,
                entities=entities,
            )
            llm_response = self._generate_llm_response(
                question,
                context,
                language,
                intent=intent,
                entities=entities,
            )

            confidence = self._infer_confidence(intent, context, llm_response)
            traces = self._build_trace(intent, context, runtime_context)
            if intent in DECISION_CRITICAL_INTENTS:
                final_answer = self._enforce_safety_response(
                    llm_response.get("answer", ""),
                    intent,
                    context,
                    confidence,
                    traces,
                    language,
                )
            else:
                final_answer = str(llm_response.get("answer", "")).strip()
                if not final_answer:
                    final_answer = self._get_fallback_response(question, context).get("answer", "")

            self._update_memory(
                user_id,
                {
                    "last_intent": intent,
                    "language_preference": language,
                    "last_crop": (runtime_context.get("crops") or [None])[0],
                    "last_location": runtime_context.get("location"),
                    "last_state": runtime_context.get("state"),
                    "last_district": runtime_context.get("district"),
                },
            )

            return {
                "answer": final_answer,
                "session_id": session_id or f"session_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "source": llm_response.get("source", "LLM"),
                "agriculture_related": True,
                "language": language,
                "context_used": context.get("has_context", False),
                "tokens_used": llm_response.get("tokens_used", 0),
                "response_time_ms": int((time.time() - start_time) * 1000),
            }

        except Exception as e:
            logger.error(f"Chatbot error: {str(e)}")
            fallback = self._simple_response(
                language,
                english="Something went wrong while generating the response. Please try again in a moment.",
                tanglish="Response generate panna issue irukku. Konjam neram kalichu try pannunga.",
                tamil="Response generate panna issue irukku. Konjam neram kalichu try pannunga.",
            )
            return {
                "answer": fallback,
                "session_id": session_id,
                "source": "ERROR",
                "agriculture_related": True,
                "language": language,
                "tokens_used": 0,
                "response_time_ms": int((time.time() - start_time) * 1000)
            }

    def _normalize_language(self, language: str) -> str:
        lang = str(language or "mixed").strip().lower()
        if lang == "ta":
            return "tamil"
        if lang == "en":
            return "english"
        if lang == "mixed":
            return "tanglish"
        if lang in ("english", "tamil", "tanglish"):
            return lang
        return "tanglish"

    def _safe_json_load(self, raw: str, default: Dict) -> Dict:
        if raw is None:
            return default
        text = str(raw).strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception:
            pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return default
        try:
            return json.loads(match.group(0))
        except Exception:
            return default

    def _sanitize_text_value(self, value):
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        invalid_tokens = {
            "none",
            "null",
            "undefined",
            "[object object]",
            "object object",
            "farmer",
            "myself",
            "me",
            "india",
        }
        if text.lower() in invalid_tokens:
            return None
        return text

    def _get_memory(self, user_id: str) -> Dict:
        if not user_id:
            return {}
        if user_id in self.memory_store:
            return dict(self.memory_store.get(user_id, {}))
        try:
            record = db_service.find_one(self.memory_collection, {"user_id": user_id}) or {}
            memory = dict(record.get("memory", {}) or {})
            if memory:
                self.memory_store[user_id] = memory
            return memory
        except Exception as e:
            logger.warning(f"Memory load failed: {str(e)}")
            return dict(self.memory_store.get(user_id, {}))

    def _update_memory(self, user_id: str, updates: Dict):
        if not user_id:
            return
        mem = self._get_memory(user_id)
        for key, value in (updates or {}).items():
            if isinstance(value, str):
                value = self._sanitize_text_value(value)
            if value is not None:
                mem[key] = value
        mem["updated_at"] = datetime.utcnow().isoformat()
        self.memory_store[user_id] = mem
        try:
            db_service.update_one(
                self.memory_collection,
                {"user_id": user_id},
                {"$set": {"memory": mem, "user_id": user_id}},
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"Memory persistence failed: {str(e)}")

    def _classify_intent_ml(self, question: str, language: str) -> str:
        if not self.enable_llm_intent_parsing:
            return self._classify_intent_fallback(question)

        prompt = f"""
        Classify the user message into exactly one intent.
        Allowed intents: {', '.join(SUPPORTED_INTENTS)}.
        Message: {question}
        Return strict JSON only:
        {{"intent":"one_allowed_intent","confidence":"high|medium|low","reason":"short"}}
        """
        try:
            raw = self.llm_service.generate_response(
                prompt=prompt,
                max_tokens=120,
                temperature=0.0,
                language="english",
            )
            payload = self._safe_json_load(raw, {})
            intent = str(payload.get("intent", "")).strip().lower()
            if intent in SUPPORTED_INTENTS:
                return intent
        except Exception as e:
            logger.warning(f"Intent classification failed: {str(e)}")
        return self._classify_intent_fallback(question)

    def _classify_intent_fallback(self, question: str) -> str:
        q = (question or "").lower()
        agri_strong_signals = [
            "crop", "soil", "fertilizer", "manure", "disease", "pest",
            "irrigation", "harvest", "farmer", "farming", "agriculture",
            "mandi", "weather", "rain", "monsoon", "yield", "seed",
            "paddy", "rice", "maize", "groundnut", "sugarcane", "wheat",
            "cotton", "onion", "tomato", "banana", "coconut",
        ]
        has_agri_signal = any(re.search(rf"\b{re.escape(token)}\b", q) for token in agri_strong_signals)

        if re.search(r"\b(hello|hi|hey|vanakkam|namaste)\b", q):
            return "greeting"
        if re.search(r"\b(today date|date)\b", q):
            return "utility_date"
        if re.search(r"\btime\b", q):
            return "utility_time"
        if not has_agri_signal:
            return "unsupported"
        if any(term in q for term in ["weather", "rain", "temperature", "climate"]):
            return "weather_check"
        if any(term in q for term in ["market", "mandi", "crop price", "farm price", "rate", "sell"]):
            return "market_price"
        if any(term in q for term in ["scheme", "subsidy", "government", "pm-kisan"]):
            return "government_scheme"
        if any(term in q for term in ["news", "headline", "updates"]):
            return "news_summary"
        if any(term in q for term in ["soil", "ph", "ec", "nutrient"]):
            return "soil_testing"
        if any(term in q for term in ["fertilizer", "urea", "dap", "npk", "potash", "manure"]):
            return "fertilizer_advice"
        if any(term in q for term in ["disease", "pest", "fungus", "blight", "leaf spot", "infection"]):
            return "disease_help"
        if any(term in q for term in ["best crop", "which crop", "what crop"]):
            return "best_crop"
        if "benefit" in q:
            return "crop_benefits"
        if self._is_agriculture_related(q):
            return "crop_info"
        return "unsupported"

    def _extract_entities_ml(self, question: str, language: str) -> Dict:
        default = {
            "crop_name": None,
            "district": None,
            "state": None,
            "quantity": None,
            "season": None,
        }
        if not self.enable_llm_intent_parsing:
            payload = dict(default)
            payload["district"] = self._extract_location(question)
            payload["crop_name"] = self._extract_crop_from_text(question)
            qty_match = re.search(r"(\d+(?:\.\d+)?)", question or "")
            if qty_match:
                try:
                    payload["quantity"] = float(qty_match.group(1))
                except Exception:
                    payload["quantity"] = None
            return payload

        prompt = f"""
        Extract structured entities from this farmer query.
        Query: {question}
        Return strict JSON only with keys:
        crop_name, district, state, quantity, season.
        Use null for unknown values.
        """
        try:
            raw = self.llm_service.generate_response(
                prompt=prompt,
                max_tokens=160,
                temperature=0.0,
                language="english",
            )
            payload = self._safe_json_load(raw, default)
        except Exception:
            payload = dict(default)

        payload = {
            "crop_name": self._sanitize_text_value(payload.get("crop_name")),
            "district": self._sanitize_text_value(payload.get("district")),
            "state": self._sanitize_text_value(payload.get("state")),
            "quantity": payload.get("quantity"),
            "season": self._sanitize_text_value(payload.get("season")),
        }

        if not payload.get("district"):
            payload["district"] = self._extract_location(question)
        if not payload.get("crop_name"):
            payload["crop_name"] = self._extract_crop_from_text(question)
        if payload.get("quantity") is None:
            qty_match = re.search(r"(\d+(?:\.\d+)?)", question or "")
            if qty_match:
                try:
                    payload["quantity"] = float(qty_match.group(1))
                except Exception:
                    payload["quantity"] = None
        return payload

    def _extract_crop_from_text(self, question: str) -> Optional[str]:
        text = str(question or "").lower()
        common = [
            "paddy", "rice", "maize", "groundnut", "sugarcane", "wheat",
            "cotton", "onion", "tomato", "banana", "coconut", "turmeric",
            "chilli", "potato",
        ]
        for name in common:
            if re.search(rf"\b{re.escape(name)}\b", text):
                return name
        if self.knowledge_base and self.knowledge_base.get("crops"):
            for crop in self.knowledge_base["crops"]:
                crop_name = str(crop.get("crop_name", "")).strip().lower()
                if crop_name and re.search(rf"\b{re.escape(crop_name)}\b", text):
                    return crop_name
        return None

    def _is_followup_question(self, question: str) -> bool:
        text = str(question or "").lower()
        return bool(re.search(r"\b(what about|today|tomorrow|same|again|now)\b", text))

    def _merge_user_context(
        self,
        user_context: Dict,
        memory: Dict,
        entities: Dict,
        language: str,
        use_memory_location: bool = False,
    ) -> Dict:
        ctx = dict(user_context or {})
        mem = memory or {}
        entities = entities or {}
        farm_info = ctx.get("farm_info", {}) if isinstance(ctx.get("farm_info"), dict) else {}

        crops = list(ctx.get("crops") or [])
        entity_crop = self._sanitize_text_value(entities.get("crop_name"))
        if entity_crop:
            crops = [entity_crop]
        elif not crops and mem.get("last_crop"):
            crops = [mem.get("last_crop")]
        ctx["crops"] = [c for c in crops if self._sanitize_text_value(c)]

        district = (
            self._sanitize_text_value(entities.get("district"))
            or self._sanitize_text_value(ctx.get("district"))
            or self._sanitize_text_value(farm_info.get("district"))
            or (self._sanitize_text_value(mem.get("last_district")) if use_memory_location else None)
        )
        state = (
            self._sanitize_text_value(entities.get("state"))
            or self._sanitize_text_value(ctx.get("state"))
            or self._sanitize_text_value(farm_info.get("state"))
            or (self._sanitize_text_value(mem.get("last_state")) if use_memory_location else None)
        )

        base_location = self._sanitize_text_value(ctx.get("location"))
        if not base_location and use_memory_location:
            base_location = self._sanitize_text_value(mem.get("last_location"))
        if district:
            location = district
        elif state:
            location = state
        else:
            location = base_location

        ctx["district"] = district
        ctx["state"] = state
        ctx["location"] = location
        ctx["language"] = language
        return ctx

    def _handle_utility_intent(self, intent: str, language: str) -> Optional[str]:
        now = datetime.now()
        if intent == "utility_date":
            if language == "english":
                return f"Today is {now.strftime('%d %B %Y, %A')}. Share crop + district if you want planning advice."
            if language == "tamil":
                return f"Innaikku date: {now.strftime('%d %B %Y, %A')}. Cropum districtum sonna planning help pannuren."
            return f"Today is {now.strftime('%d %B %Y, %A')}. Crop and district share pannunga, exact farming advice kudukiren."
        if intent == "utility_time":
            if language == "english":
                return f"Current time is {now.strftime('%I:%M %p')}. For spray/irrigation timing, ask with crop and district."
            if language == "tamil":
                return f"Ippo time {now.strftime('%I:%M %p')}. Spray/irrigation-ku cropum districtum kudunga."
            return f"Current time is {now.strftime('%I:%M %p')}. Spray timing-ku crop and district share pannunga."
        if intent == "greeting":
            greeting = self._get_language_response("greeting", language)
            if language == "english":
                return f"{greeting} Tell me your crop and district for realtime guidance."
            if language == "tamil":
                return f"{greeting} Unga crop um district um sollunga, realtime guidance tharen."
            return f"{greeting} Unga crop and district sollunga, realtime guidance kudukiren."
        return None

    def _handle_user_state_query(self, question: str, runtime_context: Dict, language: str) -> Optional[str]:
        text = str(question or "").lower()
        runtime_context = runtime_context or {}

        crop_query = bool(
            re.search(r"\b(current|my|selected|active)\s+crop\b", text)
            or re.search(r"\bwhich\s+crop\b", text)
        )
        soil_query = bool(
            re.search(r"\b(current|my|latest)\s+soil\b", text)
            or "soil result" in text
        )
        stage_query = bool(
            re.search(r"\b(current|my)\s+growth\s+stage\b", text)
            or "growth stage" in text
            or "which stage" in text
        )

        if crop_query:
            current_crop = runtime_context.get("current_crop") or ((runtime_context.get("crops") or [None])[0])
            if not current_crop:
                return "No active crop selected yet. Please select a crop first."
            if language == "english":
                return f"Your current active crop is {current_crop}."
            if language == "tamil":
                return f"Unga current active crop: {current_crop}."
            return f"Unga current crop {current_crop}."

        if soil_query:
            soil_result = runtime_context.get("soil_result") or {}
            soil_name = soil_result.get("soil_name") or runtime_context.get("soil")
            ph_range = soil_result.get("ph_range")
            if not soil_name:
                return "No soil result available. Please complete soil analysis first."
            if ph_range:
                if language == "english":
                    return f"Latest soil result: {soil_name}. Dataset pH range: {ph_range}."
                if language == "tamil":
                    return f"Latest soil result: {soil_name}. Dataset pH range: {ph_range}."
                return f"Latest soil result {soil_name}. pH range {ph_range}."
            if language == "english":
                return f"Latest soil result: {soil_name}."
            if language == "tamil":
                return f"Latest soil result: {soil_name}."
            return f"Latest soil result {soil_name}."

        if stage_query:
            growth_stage = runtime_context.get("growth_stage")
            if not growth_stage:
                return "Growth stage not available yet. Start farming to activate lifecycle tracking."
            if language == "english":
                return f"Current growth stage is {growth_stage}."
            if language == "tamil":
                return f"Current growth stage: {growth_stage}."
            return f"Ippo growth stage {growth_stage}."

        return None

    def _title_for_intent(self, intent: str) -> str:
        titles = {
            "crop_info": "🌾 **Crop Guidance**",
            "crop_benefits": "🌾 **Crop Benefits**",
            "best_crop": "🌾 **Best Crop Advice**",
            "soil_testing": "🌱 **Soil Health**",
            "fertilizer_advice": "🧪 **Fertilizer Guidance**",
            "disease_help": "🦠 **Disease Support**",
            "weather_check": "🌦 **Weather Update**",
            "market_price": "💰 **Market Snapshot**",
            "government_scheme": "🏛 **Government Scheme**",
            "news_summary": "📰 **Agriculture News**",
            "utility_date": "🌾 **Utility Date**",
            "utility_time": "🌾 **Utility Time**",
            "greeting": "🌾 **ULAGA_UNAVU Assistant**",
            "unsupported": "🌾 **ULAGA_UNAVU Assistant**",
        }
        return titles.get(intent, "🌾 **ULAGA_UNAVU Assistant**")

    def _infer_confidence(self, intent: str, context: Dict, response: Dict) -> str:
        if intent == "unsupported":
            return "Low"

        score = 0.0
        if context.get("has_context"):
            score += 0.4
        if not context.get("weather_error") and not context.get("market_error"):
            score += 0.3
        if intent != "unsupported":
            score += 0.3

        if intent in {"weather_check", "market_price"} and not context.get("has_context"):
            return "Low"
        if context.get("weather_error") or context.get("market_error"):
            score = min(score, 0.49)
        if response.get("source") == "NONE":
            return "Low"

        if score >= 0.75:
            return "High"
        if score >= 0.5:
            return "Medium"
        return "Low"

    def _build_trace(self, intent: str, context: Dict, runtime_context: Dict) -> List[str]:
        traces = []
        crops = runtime_context.get("crops") or []
        if crops:
            traces.append(f"Crop considered: {crops[0]}")
        if runtime_context.get("location"):
            traces.append(f"Location considered: {runtime_context.get('location')}")
        if intent == "market_price" and context.get("market"):
            traces.append(f"Trend signal: {context['market'].get('trend', 'STABLE')}")
        if intent == "weather_check" and context.get("weather"):
            traces.append("Weather payload fetched from live service")
        if context.get("weather_error"):
            traces.append("Weather API fallback triggered")
        if context.get("market_error"):
            traces.append("Market API fallback triggered")
        if not traces:
            traces.append("Used available query context")
        return traces[:3]

    def _extract_key_points(self, answer: str, max_points: int = 2) -> List[str]:
        raw = str(answer or "")
        sanitized_lines = []
        for line in raw.splitlines():
            line_clean = line.strip()
            if not line_clean:
                continue
            if re.match(r"^[🌾🌱🧪🦠🌦💰📰🏛].*\*\*$", line_clean):
                continue
            if line_clean.lower().startswith("key points"):
                continue
            if line_clean.startswith("📌 Key Points"):
                continue
            if line_clean.startswith("📊 Score:"):
                continue
            if line_clean.startswith("🧠 Intent:"):
                continue
            if line_clean.startswith("📊 Confidence:") or line_clean.startswith("📈 Confidence:"):
                continue
            if line_clean.startswith("🔎 Why:"):
                continue
            if line_clean.startswith("⚠️ Risk:"):
                continue
            if line_clean.startswith("🎯 Action:"):
                continue
            line_clean = re.sub(r"^[•\-]+\s*", "", line_clean).strip()
            if line_clean:
                sanitized_lines.append(line_clean)

        cleaned = re.sub(r"[#*_>`]", " ", " ".join(sanitized_lines))
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        chunks = re.split(r"[.!?\n]+", cleaned)
        points = []
        for chunk in chunks:
            text = chunk.strip(" -")
            if len(text) >= 12:
                points.append(text)
            if len(points) >= max_points:
                break
        if not points:
            points = ["Live data response generated from available inputs."]
        if len(points) == 1:
            points.append("Share crop and district for higher precision.")
        return points[:max_points]

    def _format_structured_answer(
        self,
        title: str,
        key_points: List[str],
        risk: str,
        action: str,
        intent: str,
        confidence: str,
        reasons: List[str],
    ) -> str:
        points = (key_points or [])[:2]
        while len(points) < 2:
            points.append("No additional details available.")
        why = (reasons or ["Based on available information."])[:2]
        title_clean = re.sub(r"[#*_`]", "", str(title or "")).strip()
        summary = " ".join([p for p in points if p]).strip()
        why_text = " ".join([w for w in why if w]).strip()

        lines = []
        if title_clean:
            lines.append(title_clean)
        if summary:
            lines.append(summary)
        if action:
            lines.append(f"Next step: {action}")
        if risk:
            lines.append(f"Risk: {risk}")
        if confidence:
            lines.append(f"Confidence: {confidence}")
        if why_text:
            lines.append(why_text)
        return "\n\n".join([ln for ln in lines if ln])[:1200]

    def _enforce_safety_response(
        self,
        answer: str,
        intent: str,
        context: Dict,
        confidence: str,
        traces: List[str],
        language: str,
    ) -> str:
        market = context.get("market") or {}
        weather = context.get("weather") or {}
        response_text = str(answer or "").strip()
        points = self._extract_key_points(response_text)
        risk_map = {
            "crop_info": "General guidance may vary by local soil and irrigation.",
            "crop_benefits": "Benefits vary by variety and farm conditions.",
            "best_crop": "Wrong crop choice can reduce yield if season mismatches.",
            "soil_testing": "Without lab report, recommendation precision is limited.",
            "fertilizer_advice": "Wrong dose can damage crop and soil.",
            "disease_help": "Severe symptoms require field verification.",
            "weather_check": "Weather can change quickly at local level.",
            "market_price": "Single-day volatility may affect sale decision.",
            "government_scheme": "Scheme terms can change by state updates.",
            "news_summary": "Headline summaries may miss full ground context.",
        }
        action_map = {
            "crop_info": "Confirm with local season and irrigation availability.",
            "crop_benefits": "Choose variety based on demand and water access.",
            "best_crop": "Pick crop after checking water, soil, and market demand.",
            "soil_testing": "Do a soil test before major nutrient decisions.",
            "fertilizer_advice": "Apply fertilizer based on soil test results and consult local agricultural officer.",
            "disease_help": "Consult local agri officer if symptoms spread rapidly.",
            "weather_check": "Plan spray and irrigation based on short-term forecast.",
            "market_price": "Use trend + logistics before final sell decision.",
            "government_scheme": "Verify eligibility and deadline on official portal.",
            "news_summary": "Track impact on your crop and district decisions.",
        }

        if intent in {"soil_testing", "fertilizer_advice"}:
            dosage_pattern = r"\b\d+(?:\.\d+)?\s*(kg|g|gram|grams|ml|l|litre|litres)\b"
            if re.search(dosage_pattern, response_text.lower()):
                return self._simple_response(
                    language,
                    english="I can’t give an exact fertilizer dose without a soil test. "
                    "Please share your soil report for a safe plan. For now, confirm with a local agri officer.",
                    tanglish="Exact fertilizer dose soil test illama solla mudiyadhu. "
                    "Soil report share pannunga; safe plan kudukaren. Ippo local agri officer kitte confirm pannunga.",
                    tamil="Soil test illama exact fertilizer dose solla mudiyadhu. "
                    "Soil report share pannunga; safe plan kudukaren. Ippo local agri officer kitte confirm pannunga.",
                )

        if intent == "weather_check" and context.get("weather_error"):
            return self._simple_response(
                language,
                english="I couldn’t fetch live weather right now. Please share your district/state or try again shortly.",
                tanglish="Live weather ippo kidaikkala. District/state share pannunga illa konjam neram kalichu try pannunga.",
                tamil="Live weather ippo kidaikkala. District/state share pannunga illa konjam neram kalichu try pannunga.",
            )

        if intent == "market_price":
            if context.get("market_error") or not market or market.get("current_price") in (None, ""):
                missing_reasons = []
                if context.get("market_error") == "Crop missing":
                    missing_reasons.append("Missing crop name")
                if context.get("market_error") == "Location missing":
                    missing_reasons.append("Missing district/state")
                if not missing_reasons:
                    missing_reasons = traces
                return self._simple_response(
                    language,
                    english="I need both crop name and district/state to pull live mandi prices. "
                    "Please share them and I’ll check.",
                    tanglish="Live mandi price paaka crop name + district/state venum. Please share pannunga.",
                    tamil="Live mandi price paaka crop name + district/state venum. Please share pannunga.",
                )
            trend = market.get("trend", "STABLE")
            decision = market.get("decision", "HOLD")
            if response_text:
                return response_text
            change = market.get("change_percent")
            change_text = f"{change}% " if change is not None else ""
            note = "Insufficient trend data for prediction." if market.get("insufficient_trend") else "Use trend + logistics before selling."
            return (
                f"Current mandi price: ₹{market.get('current_price')}.\n"
                f"Trend: {trend} {change_text.strip()} | Decision hint: {decision}.\n"
                f"{note}"
            )

        if intent == "government_scheme" and not context.get("has_context"):
            return self._format_structured_answer(
                title=self._title_for_intent(intent),
                key_points=[
                    "⚠️ Scheme information temporarily unavailable.",
                    "Try again to fetch latest scheme eligibility details.",
                ],
                risk="Policy terms may vary by district and time.",
                action="Verify on official agriculture portal.",
                intent=intent,
                confidence="Low",
                reasons=traces,
            )

        if intent == "weather_check" and weather:
            temp = weather.get("temperature")
            rain = weather.get("rain", 0)
            cond = weather.get("condition", "Unknown")
            if response_text:
                return response_text
            return (
                f"Weather now: {cond}, {temp}°C. "
                f"Rain estimate: {rain} mm. "
                "Plan irrigation/spray based on the next few hours."
            )

        if response_text:
            return response_text
        return self._format_structured_answer(
            title=self._title_for_intent(intent),
            key_points=points,
            risk=risk_map.get(intent, "Context may be incomplete."),
            action=action_map.get(intent, "Provide crop and district for better precision."),
            intent=intent,
            confidence=confidence,
            reasons=traces,
        )
    
    def _is_agriculture_related(self, question: str) -> bool:
        """Check if question is agriculture related (supports Tamil/English/Tanglish)"""
        question_lower = self._correct_spelling(question.lower())
        
        # Agriculture keywords (English + Tamil + Hindi)
        agri_keywords = [
            # English
            'crop', 'soil', 'fertilizer', 'manure', 'irrigation', 'harvest',
            'seed', 'plant', 'disease', 'pest', 'insect', 'spray', 'weather',
            'rain', 'monsoon', 'farmer', 'farming', 'agriculture', 'krishi',
            'kisan', 'mandi', 'price', 'market', 'yield', 'organic',
            'compost', 'weed', 'pruning', 'grafting', 'cultivation', 'sowing',
            'season', 'climate', 'temperature',
            'best crop', 'which crop', 'suggest crop',
            # Tamil
            'à®µà®¿à®µà®šà®¾à®¯à®®à¯', 'à®ªà®¯à®¿à®°à¯', 'à®®à®£à¯', 'à®‰à®°à®®à¯', 'à®¨à¯€à®°à¯à®ªà¯à®ªà®¾à®šà®©à®®à¯', 'à®…à®±à¯à®µà®Ÿà¯ˆ',
            'à®µà®¿à®¤à¯ˆ', 'à®šà¯†à®Ÿà®¿', 'à®¨à¯‹à®¯à¯', 'à®ªà¯‚à®šà¯à®šà®¿', 'à®®à®´à¯ˆ', 'à®µà®¿à®µà®šà®¾à®¯à®¿', 'à®µà®¿à®²à¯ˆ',
            'à®šà®¨à¯à®¤à¯ˆ', 'à®•à®³à¯ˆ', 'à®•à®¿à®´à®™à¯à®•à¯', 'à®•à®¾à®¯à¯à®•à®±à®¿', 'à®ªà®´à®®à¯',
            # Hindi
            'à¤¬à¥€à¤œ', 'à¤–à¤¾à¤¦', 'à¤¸à¤¿à¤‚à¤šà¤¾à¤ˆ', 'à¤«à¤¸à¤²', 'à¤®à¤¿à¤Ÿà¥à¤Ÿà¥€', 'à¤•à¥€à¤Ÿ', 'à¤°à¥‹à¤—', 'à¤¬à¤¾à¤œà¤¾à¤°', 'à¤®à¥‚à¤²à¥à¤¯'
        ]
        
        # Check for agriculture keywords
        for keyword in agri_keywords:
            if keyword in question_lower:
                return True
        
        # Check for crop names (English + Tamil)
        crop_names = [
            # English
            'rice', 'wheat', 'cotton', 'sugarcane', 'maize', 'paddy',
            'groundnut', 'soybean', 'pulses', 'oilseeds', 'vegetables',
            'fruits', 'mango', 'banana', 'tomato', 'potato', 'onion',
            'coconut', 'turmeric', 'ginger', 'chilli', 'pepper',
            'okra', 'brinjal', 'cabbage', 'cauliflower', 'carrot', 'radish',
            'jasmine', 'rose', 'marigold', 'papaya', 'guava', 'grapes',
            # Tamil crop names
            'à®¨à¯†à®²à¯', 'à®•à¯‹à®¤à¯à®®à¯ˆ', 'à®ªà®°à¯à®¤à¯à®¤à®¿', 'à®•à®°à¯à®®à¯à®ªà¯', 'à®šà¯‹à®³à®®à¯', 'à®¨à®¿à®²à®•à¯à®•à®Ÿà®²à¯ˆ',
            'à®µà®¾à®´à¯ˆ', 'à®¤à®•à¯à®•à®¾à®³à®¿', 'à®‰à®°à¯à®³à¯ˆà®•à¯à®•à®¿à®´à®™à¯à®•à¯', 'à®µà¯†à®™à¯à®•à®¾à®¯à®®à¯', 'à®¤à¯†à®©à¯à®©à¯ˆ',
            'à®®à®žà¯à®šà®³à¯', 'à®‡à®žà¯à®šà®¿', 'à®®à®¿à®³à®•à®¾à®¯à¯', 'à®•à®¤à¯à®¤à®°à®¿à®•à¯à®•à®¾à®¯à¯', 'à®µà¯†à®£à¯à®Ÿà¯ˆà®•à¯à®•à®¾à®¯à¯', 
            'à®•à¯‹à®šà¯', 'à®ªà¯‚à®•à¯à®•à¯‹à®šà¯', 'à®®à¯à®³à¯à®³à®™à¯à®•à®¿', 'à®®à®²à¯à®²à®¿à®•à¯ˆ', 'à®°à¯‹à®œà®¾'
        ]
        
        for crop in crop_names:
            if crop in question_lower:
                return True
        
        # Plant health related
        health_keywords = ['leaf', 'root', 'stem', 'yellowing', 'wilting', 'spots', 'holes', 'drying']
        if any(word in question_lower for word in health_keywords):
            return True
            
        return False

    def _correct_spelling(self, text: str) -> str:
        """Basic spelling correction for agri terms and common typos."""
        if not text:
            return text
        terms = [
            "paddy", "rice", "maize", "cotton", "weather", "climate", "rain",
            "temperature", "soil", "fertilizer", "market", "price", "mandi",
            "disease", "pest", "irrigation", "sowing", "harvest", "seed",
            "crop", "crops", "yield", "farmer", "farming", "season"
        ]
        direct_replacements = {
            "seasen": "season",
            "paady": "paddy",
            "tiruvannamalia": "tiruvannamalai",
            "tiruvanamalai": "tiruvannamalai",
        }

        fixed_parts = []
        last_idx = 0
        for token_match in re.finditer(r"[A-Za-z]+", text):
            start, end = token_match.span()
            fixed_parts.append(text[last_idx:start])
            token = token_match.group(0)
            direct = direct_replacements.get(token.lower())
            if direct:
                corrected = direct
            else:
                match = get_close_matches(token.lower(), terms, n=1, cutoff=0.8)
                corrected = match[0] if match else token
            if token and token[0].isupper():
                corrected = corrected.capitalize()
            fixed_parts.append(corrected)
            last_idx = end
        fixed_parts.append(text[last_idx:])
        return "".join(fixed_parts)

    def _handle_special_commands(self, question: str, user_context: Dict, language: str = 'tanglish') -> Optional[str]:
        """Handle greetings, identity, date, weather, and season-crop shortcuts."""
        question_lower = question.lower()
        user_context = user_context or {}

        # Bot identity
        if re.search(r"\b(your name|who are you|what is your name)\b", question_lower):
            if language == "english":
                return "**I am ULAGA_UNAVU - Smart Agriculture AI Assistant.**"
            return "**Naan ULAGA_UNAVU - Smart Agriculture AI Assistant.**"

        # Date query
        if re.search(r"\b(today\s+date|date)\b", question_lower):
            today = datetime.now().strftime("%d %B %Y, %A")
            return f"📅 **Today's Date:** {today}"

        # Season crop recommendation intent
        if (
            "season" in question_lower
            and any(
                phrase in question_lower
                for phrase in ["best crop", "which crop", "what crop", "crop in this season", "correct crop"]
            )
        ):
            location = self._extract_location(question) or user_context.get("location")
            if not location:
                return "🌾 Please provide your district name for season-based crop recommendation."
            return self._build_season_crop_response(location, language)

        # Greetings with strict word match (prevents 'hi' inside other words)
        greetings = ['hello', 'hi', 'hey', 'namaste', 'vanakkam']
        for greet in greetings:
            if re.search(rf"\b{re.escape(greet)}\b", question_lower):
                return self._get_language_response('greeting', language)

        # Thanks
        if any(word in question_lower for word in ['thank', 'thanks', 'nandri']):
            return self._get_language_response('thanks', language)

        # Weather or climate queries
        if any(word in question_lower for word in ['weather', 'rain', 'temperature', 'climate']):
            location = self._extract_location(question) or user_context.get('location')
            if not location:
                return "🌦 Please provide your district name for accurate weather update."

            weather = self.weather_service.get_current_weather(location)
            if weather.get("error"):
                return "⚠️ Weather update unavailable right now. Please try again."

            current = weather.get("current", {})
            temp = current.get("temperature")
            humidity = current.get("humidity")
            rain = current.get("rain", 0)
            condition = current.get("condition") or "Unknown"

            impact = "Normal conditions for field work."
            action = "Follow regular irrigation schedule."
            if rain and rain > 5:
                impact = "Rainfall may delay spraying and harvest."
                action = "Avoid pesticide spray today; secure harvest."
            elif temp and temp > 34:
                impact = "High temperature can stress crops."
                action = "Increase irrigation and mulch to reduce heat stress."

            return (
                f"🌦 **Location: {location}**\n\n"
                f"🌡 Temp: {temp}°C  \n"
                f"💧 Humidity: {humidity}%  \n"
                f"🌧 Rain: {rain}mm  \n"
                f"☁️ Condition: {condition}\n\n"
                f"🌾 **Impact on Farming**\n- {impact}\n\n"
                f"⚠️ **Action**\n- {action}"
            )

        return None

    def _extract_location(self, question: str) -> Optional[str]:
        """Extract location from phrases like 'weather in Chennai'."""
        text = question.strip()
        candidates = list(re.finditer(r'\b(?:in|at|near)\s+([A-Za-z\s]+?)(?:[\?,\.\!]|$)', text, re.IGNORECASE))
        if not candidates:
            candidates = list(re.finditer(r'\bfor\s+([A-Za-z\s]+?)(?:[\?,\.\!]|$)', text, re.IGNORECASE))
        if candidates:
            location = candidates[-1].group(1).strip()
            location = re.sub(
                r'\b(weather|climate|temperature|rain|season|today|tomorrow|best|crop|crops|correct|current|this|price|market|mandi|sell|buy)\b',
                '',
                location,
                flags=re.IGNORECASE
            ).strip()
            location = re.sub(r'\s+', ' ', location).strip()
            if location:
                return location.title()
        return None

    def _build_season_crop_response(self, location: str, language: str) -> str:
        """Return a short season-based crop recommendation for a location."""
        season = self._get_current_indian_season()
        crops = self._get_crops_for_season(season)
        fallback = ["Paddy", "Groundnut", "Maize"]
        combined = []
        for item in crops + fallback:
            if item not in combined:
                combined.append(item)
        top_crops = combined[:3]

        if language == "english":
            return (
                f"🌾 **Location:** {location}\n\n"
                f"📅 **Current Season:** {season}\n\n"
                f"✅ **Recommended Crops**\n"
                f"- {top_crops[0]}\n- {top_crops[1]}\n- {top_crops[2]}\n\n"
                f"💧 **Tip**\n- Check irrigation availability and choose short-duration variety for stable yield."
            )

        return (
            f"🌾 **Location:** {location}\n\n"
            f"📅 **Current Season:** {season}\n\n"
            f"✅ **Best Crops**\n"
            f"- {top_crops[0]}\n- {top_crops[1]}\n- {top_crops[2]}\n\n"
            f"💧 **Tip**\n- Neenga irrigation condition pathu short-duration variety select pannunga."
        )

    def _get_current_indian_season(self) -> str:
        """Map month to common Indian crop season."""
        month = datetime.now().month
        if month in [6, 7, 8, 9, 10]:
            return "Kharif"
        if month in [11, 12, 1, 2, 3]:
            return "Rabi"
        return "Summer"

    def _get_crops_for_season(self, season: str) -> List[str]:
        """Pick crops from knowledge base by season, then fallback to static defaults."""
        season_lower = season.lower()
        kb_crops = self.knowledge_base.get("crops", []) if self.knowledge_base else []
        matched = []

        for item in kb_crops:
            crop_name = item.get("crop_name")
            seasons = item.get("growing_season", [])
            if isinstance(seasons, str):
                seasons = [seasons]
            season_tags = [str(s).lower() for s in seasons]
            if crop_name and any(season_lower in tag for tag in season_tags):
                matched.append(crop_name)

        if matched:
            unique = []
            seen = set()
            for crop in matched:
                key = crop.lower()
                if key not in seen:
                    seen.add(key)
                    unique.append(crop)
            return unique

        fallback = {
            "kharif": ["Paddy", "Maize", "Cotton"],
            "rabi": ["Wheat", "Groundnut", "Chickpea"],
            "summer": ["Maize", "Sunflower", "Vegetables"]
        }
        return fallback.get(season_lower, ["Paddy", "Groundnut", "Maize"])

    def _get_relevant_context(self, question: str, user_context: Dict, intent: str = None, entities: Dict = None) -> Dict:
        """Get relevant context for question using intent + extracted entities."""
        context = {
            "knowledge": [],
            "news": [],
            "weather": {},
            "market": {},
            "has_context": False,
            "intent": intent or "",
            "entities": entities or {},
            "weather_error": None,
            "market_error": None,
        }

        try:
            user_context = user_context or {}
            entities = entities or {}
            crops = user_context.get("crops") or []
            crop = self._sanitize_text_value(entities.get("crop_name")) or (crops[0] if crops else None)
            district = self._sanitize_text_value(entities.get("district")) or self._sanitize_text_value(user_context.get("district"))
            state = self._sanitize_text_value(entities.get("state")) or self._sanitize_text_value(user_context.get("state"))
            location = self._sanitize_text_value(user_context.get("location")) or district

            # Knowledge and crop metadata
            if self.knowledge_base:
                if crop:
                    for crop_item in self.knowledge_base.get("crops", []):
                        crop_name = str(crop_item.get("crop_name", "")).strip().lower()
                        if crop_name and crop_name == str(crop).strip().lower():
                            context["knowledge"].append({"type": "crop", "data": crop_item})
                            context["has_context"] = True
                            break

                if intent in {"disease_help"}:
                    context["knowledge"].extend(
                        [{"type": "disease", "data": d} for d in self.knowledge_base.get("diseases", [])[:2]]
                    )
                    context["has_context"] = bool(context["knowledge"])

                if intent in {"fertilizer_advice", "soil_testing"}:
                    context["knowledge"].extend(
                        [{"type": "fertilizer", "data": f} for f in self.knowledge_base.get("fertilizers", [])[:2]]
                    )
                    context["has_context"] = bool(context["knowledge"])

                if intent == "government_scheme":
                    schemes = self.knowledge_base.get("schemes", [])[:3]
                    if schemes:
                        context["knowledge"].append({"type": "schemes", "data": schemes})
                        context["has_context"] = True

            # News
            if intent == "news_summary":
                try:
                    news_items = self.news_service.get_agriculture_news(limit=5)
                    if news_items:
                        context["news"] = news_items
                        context["has_context"] = True
                    else:
                        context["news"] = []
                except Exception as e:
                    logger.warning(f"News context unavailable: {str(e)}")

            # Weather
            if intent == "weather_check":
                if not location:
                    context["weather_error"] = "Location missing"
                else:
                    try:
                        weather = self.weather_service.get_current_weather(location)
                        if weather.get("error"):
                            context["weather_error"] = "⚠️ Weather data temporarily unavailable."
                        else:
                            current = weather.get("current", {})
                            context["weather"] = {
                                "location": location,
                                "temperature": current.get("temperature"),
                                "condition": current.get("condition"),
                                "rain": current.get("rain", 0),
                                "humidity": current.get("humidity"),
                            }
                            context["has_context"] = True
                    except Exception as e:
                        logger.warning(f"Weather context error: {str(e)}")
                        context["weather_error"] = "⚠️ Weather data temporarily unavailable."

            # Market
            if intent == "market_price":
                if not crop:
                    context["market_error"] = "Crop missing"
                elif not (district or state):
                    context["market_error"] = "Location missing"
                else:
                    try:
                        snapshot = self.market_service.get_mandi_snapshot(crop, state, district)
                        if snapshot.get("error"):
                            context["market_error"] = "Live mandi data temporarily unavailable."
                        else:
                            series = snapshot.get("series") or []
                            trend = snapshot.get("trend", "STABLE")
                            change_percent = snapshot.get("change_percent", 0)
                            decision = "HOLD"
                            if trend == "DOWN" and (change_percent or 0) <= -1:
                                decision = "SELL"
                            elif trend == "UP" and (change_percent or 0) >= 1:
                                decision = "WAIT"
                            context["market"] = {
                                "crop": snapshot.get("crop") or crop,
                                "district": snapshot.get("district") or district,
                                "state": snapshot.get("state") or state,
                                "current_price": snapshot.get("current_price"),
                                "range_min": snapshot.get("range_min"),
                                "range_max": snapshot.get("range_max"),
                                "trend": trend,
                                "change_percent": change_percent,
                                "decision": decision,
                                "series_length": len(series),
                                "insufficient_trend": len(series) < 7,
                                "source": snapshot.get("source", "Unknown"),
                            }
                            context["has_context"] = True
                    except Exception as e:
                        logger.warning(f"Market context error: {str(e)}")
                        context["market_error"] = "Live mandi data temporarily unavailable."

            return context

        except Exception as e:
            logger.error(f"Error getting context: {str(e)}")
            return context
    
    def _generate_llm_response(self, question: str, context: Dict, language: str, intent: str = None, entities: Dict = None) -> Dict:
        """Generate response using LLM with context and language preference"""
        try:
            # Build prompt with context
            prompt = self._build_prompt(question, context, language, intent=intent, entities=entities)
            
            # Generate response with language preference
            response = self.llm_service.generate_response(
                prompt=prompt,
                max_tokens=380,
                temperature=0.6,
                language=language  # Pass language preference to LLM
            )
            if not response or "unavailable" in str(response).lower():
                return self._get_fallback_response(question, context)
            
            return {
                "answer": response.strip(),
                "source": "LLM+RAG" if context["has_context"] else "LLM",
                "tokens_used": len(response.split())  # Rough estimate
            }
            
        except Exception as e:
            logger.error(f"LLM generation error: {str(e)}")
            # Fallback to rule-based response
            return self._get_fallback_response(question, context)
    
    def _build_prompt(self, question: str, context: Dict, language: str, intent: str = None, entities: Dict = None) -> str:
        """Build prompt for LLM"""
        prompt_parts = []
        
        # System instruction
        system_msg = f"""{REALTIME_SMART_MODE_PROMPT}

{INTEGRATION_V30_PROMPT}
"""
        
        if language == 'tamil':
            system_msg += "\nLanguage mode: Tamil."
        elif language == 'english':
            system_msg += "\nLanguage mode: Professional English."
        else:
            system_msg += "\nLanguage mode: Tanglish only in English letters. Never use Tamil script."
        
        prompt_parts.append(system_msg)
        resolved_intent = intent or context.get('intent') or 'crop_info'
        prompt_parts.append(f"\nIntent: {resolved_intent}")
        if resolved_intent in DECISION_CRITICAL_INTENTS:
            prompt_parts.append(
                "Response mode: Advisory Mode. Write like ChatGPT: give a clear recommendation, mention key risk, "
                "and suggest a next step in normal prose. Avoid rigid headings or fixed templates."
            )
        elif resolved_intent in {"greeting", "utility_date", "utility_time"}:
            prompt_parts.append(
                "Response mode: Greeting/Utility Mode. Keep it natural, plain, and within 1-2 lines."
            )
        else:
            prompt_parts.append(
                "Response mode: Explain Mode. Keep it natural and contextual. Use bullets only if they improve clarity."
            )
        if entities:
            prompt_parts.append(
                f"Entities: crop={entities.get('crop_name')}, district={entities.get('district')}, "
                f"state={entities.get('state')}, quantity={entities.get('quantity')}, season={entities.get('season')}"
            )
        
        # Add context if available
        if context["has_context"]:
            prompt_parts.append("\nRELEVANT CONTEXT:")
            
            # Knowledge context
            if context["knowledge"]:
                for item in context["knowledge"]:
                    if item["type"] == "crop":
                        crop = item["data"]
                        prompt_parts.append(f"Crop Info: {crop.get('crop_name')} - {crop.get('scientific_name')}")
                        prompt_parts.append(f"Season: {', '.join(crop.get('growing_season', []))}")
                        prompt_parts.append(f"Water: {crop.get('water_requirement')}")
                    elif item["type"] == "disease":
                        disease = item["data"]
                        prompt_parts.append(f"Disease: {disease.get('disease_name')}")
                        prompt_parts.append(f"Affects: {disease.get('affected_crop')}")
                        prompt_parts.append(f"Treatment: {', '.join(disease.get('treatment', {}).get('organic', [])[:2])}")
                    elif item["type"] == "schemes":
                        for scheme in item["data"][:2]:
                            prompt_parts.append(
                                f"Scheme: {scheme.get('name')} | {scheme.get('description')} | {scheme.get('link')}"
                            )
            
            # News context
            if context["news"]:
                prompt_parts.append("\nRecent Agriculture News:")
                for news in context["news"][:2]:
                    prompt_parts.append(f"- {news.get('title')} ({news.get('source')})")
            
            # Weather context
            if context.get("weather"):
                weather = context["weather"]
                prompt_parts.append(f"\nWeather in {weather.get('location')}:")
                prompt_parts.append(f"Temperature: {weather.get('temperature')} C")
                prompt_parts.append(f"Condition: {weather.get('condition')}")
                if weather.get('rain', 0) > 0:
                    prompt_parts.append(f"Rain: {weather.get('rain')}mm")
            if context.get("weather_error"):
                prompt_parts.append(f"\nWeather status: {context.get('weather_error')}")
            
            # Market context
            if context.get("market"):
                market = context["market"]
                prompt_parts.append(f"\nMarket crop: {market.get('crop')}")
                prompt_parts.append(f"Location: {market.get('district')}, {market.get('state')}")
                prompt_parts.append(f"Current price: {market.get('current_price')}")
                prompt_parts.append(f"Trend: {market.get('trend')} | Change: {market.get('change_percent')}%")
                prompt_parts.append(f"Decision hint: {market.get('decision')}")
                if market.get("insufficient_trend"):
                    prompt_parts.append("Trend warning: Insufficient trend data for forecast.")
            if context.get("market_error"):
                prompt_parts.append(f"\nMarket status: {context.get('market_error')}")
        
        # Add question
        prompt_parts.append(f"\nFARMER QUESTION: {question}")
        prompt_parts.append("\nReturn only the final user-facing response.")

        return "\n".join(prompt_parts)
    
    def get_initial_suggestions(self, user_context: Dict, language: str = 'mixed') -> List[str]:
        """Get 3 localized suggestions based on crop context"""
        try:
            user_context = user_context or {}
            crops = user_context.get('crops', [])
            active_crop = crops[0] if crops else None
            location = user_context.get("location") or user_context.get("district") or user_context.get("state")

            if language == 'tamil' or language == 'ta':
                lang_rule = "Use simple Tamil."
            elif language == 'english':
                lang_rule = "Use simple English."
            else:
                lang_rule = "Use Tanglish in English letters only. Do NOT use Tamil script."

            prompt = f"""
            Generate 3 short starter questions for a farmer chatbot.
            Crop context: {active_crop or "not specified"}
            Location context: {location or "not specified"}
            {lang_rule}

            Rules:
            - Agriculture only.
            - Practical and distinct.
            - One question per line.
            - No numbering, no prefix text.
            """

            response = self.llm_service.generate_response(
                prompt=prompt,
                max_tokens=180,
                temperature=0.4,
                language=self._normalize_language(language),
            )
            generated = []
            for line in str(response or "").split('\n'):
                cleaned = re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
                if cleaned and cleaned not in generated:
                    generated.append(cleaned)
            if len(generated) >= 3:
                return generated[:3]

            fallback = {
                "rice": [
                    "How to manage blast disease in paddy?",
                    "Best fertilizer schedule for rice?",
                    "How to improve rice yield in current season?"
                ],
                "paddy": [
                    "How to manage blast disease in paddy?",
                    "Best fertilizer schedule for rice?",
                    "How to improve rice yield in current season?"
                ],
                "tomato": [
                    "How to control leaf curl in tomato?",
                    "What is the right irrigation schedule for tomato?",
                    "Best organic nutrition plan for tomato?"
                ],
                "general": [
                    "How to test my soil health correctly?",
                    "Which government scheme fits small farmers now?",
                    "How to check today's mandi price for my crop?"
                ]
            }
            key = str(active_crop or "general").lower()
            return fallback.get(key, fallback["general"])
            
        except Exception as e:
            logger.error(f"Error getting suggestions: {str(e)}")
            return ["How to improve crop yield?", "Soil health tips", "Market price updates"]

    def get_followup_suggestions(self, last_question: str, user_context: Dict, language: str = 'mixed') -> List[str]:
        """Generate 3 follow-up suggestions based on the last user question."""
        try:
            user_context = user_context or {}
            if not last_question:
                return self.get_initial_suggestions(user_context, language)

            if language == 'tamil' or language == 'ta':
                lang_rule = "Use simple Tamil only."
            elif language == 'english':
                lang_rule = "Use simple English only."
            else:
                lang_rule = "Use Tanglish in English letters only. Do NOT use Tamil script."

            prompt = f"""
            Based on the farmer's last question: "{last_question}"
            Generate 3 short, helpful follow-up agriculture questions.
            {lang_rule}
            Output only the 3 questions, one per line.
            """

            response = self.llm_service.generate_response(prompt, max_tokens=200, temperature=0.3, language=language)
            suggestions = [q.strip().lstrip("-").strip() for q in response.split('\n') if q.strip()]
            return suggestions[:3] if suggestions else self.get_initial_suggestions(user_context, language)

        except Exception as e:
            logger.error(f"Error getting follow-up suggestions: {str(e)}")
            return self.get_initial_suggestions(user_context, language)

    def _extract_tagged_crop(self, question: str) -> Tuple[Optional[str], str]:
        """Extract crop name from @tag (e.g., @paddy)"""
        match = re.search(r'@(\w+)', question)
        if match:
            tagged = match.group(1).lower()
            clean_q = re.sub(r'@\w+', '', question).strip()
            return tagged, clean_q
        return None, question

    def _verify_crop_name(self, name: str) -> Optional[str]:
        """Verify if crop name exists in knowledge base or common list"""
        # Common names list as fallback
        common = ['rice', 'paddy', 'wheat', 'maize', 'sugarcane', 'cotton', 'tomato', 'potato', 'onion', 'groundnut']
        if name in common:
            return name
            
        if self.knowledge_base and self.knowledge_base.get('crops'):
            for crop in self.knowledge_base['crops']:
                if name == crop.get('crop_name', '').lower():
                    return crop['crop_name']
        return None

    def generate_welcome_message(self, user_context: Dict, language: str = 'tanglish') -> str:
        """Generate a personalized welcome message using LLM"""
        try:
            name = user_context.get('name', 'Farmer')
            crops = user_context.get('crops') or []
            crop = crops[0] if crops else 'None'
            location = user_context.get('location', 'Tamil Nadu')
            
            prompt = f"""
            You are Agri Namban, a friendly agriculture AI.
            Generate a short welcome message for a farmer named {name}.
            Active Crop: {crop}
            Location: {location}
            
            Language Style: {language} (If Tanglish/Mixed, use English letters only and do NOT use Tamil script. If English, use simple English. If Tamil, use simple Tamil.)
            Rule: Keep it within 2 sentences.
            """
            
            welcome = self.llm_service.generate_response(prompt, max_tokens=100)
            return welcome.strip()
        except Exception as e:
            logger.error(f"Error generating welcome message: {str(e)}")
            return self._get_language_response('greeting', language)

    def _get_fallback_response(self, question: str, context: Dict) -> Dict:
        """Return explicit fallback when context/LLM answer is unavailable."""
        return {
            "answer": "I don’t have enough live data to answer that right now. "
                      "Please share crop + district, or try again in a bit.",
            "source": "NONE",
            "tokens_used": 0
        }

