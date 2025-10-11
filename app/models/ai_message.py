"""AI Message domain model"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
from enum import Enum


class MessageRole(str, Enum):
    """Message role enum"""
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class AIMessageBase(BaseModel):
    """Base AI message fields"""
    content: str
    thread_id: int
    role: MessageRole
    meta: Optional[Dict[str, Any]] = None


class AIMessageCreate(AIMessageBase):
    """AI message creation model"""
    pass


class AIMessageUpdate(BaseModel):
    """AI message update model - all fields optional"""
    content: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class AIMessage(AIMessageBase):
    """Complete AI message model from database"""
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

