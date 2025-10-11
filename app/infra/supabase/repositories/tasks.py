"""Task repository"""
from datetime import datetime
from typing import List, Optional

from supabase import Client  # type: ignore

from app.models.task import Task, TaskCreate, TaskUpdate

from .base import BaseRepository


class TaskRepository(BaseRepository[Task, TaskCreate, TaskUpdate]):
    """Repository for task operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "tasks", Task)
    
    async def find_by_user(self, user_id: str, limit: Optional[int] = None) -> List[Task]:
        """Find all tasks for a specific user"""
        return await self.find_by_filters({"user_id": user_id}, limit=limit)
    
    async def mark_completed(self, task_id: int) -> Optional[Task]:
        """Mark a task as completed"""
        update_data = TaskUpdate(completed_at=datetime.now(), status="completed", progress=100)
        return await self.update(task_id, update_data)
    
    async def find_by_note(self, note_id: int) -> List[Task]:
        """Find tasks created from a specific note"""
        return await self.find_by_filters({"source_note_id": note_id})

