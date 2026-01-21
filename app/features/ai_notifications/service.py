"""Business logic for AI Notifications"""

from uuid import UUID
from sqlalchemy.orm import Session

from app.features.ai_notifications.repository import AINotificationRepository
from app.features.ai_notifications.domain import (
    CompleteNotificationResponse,
    PostponeNotificationResponse,
)


class AINotificationService:
    """Service layer for AI notification business logic"""
    
    def __init__(self, db: Session):
        self.repository = AINotificationRepository(db)
    
    def complete_notification(
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
        notification = self.repository.get_notification_by_id(notification_id, user_id)
        if not notification:
            raise ValueError(f"Notification {notification_id} not found")
        
        # Perform the completion (I/O delegated to repository)
        completed_id, resolved_ids = self.repository.complete_notification_and_resolve_previous(
            notification_id, user_id
        )
        
        # Build response (pure logic)
        return CompleteNotificationResponse(
            completed_notification_id=completed_id,
            resolved_notification_ids=resolved_ids,
            message=f"Notification {completed_id} completed. {len(resolved_ids)} previous notifications resolved."
        )
    
    def postpone_notification(
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
        notification = self.repository.get_notification_by_id(notification_id, user_id)
        if not notification:
            raise ValueError(f"Notification {notification_id} not found")
        
        # Perform the postponement (I/O delegated to repository)
        postponed_id, resolved_ids = self.repository.postpone_notification_and_resolve_previous(
            notification_id, user_id, reaction_text
        )
        
        # Build response (pure logic)
        return PostponeNotificationResponse(
            postponed_notification_id=postponed_id,
            resolved_notification_ids=resolved_ids,
            message=f"Notification {postponed_id} postponed. {len(resolved_ids)} previous notifications resolved."
        )
