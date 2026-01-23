"""Business logic for AI Notifications"""

from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.ai_notifications.repository import AINotificationRepository
from app.features.ai_notifications.schemas import (
    CompleteNotificationResponse,
    PostponeNotificationResponse,
    ReactedAINotification,
)


class AINotificationService:
    """Service layer for AI notification business logic"""
    
    def __init__(self, db: AsyncSession):
        self.repository = AINotificationRepository(db)
    
    async def complete_notification(
        self,
        notification_id: int,
        user_id: UUID | str
    ) -> CompleteNotificationResponse:
        """
        Complete a notification and resolve all previous ones from the same task.
        
        Business rules:
        - User must own the notification
        - Target notification is set to "completed"
        - All notifications from same task with earlier/equal due dates are "resolved"
        
        Args:
            notification_id: The notification to complete
            user_id: The authenticated user ID
            
        Returns:
            CompleteNotificationResponse with affected notification IDs
            
        Raises:
            ValueError: If notification not found or unauthorized
        """
        # Verify notification exists and belongs to user (pure logic, delegates I/O)
        notification = await self.repository.get_notification_by_id(notification_id, user_id)
        if not notification:
            raise ValueError(f"Notification {notification_id} not found")
        if not notification.can_be_actioned():
            raise ValueError(f"Notification {notification_id} has already been actioned upon")
        
        # Perform the completion (I/O delegated to repository)
        completed_id, resolved_ids = await self.repository.complete_notification_and_resolve_previous(
            notification_id, user_id
        )
        
        # Build response (pure logic)
        return CompleteNotificationResponse(
            completed_notification_id=completed_id,
            resolved_notification_ids=resolved_ids,
            message=f"Notification {completed_id} completed. {len(resolved_ids)} previous notifications resolved."
        )
    
    async def postpone_notification(
        self,
        notification_id: int,
        user_id: UUID | str,
        reaction_text: str
    ) -> PostponeNotificationResponse:
        """
        Postpone a notification with user's reaction text and resolve all previous ones from the same task.
        
        Business rules:
        - User must own the notification
        - Target notification is set to "postponed" with reaction_text stored
        - All notifications from same task with earlier/equal due dates are "resolved"
        
        Args:
            notification_id: The notification to postpone
            user_id: The authenticated user ID
            reaction_text: The user's text response/reason for postponement
            
        Returns:
            PostponeNotificationResponse with affected notification IDs
            
        Raises:
            ValueError: If notification not found or unauthorized
        """
        # Verify notification exists and belongs to user (pure logic, delegates I/O)
        notification = await self.repository.get_notification_by_id(notification_id, user_id)
        if not notification:
            raise ValueError(f"Notification {notification_id} not found")
    
        if not notification.can_be_actioned():
            raise ValueError(f"Notification {notification_id} has already been actioned upon")
        
        # Perform the postponement (I/O delegated to repository)
        postponed_id, resolved_ids = await self.repository.postpone_notification_and_resolve_previous(
            notification_id, user_id, reaction_text
        )
        
        # Build response (pure logic)
        return PostponeNotificationResponse(
            postponed_notification_id=postponed_id,
            resolved_notification_ids=resolved_ids,
            message=f"Notification {postponed_id} postponed. {len(resolved_ids)} previous notifications resolved."
        )
    
    async def verify_user_workspace_membership(
        self,
        workspace_id: int,
        user_id: UUID | str
    ) -> None:
        """
        Verify that a user is a member of a workspace.
        
        Args:
            workspace_id: The workspace ID to check
            user_id: The authenticated user ID
            
        Raises:
            ValueError: If user is not a member of the workspace
        """
        is_member = await self.repository.is_user_workspace_member(workspace_id, user_id)
        if not is_member:
            raise ValueError("You are not a member of this workspace")
    
    async def get_reacted_notifications_by_workspace(
        self,
        workspace_id: int,
        workspace_member_ids: Optional[List[int]] = None,
        user_id: Optional[UUID | str] = None
    ) -> List[ReactedAINotification]:
        """
        Get all AI notifications that have been reacted on for a workspace.
        
        Args:
            workspace_id: The workspace ID to filter by
            workspace_member_ids: Optional list of workspace_member_ids to filter by
            user_id: Optional user ID to verify workspace membership
            
        Returns:
            List of ReactedAINotification with note and user information
            
        Raises:
            ValueError: If user_id is provided and user is not a member of the workspace
        """
        if user_id is not None:
            await self.verify_user_workspace_membership(workspace_id, user_id)
        
        return await self.repository.get_reacted_notifications_by_workspace(
            workspace_id,
            workspace_member_ids
        )