"""Request and response schemas for AI Notifications API"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.features.ai_notifications.domain import NotificationStatus


class CompleteNotificationRequest(BaseModel):
    """Request model for completing a notification"""
    pass  # Empty since notification_id comes from path


class CompleteNotificationResponse(BaseModel):
    """Response model for notification completion"""
    completed_notification_id: int
    resolved_notification_ids: list[int]
    message: str


class PostponeNotificationRequest(BaseModel):
    """Request model for postponing a notification"""
    reaction_text: str


class PostponeNotificationResponse(BaseModel):
    """Response model for notification postponement"""
    postponed_notification_id: int
    resolved_notification_ids: list[int]
    message: str


class NoteInfo(BaseModel):
    """Note information for reacted notifications"""
    id: int
    title: Optional[str] = None
    
    class Config:
        from_attributes = True


class UserInfo(BaseModel):
    """User information for reacted notifications"""
    id: str  # UUID as string
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    
    class Config:
        from_attributes = True


class ReactedAINotification(BaseModel):
    """AI Notification with note and user information for reacted notifications"""
    id: int
    title: str
    body: Optional[str] = None
    due_date: datetime
    task_id: int
    workspace_id: int
    workspace_member_id: Optional[int] = None
    status: NotificationStatus
    reaction_text: Optional[str] = None
    reaction_choices: Optional[list] = None
    created_at: datetime
    updated_at: datetime

    # Joined data
    note: Optional[NoteInfo] = None
    user: Optional[UserInfo] = None

    class Config:
        from_attributes = True
