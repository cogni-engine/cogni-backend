from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from datetime import datetime
from pydantic import Field


class BulkTaskUpdate(BaseModel):
    action: str  # "create", "update", "delete"
    task_id: Optional[int] = None  # update/deleteの場合のみ
    task_data: Optional[Dict[str, Any]] = None  # create/updateの場合のみ

class TaskUpdateRequest(BaseModel):
    note_content: str
    current_tasks: List[Dict[str, Any]]

class TaskUpdateResponse(BaseModel):
    updates: List[Dict[str, Any]]
    summary: str


class TaskBase(BaseModel):
    """Base task fields for creation"""
    title: str
    workspace_id: int
    description: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    assignees: Optional[List] = None


class TaskCreate(TaskBase):
    """Task creation model"""
    pass


class TaskUpdate(BaseModel):
    """Task update model - all fields optional"""
    title: Optional[str] = None
    description: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[int] = None


class Task(TaskBase):
    """Complete task model from database"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

