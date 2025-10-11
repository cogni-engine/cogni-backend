"""Note domain model"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class NoteBase(BaseModel):
    """Base note fields"""
    text: str
    workspace_id: int


class NoteCreate(NoteBase):
    """Note creation model"""
    pass


class NoteUpdate(BaseModel):
    """Note update model - all fields optional"""
    text: Optional[str] = None
    workspace_id: Optional[int] = None


class Note(NoteBase):
    """Complete note model from database"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

