"""
Fertilizer scheduler with weather-aware planning
"""

import json
import logging
import os
from datetime import datetime, timedelta, date
from services.local_storage import db_service
from services.weather_service import WeatherService
from services.llm_service import LLMService
from utils.error_handler import APIError
from utils.date_utils import get_current_season
from utils.path_utils import get_dataset_path
from utils.localization import get_message

logger = logging.getLogger(__name__)

class FertilizerScheduler:
    """Fertilizer scheduling engine"""
    
    def __init__(self):
        self.db_service = db_service
        self.weather_service = WeatherService()
        self.llm_service = LLMService()
        self.enable_llm_guidance = os.getenv("ENABLE_LLM_FERTILIZER_GUIDANCE", "false").lower() == "true"
        self.fertilizer_dataset = self._load_fertilizer_dataset()
        self.growth_dataset = self._load_growth_dataset()
        
    def _load_fertilizer_dataset(self):
        """Load fertilizer dataset from JSON"""
        try:
            dataset_path = get_dataset_path('fertilizer_data.json')
            with open(dataset_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading fertilizer dataset: {str(e)}")
            return []
    
    def _load_growth_dataset(self):
        """Load growth dataset from JSON"""
        try:
            dataset_path = get_dataset_path('growth_data.json')
            with open(dataset_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading growth dataset: {str(e)}")
            return []
    
    def get_fertilizer_plan(self, user_id, lang="en"):
        """Get fertilizer plan for user's current crop"""
        try:
            # Get user's current crop
            crop = self._get_current_crop(user_id)
            if not crop:
                raise APIError("No crop selected. Please select a crop first.", 400)
            
            crop_name = crop.get('crop_name') or crop.get('selected_crop')
            if not crop_name:
                raise APIError("No crop selected. Please select a crop first.", 400)
            crop_selection_id = crop.get("_id")
            crop_timeline = crop.get("growth_timeline", {}) or {}
            crop_start_date = crop_timeline.get("start_date")
            crop_details = crop.get('crop_details', {})
            
            # Get soil information
            soil_info = self._get_soil_info(user_id)
            
            # Get existing plan or create new
            existing_plan = self._get_existing_plan(user_id, crop_name, crop_selection_id)
            if existing_plan:
                return existing_plan
            
            # Create new fertilizer plan
            plan = self._create_fertilizer_plan(
                user_id=user_id,
                crop_name=crop_name,
                crop_details=crop_details,
                soil_info=soil_info,
                start_date=crop_start_date,
                crop_selection_id=crop_selection_id,
                lang=lang
            )
            
            return plan
            
        except Exception as e:
            logger.error(f"Error getting fertilizer plan: {str(e)}")
            raise
    
    def get_today_action(self, user_id, lang="en"):
        """Get today's fertilizer action"""
        try:
            plan = self.get_fertilizer_plan(user_id, lang=lang)
            if not plan:
                return {"action": "NONE", "message": "No fertilizer plan available"}
            
            schedule = plan.get('schedule', [])
            user_location = self._get_user_location(user_id)
            weather_data = None
            
            if user_location:
                try:
                    weather_data = self.weather_service.get_current_weather(user_location)
                except:
                    pass
            
            today = datetime.now().date()
            
            for i, stage in enumerate(schedule):
                stage_date = self._coerce_stage_date(stage.get('date'))
                if not stage_date:
                    continue
                
                if stage_date == today and stage.get('status') == 'Pending':
                    # Check weather suitability
                    weather_suitable = self._check_weather_suitability(weather_data, stage)
                    
                    if weather_suitable:
                        return {
                            "action": "APPLY",
                            "stage": stage.get('stage'),
                            "fertilizer": stage.get('fertilizer'),
                            "quantity": stage.get('quantity'),
                            "method": stage.get('method'),
                            "best_time": stage.get('best_time'),
                            "reason": "Scheduled application for today",
                            "weather_suitable": True
                        }
                    else:
                        return {
                            "action": "WAIT",
                            "stage": stage.get('stage'),
                            "fertilizer": stage.get('fertilizer'),
                            "reason": get_message("weather_favorable", lang) if weather_suitable else get_message("no_fertilizer_data", lang), # Placeholder logic update
                            "weather_suitable": weather_suitable,
                            "weather_warning": self._get_weather_warning(weather_data, lang=lang)
                        }
            
            # Check for upcoming applications
            for i, stage in enumerate(schedule):
                stage_date = self._coerce_stage_date(stage.get('date'))
                if not stage_date:
                    continue
                
                if stage_date > today and stage.get('status') == 'Pending':
                    days_until = (stage_date - today).days
                    return {
                        "action": "WAIT",
                        "next_application": stage.get('fertilizer'),
                        "days_until": days_until,
                        "date": stage_date.strftime('%d %b %Y'),
                        "reason": f"Next application in {days_until} days"
                    }
            
            return {"action": "NONE", "message": "No fertilizer applications scheduled"}
            
        except Exception as e:
            logger.error(f"Error getting today action: {str(e)}")
            return {"action": "ERROR", "message": str(e)}
    
    def mark_applied(self, user_id, stage_index, actual_date=None, notes=''):
        """Mark fertilizer as applied"""
        try:
            plan = self.get_fertilizer_plan(user_id)
            if not plan:
                raise APIError("No fertilizer plan found", 404)
            
            schedule = plan.get('schedule', [])
            
            if stage_index < 0 or stage_index >= len(schedule):
                raise APIError("Invalid stage index", 400)
            
            # Update stage status
            schedule[stage_index]['status'] = 'Applied'
            schedule[stage_index]['actual_date'] = actual_date or datetime.utcnow()
            if notes:
                schedule[stage_index]['notes'] = notes
            
            # Update next application
            today = datetime.utcnow().date()
            next_app = None
            
            for i in range(stage_index + 1, len(schedule)):
                stage = schedule[i]
                stage_date = self._coerce_stage_date(stage.get('date'))
                if not stage_date:
                    continue
                
                if stage_date >= today and stage.get('status') == 'Pending':
                    next_app = {
                        "date": stage_date,
                        "fertilizer": stage.get('fertilizer'),
                        "days_until": (stage_date - today).days
                    }
                    break
            
            plan['next_application'] = next_app
            plan['updated_at'] = datetime.utcnow()
            
            # Save to database
            self._save_plan(plan)
            
            return {
                "success": True,
                "message": "Fertilizer application recorded",
                "updated_plan": plan
            }
            
        except Exception as e:
            logger.error(f"Error marking applied: {str(e)}")
            raise
    
    def postpone_application(self, user_id, stage_index, new_date, reason=''):
        """Postpone fertilizer application"""
        try:
            if isinstance(new_date, str):
                new_date = datetime.fromisoformat(new_date.replace('Z', '+00:00'))
            
            plan = self.get_fertilizer_plan(user_id)
            if not plan:
                raise APIError("No fertilizer plan found", 404)
            
            schedule = plan.get('schedule', [])
            
            if stage_index < 0 or stage_index >= len(schedule):
                raise APIError("Invalid stage index", 400)
            
            # Update stage date
            schedule[stage_index]['date'] = new_date
            schedule[stage_index]['status'] = 'Postponed'
            if reason:
                schedule[stage_index]['notes'] = f"Postponed: {reason}"
            
            # Resort schedule by date
            schedule.sort(key=lambda x: x.get('date', datetime.max))
            
            # Update next application
            today = datetime.utcnow().date()
            next_app = None
            
            for i, stage in enumerate(schedule):
                stage_date = self._coerce_stage_date(stage.get('date'))
                if not stage_date:
                    continue
                
                if stage_date >= today and stage.get('status') == 'Pending':
                    next_app = {
                        "date": stage_date,
                        "fertilizer": stage.get('fertilizer'),
                        "days_until": (stage_date - today).days
                    }
                    break
            
            plan['next_application'] = next_app
            plan['updated_at'] = datetime.utcnow()
            
            # Save to database
            self._save_plan(plan)
            
            return {
                "success": True,
                "message": "Application postponed",
                "updated_plan": plan
            }
            
        except Exception as e:
            logger.error(f"Error postponing application: {str(e)}")
            raise
    
    def create_fertilizer_plan_for_crop(self, user_id, crop_name, crop_data, start_date=None, crop_selection_id=None):
        """Create fertilizer plan for selected crop - called from crop selection"""
        try:
            # Get soil information
            soil_info = self._get_soil_info(user_id)

            # Create fertilizer plan
            plan = self._create_fertilizer_plan(
                user_id=user_id,
                crop_name=crop_name,
                crop_details=crop_data,
                soil_info=soil_info,
                start_date=start_date,
                crop_selection_id=crop_selection_id,
                lang="en"
            )

            # Add plan_id for tracking
            plan['plan_id'] = str(plan.get('_id', '')) if '_id' in plan else None

            return plan

        except Exception as e:
            logger.error(f"Error creating fertilizer plan for crop: {str(e)}")
            return {"error": str(e), "plan_generated": False}

    def get_fertilizer_types(self):
        """Get list of fertilizer types"""
        return [{
            "fertilizer_name": fert['fertilizer_name'],
            "tamil_name": fert.get('tamil_name', ''),
            "type": fert.get('type', ''),
            "n_p_k": fert.get('n_p_k', ''),
            "common_crops": fert.get('crops', [])[:3]
        } for fert in self.fertilizer_dataset[:20]]
    
    def _get_current_crop(self, user_id):
        """Get user's current crop"""
        collection = self.db_service.get_collection('crop_selections')
        crop = collection.find_one(
            {"user_id": user_id, "is_active": True}
        )
        return crop

    def _to_positive_int(self, value, default=0):
        try:
            parsed = int(float(value))
            return parsed if parsed > 0 else default
        except Exception:
            return default

    def _build_fallback_growth_data(self, crop_name, crop_details):
        """Create growth stage structure from crop details when growth dataset is missing."""
        details = crop_details if isinstance(crop_details, dict) else {}
        total_days = self._to_positive_int(
            details.get('growth_days') or details.get('total_growth_days'),
            default=120
        )

        source_stages = details.get('stages') or []
        stages = []
        for idx, item in enumerate(source_stages):
            if isinstance(item, dict):
                name = item.get('stage') or item.get('name') or f"Stage {idx + 1}"
                duration = self._to_positive_int(
                    item.get('duration_days') or item.get('days') or item.get('duration'),
                    default=0
                )
                stages.append({
                    "stage": str(name),
                    "duration_days": duration
                })
            elif isinstance(item, str) and item.strip():
                stages.append({
                    "stage": item.strip(),
                    "duration_days": 0
                })

        if stages:
            fixed = sum(s.get("duration_days", 0) for s in stages if s.get("duration_days", 0) > 0)
            missing = [i for i, s in enumerate(stages) if s.get("duration_days", 0) <= 0]
            if missing:
                remaining = max(0, total_days - fixed)
                per_stage = max(1, (remaining // len(missing)) if remaining > 0 else (total_days // max(1, len(stages))))
                for i in missing:
                    stages[i]["duration_days"] = per_stage
            total_from_stages = sum(self._to_positive_int(s.get("duration_days"), 0) for s in stages)
            if total_from_stages > 0:
                total_days = total_from_stages
        else:
            # Safe generic stage distribution
            ratios = [
                ("Germination", 0.15),
                ("Vegetative", 0.35),
                ("Flowering", 0.25),
                ("Fruiting", 0.25),
            ]
            assigned = 0
            for i, (name, ratio) in enumerate(ratios):
                if i == len(ratios) - 1:
                    days = max(1, total_days - assigned)
                else:
                    days = max(1, int(round(total_days * ratio)))
                    assigned += days
                stages.append({"stage": name, "duration_days": days})

        return {
            "crop_name": crop_name,
            "total_growth_days": total_days,
            "stages": stages,
        }
    
    def _get_soil_info(self, user_id):
        """Get user's soil information"""
        collection = self.db_service.get_collection('soil_results')
        soil = collection.find_one(
            {"user_id": user_id},
            sort=[("created_at", -1)],
            projection={"_id": 0, "soil_name": 1, "soil_properties": 1}
        )
        return soil
    
    def _get_existing_plan(self, user_id, crop_name, crop_selection_id=None):
        """Get existing fertilizer plan for the active crop context."""
        collection = self.db_service.get_collection('fertilizer_schedules')
        query = {"user_id": user_id, "is_active": True}
        if crop_selection_id:
            query["crop_selection_id"] = crop_selection_id
        else:
            query["crop_name"] = crop_name

        plan = collection.find_one(query, sort=[("updated_at", -1)])
        if plan:
            return plan

        # Backward compatibility for old plans without crop_selection_id.
        plan = collection.find_one(
            {"user_id": user_id, "crop_name": crop_name, "is_active": True},
            sort=[("updated_at", -1)]
        )
        return plan
    
    def _create_fertilizer_plan(
        self,
        user_id,
        crop_name,
        crop_details,
        soil_info,
        start_date=None,
        crop_selection_id=None,
        lang="en"
    ):
        """Create new fertilizer plan"""
        # Get crop growth stages
        growth_data = self._get_growth_data(crop_name)
        if not growth_data:
            growth_data = self._build_fallback_growth_data(crop_name, crop_details)
            logger.warning("Fertilizer scheduler: growth dataset missing for %s. Using crop_details fallback.", crop_name)
        
        stages = growth_data.get('stages', [])
        if not stages:
            raise APIError(f"No growth stages available for {crop_name}", 404)
        
        # Get fertilizer recommendations for crop
        fertilizer_recommendations = self._get_fertilizer_recommendations(crop_name, soil_info)
        
        # Create schedule
        schedule = []
        if isinstance(start_date, str):
            try:
                plan_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except Exception:
                plan_start_date = datetime.utcnow()
        elif isinstance(start_date, datetime):
            plan_start_date = start_date
        else:
            plan_start_date = datetime.utcnow()

        current_date = plan_start_date
        
        for i, stage in enumerate(stages):
            stage_name = stage.get('stage') or stage.get('name') or f"Stage {i + 1}"
            duration_days = self._to_positive_int(stage.get('duration_days', stage.get('days', 0)), 1)
            
            # Find suitable fertilizer for this stage
            fertilizer = self._get_stage_fertilizer(stage_name, fertilizer_recommendations)
            
            if fertilizer:
                # Calculate application date (middle of stage)
                application_date = current_date + timedelta(days=duration_days // 2)
                
                schedule.append({
                    "stage": stage_name,
                    "stage_index": i,
                    "fertilizer": fertilizer.get('fertilizer_name'),
                    "tamil_name": fertilizer.get('tamil_name', ''),
                    "type": fertilizer.get('type', ''),
                    "n_p_k": fertilizer.get('n_p_k', ''),
                    "date": application_date,
                    "quantity": fertilizer.get('application_rate', 'As per recommendation'),
                    "method": fertilizer.get('application_method', ['Basal'])[0],
                    "best_time": fertilizer.get('best_time', 'Morning'),
                    "weather_dependent": True,
                    "safety_notes": fertilizer.get('precautions', []),
                    "status": "Pending",
                    "purpose": self._get_fertilizer_purpose(stage_name, fertilizer, lang=lang)
                })
            
            current_date += timedelta(days=duration_days)
        
        # Calculate next application
        today = datetime.utcnow().date()
        next_app = None
        
        for stage in schedule:
            stage_date = stage.get('date')
            if isinstance(stage_date, datetime):
                stage_date = stage_date.date()
            
            if stage_date >= today and stage.get('status') == 'Pending':
                next_app = {
                    "date": stage_date,
                    "fertilizer": stage.get('fertilizer'),
                    "days_until": (stage_date - today).days
                }
                break
        
        plan = {
            "user_id": user_id,
            "crop_name": crop_name,
            "crop_selection_id": crop_selection_id,
            "soil_type": soil_info.get('soil_name', 'Unknown') if soil_info else 'Unknown',
            "schedule": schedule,
            "total_stages": len(schedule),
            "current_stage_index": 0,
            "next_application": next_app,
            "weather_aware": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "completed": False
        }
        
        # Save to database
        self._save_plan(plan)
        
        return plan
    
    def _get_growth_data(self, crop_name):
        """Get growth data for crop"""
        if not crop_name:
            return None
        requested = str(crop_name).strip().lower()
        normalized_requested = requested.replace(" ", "").replace("-", "").replace("_", "")

        # Exact match
        for crop in self.growth_dataset:
            if str(crop.get('crop_name', '')).strip().lower() == requested:
                return crop

        # Normalized match
        for crop in self.growth_dataset:
            candidate = str(crop.get('crop_name', '')).strip().lower()
            normalized_candidate = candidate.replace(" ", "").replace("-", "").replace("_", "")
            if normalized_candidate == normalized_requested:
                return crop

        # Partial match fallback
        for crop in self.growth_dataset:
            candidate = str(crop.get('crop_name', '')).strip().lower()
            if requested in candidate or candidate in requested:
                return crop
        return None
    
    def _get_fertilizer_recommendations(self, crop_name, soil_info):
        """Get fertilizer recommendations for crop and soil"""
        recommendations = []
        
        # Filter fertilizers suitable for crop
        for fert in self.fertilizer_dataset:
            crops = fert.get('crops', [])
            if crop_name in crops or 'All crops' in crops:
                recommendations.append(fert)
        
        # Adjust based on soil type
        if soil_info:
            soil_name = soil_info.get('soil_name', '')
            soil_fertility = soil_info.get('soil_properties', {}).get('fertility', 'Medium')
            
            # Adjust quantity based on soil fertility
            for fert in recommendations:
                if soil_fertility in ['High', 'Very High']:
                    # Reduce quantity for fertile soil
                    if 'application_rate' in fert:
                        fert['adjusted_rate'] = f"Reduce {fert['application_rate']} by 20%"
                elif soil_fertility in ['Low', 'Very Low']:
                    # Increase quantity for poor soil
                    if 'application_rate' in fert:
                        fert['adjusted_rate'] = f"Increase {fert['application_rate']} by 20%"
        
        return recommendations
    
    def _get_stage_fertilizer(self, stage_name, recommendations):
        """Get appropriate fertilizer for growth stage"""
        # Stage to fertilizer type mapping
        stage_mapping = {
            'Germination': ['Basal', 'Starter'],
            'Seedling': ['Nitrogenous'],
            'Vegetative': ['Nitrogenous', 'Complex'],
            'Flowering': ['Phosphatic', 'Complex'],
            'Fruiting': ['Potassic', 'Complex'],
            'Ripening': ['Potassic'],
            'Harvest': []  # No fertilizer at harvest
        }
        
        for fert in recommendations:
            fert_type = fert.get('type', '')
            application_methods = fert.get('application_method', [])
            
            # Check if fertilizer type matches stage
            if stage_name in stage_mapping:
                suitable_types = stage_mapping[stage_name]
                if fert_type in suitable_types:
                    return fert
            
            # Check based on application method
            if 'Basal' in application_methods and stage_name == 'Germination':
                return fert
            if 'Top Dressing' in application_methods and stage_name in ['Vegetative', 'Flowering']:
                return fert
        
        # Return first recommendation as fallback
        return recommendations[0] if recommendations else None
    
    def _get_fertilizer_purpose(self, stage_name, fertilizer, lang="en"):
        """Get purpose of fertilizer application using LLM"""
        purposes = {
            'Germination': 'Provide initial nutrients for seedling growth',
            'Seedling': 'Support early growth and root development',
            'Vegetative': 'Promote leaf and stem growth',
            'Flowering': 'Support flower formation and pollination',
            'Fruiting': 'Enhance fruit development and quality',
            'Ripening': 'Improve grain filling and maturity'
        }

        if not self.enable_llm_guidance:
            return purposes.get(stage_name, 'Support crop growth')

        try:
            language_name = "Tamil" if lang == "ta" else "English"
            prompt = f"""
            As an agriculture expert, explain in 1 sentence in {language_name} why {fertilizer.get('fertilizer_name')} 
            is applied during the {stage_name} stage of crop growth.
            """
            purpose = self.llm_service.generate_response(prompt, max_tokens=100)
            return purpose.strip()
        except:
            return purposes.get(stage_name, 'Support crop growth')

    def _coerce_stage_date(self, value):
        """Normalize stored schedule date values to date objects."""
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()

        text = str(value).strip()
        if not text:
            return None

        cleaned = text.replace('Z', '+00:00')
        for fmt in (
            None,
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                if fmt is None:
                    parsed = datetime.fromisoformat(cleaned)
                else:
                    parsed = datetime.strptime(cleaned, fmt)
                return parsed.date()
            except Exception:
                continue
        return None
    
    def _save_plan(self, plan):
        """Save fertilizer plan to database"""
        try:
            collection = self.db_service.get_collection('fertilizer_schedules')
            plan_id = plan.get("_id")
            payload = dict(plan)
            payload.pop("_id", None)

            if plan_id:
                collection.update_one(
                    {"_id": plan_id},
                    {"$set": payload},
                    upsert=True
                )
                plan["_id"] = plan_id
                logger.info("Fertilizer plan updated for user %s", plan['user_id'])
                return

            existing_query = {"user_id": plan['user_id'], "is_active": True}
            if plan.get("crop_selection_id"):
                existing_query["crop_selection_id"] = plan.get("crop_selection_id")
            elif plan.get("crop_name"):
                existing_query["crop_name"] = plan.get("crop_name")

            existing = collection.find_one(existing_query, sort=[("updated_at", -1)])
            if existing and existing.get("_id"):
                collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": payload},
                    upsert=True
                )
                plan["_id"] = existing["_id"]
                logger.info("Fertilizer plan updated for user %s", plan['user_id'])
                return

            collection.update_many(
                {"user_id": plan['user_id'], "is_active": True},
                {"$set": {"is_active": False}}
            )
            inserted = collection.insert_one(payload)
            plan["_id"] = inserted.inserted_id
            
            logger.info(f"Fertilizer plan saved for user {plan['user_id']}")
            
        except Exception as e:
            logger.error(f"Error saving fertilizer plan: {str(e)}")
            raise
    
    def _get_user_location(self, user_id):
        """Get user location"""
        try:
            user_collection = self.db_service.get_collection('users')
            user = user_collection.find_one({"user_id": user_id})
            
            if user and 'farm_info' in user:
                return user['farm_info'].get('district', '')
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user location: {str(e)}")
            return None
    
    def _check_weather_suitability(self, weather_data, stage):
        """Check if weather is suitable for fertilizer application"""
        if not weather_data:
            return True
        
        current = weather_data.get('current', {})
        rain = current.get('rain', 0) or current.get('showers', 0)
        wind_speed = current.get('wind_speed', 0)
        
        # Check weather warnings in fertilizer data
        weather_warnings = stage.get('weather_warnings', [])
        
        if rain > 5 and 'Rain within 4 hours' in weather_warnings:
            return False
        
        if wind_speed > 25 and 'Strong wind' in weather_warnings:
            return False
        
        return True
    
    def _get_weather_warning(self, weather_data, lang="en"):
        """Get weather warning message"""
        if not weather_data:
            return ""
        
        current = weather_data.get('current', {})
        rain = current.get('rain', 0) or current.get('showers', 0)
        wind_speed = current.get('wind_speed', 0)
        
        warnings = []
        
        if rain > 5:
            warnings.append(get_message("heavy_rain_warning", lang))
        
        if wind_speed > 20:
            warnings.append("High wind speed. Avoid spraying.")
        
        return ". ".join(warnings) if warnings else get_message("weather_suitable_spray", lang)
