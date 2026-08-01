"""
Open-Meteo weather engine
"""

import logging
from datetime import datetime

from services.local_storage import db_service
from services.weather_service import WeatherService
from services.llm_service import LLMService
from utils.error_handler import APIError

logger = logging.getLogger(__name__)


class WeatherEngine:
    """Weather engine for Open-Meteo integration"""

    def __init__(self):
        self.db_service = db_service
        self.weather_service = WeatherService()
        self.llm_service = LLMService()
        self.request_cache = {}
        self.request_cache_seconds = 30

    def get_user_weather(self, user_id, lang="en", location_override=None):
        """Get weather for user's location with localized insights"""
        try:
            location = self._resolve_location(user_id, location_override)
            if not location:
                raise APIError("Farm coordinates missing. Please update farm latitude and longitude.", 400)

            weather = self._get_throttled_weather(user_id, location, channel="current")

            crop = self._get_current_crop(user_id)
            if crop:
                crop_stage = crop.get("growth_timeline", {}).get("current_stage")
                crop_name = crop.get("crop_name") or crop.get("selected_crop") or "Unknown"
                weather["crop_context"] = {
                    "crop_name": crop_name,
                    "current_stage": crop_stage,
                    "weather_impact": self._get_crop_weather_impact(weather, crop_stage, lang=lang),
                }

            return weather

        except Exception as e:
            logger.error(f"Error getting user weather: {str(e)}")
            raise

    def get_forecast(self, user_id, days=3, location_override=None):
        """Get weather forecast"""
        try:
            location = self._resolve_location(user_id, location_override)
            if not location:
                raise APIError("Farm coordinates missing. Please update farm latitude and longitude.", 400)

            forecast = self.weather_service.get_forecast(location, days)
            return forecast

        except Exception as e:
            logger.error(f"Error getting forecast: {str(e)}")
            raise

    def get_farming_weather(self, user_id, lang="en", location_override=None):
        """Get weather with farming-specific insights"""
        try:
            location = self._resolve_location(user_id, location_override)
            if not location:
                raise APIError("Farm coordinates missing. Please update farm latitude and longitude.", 400)

            crop = self._get_current_crop(user_id)
            crop_stage = None
            crop_name = None
            if crop:
                crop_stage = crop.get("growth_timeline", {}).get("current_stage")
                crop_name = crop.get("crop_name") or crop.get("selected_crop")

            farming_weather = self.weather_service.get_weather_for_farming(location, crop_stage, crop_name=crop_name)
            farming_weather["summary"] = self._get_localized_weather_summary(farming_weather, lang)
            has_current = isinstance(farming_weather.get("current"), dict) and bool(farming_weather.get("current"))
            farming_weather["confidence"] = "High" if (not farming_weather.get("error") and has_current) else "Low"
            if crop_name:
                farming_weather["crop_context"] = {"crop_name": crop_name, "crop_stage": crop_stage}
            return farming_weather

        except Exception as e:
            logger.error(f"Error getting farming weather: {str(e)}")
            raise

    def get_weather_alerts(self, user_id, location_override=None):
        """Get weather alerts for farming"""
        try:
            location = self._resolve_location(user_id, location_override)
            if not location:
                raise APIError("Farm coordinates missing. Please update farm latitude and longitude.", 400)

            weather = self._get_throttled_weather(user_id, location, channel="alerts")
            alerts = weather.get("alerts", [])

            farming_alerts = self._generate_farming_alerts(weather)
            alerts.extend(farming_alerts)

            return alerts

        except Exception as e:
            logger.error(f"Error getting weather alerts: {str(e)}")
            raise

    def get_supported_locations(self):
        """Get list of supported locations"""
        return [
            "Chennai",
            "Coimbatore",
            "Madurai",
            "Tiruchirappalli",
            "Salem",
            "Tirunelveli",
            "Vellore",
            "Erode",
            "Thoothukkudi",
            "Dindigul",
            "Thanjavur",
            "Kancheepuram",
            "Tiruvallur",
            "Kanyakumari",
            "Karur",
            "Namakkal",
            "Theni",
            "Ramanathapuram",
            "Virudhunagar",
            "Sivaganga",
        ]

    def _get_user_location(self, user_id):
        """Get user location from database"""
        try:
            user_collection = self.db_service.get_collection("users")
            user = user_collection.find_one({"user_id": user_id})

            if user:
                farm_info = user.get("farm_info", {}) or {}
                profile = user.get("profile", {}) or {}
                lat = farm_info.get("latitude") or profile.get("latitude")
                lon = farm_info.get("longitude") or profile.get("longitude")
                if lat is not None and lon is not None:
                    try:
                        return f"{float(lat)},{float(lon)}"
                    except Exception:
                        pass

                location = farm_info.get("district") or farm_info.get("state")
                if location and str(location).strip():
                    return str(location).strip()

            return None

        except Exception as e:
            logger.error(f"Error getting user location: {str(e)}")
            return None

    def _resolve_location(self, user_id, location_override=None):
        if location_override and str(location_override).strip():
            return str(location_override).strip()
        return self._get_user_location(user_id)

    def _get_throttled_weather(self, user_id, location, channel="current"):
        """Simple user-level throttle to avoid external API bursts."""
        key = f"{user_id}:{channel}"
        now = datetime.utcnow().timestamp()
        cached = self.request_cache.get(key)
        if cached:
            last_ts = cached.get("ts", 0)
            if now - last_ts < self.request_cache_seconds and cached.get("location") == location:
                return cached.get("data")
        weather = self.weather_service.get_current_weather(location)
        self.request_cache[key] = {"ts": now, "location": location, "data": weather}
        return weather

    def _get_current_crop(self, user_id):
        """Get user's current crop"""
        try:
            crop_collection = self.db_service.get_collection("crop_selections")
            crop = crop_collection.find_one(
                {"user_id": user_id, "is_active": True},
                {"_id": 0},
                sort=[("selected_at", -1)],
            )
            return crop
        except Exception as e:
            logger.error(f"Error getting current crop: {str(e)}")
            return None

    def _get_crop_weather_impact(self, weather, crop_stage, lang="en"):
        """Get weather impact on crop using LLM"""
        try:
            language_name = "Tamil" if lang == "ta" else "English"
            current = weather.get("current", {})
            prompt = f"""
            As an agrometeorologist, analyze this weather for a {crop_stage} stage crop in {language_name}.
            Weather: {current.get('temperature')}C, {current.get('rain')}mm rain, {current.get('humidity')}% humidity.

            Provide:
            1. Suitability (True/False)
            2. Major concern (1 sentence)
            3. Recommendation (1 sentence)

            Format as JSON.
            """
            try:
                response = self.llm_service.generate_structured_response(prompt)
            except Exception:
                return self._get_fallback_weather_impact(weather, crop_stage)
            if not isinstance(response, dict):
                return self._get_fallback_weather_impact(weather, crop_stage)
            return {
                "suitable": bool(response.get("suitability", response.get("suitable", True))),
                "concerns": [response.get("concern")] if response.get("concern") else [],
                "recommendations": [response.get("recommendation")] if response.get("recommendation") else [],
            }
        except Exception:
            return self._get_fallback_weather_impact(weather, crop_stage)

    def _get_localized_weather_summary(self, farming_weather, lang="en"):
        """Generate short localized weather summary for weather cards."""
        current = farming_weather.get("current", {})
        farming = farming_weather.get("farming_analysis", {})

        temp = current.get("temperature")
        condition = current.get("condition", "Unknown")
        irrigation_need = farming.get("irrigation_need", "Check soil moisture before irrigation")
        spraying_suitable = farming.get("spraying_suitable", False)

        if lang == "mixed":
            spray_text = "Today spraying pannalaam." if spraying_suitable else "Today spraying avoid pannunga."
        elif lang == "ta":
            spray_text = "Spraying can be done today." if spraying_suitable else "Avoid spraying today."
        else:
            spray_text = "Spraying is suitable today." if spraying_suitable else "Avoid spraying today."

        if temp is None:
            return f"{condition}. {irrigation_need}. {spray_text}"
        return f"{temp}C, {condition}. {irrigation_need}. {spray_text}"

    def _get_fallback_weather_impact(self, weather, crop_stage):
        """Fallback rule-based impact"""
        current = weather.get("current", {})
        temp = current.get("temperature", 25)
        rain = current.get("rain", 0) or current.get("showers", 0)
        humidity = current.get("humidity", 60)

        impact = {
            "suitable": True,
            "concerns": [],
            "recommendations": [],
        }

        if temp > 35:
            impact["concerns"].append("High temperature")
            impact["recommendations"].append("Increase irrigation frequency")
        elif temp < 15:
            impact["concerns"].append("Low temperature")
            impact["recommendations"].append("Protect sensitive plants")

        if rain > 20:
            impact["concerns"].append("Heavy rain")
            impact["recommendations"].append("Ensure proper drainage")
            impact["suitable"] = False
        elif rain > 5:
            impact["concerns"].append("Rain expected")
            impact["recommendations"].append("Postpone spraying if planned")

        if crop_stage == "Flowering" and rain > 10:
            impact["concerns"].append("Rain during flowering")
            impact["recommendations"].append("Consider pollination assistance")
            impact["suitable"] = False

        if crop_stage == "Harvest" and rain > 5:
            impact["concerns"].append("Rain during harvest")
            impact["recommendations"].append("Postpone harvest if possible")
            impact["suitable"] = False

        if humidity > 80 and crop_stage in ["Fruiting", "Ripening"]:
            impact["concerns"].append("High humidity")
            impact["recommendations"].append("Monitor for fungal diseases")

        if not impact["concerns"]:
            impact["recommendations"].append("Weather conditions favorable for farming")

        return impact

    def _generate_farming_alerts(self, weather):
        """Generate farming-specific weather alerts"""
        current = weather.get("current", {})
        alerts = []

        temp = current.get("temperature", 25)
        rain = current.get("rain", 0) or current.get("showers", 0)
        wind_speed = current.get("wind_speed", 0)

        if temp > 38:
            alerts.append(
                {
                    "type": "extreme_heat",
                    "severity": "high",
                    "message": "Extreme heat warning",
                    "action": "Increase irrigation, provide shade if possible",
                    "notify": True,
                }
            )
        elif temp > 35:
            alerts.append(
                {
                    "type": "high_temp",
                    "severity": "medium",
                    "message": "High temperature",
                    "action": "Water plants in morning and evening",
                }
            )
        elif temp < 12:
            alerts.append(
                {
                    "type": "low_temp",
                    "severity": "medium",
                    "message": "Low temperature",
                    "action": "Protect sensitive crops from cold",
                }
            )

        if rain > 30:
            alerts.append(
                {
                    "type": "heavy_rain",
                    "severity": "high",
                    "message": "Heavy rain expected",
                    "action": "Avoid field activities. Ensure drainage.",
                    "notify": True,
                }
            )
        elif rain > 15:
            alerts.append(
                {
                    "type": "moderate_rain",
                    "severity": "medium",
                    "message": "Moderate rain expected",
                    "action": "Postpone spraying and fertilizer application",
                }
            )

        if wind_speed > 40:
            alerts.append(
                {
                    "type": "strong_wind",
                    "severity": "high",
                    "message": "Strong winds expected",
                    "action": "Secure farm equipment and structures",
                    "notify": True,
                }
            )
        elif wind_speed > 25:
            alerts.append(
                {
                    "type": "windy",
                    "severity": "medium",
                    "message": "Windy conditions",
                    "action": "Avoid spraying. Harvest ripe fruits.",
                }
            )

        return alerts
