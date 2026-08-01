"""
Crop recommendation engine with LLM and Image Service
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from services.local_storage import db_service
from services.llm_service import LLMService
from services.image_service import get_image_service
from services.weather_service import WeatherService
from services.market_service import MarketService
from utils.error_handler import APIError
from utils.path_utils import get_dataset_path
from utils.localization import get_message
from ..fertilizer.scheduler import FertilizerScheduler
from ..growth.tracker import GrowthTracker

logger = logging.getLogger(__name__)

class CropRecommender:
    """Crop recommendation engine"""
    
    def __init__(self):
        self.db_service = db_service
        self.llm_service = LLMService()
        self.weather_service = WeatherService()
        self.market_service = MarketService()
        self.fertilizer_scheduler = FertilizerScheduler()
        self.growth_tracker = GrowthTracker()
        self.crop_dataset = self._load_crop_dataset()
        self.image_service = get_image_service()
        # Live scoring can be expensive when upstream APIs are slow/unavailable.
        self.live_score_top_k = max(0, int(os.getenv("CROP_LIVE_SCORE_TOP_K", "3") or 0))
        self.market_failure_ttl_seconds = max(30, int(os.getenv("CROP_MARKET_FAILURE_TTL_SECONDS", "300") or 300))
        self._market_failure_until = 0.0
        
    def _load_crop_dataset(self):
        """Load crop dataset from JSON"""
        try:
            dataset_path = get_dataset_path('crop_data.json')
            with open(dataset_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading crop dataset: {str(e)}")
            return []
    
    def get_recommendations(self, user_id, soil_result_id, lang="en"):
        """Get crop recommendations with dataset-primary logic and LLM fallback."""
        try:
            user_context = self._get_user_context(user_id, soil_result_id)
            soil_result = user_context.get("soil_result")
            if not soil_result:
                raise APIError("Please complete soil analysis first", 400)

            soil_name = soil_result.get("soil_name", "")
            soil_details = soil_result.get("soil_properties", {})
            if not soil_name or not isinstance(soil_details, dict) or not soil_details:
                raise APIError("Soil data missing for recommendation scoring", 400)

            suitable_crops_list = soil_result.get("suitable_crops")
            if not suitable_crops_list:
                try:
                    soil_dataset_path = get_dataset_path('soil_types.json')
                    with open(soil_dataset_path, 'r', encoding='utf-8') as f:
                        soil_types = json.load(f)
                        for s_type in soil_types:
                            if s_type.get('soil_name') == soil_name:
                                suitable_crops_list = s_type.get('suitable_crops', [])
                                break
                except Exception as e:
                    logger.error(f"Error loading soil dataset for fallback: {e}")
                    suitable_crops_list = []

            suitable_crops = {
                str(name).strip().lower()
                for name in (suitable_crops_list or [])
                if str(name).strip()
            }
            location = user_context.get("location", "")
            coordinates = user_context.get("coordinates") or {}
            district = user_context.get("district")
            state = user_context.get("state")
            season = user_context.get("season", self._get_current_season())

            lang_key = str(lang or "").lower()
            llm_language = "english" if lang_key == "en" else "tamil" if lang_key == "ta" else "tanglish"

            dataset_results = []
            fallback_candidates = []
            seen_crops = set()
            required_fields = ("crop_name", "water_requirement", "risk_level")
            for crop_data in self.crop_dataset:
                crop_name = str(crop_data.get("crop_name", "")).strip()
                if not crop_name:
                    continue

                if any(not str(crop_data.get(field, "")).strip() for field in required_fields):
                    continue

                crop_key = crop_name.lower()
                in_suitable = crop_key in suitable_crops if suitable_crops else False

                score_payload = self._score_crop_recommendation(
                    crop_data=crop_data,
                    soil_name=soil_name,
                    soil_details=soil_details,
                    season=season,
                    location=location,
                    coordinates=coordinates,
                    district=district,
                    state=state,
                    include_live_context=False,
                )
                score = score_payload["total_score"]

                entry = {
                    "crop_name": crop_name,
                    "tamil_name": crop_data.get("tamil_name", ""),
                    "scientific_name": crop_data.get("scientific_name", ""),
                    "recommended_season": crop_data.get("growing_season", []),
                    "season_months": crop_data.get("season_months", []),
                    "soil_compatibility": crop_data.get("soil_compatibility", []),
                    "water_requirement": crop_data.get("water_requirement", "Unknown"),
                    "growth_days": crop_data.get("growth_days", "Unknown"),
                    "yield_per_acre": crop_data.get("yield_per_acre", "Unknown"),
                    "market_price_range": crop_data.get("market_price_range", "Unknown"),
                    "estimated_profit_range": crop_data.get("market_price_range", "Data unavailable"),
                    "risk_level": crop_data.get("risk_level", "Unknown"),
                    "location_context": location,
                    "season_context": season,
                    "suitability_score": score,
                    "confidence_level": score_payload["confidence_level"],
                    "score_breakdown": score_payload["score_breakdown"],
                    "weather_available": score_payload["weather_available"],
                    "market_available": score_payload["market_available"],
                    "market_score_available": score_payload["market_available"],
                    "selection_method": "adaptive_ai"
                }

                if in_suitable:
                    dataset_results.append(entry)
                    seen_crops.add(crop_key)
                else:
                    fallback_candidates.append(entry)

            recommendations = []
            if dataset_results:
                dataset_results.sort(key=lambda x: x["suitability_score"], reverse=True)
                recommendations = dataset_results[:5]
                if len(recommendations) < 5:
                    fallback_candidates.sort(key=lambda x: x["suitability_score"], reverse=True)
                    for candidate in fallback_candidates:
                        if len(recommendations) >= 5:
                            break
                        if candidate["crop_name"].lower() in seen_crops:
                            continue
                        recommendations.append(candidate)
                        seen_crops.add(candidate["crop_name"].lower())
                logger.info("Crop recommendations generated using dataset")
            else:
                fallback_candidates.sort(key=lambda x: x["suitability_score"], reverse=True)
                if fallback_candidates:
                    recommendations = fallback_candidates[:5]
                    logger.info("Crop recommendations generated using dataset fallback candidates")
                else:
                    logger.warning("Dataset empty. LLM fallback triggered")

                    llm_prompt = f"""
You are generating crop recommendation fallback for an Indian farmer.
Respond in {llm_language}.
Return valid JSON only (no markdown, no explanation, no code fences) with this exact schema:
{{
  "crop_name": "string",
  "reason": "Why suitable",
  "water_requirement": "Low/Medium/High",
  "risk_level": "Low/Medium/High",
  "estimated_growth_days": "number or Unknown",
  "note": "Short practical advice"
}}

Context:
- Soil name: {soil_name}
- Soil properties: {json.dumps(soil_details, ensure_ascii=False)}
- Season: {season}
- Location: {location}
"""

                    llm_raw = self.llm_service.generate_response(
                        llm_prompt,
                        max_tokens=300,
                        temperature=0.2,
                        language=llm_language
                    )

                    if not llm_raw or not str(llm_raw).strip():
                        raise APIError("Crop recommendation service unavailable", 503)

                    llm_text = str(llm_raw).strip()
                    lower_text = llm_text.lower()
                    if "llm service unavailable" in lower_text:
                        raise APIError("Crop recommendation service unavailable", 503)

                    if llm_text.startswith("```"):
                        parts = [p for p in llm_text.split("```") if p.strip()]
                        llm_text = parts[-1].strip() if parts else llm_text
                        if llm_text.lower().startswith("json"):
                            llm_text = llm_text[4:].strip()

                    parsed = None
                    try:
                        parsed = json.loads(llm_text)
                    except Exception:
                        start = llm_text.find("{")
                        end = llm_text.rfind("}")
                        if start != -1 and end != -1 and end > start:
                            try:
                                parsed = json.loads(llm_text[start:end + 1])
                            except Exception:
                                parsed = None

                    if isinstance(parsed, list):
                        parsed = parsed[0] if parsed else None

                    if not isinstance(parsed, dict):
                        raise APIError("Crop recommendation service unavailable", 503)

                    crop_name = str(parsed.get("crop_name", "")).strip()
                    if not crop_name:
                        raise APIError("Crop recommendation service unavailable", 503)

                    recommendations = [{
                        "crop_name": crop_name,
                        "tamil_name": "",
                        "scientific_name": "",
                        "recommended_season": [],
                        "season_months": [],
                        "soil_compatibility": [],
                        "water_requirement": parsed.get("water_requirement", "Unknown"),
                        "growth_days": parsed.get("estimated_growth_days", "Unknown"),
                        "yield_per_acre": "Unknown",
                        "market_price_range": "Unknown",
                        "estimated_profit_range": "Data unavailable",
                        "risk_level": parsed.get("risk_level", "Unknown"),
                        "location_context": location,
                        "season_context": season,
                        "suitability_score": 50,
                        "confidence_level": "Low",
                        "weather_available": False,
                        "market_available": False,
                        "market_score_available": False,
                        "selection_method": "llm_fallback",
                        "generated_by": "llm",
                        "reason": parsed.get("reason", ""),
                        "note": parsed.get("note", "")
                    }]

            recommendations = recommendations[:5]
            self._enrich_recommendations_with_live_context(
                recommendations=recommendations,
                soil_name=soil_name,
                soil_details=soil_details,
                season=season,
                location=location,
                coordinates=coordinates,
                district=district,
                state=state,
            )
            recommendations.sort(key=lambda x: x.get("suitability_score", 0), reverse=True)

            custom_option = {
                "crop_name": "Custom Crop",
                "tamil_name": "Custom Crop",
                "scientific_name": "Custom",
                "selection_method": "custom",
                "explanation": get_message("custom_crop_explanation", lang)
            }
            recommendations.append(custom_option)

            for rec in recommendations:
                try:
                    crop_name = rec.get("crop_name", "")
                    image_payload = self.image_service.get_crop_image(crop_name)
                    
                    if image_payload and image_payload.get("success"):
                        image_data = image_payload.get("data") or {}
                        rec["image_url"] = image_data.get("image_url")
                        rec["thumbnail_url"] = image_data.get("thumbnail_url")
                        rec["image_source"] = image_data.get("source")
                    else:
                        # Fallback to a placeholder if image service fails for one crop
                        logger.warning(f"Image service failed for crop '{crop_name}': {image_payload.get('error') if image_payload else 'No payload'}")
                        rec["image_url"] = f"https://source.unsplash.com/featured/?{crop_name.replace(' ', ',')},agriculture"
                        rec["thumbnail_url"] = rec["image_url"]
                        rec["image_source"] = "Unsplash Fallback"
                except Exception as e:
                    logger.error(f"Graceful image fetch fail for {rec.get('crop_name')}: {str(e)}")
                    rec["image_url"] = "https://images.unsplash.com/photo-1523348837708-15d4a09cfac2?auto=format&fit=crop&w=500&q=60"  # Generic agri placeholder
                    rec["thumbnail_url"] = rec["image_url"]
                    rec["image_source"] = "System Fallback"

            return recommendations

        except APIError:
            raise
        except Exception as e:
            logger.error(f"Error getting recommendations: {str(e)}")
            raise

    def select_crop(self, user_id, crop_name, custom_crop=False, lang="en"):
        """Select a crop for farming (no automatic downstream module triggers)."""
        try:
            if custom_crop:
                crop_data = self._validate_custom_crop(crop_name)
                selected_crop_name = crop_name
            else:
                crop_data = self._get_crop_data(crop_name)
                if not crop_data:
                    raise APIError(f"Crop '{crop_name}' not found in database", 400)
                selected_crop_name = crop_data.get("crop_name", crop_name)

            image_payload = self._generate_image_payload(selected_crop_name)
            if not image_payload.get("success"):
                raise APIError(image_payload.get("error", "Image generation services unavailable"), 503)

            image_data = image_payload.get("data", {})
            lifecycle_images = self._get_lifecycle_preview_images(selected_crop_name)

            crop_selection = {
                "user_id": user_id,
                "crop_name": selected_crop_name,
                "tamil_name": crop_data.get('tamil_name', ''),
                "scientific_name": crop_data.get('scientific_name', ''),
                "selection_method": "Custom" if custom_crop else "Recommended",
                "crop_details": crop_data,
                "image_url": image_data.get("image_url"),
                "thumbnail_url": image_data.get("thumbnail_url"),
                "selected_image_source": image_data.get("source"),
                "selected_image_provider": image_data.get("provider"),
                "lifecycle_preview_images": lifecycle_images,
                "growth_timeline": {
                    "start_date": None,
                    "current_stage": "Planning",
                    "progress_percent": 0,
                    "status": "not_started"
                },
                "selected_at": datetime.utcnow(),
                "is_active": True,
                "harvested": False
            }

            selection_id = self._save_crop_selection(crop_selection)

            return {
                "selection_id": selection_id,
                "crop_name": crop_selection["crop_name"],
                "image_url": crop_selection["image_url"],
                "image_source": crop_selection.get("selected_image_source"),
                "image_provider": crop_selection.get("selected_image_provider"),
                "lifecycle_preview_images": crop_selection.get("lifecycle_preview_images", {}),
                "status": "selected"
            }

        except Exception as e:
            logger.error(f"Error selecting crop: {str(e)}")
            raise
    
    def get_current_crop(self, user_id):
        """Get currently selected crop"""
        try:
            collection = self.db_service.get_collection('crop_selections')
            crop = collection.find_one(
                {"user_id": user_id, "is_active": True},
                {"_id": 0}
            )
            
            if not crop:
                return None
            
            return crop
            
        except Exception as e:
            logger.error(f"Error getting current crop: {str(e)}")
            return None
    
    def generate_crop_image(self, user_id):
        """Generate crop image"""
        try:
            crop = self.get_current_crop(user_id)
            if not crop:
                raise APIError("No crop selected", 400)
            
            crop_name = crop['crop_name']
            image_payload = self._generate_image_payload(crop_name)
            if not image_payload.get("success"):
                logger.error("Image generation failed for crop '%s': %s", crop_name, image_payload.get("error"))
                return None

            image_data = image_payload.get("data", {})
            image_url = image_data.get("image_url")
            lifecycle_images = self._get_lifecycle_preview_images(crop_name)
            
            # Update crop with image URL
            collection = self.db_service.get_collection('crop_selections')
            collection.update_one(
                {"user_id": user_id, "is_active": True},
                {"$set": {
                    "image_url": image_url,
                    "thumbnail_url": image_data.get("thumbnail_url"),
                    "selected_image_source": image_data.get("source"),
                    "selected_image_provider": image_data.get("provider"),
                    "lifecycle_preview_images": lifecycle_images
                }}
            )
            
            return image_url
            
        except Exception as e:
            logger.error(f"Error generating crop image: {str(e)}")
            # Do not return synthetic placeholder images.
            return None
    
    def get_crop_types(self):
        """Get list of all crop types"""
        return [{
            "crop_name": crop['crop_name'],
            "tamil_name": crop.get('tamil_name', ''),
            "season": crop.get('growing_season', ['Kharif', 'Rabi']),
            "water_requirement": crop.get('water_requirement', 'Medium')
        } for crop in self.crop_dataset[:50]]  # Limit to 50
    
    def _get_user_context(self, user_id, soil_result_id):
        """Get user context for recommendations with explicit soil result contract."""
        user_collection = self.db_service.get_collection('users')
        soil_collection = self.db_service.get_collection('soil_results')
        
        user = user_collection.find_one({"user_id": user_id}) or {}
        farm_info = user.get('farm_info', {}) or {}
        if not soil_result_id:
            raise APIError("soil_result_id is required", 400)

        soil_result = soil_collection.find_one({
            "_id": soil_result_id,
            "user_id": user_id
        })

        if not soil_result:
            raise APIError("Soil result not found or access denied", 404)
        
        return {
            "user_id": user_id,
            "location": farm_info.get('district') or farm_info.get('state') or 'Tamil Nadu',
            "coordinates": {
                "latitude": farm_info.get("latitude"),
                "longitude": farm_info.get("longitude")
            },
            "district": farm_info.get("district"),
            "state": farm_info.get("state"),
            "soil_result": soil_result,
            "season": self._get_current_season(),
            "user_settings": user.get('settings', {})
        }

    def _is_market_scoring_temporarily_disabled(self):
        return time.time() < self._market_failure_until

    def _mark_market_scoring_failure(self):
        self._market_failure_until = time.time() + self.market_failure_ttl_seconds

    def _enrich_recommendations_with_live_context(
        self,
        recommendations,
        soil_name,
        soil_details,
        season,
        location,
        coordinates=None,
        district=None,
        state=None,
    ):
        """Apply live weather/market boosts only to top-K recommendations."""
        if not recommendations or self.live_score_top_k <= 0:
            return

        shortlist = [
            rec for rec in recommendations
            if str(rec.get("selection_method", "")).lower() != "custom"
        ][: self.live_score_top_k]

        for rec in shortlist:
            crop_data = self._get_crop_data(rec.get("crop_name"))
            if not crop_data:
                continue

            score_payload = self._score_crop_recommendation(
                crop_data=crop_data,
                soil_name=soil_name,
                soil_details=soil_details,
                season=season,
                location=location,
                coordinates=coordinates,
                district=district,
                state=state,
                include_live_context=True,
            )
            rec["suitability_score"] = score_payload["total_score"]
            rec["confidence_level"] = score_payload["confidence_level"]
            rec["score_breakdown"] = score_payload["score_breakdown"]
            rec["weather_available"] = score_payload["weather_available"]
            rec["market_available"] = score_payload["market_available"]
            rec["market_score_available"] = score_payload["market_available"]

    def _score_crop_recommendation(
        self,
        crop_data,
        soil_name,
        soil_details,
        season,
        location,
        coordinates=None,
        district=None,
        state=None,
        include_live_context=True,
    ):
        """Adaptive deterministic + live scoring aligned to production weights."""
        if not soil_name or not soil_details:
            raise APIError("Soil data missing for recommendation scoring", 400)

        score_breakdown = {
            "soil_match": 0,
            "season_match": 0,
            "risk_level": 0,
            "weather_score": 0,
            "market_score": 0,
        }

        crop_soils = [str(s).lower() for s in crop_data.get("soil_compatibility", [])]
        soil_norm = str(soil_name or "").lower()
        if crop_soils:
            if any(s == soil_norm for s in crop_soils):
                score_breakdown["soil_match"] = 35
            elif any(s in soil_norm or soil_norm in s for s in crop_soils):
                score_breakdown["soil_match"] = 20
            else:
                score_breakdown["soil_match"] = 10
        else:
            score_breakdown["soil_match"] = 10

        growing = crop_data.get("growing_season", []) or []
        if season in growing:
            score_breakdown["season_match"] = 25
        elif any("throughout year" in str(item).lower() for item in growing):
            score_breakdown["season_match"] = 18
        else:
            score_breakdown["season_match"] = 5

        risk = str(crop_data.get("risk_level", "Medium")).lower()
        if risk == "low":
            score_breakdown["risk_level"] = 10
        elif risk == "medium":
            score_breakdown["risk_level"] = 7
        elif risk == "high":
            score_breakdown["risk_level"] = 3
        else:
            score_breakdown["risk_level"] = 7

        weather_available = False
        market_available = False

        if include_live_context:
            latitude = (coordinates or {}).get("latitude")
            longitude = (coordinates or {}).get("longitude")
            if latitude is not None and longitude is not None:
                try:
                    weather_payload = self.weather_service.get_current_weather(latitude, longitude)
                    score_breakdown["weather_score"] = self._calculate_weather_score(crop_data, weather_payload)
                    weather_available = True
                    logger.info("Weather score applied")
                except Exception as e:
                    logger.warning("Weather API unavailable: %s", str(e))

            if self._is_market_scoring_temporarily_disabled():
                logger.warning("Market scoring skipped due to recent upstream timeout")
            else:
                market_payload = self.market_service.get_crop_market_data(
                    crop_name=crop_data.get("crop_name", ""),
                    district=district or location,
                    state=state or "Tamil Nadu",
                )
                if market_payload.get("available"):
                    market_score = 0
                    current_price = float(market_payload.get("current_price", 0) or 0)
                    seven_day_avg = float(market_payload.get("seven_day_avg", 0) or 0)
                    trend = str(market_payload.get("trend", "STABLE")).upper()
                    volatility_percent = float(market_payload.get("volatility_percent", 0) or 0)

                    if seven_day_avg > 0 and current_price > seven_day_avg:
                        market_score += 8
                    if trend == "STABLE":
                        market_score += 4
                    if volatility_percent > 10:
                        market_score -= 3

                    score_breakdown["market_score"] = max(0, min(15, market_score))
                    market_available = True
                    logger.info("Market score applied")
                else:
                    self._mark_market_scoring_failure()
                    logger.warning("Market API unavailable")

        total = (
            score_breakdown["soil_match"]
            + score_breakdown["season_match"]
            + score_breakdown["risk_level"]
            + score_breakdown["weather_score"]
            + score_breakdown["market_score"]
        )
        total = max(0, min(100, int(round(total))))

        if weather_available and market_available:
            confidence_level = "Very High"
        elif weather_available or market_available:
            confidence_level = "High"
        else:
            confidence_level = "Medium"

        score_breakdown["total_score"] = total
        return {
            "total_score": total,
            "confidence_level": confidence_level,
            "score_breakdown": score_breakdown,
            "weather_available": weather_available,
            "market_available": market_available,
        }

    def _parse_numeric_range(self, raw_value):
        text = str(raw_value or "")
        values = [float(match) for match in re.findall(r"-?\d+(?:\.\d+)?", text)]
        if len(values) >= 2:
            return min(values[0], values[1]), max(values[0], values[1])
        if len(values) == 1:
            return values[0], values[0]
        return None, None

    def _calculate_weather_score(self, crop_data, weather_payload):
        score = 0
        current = weather_payload.get("current", {}) or {}
        forecast_daily = (weather_payload.get("forecast", {}) or {}).get("daily", []) or []

        temperature = current.get("temperature")
        min_temp, max_temp = self._parse_numeric_range(crop_data.get("temperature_range"))
        if temperature is not None and min_temp is not None and max_temp is not None:
            if min_temp <= float(temperature) <= max_temp:
                score += 8

        rain_values = []
        for day in forecast_daily[:3]:
            precipitation = day.get("precipitation")
            if precipitation is not None:
                try:
                    rain_values.append(float(precipitation))
                except Exception:
                    continue
        if not rain_values:
            try:
                rain_values = [float(current.get("rain", 0) or 0)]
            except Exception:
                rain_values = [0.0]

        avg_daily_rain = sum(rain_values) / len(rain_values) if rain_values else 0.0
        rain_min_cm, rain_max_cm = self._parse_numeric_range(crop_data.get("rainfall_needed"))
        growth_days = crop_data.get("growth_days")
        rain_fit = False
        if rain_min_cm is not None and rain_max_cm is not None and growth_days:
            try:
                growth_days_value = float(growth_days)
                if growth_days_value > 0:
                    min_daily_mm = (rain_min_cm * 10.0) / growth_days_value
                    max_daily_mm = (rain_max_cm * 10.0) / growth_days_value
                    rain_fit = (min_daily_mm * 0.5) <= avg_daily_rain <= (max_daily_mm * 1.5)
            except Exception:
                rain_fit = False
        else:
            water_req = str(crop_data.get("water_requirement", "Medium")).lower()
            if water_req == "high":
                rain_fit = avg_daily_rain >= 2
            elif water_req == "medium":
                rain_fit = 0.5 <= avg_daily_rain <= 8
            else:
                rain_fit = avg_daily_rain <= 5

        if rain_fit:
            score += 5

        alerts = weather_payload.get("alerts", []) or []
        extreme_alert = any(
            str(alert.get("severity", "")).lower() == "high"
            or str(alert.get("type", "")).lower() in {"heavy_rain", "extreme_heat", "strong_wind", "thunderstorm"}
            for alert in alerts
            if isinstance(alert, dict)
        )
        if extreme_alert:
            score -= 5

        return max(0, min(15, int(round(score))))
    
    def _get_current_season(self):
        """Get current agricultural season"""
        month = datetime.now().month
        
        if month in [6, 7, 8, 9, 10]:
            return "Kharif"
        elif month in [11, 12, 1, 2, 3]:
            return "Rabi"
        else:
            return "Zaid"

    def _normalize_crop_key(self, crop_name):
        return re.sub(r"[^a-z0-9]", "", str(crop_name or "").strip().lower())

    def _canonical_crop_key(self, crop_name):
        key = self._normalize_crop_key(crop_name)
        alias_map = {
            "paddy": "rice",
            "rice": "rice",
            "corn": "maize",
            "maize": "maize",
            "chilli": "chili",
            "chili": "chili",
            "groundnut": "groundnut",
            "peanut": "groundnut",
            "groundnutpeanut": "groundnut",
            "sugarcane": "sugarcane",
            "sugarcanecrop": "sugarcane",
        }
        return alias_map.get(key, key)
    
    def _get_crop_data(self, crop_name):
        """Get crop data from dataset"""
        target_key = self._canonical_crop_key(crop_name)
        for crop in self.crop_dataset:
            crop_key = self._canonical_crop_key(crop.get('crop_name', ''))
            if crop_key and crop_key == target_key:
                return crop
        for crop in self.crop_dataset:
            crop_key = self._canonical_crop_key(crop.get('crop_name', ''))
            if crop_key and target_key and (crop_key in target_key or target_key in crop_key):
                return crop
        return None
    
    def _is_crop_suitable(self, crop_data, season, location):
        """Check if crop is suitable for season and location"""
        # Check season
        growing_seasons = crop_data.get('growing_season', [])
        if season not in growing_seasons:
            return False
        
        # Check location (simplified)
        # In production, this would check regional suitability
        return True
    
    def _calculate_suitability_score(self, crop_data, soil_details):
        """Calculate suitability score for crop"""
        score = 50  # Base score
        
        # Adjust based on water requirement vs soil drainage
        water_req = crop_data.get('water_requirement', 'Medium')
        drainage = soil_details.get('drainage', 'Good')
        
        if water_req == 'High' and drainage == 'Poor':
            score += 20
        elif water_req == 'Low' and drainage == 'Excellent':
            score += 20
        
        # Adjust based on soil fertility
        fertility = soil_details.get('fertility', 'Medium')
        if fertility in ['High', 'Very High']:
            score += 15
        
        # Adjust for risk level
        risk = crop_data.get('risk_level', 'Medium')
        if risk == 'Low':
            score += 10
        elif risk == 'High':
            score -= 10
        
        return min(100, max(0, score))
    
    def _generate_explanation(self, crop_name, soil_name, lang="en"):
        """Generate explanation for why crop is suitable"""
        try:
            language_name = "Tamil" if lang == "ta" else "English"
            prompt = f"""
            Explain in 2 sentences in {language_name} why {crop_name} is suitable for {soil_name} soil.
            Focus on practical farming benefits.
            """
            explanation = self.llm_service.generate_response(prompt, max_tokens=100)
            return explanation.strip()
            
        except Exception as e:
            logger.error(f"LLM explanation error: {str(e)}")
            return f"{crop_name} is well-suited for {soil_name} soil conditions."
    
    def _validate_custom_crop(self, crop_name):
        """Validate custom crop name"""
        if not crop_name or len(crop_name.strip()) < 2:
            raise APIError("Invalid crop name", 400)
        
        # Check if crop exists in dataset
        for crop in self.crop_dataset:
            if crop_name.lower() == crop['crop_name'].lower():
                return crop
        
        # For truly custom crop, create basic structure
        return {
            "crop_name": crop_name,
            "tamil_name": crop_name,
            "scientific_name": "Custom",
            "growing_season": [],
            "water_requirement": "Unknown",
            "growth_days": "Unknown",
            "risk_level": "Unknown"
        }
    
    def _generate_image_payload(self, crop_name):
        """Generate crop image using SmartImageEngine provider failover contract."""
        try:
            return self.image_service.get_crop_image(crop_name)
        except Exception as e:
            logger.error("Image payload generation failed for crop '%s': %s", crop_name, str(e))
            return {"success": False, "error": "Image generation services unavailable"}

    def _generate_image_url(self, crop_name):
        """Backward-compatible URL getter."""
        payload = self._generate_image_payload(crop_name)
        if not payload.get("success"):
            return None
        return (payload.get("data") or {}).get("image_url")

    def _get_lifecycle_preview_images(self, crop_name):
        """Collect lifecycle preview image URLs without failing selection flow."""
        stages = ["seed", "seedling", "vegetative", "flowering", "harvest", "market_ready"]
        previews = {}
        for stage in stages:
            try:
                stage_payload = self.image_service.get_crop_lifecycle_image(crop_name, stage)
                if stage_payload.get("success"):
                    image_url = (stage_payload.get("data") or {}).get("image_url")
                    if image_url:
                        previews[stage] = image_url
                else:
                    logger.warning(
                        "Lifecycle image unavailable: crop='%s', stage='%s', error='%s'",
                        crop_name,
                        stage,
                        stage_payload.get("error"),
                    )
            except Exception as e:
                logger.warning(
                    "Lifecycle image generation failed: crop='%s', stage='%s', error='%s'",
                    crop_name,
                    stage,
                    str(e),
                )
        return previews
    
    def get_crop_image_details(self, crop_name):
        """Get detailed crop image info"""
        try:
            return self.image_service.get_crop_image(crop_name)
        except Exception as e:
            logger.error(f"Get crop image error: {e}")
            return {"success": False, "error": str(e)}
    
    def _save_crop_selection(self, crop_selection):
        """Save crop selection to database"""
        try:
            # Deactivate previous selections
            collection = self.db_service.get_collection('crop_selections')
            collection.update_many(
                {"user_id": crop_selection['user_id'], "is_active": True},
                {"$set": {"is_active": False}}
            )

            # Crop changed: deactivate active lifecycle artifacts so new crop controls all modules.
            self.db_service.get_collection('growth_timelines').update_many(
                {"user_id": crop_selection['user_id'], "is_active": True},
                {"$set": {"is_active": False}}
            )
            self.db_service.get_collection('fertilizer_schedules').update_many(
                {"user_id": crop_selection['user_id'], "is_active": True},
                {"$set": {"is_active": False}}
            )
            
            # Save new selection
            inserted = collection.insert_one(crop_selection)
            
            logger.info(f"Crop selection saved for user {crop_selection['user_id']}")
            return str(inserted.inserted_id)
            
        except Exception as e:
            logger.error(f"Error saving crop selection: {str(e)}")
            raise
    
    def _create_fertilizer_plan(self, user_id, crop_name, crop_data):
        """Create real fertilizer plan using scheduler"""
        try:
            # Get soil information
            soil_info = self._get_soil_info(user_id)

            if not soil_info:
                raise APIError("Soil analysis required for fertilizer planning", 400)

            # Create fertilizer plan based on crop and soil
            plan = self.fertilizer_scheduler.create_fertilizer_plan_for_crop(
                user_id, crop_name, crop_data
            )

            return plan

        except Exception as e:
            logger.error(f"Error creating fertilizer plan: {e}")
            return {"crop_name": crop_name, "plan_generated": False, "error": str(e)}
    
    def _create_growth_timeline(self, user_id, crop_name, crop_data):
        """Create real growth timeline using tracker"""
        try:
            timeline = self.growth_tracker.get_growth_timeline(user_id)
            # Add a stable timeline_id contract for callers.
            if isinstance(timeline, dict):
                timeline["timeline_id"] = timeline.get("_id") or timeline.get("timeline_id")
            return timeline
        except Exception as e:
            logger.error(f"Error creating growth timeline: {e}")
            return {"crop_name": crop_name, "timeline_created": False, "error": str(e)}

    def _get_soil_info(self, user_id):
        """Get latest soil info for user."""
        try:
            collection = self.db_service.get_collection('soil_results')
            return collection.find_one({"user_id": user_id}, sort=[("created_at", -1)])
        except Exception as e:
            logger.error(f"Error getting soil info: {e}")
            return None

    def _calculate_suitability_score_from_details(self, rec):
        """Compute suitability score from detailed recommendation payload."""
        score = 50

        demand = str(rec.get("current_market_demand", "")).lower()
        if demand == "high":
            score += 20
        elif demand == "medium":
            score += 10

        try:
            profit = float(rec.get("high_profit_rating", 5))
        except Exception:
            profit = 5
        score += int((profit - 5) * 4)

        risks = rec.get("risk_factors", [])
        if isinstance(risks, list):
            score -= min(20, len(risks) * 5)

        return max(0, min(100, score))

    def _initialize_market_intelligence(self, user_id, crop_name, crop_data):
        """Create a basic market snapshot seed for selected crop."""
        try:
            record = {
                "user_id": user_id,
                "crop_name": crop_name,
                "captured_at": datetime.utcnow(),
                "is_active": True,
                "price_data": {},
                "market_decision": {"decision": "UNAVAILABLE", "reasoning": ["Market data not fetched yet"]},
                "notes": "Initialized from crop selection"
            }
            result = self.db_service.insert_one('market_snapshots', record)
            return {"intelligence_id": str(result.inserted_id), "initialized": True}
        except Exception as e:
            logger.error(f"Error initializing market intelligence: {e}")
            return {"intelligence_id": None, "initialized": False, "error": str(e)}

    def _generate_initial_pdfs(self, user_id, crop_selection, fertilizer_plan, growth_timeline):
        """Return initial PDF placeholders (actual generation happens in /api/pdf endpoints)."""
        return {
            "soil_report": "",
            "crop_report": "",
            "fertilizer_report": "",
            "growth_report": "",
            "comprehensive_report": ""
        }

    def _update_crop_selection(self, crop_selection):
        """Patch active crop selection with generated plan IDs and URLs."""
        try:
            collection = self.db_service.get_collection('crop_selections')
            collection.update_one(
                {"user_id": crop_selection["user_id"], "is_active": True},
                {"$set": {
                    "fertilizer_plan_id": crop_selection.get("fertilizer_plan_id"),
                    "growth_timeline_id": crop_selection.get("growth_timeline_id"),
                    "market_intelligence_id": crop_selection.get("market_intelligence_id"),
                    "pdf_urls": crop_selection.get("pdf_urls", {}),
                    "updated_at": datetime.utcnow()
                }}
            )
        except Exception as e:
            logger.error(f"Error updating crop selection: {e}")
