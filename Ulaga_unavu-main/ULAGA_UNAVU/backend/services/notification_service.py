"""
Notification service for farmer alerts and reminders
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os
from enum import Enum
from .local_storage import db_service

logger = logging.getLogger(__name__)

class NotificationType(Enum):
    """Notification types"""
    WEATHER_ALERT = "weather_alert"
    FERTILIZER_REMINDER = "fertilizer_reminder"
    DISEASE_ALERT = "disease_alert"
    MARKET_UPDATE = "market_update"
    GROWTH_STAGE = "growth_stage"
    SYSTEM = "system"
    NEWS = "news"

class NotificationPriority(Enum):
    """Notification priorities"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class NotificationService:
    """Service for managing farmer notifications"""
    
    def __init__(self):
        self.db_service = db_service
    
    def create_notification(self, user_id: str, notification_type: NotificationType, 
                          title: str, message: str, priority: NotificationPriority = NotificationPriority.MEDIUM,
                          data: Dict = None, schedule_time: datetime = None) -> str:
        """Create a new notification"""
        try:
            now_iso = datetime.utcnow().isoformat()
            scheduled_iso = (schedule_time or datetime.utcnow()).isoformat()
            notification = {
                "user_id": user_id,
                "type": notification_type.value,
                "title": title,
                "message": message,
                "priority": priority.value,
                "data": data or {},
                "status": "pending",
                "is_read": False,
                "scheduled_for": scheduled_iso,
                "created_at": now_iso,
                "updated_at": now_iso
            }
            
            collection = self.db_service.get_collection('notifications')
            result = collection.insert_one(notification)
            
            logger.info(f"Notification created for user {user_id}: {title}")
            
            # Trigger immediate delivery if not scheduled
            if not schedule_time or schedule_time <= datetime.utcnow():
                self._deliver_notification(str(result.inserted_id))
            
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            raise
    
    def get_user_notifications(self, user_id: str, unread_only: bool = False, 
                              limit: int = 50) -> List[Dict]:
        """Get notifications for user"""
        try:
            collection = self.db_service.get_collection('notifications')
            
            query = {"user_id": user_id}
            if unread_only:
                query["is_read"] = False
            
            notifications = list(collection.find(
                query,
                sort=[("created_at", -1)],
                limit=limit
            ))
            
            # Convert ObjectId to string
            for notification in notifications:
                notification_id = notification.pop('_id', None)
                if notification_id is not None:
                    notification['notification_id'] = str(notification_id)
            
            return notifications
            
        except Exception as e:
            logger.error(f"Error getting notifications: {str(e)}")
            return []
    
    def mark_as_read(self, notification_id: str, user_id: str = None) -> bool:
        """Mark notification as read"""
        try:
            collection = self.db_service.get_collection('notifications')
            
            query = {"_id": notification_id}
            if user_id:
                query["user_id"] = user_id
            
            result = collection.update_one(
                query,
                {
                    "$set": {
                        "is_read": True,
                        "read_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat()
                    }
                }
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}")
            return False
    
    def mark_all_as_read(self, user_id: str) -> int:
        """Mark all user notifications as read"""
        try:
            collection = self.db_service.get_collection('notifications')
            
            result = collection.update_many(
                {"user_id": user_id, "is_read": False},
                {
                    "$set": {
                        "is_read": True,
                        "read_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat()
                    }
                }
            )
            
            logger.info(f"Marked {result.modified_count} notifications as read for user {user_id}")
            return result.modified_count
            
        except Exception as e:
            logger.error(f"Error marking all as read: {str(e)}")
            return 0
    
    def delete_notification(self, notification_id: str, user_id: str = None) -> bool:
        """Delete notification"""
        try:
            collection = self.db_service.get_collection('notifications')
            
            query = {"_id": notification_id}
            if user_id:
                query["user_id"] = user_id
            
            result = collection.delete_one(query)
            
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"Error deleting notification: {str(e)}")
            return False
    
    def create_weather_alert(self, user_id: str, weather_data: Dict) -> str:
        """Create weather alert notification"""
        try:
            alerts = weather_data.get('alerts', [])
            if not alerts:
                return None
            
            # Create notification for each alert
            notification_ids = []
            for alert in alerts:
                title = f"Weather Alert: {alert.get('type', 'alert').replace('_', ' ').title()}"
                message = alert.get('message', 'Weather condition alert')
                priority = NotificationPriority.HIGH if alert.get('severity') == 'high' else NotificationPriority.MEDIUM
                
                nid = self.create_notification(
                    user_id=user_id,
                    notification_type=NotificationType.WEATHER_ALERT,
                    title=title,
                    message=message,
                    priority=priority,
                    data={"weather_alert": alert}
                )
                
                if nid:
                    notification_ids.append(nid)
            
            return notification_ids[0] if notification_ids else None
            
        except Exception as e:
            logger.error(f"Error creating weather alert: {str(e)}")
            return None
    
    def create_fertilizer_reminder(self, user_id: str, fertilizer_data: Dict) -> str:
        """Create fertilizer reminder notification"""
        try:
            days_until = fertilizer_data.get('days_until_next', 0)
            
            if days_until <= 0:
                # Due today or overdue
                title = "Fertilizer Application Due Today"
                message = f"Apply {fertilizer_data.get('next_fertilizer', 'fertilizer')} today"
                priority = NotificationPriority.HIGH
            elif days_until <= 1:
                # Due tomorrow
                title = "Fertilizer Application Tomorrow"
                message = f"Prepare to apply {fertilizer_data.get('next_fertilizer', 'fertilizer')} tomorrow"
                priority = NotificationPriority.MEDIUM
            elif days_until <= 3:
                # Due in 3 days
                title = "Upcoming Fertilizer Application"
                message = f"Fertilizer application in {days_until} days"
                priority = NotificationPriority.LOW
            else:
                return None  # Not urgent enough
            
            return self.create_notification(
                user_id=user_id,
                notification_type=NotificationType.FERTILIZER_REMINDER,
                title=title,
                message=message,
                priority=priority,
                data={"fertilizer_data": fertilizer_data}
            )
            
        except Exception as e:
            logger.error(f"Error creating fertilizer reminder: {str(e)}")
            return None
    
    def create_disease_alert(self, user_id: str, disease_data: Dict) -> str:
        """Create disease alert notification"""
        try:
            severity = disease_data.get('severity_level', 'Medium')
            
            if severity in ['High', 'Critical']:
                title = f"⚠️ Disease Alert: {disease_data.get('disease_name', 'Disease')}"
                message = f"Immediate action needed for {disease_data.get('disease_name', 'disease')}"
                priority = NotificationPriority.HIGH
            else:
                title = f"Disease Detected: {disease_data.get('disease_name', 'Disease')}"
                message = f"Monitor for {disease_data.get('disease_name', 'disease')} symptoms"
                priority = NotificationPriority.MEDIUM
            
            return self.create_notification(
                user_id=user_id,
                notification_type=NotificationType.DISEASE_ALERT,
                title=title,
                message=message,
                priority=priority,
                data={"disease_data": disease_data}
            )
            
        except Exception as e:
            logger.error(f"Error creating disease alert: {str(e)}")
            return None
    
    def create_market_update(self, user_id: str, market_data: Dict) -> str:
        """Create market update notification"""
        try:
            decision = market_data.get('decision', '')
            
            if decision == 'SELL':
                title = "Market Opportunity: Good Time to Sell"
                message = f"Consider selling {market_data.get('crop', 'crop')} at current prices"
                priority = NotificationPriority.MEDIUM
            elif decision == 'WAIT':
                title = "Market Update: Hold Your Produce"
                message = f"Better prices expected for {market_data.get('crop', 'crop')} soon"
                priority = NotificationPriority.LOW
            else:
                return None
            
            return self.create_notification(
                user_id=user_id,
                notification_type=NotificationType.MARKET_UPDATE,
                title=title,
                message=message,
                priority=priority,
                data={"market_data": market_data}
            )
            
        except Exception as e:
            logger.error(f"Error creating market update: {str(e)}")
            return None
    
    def create_growth_stage_notification(self, user_id: str, growth_data: Dict) -> str:
        """Create growth stage notification"""
        try:
            stage = growth_data.get('current_stage', '')
            
            if stage and stage != 'Unknown':
                title = f"Crop Stage Update: {stage}"
                message = f"Your crop has entered {stage} stage. Check recommended practices."
                priority = NotificationPriority.INFO
                
                return self.create_notification(
                    user_id=user_id,
                    notification_type=NotificationType.GROWTH_STAGE,
                    title=title,
                    message=message,
                    priority=priority,
                    data={"growth_data": growth_data}
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating growth stage notification: {str(e)}")
            return None
    
    def create_daily_summary(self, user_id: str, summary_data: Dict) -> str:
        """Create daily summary notification"""
        try:
            title = "Your Daily Farming Summary"
            message = "Check today's weather, tasks, and recommendations"
            priority = NotificationPriority.INFO
            
            return self.create_notification(
                user_id=user_id,
                notification_type=NotificationType.SYSTEM,
                title=title,
                message=message,
                priority=priority,
                data={"summary_data": summary_data},
                schedule_time=datetime.utcnow().replace(hour=8, minute=0, second=0)  # 8 AM
            )
            
        except Exception as e:
            logger.error(f"Error creating daily summary: {str(e)}")
            return None
    
    def schedule_notifications(self, user_id: str, user_data: Dict):
        """Schedule regular notifications for user"""
        try:
            # Clear existing scheduled notifications
            self._clear_scheduled_notifications(user_id)
            
            # Schedule daily summary (8 AM)
            summary_time = datetime.utcnow().replace(hour=8, minute=0, second=0)
            if summary_time < datetime.utcnow():
                summary_time += timedelta(days=1)
            
            self.create_daily_summary(user_id, {})
            
            # Schedule weekly reminder (Monday 9 AM)
            today = datetime.utcnow()
            days_until_monday = (0 - today.weekday()) % 7
            if days_until_monday == 0 and today.hour >= 9:
                days_until_monday = 7
            
            monday_time = (today + timedelta(days=days_until_monday)).replace(hour=9, minute=0, second=0)
            
            self.create_notification(
                user_id=user_id,
                notification_type=NotificationType.SYSTEM,
                title="Weekly Farming Check",
                message="Time for your weekly farm inspection and planning",
                priority=NotificationPriority.LOW,
                schedule_time=monday_time
            )
            
            logger.info(f"Scheduled notifications for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error scheduling notifications: {str(e)}")
    
    def _clear_scheduled_notifications(self, user_id: str):
        """Clear scheduled notifications for user"""
        try:
            collection = self.db_service.get_collection('notifications')
            
            # Delete pending scheduled notifications
            cutoff_iso = datetime.utcnow().isoformat()
            result = collection.delete_many({
                "user_id": user_id,
                "status": "pending",
                "scheduled_for": {"$gt": cutoff_iso}
            })
            
            if result.deleted_count > 0:
                logger.info(f"Cleared {result.deleted_count} scheduled notifications for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error clearing scheduled notifications: {str(e)}")
    
    def _deliver_notification(self, notification_id: str):
        """Deliver notification (simulate delivery)"""
        try:
            collection = self.db_service.get_collection('notifications')
            
            collection.update_one(
                {"_id": notification_id},
                {
                    "$set": {
                        "status": "delivered",
                        "delivered_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat()
                    }
                }
            )
            
            # In production, this would trigger:
            # 1. Push notification to mobile app
            # 2. Email notification
            # 3. SMS notification (for critical alerts)
            
            logger.info(f"Notification {notification_id} delivered")
            
        except Exception as e:
            logger.error(f"Error delivering notification: {str(e)}")
    
    def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications"""
        try:
            collection = self.db_service.get_collection('notifications')
            return collection.count_documents({
                "user_id": user_id,
                "is_read": False
            })
        except Exception as e:
            logger.error(f"Error getting unread count: {str(e)}")
            return 0
    
    def cleanup_old_notifications(self, days_old: int = 30):
        """Cleanup notifications older than specified days"""
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days_old)).isoformat()
            
            collection = self.db_service.get_collection('notifications')
            result = collection.delete_many({
                "created_at": {"$lt": cutoff_date}
            })
            
            logger.info(f"Cleaned up {result.deleted_count} old notifications")
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old notifications: {str(e)}")
            return 0
    
    def send_bulk_notification(self, user_ids: List[str], title: str, message: str, 
                              notification_type: NotificationType = NotificationType.SYSTEM,
                              priority: NotificationPriority = NotificationPriority.INFO) -> int:
        """Send notification to multiple users"""
        try:
            count = 0
            for user_id in user_ids:
                try:
                    self.create_notification(
                        user_id=user_id,
                        notification_type=notification_type,
                        title=title,
                        message=message,
                        priority=priority
                    )
                    count += 1
                except Exception as e:
                    logger.error(f"Error sending to user {user_id}: {str(e)}")
            
            logger.info(f"Sent bulk notification to {count} users")
            return count
            
        except Exception as e:
            logger.error(f"Error sending bulk notification: {str(e)}")
            return 0
