"""
Dashboard aggregation logic
"""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from services.local_storage import db_service
from services.weather_service import WeatherService
from services.llm_service import LLMService
from services.market_service import MarketService
from services.news_service import NewsService
from utils.date_utils import get_current_season, format_date
from utils.localization import get_message
import time

logger = logging.getLogger(__name__)

class DashboardAggregator:
    """Dashboard data aggregation engine"""
    
    def __init__(self):
        self.db_service = db_service
        self.weather_service = WeatherService()
        self.llm_service = LLMService()
        self.market_service = MarketService()
        self.news_service = NewsService()
        self.cache = {}
        self.cache_timeout = 300  # 5 minutes
        self.enable_llm_summary = os.getenv("ENABLE_LLM_DASHBOARD_SUMMARY", "false").lower() == "true"
        
    def get_dashboard_data(self, user_id, force_refresh=False):
        """Get complete dashboard data for user"""
        cache_key = f"dashboard_{user_id}"
        
        # Check cache
        if not force_refresh and cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_timeout:
                logger.info(f"Using cached dashboard for user {user_id}")
                return cached_data
        
        logger.info(f"Building dashboard for user {user_id}")
        
        # Get user context
        user_context = self._get_user_context(user_id)
        
        # Build dashboard data
        dashboard_data = {
            "navbar": self._get_navbar_data(user_context),
            "cards": self._get_all_cards(user_context),
            "summary": self._get_dashboard_summary(user_context),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Cache the result
        self.cache[cache_key] = (dashboard_data, time.time())
        
        return dashboard_data
    
    def _get_user_context(self, user_id):
        """Get user context from database"""
        user_collection = self.db_service.get_collection('users')
        soil_collection = self.db_service.get_collection('soil_results')
        crop_collection = self.db_service.get_collection('crop_selections')
        disease_collection = self.db_service.get_collection('disease_results')
        
        user = user_collection.find_one({"user_id": user_id})
        if not user:
            raise Exception("User not found")
        
        # Get latest soil result
        soil_result = soil_collection.find_one(
            {"user_id": user_id},
            sort=[("created_at", -1)]
        )
        
        # Get latest crop selection
        crop_selection = crop_collection.find_one(
            {"user_id": user_id},
            sort=[("created_at", -1)]
        )
        
        # Get latest disease result
        disease_result = disease_collection.find_one(
            {"user_id": user_id},
            sort=[("created_at", -1)]
        )
        
        # Get user location
        farm_info = user.get('farm_info', {}) or {}
        location = farm_info.get('district') or farm_info.get('state') or 'Tamil Nadu'
        
        return {
            "user_id": user_id,
            "location": location,
            "soil_result": soil_result,
            "crop_selection": crop_selection,
            "disease_result": disease_result,
            "user_settings": user.get('settings', {}),
            "farm_info": farm_info
        }
    
    def _get_navbar_data(self, user_context):
        """Get navbar data"""
        location = user_context['location']
        
        # Get current weather for location
        try:
            weather = self.weather_service.get_current_weather(location)
            current = weather.get("current", {}) if isinstance(weather, dict) else {}
            temperature_value = current.get("temperature")
            temperature = f"{temperature_value}°C" if temperature_value is not None else 'N/A'
            condition = current.get("condition", 'Unknown')
        except:
            temperature = 'N/A'
            condition = 'Unknown'
        
        return {
            "location": location,
            "temperature": temperature,
            "condition": condition,
            "date": datetime.now().strftime("%d %b %Y"),
            "season": get_current_season()
        }
    
    def _get_all_cards(self, user_context):
        """Get data for all dashboard cards"""
        card_builders = {
            "weather": self._get_weather_card,
            "soil": self._get_soil_card,
            "crop": self._get_crop_card,
            "disease": self._get_disease_card,
            "fertilizer": self._get_fertilizer_card,
            "growth": self._get_growth_card,
            "market": self._get_market_card,
            "news": self._get_news_card,
            "recent_results": self._get_recent_results,
        }

        cards = {}
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                key: executor.submit(builder, user_context)
                for key, builder in card_builders.items()
            }
            for key, future in futures.items():
                try:
                    cards[key] = future.result(timeout=12)
                except FuturesTimeoutError:
                    logger.warning("Dashboard card timed out: %s", key)
                    cards[key] = {"status": "yellow", "message": "Data unavailable", "icon": "⚠️"}
                except Exception as e:
                    logger.warning("Dashboard card failed: %s (%s)", key, str(e))
                    cards[key] = {"status": "yellow", "message": "Data unavailable", "icon": "⚠️"}
        return cards
    
    def _get_weather_card(self, user_context):
        """Weather alert card logic"""
        location = user_context['location']
        
        try:
            weather = self.weather_service.get_current_weather(location)
            if isinstance(weather, dict) and weather.get("error"):
                raise Exception(weather.get("error"))

            current = weather.get("current", {})
            hourly = weather.get("forecast", {}).get("hourly", [])
            rain_probability = 0
            if hourly:
                next_hours = hourly[:12]
                rain_probability = max([(h.get("precipitation_probability") or 0) for h in next_hours])
            current_rain = (current.get("rain") or 0) + (current.get("showers") or 0)
            
            # Determine alert level
            alert_level = "green"
            message = "Weather conditions are favorable for farming"
            
            if rain_probability >= 70 or current_rain > 8:
                alert_level = "red"
                message = "Heavy rain expected. Avoid spraying and fertilizer application."
            elif rain_probability >= 40 or current_rain > 2:
                alert_level = "yellow"
                message = "Rain likely. Plan activities accordingly."
            elif (current.get("temperature") or 25) > 35:
                alert_level = "yellow"
                message = "High temperature. Ensure proper irrigation."
            
            return {
                "status": alert_level,
                "message": message,
                "temperature": current.get("temperature", 'N/A'),
                "humidity": current.get("humidity", 'N/A'),
                "rain_probability": rain_probability,
                "wind_speed": current.get("wind_speed", 0),
                "icon": self._get_weather_icon(current.get("condition", 'clear')),
                "updated_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Weather card error: {str(e)}")
            return {
                "status": "yellow",
                "message": "Weather data temporarily unavailable",
                "icon": "⚠️",
                "updated_at": datetime.utcnow().isoformat()
            }
    
    def _get_soil_card(self, user_context):
        """Soil status card logic"""
        soil_result = user_context.get('soil_result')
        lang = user_context.get('user_settings', {}).get('language', 'en')
        
        if not soil_result:
            return {
                "status": "yellow",
                "message": get_message("no_soil_data", lang),
                "action": get_message("analyze_soil_action", lang),
                "icon": "🧪"
            }
        
        soil_name = soil_result.get('soil_name', 'Unknown')
        fertility = soil_result.get('fertility', 'Medium')
        
        # Determine status based on fertility
        if fertility == 'High':
            status = "green"
            message = get_message("soil_high_fertility", lang).format(soil_name=soil_name)
        elif fertility == 'Medium':
            status = "yellow"
            message = get_message("soil_medium_fertility", lang).format(soil_name=soil_name)
        else:
            status = "red"
            message = get_message("soil_low_fertility", lang).format(soil_name=soil_name)
        
        return {
            "status": status,
            "message": message,
            "soil_name": soil_name,
            "fertility": fertility,
            "last_checked": soil_result.get('created_at', ''),
            "icon": "🧱"
        }
    
    def _get_crop_card(self, user_context):
        """Crop card logic"""
        crop_selection = user_context.get('crop_selection')
        lang = user_context.get('user_settings', {}).get('language', 'en')
        
        if not crop_selection:
            return {
                "status": "yellow",
                "message": get_message("no_crop_data", lang),
                "action": get_message("select_crop_action", lang),
                "icon": "🌾"
            }
        
        crop_name = crop_selection.get('crop_name', 'Unknown')
        image_url = crop_selection.get('image_url', '')
        stage = crop_selection.get('current_stage', 'Not started')
        
        return {
            "status": "green",
            "crop_name": crop_name,
            "stage": stage,
            "image_url": image_url,
            "message": get_message("crop_stage_msg", lang).format(crop_name=crop_name, stage=stage),
            "icon": "🌱"
        }
    
    def _get_disease_card(self, user_context):
        """Disease card logic"""
        disease_result = user_context.get('disease_result')
        lang = user_context.get('user_settings', {}).get('language', 'en')
        
        if not disease_result:
            return {
                "status": "green",
                "message": get_message("no_disease_data", lang),
                "icon": "✅"
            }
        
        disease_name = disease_result.get('disease_name', 'Unknown')
        severity = disease_result.get('severity', 'Low')
        
        # Determine status based on severity
        if severity == 'High':
            status = "red"
            message = get_message("disease_detected_high", lang).format(disease_name=disease_name)
        elif severity == 'Medium':
            status = "yellow"
            message = get_message("disease_detected_medium", lang).format(disease_name=disease_name)
        else:
            status = "green"
            message = get_message("disease_detected_low", lang).format(disease_name=disease_name)
        
        return {
            "status": status,
            "disease_name": disease_name,
            "severity": severity,
            "message": message,
            "last_detected": disease_result.get('created_at', ''),
            "icon": "🦠"
        }
    
    def _get_fertilizer_card(self, user_context):
        """Fertilizer card logic"""
        user_id = user_context['user_id']
        lang = user_context.get('user_settings', {}).get('language', 'en')
        
        # Get fertilizer schedule from DB
        schedule_collection = self.db_service.get_collection('fertilizer_schedules')
        next_schedule = schedule_collection.find_one(
            {"user_id": user_id, "status": "pending"},
            sort=[("scheduled_date", 1)]
        )
        
        if not next_schedule:
            return {
                "status": "green",
                "message": get_message("no_fertilizer_data", lang),
                "icon": "💊"
            }
        
        fertilizer_name = next_schedule.get('fertilizer_name', 'Urea')
        due_date = next_schedule.get('scheduled_date', '')
        
        return {
            "status": "yellow",
            "message": get_message("next_fertilizer_msg", lang).format(fertilizer=fertilizer_name),
            "fertilizer": fertilizer_name,
            "due_date": due_date,
            "icon": "💊"
        }
    
    def _get_growth_card(self, user_context):
        """Growth card logic"""
        crop_selection = user_context.get('crop_selection')
        lang = user_context.get('user_settings', {}).get('language', 'en')
        
        if not crop_selection:
            return {
                "status": "yellow",
                "message": get_message("no_growth_data", lang),
                "icon": "📈"
            }
        
        stage = crop_selection.get('current_stage', 'Vegetative')
        progress = crop_selection.get('progress_percent', 0)
        
        return {
            "status": "green",
            "stage": stage,
            "progress": progress,
            "message": get_message("growth_progress_msg", lang).format(stage=stage, progress=progress),
            "icon": "🌿"
        }
    
    def _get_market_card(self, user_context):
        """Market card logic"""
        crop_selection = user_context.get('crop_selection')
        lang = user_context.get('user_settings', {}).get('language', 'en')
        
        if not crop_selection:
            return {
                "status": "yellow",
                "message": get_message("no_crop_data", lang),
                "icon": "💰"
            }
        
        crop_name = crop_selection.get('crop_name', 'Rice')
        location = user_context.get('location', 'Tamil Nadu')
        
        try:
            market_data = self.market_service.get_mandi_prices(crop_name, district=location)
            if not market_data or market_data.get("error") or not market_data.get("prices"):
                return {
                    "status": "yellow",
                    "message": market_data.get("error", get_message("no_data", lang)) if isinstance(market_data, dict) else get_message("no_data", lang),
                    "icon": "📊"
                }

            latest_price = market_data['prices'][0].get('modal_price', 0)
            trend_data = self.market_service._analyze_price_trend(crop_name)
            trend = (trend_data or {}).get("trend", "UNKNOWN")

            if trend == "UP":
                decision = "WAIT"
                trend_label = get_message("market_trend_up", lang)
                advisory = get_message("market_advice_wait", lang).format(crop_name=crop_name)
                status = "green"
            elif trend == "DOWN":
                decision = "SELL"
                trend_label = get_message("market_trend_down", lang)
                advisory = get_message("market_advice_sell", lang).format(crop_name=crop_name)
                status = "yellow"
            elif trend == "STABLE":
                decision = "WAIT"
                trend_label = get_message("market_trend_stable", lang)
                advisory = get_message("market_advice_wait", lang).format(crop_name=crop_name)
                status = "green"
            else:
                decision = "UNAVAILABLE"
                trend_label = "Unknown"
                advisory = get_message("no_data", lang)
                status = "yellow"
            
            return {
                "status": status,
                "decision": get_message("market_wait", lang) if decision == "WAIT" else (get_message("market_sell", lang) if decision == "SELL" else decision),
                "price": latest_price,
                "trend": trend_label,
                "message": advisory,
                "icon": "📊"
            }
        except Exception:
            return {
                "status": "yellow",
                "message": get_message("no_data", lang),
                "icon": "📊"
            }
    
    def _get_news_card(self, user_context):
        """News card logic"""
        lang = user_context.get('user_settings', {}).get('language', 'en')
        
        try:
            # Use real-time news with user language
            news = self.news_service.get_todays_agricultural_news(lang=lang, limit=3)
            headlines = [item['title'] for item in news]
            
            if not headlines:
                raise Exception("No news")
                
            return {
                "status": "info",
                "title": get_message("news_headlines_label", lang),
                "headlines": headlines,
                "icon": "📰"
            }
        except:
            return {
                "status": "info",
                "message": get_message("no_news_data", lang),
                "icon": "📰"
            }
    
    def _get_recent_results(self, user_context):
        """Recent results logic"""
        user_id = user_context['user_id']
        
        # Get recent results from all modules
        recent_results = []
        
        collections = [
            ('soil_results', 'Soil Analysis', '🧱'),
            ('crop_selections', 'Crop Selection', '🌾'),
            ('disease_results', 'Disease Detection', '🦠'),
            ('fertilizer_schedules', 'Fertilizer Plan', '💊')
        ]
        
        for collection_name, label, icon in collections:
            collection = self.db_service.get_collection(collection_name)
            result = collection.find_one(
                {"user_id": user_id},
                sort=[("created_at", -1)],
                projection={"_id": 0, "created_at": 1, "result_summary": 1}
            )
            
            if result:
                recent_results.append({
                    "type": label,
                    "icon": icon,
                    "summary": result.get('result_summary', 'Analysis completed'),
                    "date": result.get('created_at', '')
                })
        
        return recent_results[:3]  # Return only 3 most recent
    
    def _get_dashboard_summary(self, user_context):
        """Get dashboard summary"""
        if not self.enable_llm_summary:
            crop_name = (user_context.get('crop_selection') or {}).get('crop_name')
            soil_name = (user_context.get('soil_result') or {}).get('soil_name')
            if crop_name:
                return f"{crop_name} workflow is active. Track weather, fertilizer, and growth updates today."
            if soil_name:
                return f"Soil analysis completed ({soil_name}). Next step is crop selection to start the farming plan."
            return "Welcome to your farming dashboard. Complete soil analysis and crop selection for personalized recommendations."

        # Generate summary using LLM
        try:
            summary_prompt = f"""
            User Context:
            - Location: {user_context['location']}
            - Soil: {user_context.get('soil_result', {}).get('soil_name', 'Not analyzed')}
            - Crop: {user_context.get('crop_selection', {}).get('crop_name', 'Not selected')}
            - Disease: {user_context.get('disease_result', {}).get('disease_name', 'None detected')}
            
            Generate a brief (2-3 sentence) farming summary for today.
            """
            
            summary = self.llm_service.generate_response(summary_prompt, max_tokens=100)
            return summary.strip()
        except:
            return "Welcome to your farming dashboard. Complete soil analysis and crop selection for personalized recommendations."
    
    def _get_weather_icon(self, condition):
        """Get weather icon based on condition"""
        icon_map = {
            'clear': '☀️',
            'cloudy': '☁️',
            'rain': '🌧️',
            'storm': '⛈️',
            'wind': '💨',
            'fog': '🌫️',
            'snow': '❄️'
        }
        return icon_map.get(condition.lower(), '☀️')
    
    def get_quick_summary(self, user_id):
        """Get quick summary for dashboard"""
        user_context = self._get_user_context(user_id)
        
        # Handle None values safely
        crop_selection = user_context.get('crop_selection') or {}
        soil_result = user_context.get('soil_result') or {}
        disease_result = user_context.get('disease_result') or {}
        
        return {
            "active_crop": crop_selection.get('crop_name', 'None'),
            "soil_status": soil_result.get('fertility', 'Unknown'),
            "disease_alert": disease_result.get('severity', 'None'),
            "next_action": "Check weather forecast for today"
        }
    
    def get_card_data(self, user_id, card_type):
        """Get specific card data"""
        user_context = self._get_user_context(user_id)
        
        card_methods = {
            'weather': self._get_weather_card,
            'soil': self._get_soil_card,
            'crop': self._get_crop_card,
            'disease': self._get_disease_card,
            'fertilizer': self._get_fertilizer_card,
            'growth': self._get_growth_card,
            'market': self._get_market_card,
            'news': self._get_news_card
        }
        
        if card_type in card_methods:
            return card_methods[card_type](user_context)
        else:
            raise Exception(f"Unknown card type: {card_type}")
    
    def get_alerts(self, user_id):
        """Get active alerts for user"""
        user_context = self._get_user_context(user_id)
        alerts = []
        
        # Check various conditions for alerts
        weather_card = self._get_weather_card(user_context)
        if weather_card['status'] in ['red', 'yellow']:
            alerts.append({
                "type": "weather",
                "severity": weather_card['status'],
                "message": weather_card['message'],
                "timestamp": datetime.utcnow().isoformat()
            })
        
        disease_card = self._get_disease_card(user_context)
        if disease_card['status'] in ['red', 'yellow']:
            alerts.append({
                "type": "disease",
                "severity": disease_card['status'],
                "message": disease_card['message'],
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Add more alert checks as needed
        
        return alerts

    def get_next_steps(self, user_id, lang='en'):
        """Compute farmer-first next steps based on mandatory flow."""
        user_context = self._get_user_context(user_id)
        steps = []

        soil = user_context.get('soil_result')
        crop = user_context.get('crop_selection')

        if not soil:
            steps.append({
                "id": "soil_analysis",
                "label": get_message("analyze_soil_action", lang),
                "cta": "/api/soil/analyze",
                "reason": "Soil not analyzed yet",
                "priority": 1
            })
        elif not crop:
            steps.append({
                "id": "crop_recommendation",
                "label": get_message("select_crop_action", lang),
                "cta": "/api/crop/recommend",
                "reason": "Crop not selected",
                "priority": 1
            })
        else:
            # Fertilizer schedule pending?
            schedule_collection = self.db_service.get_collection('fertilizer_schedules')
            pending = schedule_collection.find_one(
                {"user_id": user_id, "status": "pending"},
                sort=[("scheduled_date", 1)]
            )
            if pending:
                steps.append({
                    "id": "fertilizer_next",
                    "label": get_message("next_fertilizer_msg", lang).format(
                        fertilizer=pending.get('fertilizer_name', 'Fertilizer')
                    ),
                    "cta": "/api/fertilizer/today",
                    "reason": "Fertilizer due soon",
                    "priority": 2
                })

            # Growth monitor
            steps.append({
                "id": "growth_monitor",
                "label": get_message("growth_progress_msg", lang).format(
                    stage=crop.get('current_stage', 'Vegetative'),
                    progress=crop.get('progress_percent', 0)
                ),
                "cta": "/api/growth/status",
                "reason": "Track current stage",
                "priority": 3
            })

            # Disease check reminder
            steps.append({
                "id": "disease_scan",
                "label": get_message("no_disease_data", lang),
                "cta": "/api/disease/detect",
                "reason": "Routine disease check recommended",
                "priority": 4
            })

            # Market watch
            steps.append({
                "id": "market_watch",
                "label": get_message("market_advice_wait", lang).format(
                    crop_name=crop.get('crop_name', '')
                ),
                "cta": "/api/market/prices",
                "reason": "Check prices before harvest",
                "priority": 5
            })

        # Sort by priority and return top 3
        steps = sorted(steps, key=lambda s: s.get('priority', 99))
        return steps[:3]
    
    def clear_cache(self, user_id=None):
        """Clear dashboard cache"""
        if user_id:
            cache_key = f"dashboard_{user_id}"
            if cache_key in self.cache:
                del self.cache[cache_key]
                logger.info(f"Cleared cache for user {user_id}")
        else:
            self.cache.clear()
            logger.info("Cleared all dashboard cache")
    
    def get_current_timestamp(self):
        """Get current timestamp"""
        return datetime.utcnow().isoformat()
