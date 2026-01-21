"""SQLAlchemy repository for AI Notifications"""

from datetime import datetime
from typing import List
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from sqlalchemy.sql import select

# SQLAlchemy ORM models
from app.db.models.ai_notification import AINotification as AINotificationORM
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
        Get all past notifications for a specific user.
        
        Returns notifications where due_date is in the past (before current_time),
        regardless of status (scheduled/sent/resolved).
        
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
            # Returns Pydantic AINotification objects
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
                    AINotificationORM.task_result_id.is_(None)
                )
            )
            .group_by(AINotificationORM.task_id)
            .subquery()
        )
        
        # Main query with conditions:
        # - Include notifications WITH task_result_id, OR
        # - Include notifications that match the subquery (most recent per task without result)
        orm_notifications = (
            self.db.query(AINotificationORM)
            .outerjoin(TaskResultORM, AINotificationORM.task_result_id == TaskResultORM.id)
            .filter(
                and_(
                    AINotificationORM.user_id == user_id,
                    AINotificationORM.due_date < current_time,
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
    
    def _to_domain_model(self, orm_notification: AINotificationORM) -> AINotification:
        """
        Convert SQLAlchemy ORM model to Pydantic domain model.
        
        Args:
            orm_notification: SQLAlchemy AINotification ORM object
            
        Returns:
            Pydantic AINotification domain model
        """
        return AINotification.model_validate(orm_notification)
