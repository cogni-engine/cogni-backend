from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class PushTokenBase(BaseModel):
    """Base push token fields"""
    user_id: str  # UUID as string
    expo_push_token: str


class PushTokenCreate(PushTokenBase):
    """Push token creation model"""
    pass


class PushToken(PushTokenBase):
    """Complete push token model from database"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PushNotificationStatus(str):
    """Push notification status constants"""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class PushNotificationBase(BaseModel):
    """Base push notification fields"""
    user_id: str  # UUID as string
    title: str
    body: str
    data: Optional[Dict[str, Any]] = None


class PushNotificationCreate(PushNotificationBase):
    """Push notification creation model"""
    pass


class PushNotification(PushNotificationBase):
    """Complete push notification model from database"""
    id: int
    status: str
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SendNotificationRequest(BaseModel):
    """Request to send a push notification"""
    notificationId: int


class SupabaseWebhookRecord(BaseModel):
    """Push notification record from Supabase webhook"""
    id: int
    user_id: str
    title: str
    body: str
    data: Optional[Dict[str, Any]] = None
    status: str
    sent_at: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str


class SupabaseWebhookPayload(BaseModel):
    """Supabase INSERT webhook payload"""
    type: str  # 'INSERT'
    table: str
    schema: str
    record: SupabaseWebhookRecord
    old_record: Optional[Dict[str, Any]] = None


class ExpoPushMessage(BaseModel):
    """Expo push notification message format"""
    to: str
    title: str
    body: str
    data: Optional[Dict[str, Any]] = None
    sound: str = "default"
    priority: str = "high"
    channelId: str = "default"


class ExpoPushTicket(BaseModel):
    """Expo push notification response ticket"""
    status: str
    id: Optional[str] = None
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class SendPushNotificationResponse(BaseModel):
    """Response from send push notification endpoint"""
    success: bool
    notificationId: int
    sent: int
    failed: int
    tickets: list

