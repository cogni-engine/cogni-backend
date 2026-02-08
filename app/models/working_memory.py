"""Working memory domain model"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class WorkingMemoryBase(BaseModel):
    """Base working memory fields"""
    content: Optional[str] = None
    workspace_id: int


class WorkingMemoryCreate(WorkingMemoryBase):
    """Working memory creation model"""
    pass


class WorkingMemoryUpdate(BaseModel):
    """Working memory update model - all fields optional"""
    content: Optional[str] = None


class WorkingMemory(WorkingMemoryBase):
    """Complete working memory model from database"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
