"""Task domain model"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TaskBase(BaseModel):
    """Base task fields for creation"""
    title: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    status: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    source_note_id: Optional[int] = None


class TaskCreate(TaskBase):
    """Task creation model"""
    user_id: str   # UUID as string
    assigner_id: Optional[str] = None


class TaskUpdate(BaseModel):
    """Task update model - all fields optional"""
    title: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    status: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    completed_at: Optional[datetime] = None
    assigner_id: Optional[str] = None


class Task(TaskBase):
    """Complete task model from database"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    user_id: str
    assigner_id: Optional[str] = None
    
    class Config:
        from_attributes = True

