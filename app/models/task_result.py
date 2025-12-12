from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class TaskResultBase(BaseModel):
    """Base task result fields"""
    task_id: int
    result_title: str
    result_text: str


class TaskResultCreate(TaskResultBase):
    """Task result creation model"""
    executed_at: datetime


class TaskResult(TaskResultBase):
    """Complete task result model from database"""
    id: int
    executed_at: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True

