"""Task result repository"""
from typing import List, Optional

from supabase import Client  # type: ignore

from app.models.task_result import TaskResult, TaskResultCreate

from .base import BaseRepository


class TaskResultRepository(BaseRepository[TaskResult, TaskResultCreate, TaskResult]):
    """Repository for task result operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "task_results", TaskResult)
    
    async def find_by_task(self, task_id: int, limit: Optional[int] = None) -> List[TaskResult]:
        """Find all results for a specific task"""
        return await self.find_by_filters({"task_id": task_id}, limit=limit)

