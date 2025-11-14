"""AI Message domain model"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from enum import Enum


class MessageRole(str, Enum):
    """Message role enum"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageFile(BaseModel):
    """File attachment model"""
    id: int
    original_filename: str
    file_path: str
    mime_type: str
    file_size: int


class AIMessageBase(BaseModel):
    """Base AI message fields"""
    content: str
    thread_id: int
    role: MessageRole
    meta: Optional[Dict[str, Any]] = None


class AIMessageCreate(AIMessageBase):
    """AI message creation model"""
    file_ids: Optional[List[int]] = None


class AIMessageUpdate(BaseModel):
    """AI message update model - all fields optional"""
    content: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class AIMessage(AIMessageBase):
    """Complete AI message model from database"""
    id: int
    created_at: datetime
    files: Optional[List[MessageFile]] = None
    
    class Config:
        from_attributes = True

