"""Notification domain model"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from enum import Enum


class NotificationStatus(str, Enum):
    """Notification status enum"""
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    RESOLVED = "RESOLVED"


class NotificationBase(BaseModel):
    """Base notification fields"""
    title: str
    content: str
    due_date: datetime
    task_id: int
    user_id: str  # UUID as string
    status: NotificationStatus = NotificationStatus.SCHEDULED


class NotificationCreate(NotificationBase):
    """Notification creation model"""
    pass


class NotificationUpdate(BaseModel):
    """Notification update model - all fields optional"""
    title: Optional[str] = None
    content: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[NotificationStatus] = None


class Notification(NotificationBase):
    """Complete notification model from database"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

