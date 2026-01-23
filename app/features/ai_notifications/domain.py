"""Domain models for AI Notifications feature"""

from pydantic import BaseModel, field_serializer
from enum import Enum
from typing import Optional
from datetime import datetime
from uuid import UUID


class NotificationStatus(str, Enum):
    """Notification status enum"""
    SCHEDULED = "scheduled"
    SENT = "sent"
    RESOLVED = "resolved"


class ReactionStatus(str, Enum):
    """Reaction status enum for user reactions to notifications"""
    NONE = "None"
    COMPLETED = "completed"
    POSTPONED = "postponed"
    DISMISSED = "dismissed"


class TaskResult(BaseModel):
    """Task result model (embedded in notification response)"""
    id: int
    task_id: int
    result_title: str
    result_text: str
    executed_at: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True


class AINotificationBase(BaseModel):
    """Base AI notification fields"""
    title: str
    ai_context: str
    body: Optional[str] = None
    due_date: datetime
    task_id: int
    task_result_id: Optional[int] = None
    user_id: UUID | str  # Accept both UUID and string
    workspace_member_id: Optional[int] = None
    status: NotificationStatus = NotificationStatus.SCHEDULED
    reaction_status: ReactionStatus = ReactionStatus.NONE
    reaction_text: Optional[str] = None
    
    @field_serializer('user_id')
    def serialize_user_id(self, user_id: UUID | str) -> str:
        """Serialize UUID to string for JSON"""
        return str(user_id)

    def has_reaction(self) -> bool:
        return self.reaction_status != ReactionStatus.NONE

    def can_be_actioned(self) -> bool:
        return self.status == NotificationStatus.SENT and not self.has_reaction()


class AINotificationCreate(AINotificationBase):
    """AI notification creation model"""
    pass


class AINotificationUpdate(BaseModel):
    """AI notification update model - all fields optional"""
    title: Optional[str] = None
    ai_context: Optional[str] = None
    body: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[NotificationStatus] = None


class AINotification(AINotificationBase):
    """Complete AI notification domain model"""
    id: int
    created_at: datetime
    updated_at: datetime
    task_result: Optional[TaskResult] = None  # Included if notification has a task_result_id
    
    class Config:
        from_attributes = True


