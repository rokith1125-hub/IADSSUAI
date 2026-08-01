"""
Weather service for Open-Meteo API integration
"""

import requests
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
from utils.error_handler import APIError

logger = logging.getLogger(__name__)

class WeatherService:
    """Service for weather data operations using Open-Meteo API"""
    
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1"
        self.cache = {}
        self.cache_timeout = 1800  # 30 minutes
        self.request_connect_timeout = max(1.0, float(os.getenv("WEATHER_API_CONNECT_TIMEOUT", "2.0") or 2.0))
        self.request_read_timeout = max(2.0, float(os.getenv("WEATHER_API_READ_TIMEOUT", "4.0") or 4.0))
        self.crop_thresholds = {
            "paddy": {"max_temp": 38, "rain_sensitive": True},
            "rice": {"max_temp": 38, "rain_sensitive": True},
            "groundnut": {"max_temp": 40, "rain_sensitive": False},
            "maize": {"max_temp": 37, "rain_sensitive": True},
            "sugarcane": {"max_temp": 40, "rain_sensitive": False},
            "tomato": {"max_temp": 35, "rain_sensitive": True},
            "onion": {"max_temp": 36, "rain_sensitive": True},
            "cotton": {"max_temp": 39, "rain_sensitive": False},
        }
        
    def get_coordinates(self, location: str) -> Optional[Dict]:
        """Get coordinates for location using geocoding"""
        try:
            # GPS string support: "lat,lon"
            if isinstance(location, str) and "," in location:
                left, right = [p.strip() for p in location.split(",", 1)]
                try:
                    lat = float(left)
                    lon = float(right)
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        return {"lat": lat, "lon": lon}
                except Exception:
                    pass

            # Simple geocoding for common Indian locations
            location_map = {
                "chennai": {"lat": 13.0827, "lon": 80.2707},
                "coimbatore": {"lat": 11.0168, "lon": 76.9558},
                "madurai": {"lat": 9.9252, "lon": 78.1198},
                "tiruchirappalli": {"lat": 10.7905, "lon": 78.7047},
                "salem": {"lat": 11.6643, "lon": 78.1460},
                "tirunelveli": {"lat": 8.7139, "lon": 77.7567},
                "vellore": {"lat": 12.9165, "lon": 79.1325},
                "erode": {"lat": 11.3410, "lon": 77.7172},
                "thoothukkudi": {"lat": 8.7642, "lon": 78.1348},
                "dindigul": {"lat": 10.3629, "lon": 77.9756},
                "thanjavur": {"lat": 10.7870, "lon": 79.1378},
                "kancheepuram": {"lat": 12.8342, "lon": 79.7036},
                "tiruvallur": {"lat": 13.1442, "lon": 79.9084},
                "kanyakumari": {"lat": 8.0883, "lon": 77.5385},
                "karur": {"lat": 10.9603, "lon": 78.0766},
                "namakkal": {"lat": 11.2213, "lon": 78.1652},
                "theni": {"lat": 10.0104, "lon": 77.4768},
                "ramanathapuram": {"lat": 9.3789, "lon": 78.8378},
                "virudhunagar": {"lat": 9.5858, "lon": 77.9579},
                "sivaganga": {"lat": 9.8432, "lon": 78.4809},
                "pudukkottai": {"lat": 10.3803, "lon": 78.8214},
                "nagapattinam": {"lat": 10.7649, "lon": 79.8430},
                "dharmapuri": {"lat": 12.1277, "lon": 78.1579},
                "krishnagiri": {"lat": 12.5186, "lon": 78.2137},
                "ariyalur": {"lat": 11.1379, "lon": 79.0752},
                "perambalur": {"lat": 11.2400, "lon": 78.8822},
                "cuddalore": {"lat": 11.7447, "lon": 79.7680},
                "viluppuram": {"lat": 11.9421, "lon": 79.4873},
                "villupuram": {"lat": 11.9421, "lon": 79.4873},
                "tiruvannamalai": {"lat": 12.2253, "lon": 79.0747},
                "thiruvannamalai": {"lat": 12.2253, "lon": 79.0747},
                "tiruvarur": {"lat": 10.7726, "lon": 79.6368},
                # State/country fallbacks for users with only high-level location in profile.
                "tamil nadu": {"lat": 11.1271, "lon": 78.6569},
                "karnataka": {"lat": 15.3173, "lon": 75.7139},
                "andhra pradesh": {"lat": 15.9129, "lon": 79.7400},
                "kerala": {"lat": 10.8505, "lon": 76.2711},
                "india": {"lat": 20.5937, "lon": 78.9629},
            }
            
            location_lower = location.lower().strip()
            
            # Try exact match first
            if location_lower in location_map:
                return location_map[location_lower]
            
            # Try partial match
            for key, coords in location_map.items():
                if location_lower in key or key in location_lower:
                    return coords
            
            logger.warning(f"Location '{location}' not found in geocoding map")
            return None
            
        except Exception as e:
            logger.error(f"Error getting coordinates: {str(e)}")
            return None
    
    def get_current_weather(self, location: str, longitude: Optional[float] = None) -> Dict:
        """Get current weather for location"""
        if longitude is not None:
            try:
                lat_value = float(location)
                lon_value = float(longitude)
                location = f"{lat_value},{lon_value}"
            except Exception:
                raise APIError("Farm coordinates missing or invalid", 400)

        location = str(location or "").strip()
        if not location:
            raise APIError("Farm coordinates missing. Please set latitude and longitude.", 400)

        cache_key = f"current_{location}"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if datetime.now().timestamp() - timestamp < self.cache_timeout:
                logger.info(f"Using cached weather for {location}")
                return cached_data
        
        try:
            coords = self.get_coordinates(location)
            if not coords:
                raise APIError("Farm coordinates missing or invalid", 400)
            
            # Open-Meteo API parameters
            params = {
                "latitude": coords["lat"],
                "longitude": coords["lon"],
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
                "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,precipitation,rain,showers,snowfall,weather_code,visibility,wind_speed_10m,wind_direction_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_sum,rain_sum,showers_sum,snowfall_sum,precipitation_hours,precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant",
                "timezone": "auto",
                "forecast_days": 3
            }
            
            # Keep weather call bounded to avoid blocking upstream APIs (e.g., disease analysis).
            response = requests.get(
                f"{self.base_url}/forecast",
                params=params,
                timeout=(self.request_connect_timeout, self.request_read_timeout),
            )
            response.raise_for_status()
            data = response.json()
            
            # Process current weather
            current = data.get("current", {})
            daily = data.get("daily", {})
            hourly = data.get("hourly", {})
            
            current_payload = {
                "temperature": current.get("temperature_2m"),
                "feels_like": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "weather_code": current.get("weather_code"),
                "condition": self._get_weather_condition(current.get("weather_code", 0)),
                "wind_speed": current.get("wind_speed_10m"),
                "wind_direction": self._get_wind_direction(current.get("wind_direction_10m", 0)),
                "rain": current.get("rain", 0),
                "showers": current.get("showers", 0),
                "snowfall": current.get("snowfall", 0),
                "cloud_cover": current.get("cloud_cover"),
                "pressure": current.get("pressure_msl"),
                "precipitation": current.get("precipitation", 0),
                "wind_speed_10m": current.get("wind_speed_10m"),
                "relative_humidity_2m": current.get("relative_humidity_2m"),
            }
            # Normalize keys used by downstream farming logic.
            current_payload["rain"] = current.get("rain", current_payload.get("precipitation", 0) or 0)
            current_payload["wind_speed"] = current.get("wind_speed_10m", current_payload.get("wind_speed", 0) or 0)
            current_payload["humidity"] = current.get("relative_humidity_2m", current_payload.get("humidity", 0) or 0)
            current_payload["heat_index"] = self._calculate_heat_index(
                current_payload.get("temperature"),
                current_payload.get("humidity"),
            )

            weather_data = {
                "location": location,
                "timestamp": datetime.now().isoformat(),
                "current": current_payload,
                "today": {
                    "max_temp": daily.get("temperature_2m_max", [None])[0] if daily.get("temperature_2m_max") else None,
                    "min_temp": daily.get("temperature_2m_min", [None])[0] if daily.get("temperature_2m_min") else None,
                    "sunrise": daily.get("sunrise", [None])[0] if daily.get("sunrise") else None,
                    "sunset": daily.get("sunset", [None])[0] if daily.get("sunset") else None,
                    "precipitation": daily.get("precipitation_sum", [0])[0] if daily.get("precipitation_sum") else 0
                },
                "forecast": {
                    "hourly": self._process_hourly_forecast(hourly),
                    "daily": self._process_daily_forecast(daily)
                },
                "alerts": self._generate_weather_alerts({
                    "current": current_payload,
                    "forecast": {
                        "hourly": self._process_hourly_forecast(hourly),
                        "daily": self._process_daily_forecast(daily)
                    }
                })
            }
            
            # Cache the result
            self.cache[cache_key] = (weather_data, datetime.now().timestamp())
            
            return weather_data

        except APIError:
            raise
        except requests.RequestException as e:
            logger.error(f"Error getting weather data: {str(e)}")
            raise APIError("Weather service unavailable", 503)
        except Exception as e:
            logger.error(f"Error getting weather data: {str(e)}")
            raise APIError("Weather service unavailable", 503)
    
    def get_forecast(self, location: str, days: int = 3) -> Dict:
        """Get weather forecast for location"""
        try:
            current_weather = self.get_current_weather(location)
            forecast = current_weather.get("forecast", {}).get("daily", [])
            
            # Limit to requested days
            if len(forecast) > days:
                forecast = forecast[:days]
            
            return {
                "location": location,
                "days": days,
                "forecast": forecast,
                "updated_at": datetime.now().isoformat()
            }

        except APIError:
            raise
        except Exception as e:
            logger.error(f"Error getting forecast: {str(e)}")
            raise APIError("Weather service unavailable", 503)
    
    def get_weather_for_farming(self, location: str, crop_stage: str = None, crop_name: str = None) -> Dict:
        """Get weather data with farming-specific insights"""
        try:
            weather = self.get_current_weather(location)
            current = weather.get("current", {})
            
            # Farming-specific analysis
            farming_advice = self._get_farming_advice(weather, crop_stage, crop_name=crop_name)
            rain_probability_risk = self._calculate_rain_probability_risk(weather)
            
            farming_weather = {
                **weather,
                "farming_analysis": {
                    "irrigation_need": self._calculate_irrigation_need(weather),
                    "spraying_suitable": self._is_spraying_suitable(weather),
                    "harvest_suitable": self._is_harvest_suitable(weather),
                    "soil_moisture_level": self._estimate_soil_moisture(weather),
                    "pest_risk": self._calculate_pest_risk(weather),
                    "rain_probability_risk": rain_probability_risk,
                    "heat_index": current.get("heat_index"),
                    "advice": farming_advice
                }
            }
            farming_weather["confidence"] = "High" if not farming_weather.get("error") else "Low"
            return farming_weather

        except APIError:
            raise
        except Exception as e:
            logger.error(f"Error getting farming weather: {str(e)}")
            raise APIError("Weather service unavailable", 503)
    
    def _get_weather_condition(self, weather_code: int) -> str:
        """Convert weather code to condition string"""
        # WMO Weather interpretation codes (WW)
        weather_codes = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            56: "Light freezing drizzle",
            57: "Dense freezing drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            66: "Light freezing rain",
            67: "Heavy freezing rain",
            71: "Slight snow fall",
            73: "Moderate snow fall",
            75: "Heavy snow fall",
            77: "Snow grains",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail"
        }
        
        return weather_codes.get(weather_code, "Unknown")
    
    def _get_wind_direction(self, degrees: float) -> str:
        """Convert wind direction degrees to cardinal direction"""
        if degrees is None:
            return "Unknown"
        
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", 
                     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        index = round(degrees / 22.5) % 16
        return directions[index]
    
    def _process_hourly_forecast(self, hourly_data: Dict) -> List[Dict]:
        """Process hourly forecast data"""
        if not hourly_data:
            return []
        
        # Get first 24 hours (today)
        hourly_forecast = []
        time_list = hourly_data.get("time", [])[:24]
        
        for i in range(min(24, len(time_list))):
            hourly_forecast.append({
                "time": time_list[i],
                "temperature": hourly_data.get("temperature_2m", [None])[i],
                "humidity": hourly_data.get("relative_humidity_2m", [None])[i],
                "precipitation_probability": hourly_data.get("precipitation_probability", [None])[i],
                "rain": hourly_data.get("rain", [None])[i],
                "wind_speed": hourly_data.get("wind_speed_10m", [None])[i]
            })
        
        return hourly_forecast
    
    def _process_daily_forecast(self, daily_data: Dict) -> List[Dict]:
        """Process daily forecast data"""
        if not daily_data:
            return []
        
        daily_forecast = []
        time_list = daily_data.get("time", [])
        
        for i in range(min(7, len(time_list))):  # Next 7 days
            daily_forecast.append({
                "date": time_list[i],
                "max_temp": daily_data.get("temperature_2m_max", [None])[i],
                "min_temp": daily_data.get("temperature_2m_min", [None])[i],
                "condition": self._get_weather_condition(daily_data.get("weather_code", [0])[i]),
                "precipitation": daily_data.get("precipitation_sum", [0])[i],
                "sunrise": daily_data.get("sunrise", [None])[i],
                "sunset": daily_data.get("sunset", [None])[i],
                "wind_speed": daily_data.get("wind_speed_10m_max", [None])[i]
            })
        
        return daily_forecast
    
    def _generate_weather_alerts(self, weather_data: Dict) -> List[Dict]:
        """Generate weather alerts for farming"""
        alerts = []
        current = weather_data.get("current", {})
        daily = weather_data.get("forecast", {}).get("daily", [])
        hourly = weather_data.get("forecast", {}).get("hourly", [])
        
        # Heavy rain alert
        rain = current.get("rain", 0) or current.get("showers", 0) or current.get("precipitation", 0)
        if rain > 20:  
            alerts.append({
                "type": "heavy_rain",
                "severity": "high",
                "message": "Heavy rain expected. Avoid field activities.",
                "action": "Postpone spraying and fertilizer application",
                "notify": True,
            })
        elif rain > 5:
            alerts.append({
                "type": "rain",
                "severity": "medium",
                "message": "Rain expected today.",
                "action": "Carry out indoor activities"
            })
        
        # High wind alert
        wind_speed = current.get("wind_speed", 0) or current.get("wind_speed_10m", 0)
        if wind_speed > 30:  # km/h
            alerts.append({
                "type": "high_wind",
                "severity": "high",
                "message": "High wind speeds expected.",
                "action": "Avoid spraying and secure farm equipment",
                "notify": True,
            })
        
        # Temperature alerts
        temp = current.get("temperature", 25) if current.get("temperature") is not None else current.get("temperature_2m", 25)
        if temp > 35:
            alerts.append({
                "type": "high_temp",
                "severity": "medium",
                "message": "High temperature expected.",
                "action": "Increase irrigation frequency"
            })
        elif temp < 15:
            alerts.append({
                "type": "low_temp",
                "severity": "medium",
                "message": "Low temperature expected.",
                "action": "Protect sensitive crops"
            })

        # Rain probability alert from hourly forecast.
        rain_prob = 0
        if hourly:
            probabilities = [
                item.get("precipitation_probability")
                for item in hourly[:24]
                if isinstance(item.get("precipitation_probability"), (int, float))
            ]
            rain_prob = max(probabilities) if probabilities else 0
        if rain_prob > 70:
            alerts.append({
                "type": "rain_probability",
                "severity": "high",
                "message": "High rain probability in next 24 hours.",
                "action": "Avoid spraying and plan drainage.",
                "notify": True,
            })
        
        return alerts
    
    def _get_farming_advice(self, weather: Dict, crop_stage: str = None, crop_name: str = None) -> Dict:
        """Get farming advice based on weather"""
        current = weather.get("current", {})
        temp = current.get("temperature", 25)
        rain = current.get("rain", 0) or current.get("showers", 0)
        wind_speed = current.get("wind_speed", 0)
        humidity = current.get("humidity", 60)
        
        advice = {
            "irrigation": "Normal irrigation recommended",
            "spraying": "Suitable for spraying",
            "fertilizer": "Can apply fertilizer",
            "harvest": "Good day for harvest",
            "general": "Normal farming activities can be carried out"
        }
        
        # Adjust based on weather
        if rain > 5:
            advice["spraying"] = "Avoid spraying - rain expected"
            advice["fertilizer"] = "Postpone fertilizer application"
        
        if wind_speed > 20:
            advice["spraying"] = "Avoid spraying - high wind"
        
        if temp > 35:
            advice["irrigation"] = "Increase irrigation frequency"
            advice["spraying"] = "Spray in early morning or late evening"
        
        if humidity > 80:
            advice["spraying"] = "Good for spraying - high humidity helps absorption"
        
        # Crop stage specific advice
        if crop_stage:
            if crop_stage == "flowering" and rain > 10:
                advice["general"] = "Protect flowering crops from heavy rain"
            elif crop_stage == "harvest" and rain > 5:
                advice["harvest"] = "Postpone harvest - rain expected"

        # Crop-specific thresholds
        if crop_name:
            thresholds = self.crop_thresholds.get(str(crop_name).strip().lower(), {})
            max_temp = thresholds.get("max_temp")
            rain_sensitive = thresholds.get("rain_sensitive", False)
            if max_temp is not None and temp > max_temp:
                advice["general"] = f"Temperature above {max_temp}C for {crop_name}; use heat stress protection."
                advice["irrigation"] = "Increase irrigation frequency with short cycles"
            if rain_sensitive and rain > 5:
                advice["spraying"] = "Avoid spraying - crop is rain sensitive"
        
        return advice

    def _calculate_heat_index(self, temperature: Optional[float], humidity: Optional[float]) -> Optional[float]:
        """Calculate heat index in Celsius."""
        if temperature is None or humidity is None:
            return None
        try:
            t = float(temperature)
            rh = float(humidity)
        except Exception:
            return None
        if t < 27:
            return round(t, 2)
        hi = (
            -8.784695
            + 1.61139411 * t
            + 2.338549 * rh
            - 0.14611605 * t * rh
            - 0.012308094 * (t ** 2)
            - 0.016424828 * (rh ** 2)
            + 0.002211732 * (t ** 2) * rh
            + 0.00072546 * t * (rh ** 2)
            - 0.000003582 * (t ** 2) * (rh ** 2)
        )
        return round(hi, 2)

    def _calculate_rain_probability_risk(self, weather: Dict) -> str:
        hourly = weather.get("forecast", {}).get("hourly", []) or []
        probabilities = [
            item.get("precipitation_probability")
            for item in hourly[:24]
            if isinstance(item.get("precipitation_probability"), (int, float))
        ]
        if not probabilities:
            return "Unknown"
        peak = max(probabilities)
        if peak >= 70:
            return "High"
        if peak >= 40:
            return "Medium"
        return "Low"
    
    def _calculate_irrigation_need(self, weather: Dict) -> str:
        """Calculate irrigation need"""
        temp = weather.get("current", {}).get("temperature", 25)
        rain = weather.get("current", {}).get("rain", 0) or weather.get("current", {}).get("showers", 0)
        humidity = weather.get("current", {}).get("humidity", 60)
        
        if rain > 10:
            return "No irrigation needed today"
        elif temp > 35 and humidity < 50:
            return "High irrigation needed"
        elif temp > 30:
            return "Moderate irrigation needed"
        else:
            return "Normal irrigation"
    
    def _is_spraying_suitable(self, weather: Dict) -> bool:
        """Check if spraying is suitable"""
        rain = weather.get("current", {}).get("rain", 0) or weather.get("current", {}).get("showers", 0)
        wind_speed = weather.get("current", {}).get("wind_speed", 0)
        
        return rain < 2 and wind_speed < 20
    
    def _is_harvest_suitable(self, weather: Dict) -> bool:
        """Check if harvest is suitable"""
        rain = weather.get("current", {}).get("rain", 0) or weather.get("current", {}).get("showers", 0)
        
        return rain < 5
    
    def _estimate_soil_moisture(self, weather: Dict) -> str:
        """Estimate soil moisture level"""
        rain = weather.get("current", {}).get("rain", 0) or weather.get("current", {}).get("showers", 0)
        temp = weather.get("current", {}).get("temperature", 25)
        
        if rain > 20:
            return "Very High (risk of waterlogging)"
        elif rain > 10:
            return "High"
        elif rain > 5:
            return "Moderate"
        elif temp > 35:
            return "Low (needs irrigation)"
        else:
            return "Normal"
    
    def _calculate_pest_risk(self, weather: Dict) -> str:
        """Calculate pest risk level"""
        humidity = weather.get("current", {}).get("humidity", 60)
        temp = weather.get("current", {}).get("temperature", 25)
        
        if humidity > 80 and temp > 25:
            return "High (fungal disease risk)"
        elif humidity > 70:
            return "Medium"
        else:
            return "Low"
    
    def _get_fallback_weather(self, location: str) -> Dict:
        """[DEPRECATED] Only returns empty/error state to enforce real data policy"""
        return {"error": "Weather data unavailable", "location": location}
    
    def clear_cache(self):
        """Clear weather cache"""
        self.cache.clear()
        logger.info("Weather cache cleared")
