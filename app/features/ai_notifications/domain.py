"""Domain models for AI Notifications feature"""

from pydantic import BaseModel
from enum import Enum
from typing import Optional
from datetime import datetime


class NotificationStatus(str, Enum):
    """Notification status enum"""
    SCHEDULED = "scheduled"
    SENT = "sent"
    RESOLVED = "resolved"


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


class NoteInfo(BaseModel):
    """Note information for notifications"""
    id: int
    title: Optional[str] = None

    class Config:
        from_attributes = True


class AINotificationBase(BaseModel):
    """Base AI notification fields"""
    title: str
    body: Optional[str] = None
    due_date: datetime
    task_id: int
    workspace_id: int
    workspace_member_id: Optional[int] = None
    status: NotificationStatus = NotificationStatus.SCHEDULED
    reaction_text: Optional[str] = None
    reaction_choices: Optional[list] = None

    def has_reaction(self) -> bool:
        return self.reaction_text is not None

    def can_be_actioned(self) -> bool:
        return self.status == NotificationStatus.SENT and not self.has_reaction()


class AINotificationCreate(AINotificationBase):
    """AI notification creation model"""
    pass


class AINotificationUpdate(BaseModel):
    """AI notification update model - all fields optional"""
    title: Optional[str] = None
    body: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[NotificationStatus] = None


class AINotification(AINotificationBase):
    """Complete AI notification domain model"""
    id: int
    created_at: datetime
    updated_at: datetime
    task_result: Optional[TaskResult] = None
    note: Optional[NoteInfo] = None  # Included if notification's task has a source_note_id

    class Config:
        from_attributes = True


