"""
LLM service for Groq API integration with Multi-Language Support
Supports: Tamil, English, Tanglish (Mixed)
"""

import os
import json
import logging
import re
from typing import List, Dict, Any
try:
    from groq import Groq
except ImportError:
    # Fallback for older versions
    from groq import Client as Groq
from openai import OpenAI
import time

logger = logging.getLogger(__name__)

# Language-specific system prompts
LANGUAGE_PROMPTS = {
    "tamil": """நீங்கள் இந்திய விவசாயிகளுக்கு உதவும் விவசாய நிபுணர். 
    முழுமையாக தமிழில் மட்டுமே பதிலளிக்கவும். ஆங்கிலம் பயன்படுத்த வேண்டாம்.
    எளிமையான தமிழில், விவசாயிகள் புரிந்துகொள்ளும் வகையில் பதில் தரவும்.""",
    
    "english": """You are an agriculture expert helping Indian farmers.
    Respond ONLY in English. Use simple, clear language that farmers can understand.
    Provide practical, actionable advice for farming in India.
    Use a friendly conversational tone like ChatGPT. Avoid rigid templates; use bullets only when helpful.""",
    
    "tanglish": """You are an agriculture expert helping Tamil farmers in India.\n    Respond in Tanglish (Tamil mixed with English words), but ONLY using English letters.\n    Do NOT use Tamil script. Keep it conversational and friendly, like ChatGPT. Avoid rigid templates.""",
    
    "mixed": """You are an agriculture expert helping Tamil farmers in India.\n    Respond in Tanglish (Tamil mixed with English words), but ONLY using English letters.\n    Do NOT use Tamil script. Keep it friendly and conversational, like ChatGPT. Avoid rigid templates."""
}

class LLMService:
    """Service for LLM operations with multi-language support"""
    
    # Supported languages
    SUPPORTED_LANGUAGES = ['tamil', 'english', 'tanglish', 'mixed']
    
    def __init__(self):
        self.groq_client = None
        self.openai_client = None
        self.init_clients()
    
    def init_clients(self):
        """Initialize LLM clients"""
        try:
            # Initialize Groq client
            groq_api_key = os.getenv('GROQ_API_KEY')
            if groq_api_key:
                self.groq_client = Groq(api_key=groq_api_key)
                logger.info("Groq client initialized")
            
            # Initialize OpenAI client (fallback)
            openai_api_key = os.getenv('OPENAI_API_KEY')
            if openai_api_key:
                self.openai_client = OpenAI(api_key=openai_api_key)
                logger.info("OpenAI client initialized")
                
        except Exception as e:
            logger.error(f"Error initializing LLM clients: {str(e)}")
    
    def generate_response(self, prompt, max_tokens=500, temperature=0.7, language='tanglish'):
        """Generate response using LLM with language preference
        
        Args:
            prompt: User's question
            max_tokens: Maximum tokens in response
            temperature: Creativity (0.0-1.0)
            language: 'tamil' | 'english' | 'tanglish' | 'mixed'
        """
        # Normalize language
        language = language.lower() if language else 'tanglish'
        if language not in self.SUPPORTED_LANGUAGES:
            language = 'tanglish'

        # Attempt lazy initialization if clients are missing
        if not self.groq_client and not self.openai_client:
            self.init_clients()

        # Do not fabricate responses when providers are unavailable.
        if not self.groq_client and not self.openai_client:
            logger.error("LLM clients unavailable; set GROQ_API_KEY or OPENAI_API_KEY")
            return self._generate_fallback_response(prompt, language)

        try:
            if self.groq_client:
                response = self._generate_with_groq(prompt, max_tokens, temperature, language)
            elif self.openai_client:
                response = self._generate_with_openai(prompt, max_tokens, temperature, language)
            else:
                logger.warning("No LLM client available after init")
                response = self._generate_fallback_response(prompt, language)

            if language in ('tanglish', 'mixed'):
                response = re.sub(r'[^\x00-\x7F]+', '', response)
            return response
        except Exception as e:
            logger.error(f"LLM generation error: {str(e)}")
            return self._generate_fallback_response(prompt, language)
    
    def _generate_with_groq(self, prompt, max_tokens, temperature, language='tanglish'):
        """Generate response using Groq with language preference"""
        try:
            system_prompt = LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS['tanglish'])
            
            response = self.groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.1-8b-instant",
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq API error: {str(e)}")
            raise
    
    def _generate_with_openai(self, prompt, max_tokens, temperature, language='tanglish'):
        """Generate response using OpenAI with language preference"""
        try:
            system_prompt = LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS['tanglish'])
            
            response = self.openai_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-3.5-turbo",
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise
    
    def _generate_fallback_response(self, prompt, language='tanglish'):
        """Return explicit provider-unavailable response (no fabricated content)."""
        unavailable = {
            'tamil': "LLM service unavailable right now. Please try again later.",
            'english': "LLM service is unavailable right now. Please try again later.",
            'tanglish': "LLM service ippo unavailable. Konjam neram apram try pannunga.",
            'mixed': "LLM service ippo unavailable. Konjam neram apram try pannunga."
        }
        return unavailable.get(language, unavailable['english'])

    def _deterministic_stub_response(self, prompt: str, language: str = 'tanglish') -> str:
        """Return a short deterministic message to keep dev environments stable."""
        # Keep it predictable and terse for tests/dev flows
        base = {
            'tamil': "இது மெய்நிகர் (stub) பதில். முக்கிய அம்சங்களை சுருக்கமாகக் காணுங்கள்.",
            'english': "Stub response: offline LLM. Summarize key farming steps simply.",
            'tanglish': "Stub response (dev): key farming steps summarized in Tanglish.",
            'mixed': "Stub response (dev): key farming steps summarized in Tanglish."
        }

        prompt_lower = (prompt or '').lower()
        if 'soil' in prompt_lower:
            detail = "Soil analyzed → pick 5 crops → continue to fertilizer and growth timeline."
        elif 'disease' in prompt_lower:
            detail = "Disease check: confirm plant, confidence, give 3-day action plan."
        elif 'market' in prompt_lower:
            detail = "Market: compare today vs 7-day avg; advise SELL/WAIT with reason."
        else:
            detail = "Follow flow: soil → crop → fertilizer → growth → weather → market → reports."

        return f"{base.get(language, base['tanglish'])} {detail}"
    
    def generate_structured_response(self, prompt):
        """Generate structured JSON response"""
        try:
            structured_prompt = f"""
            {prompt}
            
            Return response as valid JSON only. No additional text.
            """
            
            response = self.generate_response(structured_prompt, max_tokens=300, temperature=0.3)
            
            # Try to parse JSON
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                # If not valid JSON, wrap it
                return {"response": response}
                
        except Exception as e:
            logger.error(f"Structured response error: {str(e)}")
            return {"error": "Failed to generate structured response"}
    
    def summarize_text(self, text, max_length=200):
        """Summarize text using LLM"""
        prompt = f"Summarize this text in {max_length} characters or less: {text}"
        return self.generate_response(prompt, max_tokens=100)
    
    def translate_text(self, text, target_language="Tamil"):
        """Translate text to target language"""
        prompt = f"Translate this to {target_language} (mix with English if needed): {text}"
        return self.generate_response(prompt, max_tokens=200)


# =============================================================================
# HELPER FUNCTIONS FOR EASY USE
# =============================================================================

# Singleton instance for easy import
_llm_service = None

def get_llm_service():
    """Get singleton LLM service instance"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def get_soil_explanation(soil_data: dict, lang: str = 'tanglish') -> str:
    """
    Generate farmer-friendly explanation for soil analysis
    
    Args:
        soil_data: Dict with soil_name, fertility, ph_range, etc.
        lang: Language preference (tamil/english/tanglish)
    
    Returns:
        Explanation string in requested language
    """
    llm = get_llm_service()
    
    soil_name = soil_data.get('soil_name', 'Unknown')
    tamil_name = soil_data.get('tamil_name', '')
    fertility = soil_data.get('fertility', 'Medium')
    ph_range = soil_data.get('ph_range', '6.0-7.5')
    characteristics = soil_data.get('characteristics', [])
    
    prompt = f"""You are an agriculture expert explaining soil analysis to a Tamil Nadu farmer.

Soil Type: {soil_name} ({tamil_name})
Fertility: {fertility}
pH Range: {ph_range}
Characteristics: {', '.join(characteristics) if characteristics else 'General soil'}

Explain to the farmer in simple terms:
1. What this soil type means for their farming
2. Which crops grow well in this soil
3. One key tip for improving this soil

Keep response under 100 words. Be practical and encouraging."""

    try:
        return llm.generate_response(prompt, max_tokens=200, language=lang)
    except Exception as e:
        logger.error(f"Soil explanation error: {e}")
        # Return fallback
        return llm._generate_fallback_response(f"soil {soil_name}", lang)


def get_disease_explanation(disease_data: dict, lang: str = 'tanglish') -> str:
    """
    Generate farmer-friendly explanation for disease detection
    
    Args:
        disease_data: Dict with disease_name, severity, treatment, etc.
        lang: Language preference
    
    Returns:
        Explanation with treatment advice
    """
    llm = get_llm_service()
    
    disease_name = disease_data.get('disease_name', 'Unknown')
    tamil_name = disease_data.get('tamil_name', '')
    severity = disease_data.get('severity', 'Medium')
    treatment = disease_data.get('treatment', {})
    affected_crop = disease_data.get('affected_crop', '')
    
    prompt = f"""You are an agriculture expert advising a Tamil Nadu farmer about crop disease.

Disease: {disease_name} ({tamil_name})
Severity: {severity}
Affected Crop: {affected_crop}

Treatment Options:
- Organic: {treatment.get('organic', 'Not specified')}
- Chemical: {treatment.get('chemical', 'Not specified')}
- Prevention: {treatment.get('prevention', 'Not specified')}

Explain to the farmer:
1. How serious is this disease (urgency)
2. Immediate action they should take
3. When to consult agriculture officer

Keep under 100 words. Use simple language. If HIGH severity, emphasize urgency."""

    try:
        return llm.generate_response(prompt, max_tokens=200, language=lang)
    except Exception as e:
        logger.error(f"Disease explanation error: {e}")
        return llm._generate_fallback_response(f"disease {disease_name}", lang)


def get_crop_recommendation_explanation(recommendations: list, soil_type: str, lang: str = 'tanglish') -> str:
    """
    Generate explanation for crop recommendations
    
    Args:
        recommendations: List of recommended crops with suitability scores
        soil_type: Current soil type
        lang: Language preference
    
    Returns:
        Explanation of why these crops are recommended
    """
    llm = get_llm_service()
    
    top_crops = [r.get('crop_name', '') for r in recommendations[:3]]
    
    prompt = f"""You are an agriculture expert helping a Tamil Nadu farmer choose crops.

Soil Type: {soil_type}
Recommended Crops: {', '.join(top_crops)}

Briefly explain why these crops suit this soil type.
Mention current season suitability if relevant.
Keep under 80 words."""

    try:
        return llm.generate_response(prompt, max_tokens=150, language=lang)
    except Exception as e:
        logger.error(f"Crop recommendation explanation error: {e}")
        return f"Based on your {soil_type}, these crops are well-suited for cultivation."


def get_chatbot_response(question: str, context: dict, lang: str = 'tanglish') -> str:
    """
    Generate chatbot response with agriculture context
    
    Args:
        question: User's question
        context: Dict with user_context (crops, soil, location)
        lang: Language preference
    
    Returns:
        Chatbot response
    """
    llm = get_llm_service()
    
    user_context = context.get('user_context', {})
    current_crop = user_context.get('crops', ['Not selected'])[0]
    soil_type = user_context.get('soil', 'Not analyzed')
    location = user_context.get('location', 'Tamil Nadu')
    
    prompt = f"""You are Agri Namban, a helpful agriculture assistant for Tamil Nadu farmers.

User's Context:
- Current Crop: {current_crop}
- Soil Type: {soil_type}
- Location: {location}

User's Question: {question}

Rules:
1. ONLY answer agriculture-related questions
2. If not farming-related, politely redirect to farming topics
3. Keep response under 100 words
4. Be practical and helpful
5. If unsure, suggest consulting local agriculture officer

Answer:"""

    try:
        return llm.generate_response(prompt, max_tokens=200, language=lang)
    except Exception as e:
        logger.error(f"Chatbot response error: {e}")
        return llm._generate_fallback_response(question, lang)


def is_agriculture_question(question: str) -> bool:
    """
    Check if question is related to agriculture
    
    Args:
        question: User's question text
    
    Returns:
        True if agriculture-related, False otherwise
    """
    agri_keywords = [
        'crop', 'soil', 'farm', 'fertilizer', 'pesticide', 'harvest',
        'seed', 'water', 'irrigation', 'disease', 'pest', 'weather',
        'rain', 'market', 'price', 'mandi', 'yield', 'plant', 'grow',
        'பயிர்', 'மண்', 'உரம்', 'பூச்சி', 'நோய்', 'அறுவடை', 'விவசாய',
        'paddy', 'rice', 'cotton', 'sugarcane', 'groundnut', 'banana',
        'mango', 'tomato', 'onion', 'vegetable', 'fruit'
    ]
    
    question_lower = question.lower()
    return any(keyword in question_lower for keyword in agri_keywords)


def get_farming_weather_advice(weather_data: dict, crop_stage: str, lang: str = 'tanglish') -> str:
    """
    Generate farming advice based on weather conditions
    
    Args:
        weather_data: Current weather data
        crop_stage: Current growth stage (germination, flowering, etc.)
        lang: Language preference
    
    Returns:
        Weather-based farming advice
    """
    llm = get_llm_service()
    
    temp = weather_data.get('temperature', 30)
    humidity = weather_data.get('humidity', 60)
    rain_probability = weather_data.get('rain_probability', 0)
    condition = weather_data.get('condition', 'Clear')
    
    prompt = f"""You are an agriculture expert giving weather-based advice to a Tamil Nadu farmer.

Current Weather:
- Temperature: {temp}°C
- Humidity: {humidity}%
- Rain Probability: {rain_probability}%
- Condition: {condition}

Crop Stage: {crop_stage}

Give 2-3 short, practical farming tips based on this weather.
Focus on: irrigation, fertilizer timing, pest watch, harvest timing.
Keep under 80 words."""

    try:
        return llm.generate_response(prompt, max_tokens=150, language=lang)
    except Exception as e:
        logger.error(f"Weather advice error: {e}")
        if rain_probability > 50:
            return "Rain expected ஏற்படும், fertilizer apply பண்ணாதீர்கள். Wait for dry weather."
        return "Normal weather conditions. Regular farming activities பண்ணலாம்."

