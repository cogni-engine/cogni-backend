from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import datetime

class Task(BaseModel):
    id: int
    title: str
    deadline: datetime.datetime
    importance: int
    urgency: int
    status: str
    method: str
    reason: str

class TaskUpdate(BaseModel):
    action: str  # "create", "update", "delete"
    task_id: Optional[int] = None  # update/deleteの場合のみ
    task_data: Optional[Dict[str, Any]] = None  # create/updateの場合のみ

class TaskUpdateRequest(BaseModel):
    note_content: str
    current_tasks: List[Dict[str, Any]]

class TaskUpdateResponse(BaseModel):
    updates: List[Dict[str, Any]]
    summary: str

