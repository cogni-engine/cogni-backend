from pydantic import BaseModel
from enum import Enum
from typing import List, Optional, Dict, Any

class NotificationStatus(str, Enum):
    scheduled = "scheduled"
    delivered = "delivered"
    read = "read"
    archived = "archived"

class Notification(BaseModel):
    id: int
    title: str
    content: str
    user_id: str
    meta: Optional[Dict[str, Any]] = None
    due_date: Optional[str] = None  # ISO format string
    createdAt: str
    updatedAt: str
    status: NotificationStatus
    task_id: Optional[int] = None
    suggestions: Optional[List[str]] = None

class NotificationCreateRequest(BaseModel):
    task_id: int

class NotificationUpdateStatusRequest(BaseModel):
    status: NotificationStatus

class NotificationUpdate(BaseModel):
    action: str  # "create", "update", "delete"
    notification_id: Optional[int] = None  # update/deleteの場合のみ
    notification_data: Optional[Dict[str, Any]] = None  # create/updateの場合のみ

class NotificationAnalysisRequest(BaseModel):
    task: Dict[str, Any]  # タスクの完全な情報
    current_notifications: List[Dict[str, Any]]

class NotificationAnalysisResponse(BaseModel):
    updates: List[Dict[str, Any]]
    summary: str

