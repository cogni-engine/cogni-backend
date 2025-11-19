"""Notifications repository"""
from typing import List

from supabase import Client  # type: ignore

from app.models.notification import (
    AINotification,
    AINotificationCreate,
    NotificationStatus,
    AINotificationUpdate,
)

from .base import BaseRepository


class AINotificationRepository(BaseRepository[AINotification, AINotificationCreate, AINotificationUpdate]):
    """Repository for AI notification operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "ai_notifications", AINotification)
    
    async def find_by_user(self, user_id: str) -> List[AINotification]:
        """Find all AI notifications for a user"""
        return await self.find_by_filters({"user_id": user_id})
    
    async def mark_sent(self, notification_id: int) -> AINotification | None:
        """Mark an AI notification as sent"""
        update_data = AINotificationUpdate(status=NotificationStatus.SENT)
        return await self.update(notification_id, update_data)
    
    async def delete_by_task(self, task_id: int) -> int:
        """Delete all notifications associated with a specific task
        
        Args:
            task_id: The task ID to delete notifications for
            
        Returns:
            Number of deleted notifications
        """
        response = self._client.table(self._table_name).delete().eq("task_id", task_id).execute()
        return len(response.data) if response.data else 0
    
    async def delete_by_tasks(self, task_ids: List[int]) -> int:
        """Delete all notifications for multiple tasks
        
        Args:
            task_ids: List of task IDs to delete notifications for
            
        Returns:
            Number of deleted notifications
        """
        if not task_ids:
            return 0
        response = self._client.table(self._table_name).delete().in_("task_id", task_ids).execute()
        return len(response.data) if response.data else 0