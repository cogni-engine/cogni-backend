"""Notifications repository"""
from typing import List

from supabase import Client  # type: ignore

from app.models.notification import (
    Notification,
    NotificationCreate,
    NotificationStatus,
    NotificationUpdate,
)

from .base import BaseRepository


class NotificationRepository(BaseRepository[Notification, NotificationCreate, NotificationUpdate]):
    """Repository for notification operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "notifications", Notification)
    
    async def find_by_user(self, user_id: str) -> List[Notification]:
        """Find all notifications for a user"""
        return await self.find_by_filters({"user_id": user_id})
    
    async def mark_sent(self, notification_id: int) -> Notification | None:
        """Mark a notification as sent"""
        update_data = NotificationUpdate(status=NotificationStatus.SENT)
        return await self.update(notification_id, update_data)
