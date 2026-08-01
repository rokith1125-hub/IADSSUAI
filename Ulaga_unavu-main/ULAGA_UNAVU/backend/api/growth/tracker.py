"""
Growth tracking engine
"""

import json
import logging
import os
from datetime import datetime, timedelta
from services.local_storage import db_service
from services.weather_service import WeatherService
from services.llm_service import LLMService
from utils.error_handler import APIError
from utils.date_utils import time_ago
from utils.path_utils import get_dataset_path
from utils.localization import get_message

logger = logging.getLogger(__name__)

class GrowthTracker:
    """Growth tracking engine"""
    
    def __init__(self):
        self.db_service = db_service
        self.weather_service = WeatherService()
        self.llm_service = LLMService()
        self.growth_dataset = self._load_growth_dataset()
        
    def _load_growth_dataset(self):
        """Load growth dataset from JSON"""
        try:
            dataset_path = get_dataset_path('growth_data.json')
            with open(dataset_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading growth dataset: {str(e)}")
            return []
    
    def get_growth_timeline(self, user_id, lang="en"):
        """Get growth timeline for user's current crop with localization"""
        try:
            crop = self._get_current_crop(user_id)
            if not crop:
                raise APIError("No crop selected. Please select a crop first.", 400)
            
            crop_name = crop.get('crop_name') or crop.get('selected_crop')
            if not crop_name:
                raise APIError("No crop selected. Please select a crop first.", 400)
            crop_selection_id = crop.get("_id")
            crop_details = crop.get('crop_details', {})

            # Get existing timeline scoped to current crop selection.
            existing_timeline = self._get_existing_timeline(
                user_id=user_id,
                crop_name=crop_name,
                crop_selection_id=crop_selection_id
            )
            if existing_timeline:
                existing_timeline["crop_selection_id"] = existing_timeline.get("crop_selection_id") or crop_selection_id
                return self._update_timeline_progress(existing_timeline, lang=lang)
            
            crop_timeline = crop.get("growth_timeline", {}) or {}
            stored_start = crop_timeline.get("start_date")
            stored_status = crop_timeline.get("status") or ("active" if stored_start else "not_started")

            timeline = self._create_growth_timeline(
                user_id=user_id,
                crop_name=crop_name,
                crop_details=crop_details,
                start_date=stored_start,
                timeline_status=stored_status,
                crop_selection_id=crop_selection_id,
                lang=lang
            )
            
            return timeline
            
        except Exception as e:
            logger.error(f"Error getting growth timeline: {str(e)}")
            raise
    
    def start_tracking(self, user_id, start_date=None, lang="en"):
        """Start growth tracking"""
        try:
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            elif not start_date:
                start_date = datetime.utcnow()
            
            timeline = self.get_growth_timeline(user_id, lang=lang)
            if not timeline:
                raise APIError("No crop timeline found", 404)

            # Already started: keep existing start date stable.
            if timeline.get('start_date'):
                return self._update_timeline_progress(timeline, lang=lang)
            
            # Update start date
            timeline['start_date'] = start_date
            timeline['timeline_status'] = 'active'
            
            # Recalculate timeline
            timeline = self._recalculate_timeline(timeline, lang=lang)
            
            # Save to database
            self._save_timeline(timeline)
            self._sync_crop_start_state(user_id, timeline)
            
            return timeline
            
        except Exception as e:
            logger.error(f"Error starting tracking: {str(e)}")
            raise
    
    def update_stage(self, user_id, stage_index, notes='', lang="en"):
        """Update growth stage manually"""
        try:
            timeline = self.get_growth_timeline(user_id, lang=lang)
            if not timeline:
                raise APIError("No growth timeline found", 404)
            
            stages = timeline.get('stages', [])
            
            if stage_index < 0 or stage_index >= len(stages):
                raise APIError("Invalid stage index", 400)
            
            # Mark stage as completed
            stages[stage_index]['is_completed'] = True
            stages[stage_index]['completed_date'] = datetime.utcnow()
            if notes:
                stages[stage_index]['notes'] = notes
            
            # Update current stage
            if stage_index < len(stages) - 1:
                timeline['current_stage'] = stages[stage_index + 1]['name']
                timeline['current_stage_index'] = stage_index + 1
            else:
                timeline['current_stage'] = "Harvest"
                timeline['current_stage_index'] = len(stages)
            
            timeline['updated_at'] = datetime.utcnow()
            
            # Save to database
            self._save_timeline(timeline)
            
            return {
                "success": True,
                "message": "Stage updated successfully",
                "updated_timeline": timeline
            }
            
        except Exception as e:
            logger.error(f"Error updating stage: {str(e)}")
            raise
    
    def mark_harvested(self, user_id, actual_date=None, yield_amount='', notes='', lang="en"):
        """Mark crop as harvested"""
        try:
            if isinstance(actual_date, str):
                actual_date = datetime.fromisoformat(actual_date.replace('Z', '+00:00'))
            elif not actual_date:
                actual_date = datetime.utcnow()
            
            timeline = self.get_growth_timeline(user_id, lang=lang)
            if not timeline:
                raise APIError("No growth timeline found", 404)
            
            # Update timeline
            timeline['actual_end_date'] = actual_date
            timeline['harvest_status'] = 'Harvested'
            timeline['is_active'] = False
            timeline['progress_percent'] = 100
            timeline['current_stage'] = 'Harvested'
            
            if yield_amount:
                timeline['yield_estimate']['actual_yield'] = yield_amount
            
            if notes:
                timeline['farmer_notes'] = notes
            
            timeline['updated_at'] = datetime.utcnow()
            
            # Update crop selection
            self._update_crop_harvested(user_id, actual_date, yield_amount)
            
            # Save to database
            self._save_timeline(timeline)
            
            # Generate harvest guidance
            harvest_guidance = self._generate_harvest_guidance(timeline, lang=lang)
            
            return {
                "success": True,
                "message": "Harvest recorded successfully",
                "timeline": timeline,
                "harvest_guidance": harvest_guidance
            }
            
        except Exception as e:
            logger.error(f"Error marking harvested: {str(e)}")
            raise
    
    def get_current_status(self, user_id, lang="en"):
        """Get current growth status"""
        try:
            timeline = self.get_growth_timeline(user_id, lang=lang)
            if not timeline:
                return {"status": "No active crop"}
            
            # Get today's message
            today_message = self._generate_today_message(timeline, lang=lang)
            
            # Get harvest readiness
            harvest_readiness = self._check_harvest_readiness(timeline)
            
            # Get weather impact
            weather_impact = self._get_weather_impact(user_id, timeline)
            
            return {
                "crop_name": timeline.get('crop_name', 'Unknown'),
                "current_stage": timeline.get('current_stage', 'Unknown'),
                "progress_percent": timeline.get('progress_percent', 0),
                "days_completed": timeline.get('days_completed', 0),
                "days_remaining": timeline.get('days_remaining', 0),
                "today_message": today_message,
                "harvest_status": timeline.get('harvest_status', 'Not Ready'),
                "harvest_readiness": harvest_readiness,
                "weather_impact": weather_impact,
                "next_milestone": self._get_next_milestone(timeline)
            }
            
        except Exception as e:
            logger.error(f"Error getting current status: {str(e)}")
            return {"status": "Error", "message": str(e)}
    
    def _get_existing_timeline(self, user_id, crop_name=None, crop_selection_id=None):
        """Get existing growth timeline for the active crop context."""
        collection = self.db_service.get_collection('growth_timelines')
        query = {"user_id": user_id, "is_active": True}
        if crop_selection_id:
            query["crop_selection_id"] = crop_selection_id
        elif crop_name:
            query["crop_name"] = crop_name

        timeline = collection.find_one(query, sort=[("updated_at", -1)])
        if timeline:
            return timeline

        # Backward compatibility for timelines created before crop_selection_id was tracked.
        if crop_name:
            return collection.find_one(
                {"user_id": user_id, "crop_name": crop_name, "is_active": True},
                sort=[("updated_at", -1)]
            )

        return None
    
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
        """
        Build growth data from selected crop details when growth_data.json
        doesn't contain this crop.
        """
        details = crop_details if isinstance(crop_details, dict) else {}
        total_days = self._to_positive_int(
            details.get('growth_days') or details.get('total_growth_days'),
            default=120
        )

        source_stages = details.get('stages') or []
        normalized = []
        for idx, item in enumerate(source_stages):
            if isinstance(item, dict):
                name = item.get('stage') or item.get('name') or f"Stage {idx + 1}"
                duration = self._to_positive_int(
                    item.get('duration_days') or item.get('days') or item.get('duration'),
                    default=0
                )
                normalized.append({
                    "stage": str(name),
                    "duration_days": duration,
                    "critical_actions": item.get('critical_actions', []),
                    "irrigation": item.get('irrigation', 'Medium'),
                    "temperature": item.get('temperature', ''),
                    "monitoring_focus": item.get('monitoring_focus', '')
                })
            elif isinstance(item, str) and item.strip():
                normalized.append({
                    "stage": item.strip(),
                    "duration_days": 0,
                    "critical_actions": [],
                    "irrigation": 'Medium',
                    "temperature": '',
                    "monitoring_focus": ''
                })

        # If stage durations are missing, distribute remaining days.
        if normalized:
            fixed = sum(s.get("duration_days", 0) for s in normalized if s.get("duration_days", 0) > 0)
            missing_indices = [i for i, s in enumerate(normalized) if s.get("duration_days", 0) <= 0]
            if missing_indices:
                remaining = max(0, total_days - fixed)
                per_stage = max(1, (remaining // len(missing_indices)) if remaining > 0 else (total_days // max(1, len(normalized))))
                for i in missing_indices:
                    normalized[i]["duration_days"] = per_stage

            total_from_stages = sum(self._to_positive_int(s.get("duration_days"), 0) for s in normalized)
            if total_from_stages > 0:
                total_days = total_from_stages

        # If no stages at all, use a safe generic lifecycle.
        if not normalized:
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
                normalized.append({
                    "stage": name,
                    "duration_days": days,
                    "critical_actions": [],
                    "irrigation": 'Medium',
                    "temperature": '',
                    "monitoring_focus": ''
                })

        return {
            "crop_name": crop_name,
            "total_growth_days": total_days,
            "stages": normalized,
            "post_harvest": details.get("special_notes", []),
        }
    
    def _create_growth_timeline(
        self,
        user_id,
        crop_name,
        crop_details,
        start_date=None,
        timeline_status="not_started",
        crop_selection_id=None,
        lang="en"
    ):
        """Create new growth timeline"""
        # Get growth data for crop
        growth_data = self._get_growth_data(crop_name)
        if not growth_data:
            growth_data = self._build_fallback_growth_data(crop_name, crop_details)
            logger.warning("Growth dataset missing for %s. Using crop_details fallback timeline.", crop_name)
        
        stages = growth_data.get('stages', [])
        total_days = growth_data.get('total_growth_days', 90)
        if not stages:
            raise APIError(f"No growth stages available for {crop_name}", 404)
        
        # Process stages
        processed_stages = []
        current_day = 0
        
        for i, stage in enumerate(stages):
            stage_name = stage.get('stage') or stage.get('name') or f"Stage {i + 1}"
            duration_days = self._to_positive_int(stage.get('duration_days', stage.get('days', 0)), 1)
            
            processed_stages.append({
                "name": stage_name,
                "tamil_name": stage.get('tamil_name', ''),
                "duration_days": duration_days,
                "start_day": current_day,
                "end_day": current_day + duration_days,
                "critical_actions": stage.get('critical_actions', []),
                "irrigation_need": stage.get('irrigation', 'Medium'),
                "temperature_range": stage.get('temperature', ''),
                "monitoring_focus": stage.get('monitoring_focus', ''),
                "is_completed": False,
                "completed_date": None,
                "notes": ""
            })
            
            current_day += duration_days

        # Keep timeline total consistent with stage breakdown.
        summed_stage_days = sum(self._to_positive_int(s.get("duration_days"), 0) for s in processed_stages)
        if summed_stage_days > 0:
            total_days = summed_stage_days
        
        normalized_start = None
        if isinstance(start_date, str):
            try:
                normalized_start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except Exception:
                normalized_start = None
        elif isinstance(start_date, datetime):
            normalized_start = start_date

        is_started = bool(normalized_start) and str(timeline_status or "").lower() == "active"

        if is_started:
            expected_end_date = normalized_start + timedelta(days=max(total_days - 1, 0))
            today = datetime.now().date()
            start_date_date = normalized_start.date()
            days_completed = max(0, (today - start_date_date).days)
            days_remaining = max(0, total_days - days_completed - 1)
            progress_percent = min(100, (((days_completed + 1) / total_days) * 100) if total_days > 0 else 0)

            current_stage = "Not Started"
            current_stage_index = 0
            for i, stage in enumerate(processed_stages):
                if days_completed >= stage["start_day"] and days_completed < stage["end_day"]:
                    current_stage = stage["name"]
                    current_stage_index = i
                    break
            if days_completed >= total_days:
                current_stage = "Harvest"
                current_stage_index = len(processed_stages)
        else:
            normalized_start = None
            expected_end_date = None
            days_completed = 0
            days_remaining = total_days
            progress_percent = 0
            current_stage = "Planning"
            current_stage_index = 0
        
        timeline = {
            "user_id": user_id,
            "crop_name": crop_name,
            "crop_selection_id": crop_selection_id,
            "start_date": normalized_start,
            "expected_end_date": expected_end_date,
            "total_days": total_days,
            "stages": processed_stages,
            "current_stage": current_stage,
            "current_stage_index": current_stage_index,
            "days_completed": days_completed,
            "days_remaining": days_remaining,
            "progress_percent": progress_percent,
            "today_message": "",
            "harvest_status": "Not Ready",
            "harvest_guidance": growth_data.get('post_harvest', []),
            "growth_conditions": {},
            "yield_estimate": {
                "estimated_yield": crop_details.get('yield_per_acre', ''),
                "confidence": "Medium",
                "factors": ["Soil fertility", "Weather conditions", "Management practices"]
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "timeline_status": "active" if normalized_start else "not_started",
            "farmer_notes": ""
        }
        
        # Generate today's message
        timeline['today_message'] = self._generate_today_message(timeline, lang=lang)
        
        # Save to database
        self._save_timeline(timeline)
        
        return timeline
    
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

        # Normalized match (handles minor naming differences)
        for crop in self.growth_dataset:
            candidate = str(crop.get('crop_name', '')).strip().lower()
            normalized_candidate = candidate.replace(" ", "").replace("-", "").replace("_", "")
            if normalized_candidate == normalized_requested:
                return crop

        # Partial match as final attempt
        for crop in self.growth_dataset:
            candidate = str(crop.get('crop_name', '')).strip().lower()
            if requested in candidate or candidate in requested:
                return crop
        return None
    
    def _update_timeline_progress(self, timeline, lang="en"):
        """Update timeline progress based on current date"""
        if not timeline.get('start_date'):
            total_days = timeline.get("total_days", 0)
            timeline['days_completed'] = 0
            timeline['days_remaining'] = total_days
            timeline['progress_percent'] = 0
            timeline['current_stage'] = 'Planning'
            timeline['current_stage_index'] = 0
            timeline['harvest_status'] = 'Not Started'
            timeline['timeline_status'] = 'not_started'
            timeline['today_message'] = self._generate_today_message(timeline, lang=lang)
            timeline['updated_at'] = datetime.utcnow()
            self._save_timeline(timeline)
            return timeline
        
        start_date = timeline['start_date']
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        
        total_days = timeline['total_days']
        today = datetime.now().date()
        start_date_date = start_date.date()
        
        days_completed = max(0, (today - start_date_date).days)
        days_remaining = max(0, total_days - days_completed - 1)
        progress_percent = min(100, (((days_completed + 1) / total_days) * 100) if total_days > 0 else 0)
        
        # Update basic progress
        timeline['days_completed'] = days_completed
        timeline['days_remaining'] = days_remaining
        timeline['progress_percent'] = progress_percent
        timeline['timeline_status'] = 'active'
        
        # Update current stage
        current_stage = "Not Started"
        current_stage_index = 0
        
        for i, stage in enumerate(timeline['stages']):
            if days_completed >= stage["start_day"] and days_completed < stage["end_day"]:
                current_stage = stage["name"]
                current_stage_index = i
                break
        
        if days_completed >= total_days:
            current_stage = "Harvest"
            current_stage_index = len(timeline['stages'])
            timeline['harvest_status'] = "Ready"
        
        timeline['current_stage'] = current_stage
        timeline['current_stage_index'] = current_stage_index
        
        # Update stage completion status
        for stage in timeline['stages']:
            if days_completed >= stage["end_day"] and not stage.get("is_completed"):
                stage["is_completed"] = True
                if "completed_date" not in stage:
                    stage["completed_date"] = datetime.utcnow()
        
        # Generate today's message
        timeline['today_message'] = self._generate_today_message(timeline, lang=lang)
        
        # Update harvest status
        timeline = self._update_harvest_status(timeline)
        
        timeline['updated_at'] = datetime.utcnow()
        
        # Save to database
        self._save_timeline(timeline)
        
        return timeline
    
    def _recalculate_timeline(self, timeline, lang="en"):
        """Recalculate timeline based on new start date"""
        start_date = timeline['start_date']
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        
        total_days = timeline['total_days']
        expected_end_date = start_date + timedelta(days=max(total_days - 1, 0))
        
        timeline['expected_end_date'] = expected_end_date
        
        # Reset progress
        timeline = self._update_timeline_progress(timeline, lang=lang)
        
        return timeline
    
    def _save_timeline(self, timeline):
        """Save timeline to database"""
        try:
            collection = self.db_service.get_collection('growth_timelines')
            timeline_id = timeline.get("_id")
            payload = dict(timeline)
            payload.pop("_id", None)

            if timeline_id:
                collection.update_one(
                    {"_id": timeline_id},
                    {"$set": payload},
                    upsert=True
                )
                timeline["_id"] = timeline_id
                logger.info("Growth timeline updated for user %s", timeline['user_id'])
                return

            existing_query = {"user_id": timeline['user_id'], "is_active": True}
            if timeline.get("crop_selection_id"):
                existing_query["crop_selection_id"] = timeline.get("crop_selection_id")
            elif timeline.get("crop_name"):
                existing_query["crop_name"] = timeline.get("crop_name")

            existing = collection.find_one(existing_query, sort=[("updated_at", -1)])
            if existing and existing.get("_id"):
                collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": payload},
                    upsert=True
                )
                timeline["_id"] = existing["_id"]
                logger.info("Growth timeline updated for user %s", timeline['user_id'])
                return

            # Insert first timeline for this active crop.
            collection.update_many(
                {"user_id": timeline['user_id'], "is_active": True},
                {"$set": {"is_active": False}}
            )
            inserted = collection.insert_one(payload)
            timeline["_id"] = inserted.inserted_id
            
            logger.info(f"Growth timeline saved for user {timeline['user_id']}")
            
        except Exception as e:
            logger.error(f"Error saving timeline: {str(e)}")
            raise

    def _sync_crop_start_state(self, user_id, timeline):
        """Mirror timeline start state into active crop selection for stable UI state."""
        try:
            start_date = timeline.get("start_date")
            if isinstance(start_date, datetime):
                start_date = start_date.isoformat()

            collection = self.db_service.get_collection('crop_selections')
            collection.update_one(
                {"user_id": user_id, "is_active": True},
                {"$set": {
                    "growth_timeline.start_date": start_date,
                    "growth_timeline.status": "active",
                    "growth_timeline.current_stage": timeline.get("current_stage", "Germination"),
                    "growth_timeline.progress_percent": timeline.get("progress_percent", 0),
                }}
            )
        except Exception as e:
            logger.error(f"Error syncing crop start state: {str(e)}")
    
    def _update_crop_harvested(self, user_id, harvest_date, yield_amount):
        """Update crop selection with harvest information"""
        try:
            collection = self.db_service.get_collection('crop_selections')
            collection.update_one(
                {"user_id": user_id, "is_active": True},
                {
                    "$set": {
                        "harvested": True,
                        "harvest_date": harvest_date,
                        "is_active": False
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error updating crop harvest: {str(e)}")
    
    def _generate_today_message(self, timeline, lang="en"):
        """Generate today's message for farmer using LLM"""
        try:
            language_name = "Tamil" if lang == "ta" else "English"
            current_stage = timeline.get('current_stage', '')
            crop_name = timeline.get('crop_name', 'crop')
            days_remaining = timeline.get('days_remaining', 0)
            
            prompt = f"""
            Generate a short 1-sentence farming advice for {crop_name} in {current_stage} stage in {language_name}.
            Days Remaining: {days_remaining}.
            Be practical and encouraging.
            """
            message = self.llm_service.generate_response(prompt, max_tokens=100)
            return message.strip()
        except:
            current_stage = timeline.get('current_stage', '')
            crop_name = timeline.get('crop_name', 'crop')
            days_remaining = timeline.get('days_remaining', 0)
            
            if current_stage == "Harvest":
                return f"{crop_name} is ready for harvest! Check harvest guidance."
            elif days_remaining <= 7:
                return f"{crop_name} nearing harvest ({days_remaining} days left). Prepare for harvesting."
            elif current_stage == "Not Started":
                return f"Ready to start {crop_name} cultivation. Set start date to begin tracking."
            else:
                return f"Continue {current_stage} activities for {crop_name}."
    
    def _update_harvest_status(self, timeline):
        """Update harvest status based on progress"""
        days_remaining = timeline.get('days_remaining', 0)
        expected_end_date = timeline.get('expected_end_date')
        
        if not expected_end_date:
            return timeline
        
        if isinstance(expected_end_date, str):
            expected_end_date = datetime.fromisoformat(expected_end_date.replace('Z', '+00:00'))
        
        today = datetime.now()
        
        if today >= expected_end_date:
            timeline['harvest_status'] = 'Ready'
        elif days_remaining <= 7:
            timeline['harvest_status'] = 'Approaching'
        elif days_remaining <= 0:
            timeline['harvest_status'] = 'Overdue'
        else:
            timeline['harvest_status'] = 'Not Ready'
        
        return timeline
    
    def _check_harvest_readiness(self, timeline):
        """Check harvest readiness"""
        harvest_status = timeline.get('harvest_status', 'Not Ready')
        current_stage = timeline.get('current_stage', '')
        
        if harvest_status == 'Ready':
            return {
                "ready": True,
                "message": "Crop is ready for harvest",
                "indicators": timeline.get('harvest_indicators', ['Grain hardness test'])
            }
        elif harvest_status == 'Approaching':
            days_remaining = timeline.get('days_remaining', 0)
            return {
                "ready": False,
                "message": f"Harvest approaching in {days_remaining} days",
                "preparation": ["Prepare harvesting tools", "Arrange labor", "Check weather forecast"]
            }
        else:
            return {
                "ready": False,
                "message": f"Currently in {current_stage} stage",
                "focus": "Continue regular care and monitoring"
            }
    
    def _get_weather_impact(self, user_id, timeline):
        """Get weather impact on growth"""
        try:
            user_location = self._get_user_location(user_id)
            if not user_location:
                return {"impact": "Unknown", "message": "Location not set"}
            
            weather_data = self.weather_service.get_current_weather(user_location)
            current = weather_data.get('current', {})
            
            temp = current.get('temperature', 25)
            rain = current.get('rain', 0) or current.get('showers', 0)
            humidity = current.get('humidity', 60)
            condition = current.get('condition', 'Clear')
            
            current_stage = timeline.get('current_stage', '')
            
            impact = "Normal"
            message = "Weather conditions suitable for crop growth"
            
            if current_stage == "Flowering" and rain > 10:
                impact = "Negative"
                message = "Heavy rain may affect pollination"
            elif current_stage in ["Germination", "Seedling"] and temp > 35:
                impact = "Negative"
                message = "High temperature may stress young plants"
            elif current_stage == "Fruiting" and humidity > 80:
                impact = "Caution"
                message = "High humidity may increase disease risk"
            elif rain > 20:
                impact = "Negative"
                message = "Heavy rain may cause waterlogging"
            
            return {
                "impact": impact,
                "message": message,
                "temperature": temp,
                "rainfall": rain,
                "condition": condition,
                "recommendation": self._get_weather_recommendation(impact, current_stage)
            }
            
        except Exception as e:
            logger.error(f"Error getting weather impact: {str(e)}")
            return {"impact": "Unknown", "message": "Weather data unavailable"}
    
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
    
    def _get_weather_recommendation(self, impact, stage):
        """Get weather recommendation"""
        if impact == "Negative":
            if stage == "Flowering":
                return "Consider pollination assistance if needed"
            elif stage in ["Germination", "Seedling"]:
                return "Provide shade or increase irrigation frequency"
            else:
                
                return "Take protective measures as needed"
        elif impact == "Caution":
            return "Monitor closely for any issues"
        else:
            return "Continue normal practices"
    
    def _get_next_milestone(self, timeline):
        """Get next milestone"""
        stages = timeline.get('stages', [])
        current_index = timeline.get('current_stage_index', 0)
        
        if current_index < len(stages):
            next_stage = stages[current_index]
            days_to_next = next_stage['start_day'] - timeline.get('days_completed', 0)
            
            return {
                "milestone": next_stage['name'],
                "days_until": max(0, days_to_next),
                "critical_actions": next_stage.get('critical_actions', [])[:2]
            }
        elif timeline.get('harvest_status') == 'Ready':
            return {
                "milestone": "Harvest",
                "days_until": 0,
                "critical_actions": ["Check grain hardness", "Prepare harvesting tools"]
            }
        else:
            return {
                "milestone": "Harvest",
                "days_until": timeline.get('days_remaining', 0),
                "critical_actions": ["Monitor maturity", "Prepare storage"]
            }
    
    def _generate_harvest_guidance(self, timeline, lang="en"):
        """Generate harvest guidance using LLM"""
        try:
            language_name = "Tamil" if lang == "ta" else "English"
            crop_name = timeline.get('crop_name', 'crop')
            
            prompt = f"""
            Generate step-by-step harvest guidance for {crop_name} in {language_name}.
            Include simple practical steps for an Indian farmer.
            Format as a bulleted list.
            """
            guidance = self.llm_service.generate_response(prompt, max_tokens=250)
            
            return {
                "crop": crop_name,
                "guidance": guidance,
                "key_steps": [
                    "Harvest in morning when cool",
                    "Use sharp, clean tools",
                    "Handle produce gently",
                    "Clean and sort immediately",
                    "Store in dry, ventilated area"
                ]
            }
        except:
            return {
                "crop": timeline.get('crop_name', 'crop'),
                "guidance": "Harvest when fully mature. Handle carefully. Store properly.",
                "key_steps": ["Check maturity", "Harvest carefully", "Store properly"]
            }
