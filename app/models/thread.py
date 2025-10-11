"""Thread domain model"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ThreadBase(BaseModel):
    """Base thread fields"""
    title: Optional[str] = ""
    workspace_id: Optional[int] = None


class ThreadCreate(ThreadBase):
    """Thread creation model"""
    pass


class ThreadUpdate(BaseModel):
    """Thread update model - all fields optional"""
    title: Optional[str] = None
    workspace_id: Optional[int] = None


class Thread(ThreadBase):
    """Complete thread model from database"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

