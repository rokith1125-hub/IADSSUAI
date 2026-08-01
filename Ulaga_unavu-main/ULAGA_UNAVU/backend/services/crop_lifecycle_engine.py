"""
CropLifecycleEngine - Centralized crop state management
Makes ONE selected crop drive entire system behavior
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from services.local_storage import db_service
from api.fertilizer.scheduler import FertilizerScheduler
from api.growth.tracker import GrowthTracker

logger = logging.getLogger(__name__)


class CropLifecycleEngine:
    """
    Centralized lifecycle intelligence engine.
    Makes ONE selected crop drive entire system behavior.
    """
    
    # Crop growth stages
    STAGES = [
        "Planning",      # Before start
        "Germination",   # Days 1-15
        "Vegetative",    # Days 15-45
        "Flowering",     # Days 45-75
        "Fruiting",      # Days 75-105
        "Harvest Ready", # Days 105+
        "Harvested"      # Completed
    ]
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.current_crop = None
        self.fertilizer_scheduler = FertilizerScheduler()
        self.growth_tracker = GrowthTracker()
        self._load_active_crop()
    
    def _load_active_crop(self):
        """Load the active crop for this user"""
        try:
            collection = db_service.get_collection('crop_selections')
            self.current_crop = collection.find_one(
                {"user_id": self.user_id, "is_active": True},
                {"_id": 0}
            )
        except Exception as e:
            logger.error(f"Error loading crop: {e}")
            self.current_crop = None
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get complete current state of the crop lifecycle"""
        if not self.current_crop:
            return {
                "status": "no_crop",
                "message": "No crop selected",
                "stage": None,
                "days_elapsed": 0,
                "days_remaining": 0,
                "progress_percent": 0,
                "can_start": True
            }
        
        # Check if growth has started
        start_date = self.current_crop.get("growth_timeline", {}).get("start_date")
        
        if not start_date:
            # Growth hasn't started yet
            return {
                "status": "not_started",
                "message": "Growth not started - Click 'Start Growth' to begin",
                "stage": "Planning",
                "days_elapsed": 0,
                "days_remaining": self._get_total_growth_days(),
                "progress_percent": 0,
                "can_start": True,
                "crop_name": self.current_crop.get("crop_name")
            }
        
        # Calculate current state
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00')) if isinstance(start_date, str) else start_date
        now = datetime.now()
        days_elapsed = (now - start.replace(tzinfo=None) if start.tzinfo else now - start).days
        
        current_stage, progress_percent = self._calculate_stage(days_elapsed)
        total_days = self._get_total_growth_days()
        days_remaining = max(0, total_days - days_elapsed - 1)
        
        return {
            "status": "active",
            "message": f"Currently in {current_stage} stage",
            "stage": current_stage,
            "days_elapsed": days_elapsed,
            "days_remaining": days_remaining,
            "progress_percent": min(100, progress_percent),
            "can_start": False,
            "crop_name": self.current_crop.get("crop_name"),
            "start_date": start_date,
            "expected_harvest": (start + timedelta(days=max(total_days - 1, 0))).isoformat() if start else None
        }
    
    def _calculate_stage(self, days_elapsed: int) -> tuple:
        """Calculate current stage based on days elapsed"""
        total_days = self._get_total_growth_days()
        
        if total_days == 0:
            return "Planning", 0
        
        progress = (days_elapsed + 1) / total_days
        
        if progress < 0.15:
            return "Germination", int(progress * 100)
        elif progress < 0.40:
            return "Vegetative", int(progress * 100)
        elif progress < 0.70:
            return "Flowering", int(progress * 100)
        elif progress < 0.95:
            return "Fruiting", int(progress * 100)
        elif progress < 1.0:
            return "Harvest Ready", 95
        else:
            return "Harvested", 100
    
    def _get_total_growth_days(self) -> int:
        """Get total growth days for current crop"""
        try:
            timeline_collection = db_service.get_collection('growth_timelines')
            active_timeline = timeline_collection.find_one(
                {"user_id": self.user_id, "is_active": True},
                sort=[("updated_at", -1)]
            )
            if active_timeline and active_timeline.get("total_days"):
                return int(active_timeline.get("total_days"))
        except Exception as e:
            logger.warning("Could not read active timeline total days for %s: %s", self.user_id, e)

        if not self.current_crop:
            return 120  # Default
        
        crop_details = self.current_crop.get("crop_details", {})
        raw_days = crop_details.get("growth_days", 120)
        try:
            parsed = int(float(raw_days))
            return parsed if parsed > 0 else 120
        except Exception:
            return 120

    def _parse_start_date(self, start_date: Optional[str]) -> datetime:
        """Parse optional start date; defaults to current UTC datetime."""
        if not start_date:
            return datetime.utcnow()

        if isinstance(start_date, datetime):
            return start_date

        if not isinstance(start_date, str):
            raise ValueError("Invalid start date")

        cleaned = start_date.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed

    def _get_dataset_stage_context(self, crop_name: str) -> Dict[str, Any]:
        """Resolve first stage and total days from dataset; fallback to selected crop details."""
        # Primary: growth dataset.
        growth_data = self.growth_tracker._get_growth_data(crop_name)
        if growth_data:
            stages = growth_data.get("stages", []) or []
            first_stage = (stages[0].get("stage") or stages[0].get("name")) if stages else None
            total_growth_days = growth_data.get("total_growth_days") or self._get_total_growth_days()
            if first_stage:
                return {
                    "first_stage": first_stage,
                    "total_growth_days": int(total_growth_days) if str(total_growth_days).strip() else self._get_total_growth_days()
                }

        # Fallback: crop_details from selected crop (supports crops not present in growth_data.json).
        crop_details = (self.current_crop or {}).get("crop_details", {}) or {}
        detail_stages = crop_details.get("stages") or []
        first_detail_stage = None
        if detail_stages:
            first_item = detail_stages[0]
            if isinstance(first_item, dict):
                first_detail_stage = first_item.get("stage") or first_item.get("name")
            elif isinstance(first_item, str):
                first_detail_stage = first_item

        total_growth_days = crop_details.get("growth_days") or crop_details.get("total_growth_days") or self._get_total_growth_days()
        if not first_detail_stage:
            first_detail_stage = "Germination"

        return {
            "first_stage": str(first_detail_stage),
            "total_growth_days": int(total_growth_days) if str(total_growth_days).strip() else self._get_total_growth_days()
        }
    
    def start_growth(self, start_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Start farming lifecycle explicitly from "Generate Process" action.
        Validates active crop state, initializes fertilizer + growth tracking + notification,
        and updates active crop timeline in one controlled flow.
        """
        if not self.current_crop:
            return {"success": False, "error": "Select crop first", "status_code": 400}

        if self.current_crop.get("harvested"):
            return {"success": False, "error": "Crop already harvested", "status_code": 400}

        growth_timeline = self.current_crop.get("growth_timeline", {}) or {}
        existing_start = growth_timeline.get("start_date")
        if existing_start or growth_timeline.get("status") == "active":
            return {"success": False, "error": "Farming already started", "status_code": 400}

        crop_name = str(self.current_crop.get("crop_name", "")).strip()
        if not crop_name:
            return {"success": False, "error": "Select crop first", "status_code": 400}

        stage_context = self._get_dataset_stage_context(crop_name)

        try:
            growth_start_dt = self._parse_start_date(start_date)
        except Exception:
            return {"success": False, "error": "Invalid start date", "status_code": 400}

        growth_start_iso = growth_start_dt.isoformat()
        first_stage = stage_context["first_stage"]
        total_growth_days = stage_context["total_growth_days"]

        crop_collection = db_service.get_collection("crop_selections")
        fert_collection = db_service.get_collection("fertilizer_schedules")
        growth_collection = db_service.get_collection("growth_timelines")
        notification_collection = db_service.get_collection("notifications")

        previous_crop_timeline = dict(growth_timeline)
        previous_active_fertilizer = fert_collection.find_one({"user_id": self.user_id, "is_active": True})
        previous_active_growth = growth_collection.find_one({"user_id": self.user_id, "is_active": True})

        created_fertilizer_id = None
        created_growth_id = None
        created_notification_id = None

        try:
            # 1) Initialize fertilizer schedule from real scheduler (no simulation).
            fertilizer_plan = self.fertilizer_scheduler.create_fertilizer_plan_for_crop(
                self.user_id,
                crop_name,
                self.current_crop.get("crop_details", {}),
                start_date=growth_start_dt,
                crop_selection_id=self.current_crop.get("_id")
            )
            if not isinstance(fertilizer_plan, dict) or fertilizer_plan.get("error"):
                raise RuntimeError(fertilizer_plan.get("error", "Fertilizer initialization failed"))
            created_fertilizer_id = fertilizer_plan.get("_id") or fertilizer_plan.get("plan_id")

            # 2) Initialize growth tracking entry from growth dataset.
            growth_timeline_doc = self.growth_tracker.start_tracking(
                self.user_id,
                start_date=growth_start_dt
            )
            if not isinstance(growth_timeline_doc, dict):
                raise RuntimeError("Growth tracking initialization failed")
            created_growth_id = growth_timeline_doc.get("_id")

            # 3) Create first lifecycle notification entry.
            notif_result = notification_collection.insert_one({
                "user_id": self.user_id,
                "type": "farming_started",
                "title": "Farming Process Started",
                "message": f"{crop_name} farming lifecycle started",
                "is_read": False,
                "status": "active",
                "created_at": datetime.utcnow().isoformat()
            })
            created_notification_id = str(notif_result.inserted_id)

            # 4) Activate crop timeline state.
            crop_collection.update_one(
                {"user_id": self.user_id, "is_active": True},
                {"$set": {
                    "growth_timeline.start_date": growth_start_iso,
                    "growth_timeline.status": "active",
                    "growth_timeline.current_stage": first_stage,
                    "growth_timeline.progress_percent": 0
                }}
            )

            self._load_active_crop()
            logger.info("Farming lifecycle started for user: %s", self.user_id)

            return {
                "success": True,
                "status": "farming_started",
                "start_date": growth_start_iso,
                "current_stage": first_stage,
                "total_growth_days": total_growth_days,
                "next_step": "Track Growth"
            }

        except Exception as e:
            # Best-effort rollback to keep state consistent in local-storage mode.
            try:
                crop_collection.update_one(
                    {"user_id": self.user_id, "is_active": True},
                    {"$set": {
                        "growth_timeline.start_date": previous_crop_timeline.get("start_date"),
                        "growth_timeline.status": previous_crop_timeline.get("status", "not_started"),
                        "growth_timeline.current_stage": previous_crop_timeline.get("current_stage", "Planning"),
                        "growth_timeline.progress_percent": previous_crop_timeline.get("progress_percent", 0)
                    }}
                )

                if created_notification_id:
                    notification_collection.delete_one({"_id": created_notification_id})

                if created_growth_id:
                    growth_collection.delete_one({"_id": created_growth_id})
                if previous_active_growth and previous_active_growth.get("_id"):
                    growth_collection.update_one(
                        {"_id": previous_active_growth.get("_id")},
                        {"$set": {"is_active": True}}
                    )

                if created_fertilizer_id:
                    fert_collection.delete_one({"_id": created_fertilizer_id})
                if previous_active_fertilizer and previous_active_fertilizer.get("_id"):
                    fert_collection.update_one(
                        {"_id": previous_active_fertilizer.get("_id")},
                        {"$set": {"is_active": True}}
                    )
            except Exception as rollback_error:
                logger.error("Lifecycle rollback failed: %s", rollback_error)

            logger.error("Lifecycle start failed: %s", e)
            return {
                "success": False,
                "error": "Farming initialization failed",
                "status_code": 503
            }
    
    def advance_stage(self, new_stage: str) -> Dict[str, Any]:
        """Manually advance to next stage"""
        if new_stage not in self.STAGES:
            return {
                "success": False,
                "error": f"Invalid stage: {new_stage}"
            }
        
        try:
            collection = db_service.get_collection('crop_selections')
            collection.update_one(
                {"user_id": self.user_id, "is_active": True},
                {"$set": {
                    "growth_timeline.current_stage": new_stage
                }}
            )
            
            self._load_active_crop()
            
            return {
                "success": True,
                "message": f"Stage advanced to {new_stage}",
                "stage": new_stage
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_fertilizer_for_current_stage(self) -> List[Dict]:
        """Get fertilizer recommendations for current growth stage"""
        state = self.get_current_state()
        stage = state.get("stage", "Planning")
        
        # Get fertilizer schedules for this crop
        try:
            fert_collection = db_service.get_collection('fertilizer_schedules')
            schedules = list(fert_collection.find(
                {"user_id": self.user_id},
                {"_id": 0}
            ).sort("stage_order", 1))
            
            # Filter by current stage
            current_stage_ferts = [
                s for s in schedules 
                if s.get("stage", "").lower() == stage.lower()
            ]
            
            return current_stage_ferts if current_stage_ferts else schedules[:3]
            
        except Exception as e:
            logger.error(f"Error getting fertilizer: {e}")
            return []
    
    def get_risk_assessment(self) -> Dict[str, Any]:
        """Get risk level based on stage + weather + disease"""
        risks = []
        risk_level = "low"
        
        # Check disease results
        try:
            disease_collection = db_service.get_collection('disease_results')
            latest_disease = disease_collection.find_one(
                {"user_id": self.user_id},
                sort=[("created_at", -1)]
            )
            
            if latest_disease:
                severity = latest_disease.get("severity", "Low")
                if severity == "High":
                    risks.append({
                        "type": "disease",
                        "severity": "high",
                        "message": f"Disease detected: {latest_disease.get('disease_name')}"
                    })
                    risk_level = "high"
                elif severity == "Medium":
                    risks.append({
                        "type": "disease", 
                        "severity": "medium",
                        "message": f"Disease warning: {latest_disease.get('disease_name')}"
                    })
                    if risk_level != "high":
                        risk_level = "medium"
        except Exception as e:
            logger.error(f"Error checking disease: {e}")
        
        return {
            "risk_level": risk_level,
            "risks": risks,
            "recommendations": self._get_risk_recommendations(risk_level)
        }
    
    def _get_risk_recommendations(self, risk_level: str) -> List[str]:
        """Get recommendations based on risk level"""
        if risk_level == "high":
            return [
                "Immediate action required",
                "Check crop for disease treatment",
                "Avoid fertilizer application"
            ]
        elif risk_level == "medium":
            return [
                "Monitor crop closely",
                "Consider preventive measures"
            ]
        else:
            return [
                "Continue regular maintenance",
                "Follow fertilizer schedule"
            ]
    
    def get_market_readiness(self) -> Dict[str, Any]:
        """Check if crop is ready for market sale"""
        state = self.get_current_state()
        
        if state.get("stage") == "Harvest Ready":
            return {
                "ready": True,
                "message": "Crop is ready for harvest and market sale!",
                "recommendation": "Check current market prices"
            }
        elif state.get("stage") == "Harvested":
            return {
                "ready": True,
                "message": "Harvest complete - sell now for best prices",
                "recommendation": "Review market trends"
            }
        else:
            days_remaining = state.get("days_remaining", 0)
            return {
                "ready": False,
                "message": f"Not ready for harvest",
                "days_remaining": days_remaining,
                "recommendation": f"Wait approximately {days_remaining} days"
            }
    
    def get_unified_crop_context(self) -> Dict[str, Any]:
        """Get complete unified context for all modules"""
        state = self.get_current_state()
        risks = self.get_risk_assessment()
        market = self.get_market_readiness()
        fertilizers = self.get_fertilizer_for_current_stage()
        
        return {
            "crop": self.current_crop,
            "lifecycle_state": state,
            "risk_assessment": risks,
            "market_readiness": market,
            "current_fertilizers": fertilizers,
            "dashboard_data": {
                "crop_name": state.get("crop_name"),
                "current_stage": state.get("stage"),
                "progress": state.get("progress_percent"),
                "risk_level": risks.get("risk_level"),
                "market_ready": market.get("ready"),
                "next_action": self._get_next_action(state, risks, market)
            }
        }
    
    def _get_next_action(self, state: Dict, risks: Dict, market: Dict) -> str:
        """Determine next recommended action"""
        if state.get("status") == "not_started":
            return "Start Growth"
        
        if risks.get("risk_level") == "high":
            return "Check Disease Detection"
        
        if market.get("ready"):
            return "Check Market Prices"
        
        stage = state.get("stage")
        if stage == "Germination":
            return "Apply First Fertilizer"
        elif stage == "Vegetative":
            return "Monitor Growth"
        elif stage == "Flowering":
            return "Check Weather"
        elif stage == "Fruiting":
            return "Prepare for Harvest"
        
        return "Continue Monitoring"


def get_lifecycle_engine(user_id: str) -> CropLifecycleEngine:
    """Factory function to get lifecycle engine"""
    return CropLifecycleEngine(user_id)
