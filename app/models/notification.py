from pydantic import BaseModel
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime


class NotificationStatus(str, Enum):
    """Notification status enum"""
    SCHEDULED = "scheduled"  
    SENT = "sent"            
    RESOLVED = "resolved"    

class NotificationCreateRequest(BaseModel):
    task_id: int

class NotificationUpdateStatusRequest(BaseModel):
    status: NotificationStatus

class BulkNotificationUpdate(BaseModel):
    action: str  # "create", "update", "delete"
    notification_id: Optional[int] = None  # update/deleteの場合のみ
    notification_data: Optional[Dict[str, Any]] = None  # create/updateの場合のみ

class NotificationAnalysisRequest(BaseModel):
    task: Dict[str, Any]  # タスクの完全な情報
    current_notifications: List[Dict[str, Any]]

class NotificationAnalysisResponse(BaseModel):
    updates: List[Dict[str, Any]]
    summary: str

class AINotificationBase(BaseModel):
    """Base AI notification fields"""
    title: str
    ai_context: str
    body: Optional[str] = None
    due_date: datetime
    task_id: int
    user_id: str  # UUID as string
    workspace_member_id: Optional[int] = None
    status: NotificationStatus = NotificationStatus.SCHEDULED


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
    """Complete AI notification model from database"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

