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
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    status: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    source_note_id: Optional[int] = None
    recurrence_pattern: Optional[str] = None
    # next_run_timeはAI生成タスクでは必須だが、既存データとの互換性のためOptional
    # 新規作成時はAIがNote内容とdeadlineから最適な実行タイミングを判断して設定する
    next_run_time: Optional[datetime] = None
    is_ai_task: bool = False
    is_recurring_task_active: bool = True
    last_recurring_at: Optional[datetime] = None


class TaskCreate(TaskBase):
    """Task creation model"""
    user_id: str   # UUID as string
    assigner_id: Optional[str] = None
    workspace_member_id: Optional[int] = None


class TaskUpdate(BaseModel):
    """Task update model - all fields optional"""
    title: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    status: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    completed_at: Optional[datetime] = None
    assigner_id: Optional[str] = None
    recurrence_pattern: Optional[str] = None
    is_ai_task: Optional[bool] = None
    is_recurring_task_active: Optional[bool] = None
    next_run_time: Optional[datetime] = None


class Task(TaskBase):
    """Complete task model from database"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    user_id: str
    assigner_id: Optional[str] = None
    workspace_member_id: Optional[int] = None
    recurrence_pattern: Optional[str] = None
    is_ai_task: bool = False
    is_recurring_task_active: bool = True
    next_run_time: Optional[datetime] = None
    
    class Config:
        from_attributes = True

