"""SQLAlchemy repository for AI Notifications"""

from datetime import datetime
from typing import List
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from sqlalchemy.sql import select

# SQLAlchemy ORM models
from app.db.models.ai_notification import (
    AINotification as AINotificationORM, 
    NotificationStatus,
    ReactionStatus
)
from app.db.models.task_result import TaskResult as TaskResultORM

# Pydantic domain models (feature-local)
from app.features.ai_notifications.domain import AINotification


class AINotificationRepository:
    """Repository for AI Notification operations using SQLAlchemy"""
    
    def __init__(self, db: Session):
        """
        Initialize the repository with a database session.
        
        Args:
            db: SQLAlchemy database session
        """
        self.db = db
    
    def get_past_due_notifications_for_user(
        self, 
        user_id: UUID | str,
        current_time: datetime | None = None
    ) -> List[AINotification]:
        """
        Get all past due notifications for a specific user that need action.
        
        Returns notifications where:
        - due_date is in the past
        - status is not "resolved"
        - reaction_status is "None" (not completed, postponed, or dismissed)
        
        Args:
            user_id: The UUID of the user (can be UUID object or string)
            current_time: The reference time to compare against (defaults to now)
            
        Returns:
            List of past AINotification domain models (Pydantic), 
            ordered by due_date (oldest first)
            
        Example:
            ```python
            from app.db import get_db
            from app.features.ai_notifications import AINotificationRepository
            
            db = next(get_db())
            repo = AINotificationRepository(db)
            past_due = repo.get_past_due_notifications_for_user(user_id)
            # Returns Pydantic AINotification objects that need user action
            ```
        """
        if current_time is None:
            current_time = datetime.now()
        
        # Convert string UUID to UUID object if needed
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        # Build query for past notifications with intelligent deduplication:
        # 1. Include ALL notifications that have a task_result_id
        # 2. For notifications WITHOUT task_result_id, only include the most recent per task
        # 3. Exclude resolved notifications or notifications with user reactions
        
        # Subquery: Get the max ID (most recent) for each task where task_result_id is NULL
        subquery = (
            select(
                AINotificationORM.task_id,
                func.max(AINotificationORM.id).label('max_id')
            )
            .where(
                and_(
                    AINotificationORM.user_id == user_id,
                    AINotificationORM.due_date < current_time,
                    AINotificationORM.task_result_id.is_(None),
                    AINotificationORM.status != "resolved",
                    AINotificationORM.reaction_status == "None"
                )
            )
            .group_by(AINotificationORM.task_id)
            .subquery()
        )
        
        # Main query with conditions:
        # - Include notifications WITH task_result_id, OR
        # - Include notifications that match the subquery (most recent per task without result)
        # - EXCLUDE resolved notifications or notifications with reactions
        orm_notifications = (
            self.db.query(AINotificationORM)
            .outerjoin(TaskResultORM, AINotificationORM.task_result_id == TaskResultORM.id)
            .filter(
                and_(
                    AINotificationORM.user_id == user_id,
                    AINotificationORM.due_date < current_time,
                    AINotificationORM.status != "resolved",
                    AINotificationORM.reaction_status == "None",
                    or_(
                        # Include if it has a task_result
                        AINotificationORM.task_result_id.isnot(None),
                        # OR if it's the most recent notification for this task without result
                        and_(
                            AINotificationORM.task_id == subquery.c.task_id,
                            AINotificationORM.id == subquery.c.max_id
                        )
                    )
                )
            )
            .order_by(AINotificationORM.due_date.asc())  # Oldest first
            .all()
        )
        
        # Convert SQLAlchemy ORM models to Pydantic domain models
        domain_notifications = [
            self._to_domain_model(orm_notification)
            for orm_notification in orm_notifications
        ]
        
        return domain_notifications
    
    def get_notification_by_id(
        self, 
        notification_id: int,
        user_id: UUID | str
    ) -> AINotification | None:
        """
        Get a specific notification by ID for a user.
        
        Args:
            notification_id: The notification ID
            user_id: The UUID of the user (for authorization)
            
        Returns:
            AINotification domain model or None if not found
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        orm_notification = (
            self.db.query(AINotificationORM)
            .filter(
                and_(
                    AINotificationORM.id == notification_id,
                    AINotificationORM.user_id == user_id
                )
            )
            .first()
        )
        
        if not orm_notification:
            return None
        
        return self._to_domain_model(orm_notification)
    
    def complete_notification_and_resolve_previous(
        self,
        notification_id: int,
        user_id: UUID | str
    ) -> tuple[int, List[int]]:
        """
        Complete a notification and resolve all previous notifications from the same task.
        
        This method:
        1. Sets the target notification's reaction_status to "completed"
        2. Sets all notifications from the same task with due_date <= target's due_date status to "resolved"
        
        Args:
            notification_id: The ID of the notification being completed
            user_id: The UUID of the user (for authorization)
            
        Returns:
            Tuple of (completed_notification_id, list of resolved_notification_ids)
            
        Raises:
            ValueError: If notification not found or doesn't belong to user
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        # Get the target notification (with row-level lock for consistency)
        target_notification = (
            self.db.query(AINotificationORM)
            .filter(
                and_(
                    AINotificationORM.id == notification_id,
                    AINotificationORM.user_id == user_id
                )
            )
            .with_for_update()
            .first()
        )
        
        if not target_notification:
            raise ValueError(f"Notification {notification_id} not found or access denied")
        
        # Extract task_id and due_date for the query
        task_id = target_notification.task_id
        target_due_date = target_notification.due_date
        
        # Update the target notification's reaction_status to "completed"
        target_notification.reaction_status = ReactionStatus.COMPLETED.value  # type: ignore
        
        # Find all notifications from the same task with due_date <= target's due_date
        # excluding the target itself (it's already set to completed)
        previous_notifications = (
            self.db.query(AINotificationORM)
            .filter(
                and_(
                    AINotificationORM.task_id == task_id,
                    AINotificationORM.user_id == user_id,
                    AINotificationORM.due_date <= target_due_date,
                    AINotificationORM.id != notification_id,
                    # Only update if not already resolved
                    AINotificationORM.status != "resolved"
                )
            )
            .all()
        )
        
        # Update all previous notifications' status to "resolved"
        resolved_ids = []
        for notification in previous_notifications:
            notification.status = NotificationStatus.RESOLVED.value  # type: ignore
            resolved_ids.append(notification.id)
        
        # Commit the transaction (I/O happens here)
        self.db.commit()
        
        return (notification_id, resolved_ids)
    
    def postpone_notification_and_resolve_previous(
        self,
        notification_id: int,
        user_id: UUID | str,
        reaction_text: str
    ) -> tuple[int, List[int]]:
        """
        Postpone a notification with user's reaction text and resolve all previous notifications from the same task.
        
        This method:
        1. Sets the target notification's reaction_status to "postponed"
        2. Stores the user's reaction_text
        3. Sets all notifications from the same task with due_date <= target's due_date status to "resolved"
        
        Args:
            notification_id: The ID of the notification being postponed
            user_id: The UUID of the user (for authorization)
            reaction_text: The user's text response/reason for postponement
            
        Returns:
            Tuple of (postponed_notification_id, list of resolved_notification_ids)
            
        Raises:
            ValueError: If notification not found or doesn't belong to user
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        # Get the target notification (with row-level lock for consistency)
        target_notification = (
            self.db.query(AINotificationORM)
            .filter(
                and_(
                    AINotificationORM.id == notification_id,
                    AINotificationORM.user_id == user_id
                )
            )
            .with_for_update()
            .first()
        )
        
        if not target_notification:
            raise ValueError(f"Notification {notification_id} not found or access denied")
        
        # Extract task_id and due_date for the query
        task_id = target_notification.task_id
        target_due_date = target_notification.due_date
        
        # Update the target notification's reaction_status to "postponed" and store reaction text
        target_notification.reaction_status = ReactionStatus.POSTPONED.value  # type: ignore
        target_notification.reaction_text = reaction_text  # type: ignore
        
        # Find all notifications from the same task with due_date <= target's due_date
        # excluding the target itself (it's already set to postponed)
        previous_notifications = (
            self.db.query(AINotificationORM)
            .filter(
                and_(
                    AINotificationORM.task_id == task_id,
                    AINotificationORM.user_id == user_id,
                    AINotificationORM.due_date <= target_due_date,
                    AINotificationORM.id != notification_id,
                    # Only update if not already resolved
                    AINotificationORM.status != "resolved"
                )
            )
            .all()
        )
        
        # Update all previous notifications' status to "resolved"
        resolved_ids = []
        for notification in previous_notifications:
            notification.status = NotificationStatus.RESOLVED.value  # type: ignore
            resolved_ids.append(notification.id)
        
        # Commit the transaction (I/O happens here)
        self.db.commit()
        
        return (notification_id, resolved_ids)
    
    def _to_domain_model(self, orm_notification: AINotificationORM) -> AINotification:
        """
        Convert SQLAlchemy ORM model to Pydantic domain model.
        
        Args:
            orm_notification: SQLAlchemy AINotification ORM object
            
        Returns:
            Pydantic AINotification domain model
        """
        return AINotification.model_validate(orm_notification)
