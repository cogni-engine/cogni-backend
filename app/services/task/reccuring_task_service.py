"""
Recurring Task Service

Handles business logic for recurring tasks including:
- CRUD operations
- Calculating next run times based on recurrence patterns
- Finding and processing due tasks
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from supabase import Client

from app.models.task import Task, TaskCreate, TaskUpdate
from app.infra.supabase.repositories.tasks import TaskRepository

logger = logging.getLogger(__name__)


# Supported recurrence patterns
RECURRENCE_PATTERNS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "biweekly": timedelta(weeks=2),
    "monthly": timedelta(days=30),  # Approximate
    "yearly": timedelta(days=365),  # Approximate
}


class RecurringTaskService:
    """Service for managing recurring tasks"""

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.task_repo = TaskRepository(supabase_client)

    async def get_recurring_tasks(self, user_id: str) -> List[Task]:
        """
        Get all recurring tasks for a user.
        
        Args:
            user_id: The user ID to fetch tasks for
            
        Returns:
            List of recurring tasks
        """
        return await self.task_repo.find_recurring_by_user(user_id)

    async def get_task(self, task_id: int) -> Optional[Task]:
        """
        Get a single recurring task by ID.
        
        Args:
            task_id: The task ID
            
        Returns:
            The task if found, None otherwise
        """
        return await self.task_repo.find_by_id(task_id)

    async def create_recurring_task(
        self,
        user_id: str,
        title: str,
        recurrence_pattern: str,
        next_run_time: datetime,
        description: Optional[str] = None,
        is_ai_task: bool = False,
        **kwargs
    ) -> Task:
        """
        Create a new recurring task.
        
        Args:
            user_id: The user ID
            title: Task title
            recurrence_pattern: Optional pattern like 'daily', 'weekly', 'monthly'
            description: Optional task description
            next_run_time: When to run next (auto-calculated if pattern provided)
            is_ai_task: Whether this is an AI-generated task
            **kwargs: Additional task fields
            
        Returns:
            The created task
        """
        # Calculate next_run_time if not provided and recurrence_pattern is set
        if next_run_time is None and recurrence_pattern:
            next_run_time = self.calculate_next_run_time(recurrence_pattern)

        task_data = TaskCreate(
            user_id=user_id,
            title=title,
            description=description,
            recurrence_pattern=recurrence_pattern,
            next_run_time=next_run_time,
            is_ai_task=is_ai_task,
            status=None,
            deadline=None,
            progress=None,
            source_note_id=kwargs.get("source_note_id"),
            assigner_id=kwargs.get("assigner_id"),
        )

        task = await self.task_repo.create(task_data)
        logger.info(f"Created recurring task {task.id} with pattern '{recurrence_pattern}'")
        return task

    async def update_recurring_task(
        self,
        task_id: int,
        **updates
    ) -> Optional[Task]:
        """
        Update a recurring task.
        
        Args:
            task_id: The task ID to update
            **updates: Fields to update
            
        Returns:
            The updated task if found, None otherwise
        """
        # Check if task exists
        existing = await self.task_repo.find_by_id(task_id)
        if not existing:
            return None

        # Handle status changes
        if updates.get("status") == "completed" and not updates.get("completed_at"):
            updates["completed_at"] = datetime.now(timezone.utc)
        elif updates.get("status") == "pending":
            updates["completed_at"] = None

        # Build update data with only provided fields (non-None values)
        update_fields = {}
        field_mapping = [
            "title", "description", "deadline", "status", "progress",
            "completed_at", "recurrence_pattern", "is_ai_task",
            "is_recurring_task_active", "next_run_time"
        ]
        
        for field in field_mapping:
            if field in updates and updates[field] is not None:
                update_fields[field] = updates[field]
        
        # Special case: allow explicit setting of is_recurring_task_active to False
        if "is_recurring_task_active" in updates:
            update_fields["is_recurring_task_active"] = updates["is_recurring_task_active"]

        update_data = TaskUpdate(**update_fields)

        task = await self.task_repo.update(task_id, update_data)
        if task:
            logger.info(f"Updated recurring task {task_id}")
        return task

    async def delete_recurring_task(self, task_id: int) -> bool:
        """
        Delete a recurring task.
        
        Args:
            task_id: The task ID to delete
            
        Returns:
            True if deleted, False otherwise
        """
        # Check if task exists
        existing = await self.task_repo.find_by_id(task_id)
        if not existing:
            return False

        success = await self.task_repo.delete(task_id)
        if success:
            logger.info(f"Deleted recurring task {task_id}")
        return success

    async def find_due_tasks(self, before: Optional[datetime] = None) -> List[Task]:
        """
        Find all recurring tasks that are due to run.
        
        Args:
            before: Find tasks due before this time (defaults to now in UTC)
            
        Returns:
            List of tasks that are due
        """
        if before is None:
            before = datetime.now(timezone.utc)

        response = (
            self.supabase.table("tasks")
            .select("*")
            .not_.is_("recurrence_pattern", "null")
            .lte("next_run_time", before.isoformat())
            .execute()
        )

        return [Task(**item) for item in response.data] if response.data else []

    async def advance_next_run_time(self, task_id: int) -> Optional[Task]:
        """
        Advance a task's next_run_time based on its recurrence pattern.
        Call this after a recurring task has been executed.
        
        Args:
            task_id: The task ID
            
        Returns:
            The updated task if found, None otherwise
        """
        task = await self.task_repo.find_by_id(task_id)
        if not task or not task.recurrence_pattern:
            return None

        new_next_run_time = self.calculate_next_run_time(
            task.recurrence_pattern,
            from_time=task.next_run_time or datetime.now(timezone.utc)
        )

        update_data = TaskUpdate(
            next_run_time=new_next_run_time,
            status="pending",  # Reset status for next run
            completed_at=None,
            progress=0,
        )

        updated_task = await self.task_repo.update(task_id, update_data)
        if updated_task:
            logger.info(
                f"Advanced task {task_id} next_run_time to {new_next_run_time}"
            )
        return updated_task

    def calculate_next_run_time(
        self,
        recurrence_pattern: str,
        from_time: Optional[datetime] = None
    ) -> datetime:
        """
        Calculate the next run time based on recurrence pattern.
        
        Args:
            recurrence_pattern: Pattern like 'daily', 'weekly', etc.
            from_time: Base time to calculate from (defaults to now in UTC)
            
        Returns:
            The next run time (timezone-aware UTC)
        """
        if from_time is None:
            from_time = datetime.now(timezone.utc)
        
        # Ensure from_time is timezone-aware (convert naive to UTC)
        if from_time.tzinfo is None:
            from_time = from_time.replace(tzinfo=timezone.utc)

        pattern_lower = recurrence_pattern.lower()
        interval = RECURRENCE_PATTERNS.get(pattern_lower)

        if interval:
            return from_time + interval
        else:
            # Default to daily if pattern not recognized
            logger.warning(
                f"Unknown recurrence pattern '{recurrence_pattern}', defaulting to daily"
            )
            return from_time + timedelta(days=1)

    async def process_due_tasks(self) -> Dict[str, Any]:
        """
        Find and process all due recurring tasks.
        This advances their next_run_time for the next occurrence.
        
        Returns:
            Summary of processed tasks
        """
        due_tasks = await self.find_due_tasks()
        processed = []
        errors = []

        for task in due_tasks:
            try:
                await self.advance_next_run_time(task.id)
                processed.append(task.id)
            except Exception as e:
                logger.error(f"Error processing task {task.id}: {e}")
                errors.append({"task_id": task.id, "error": str(e)})

        return {
            "processed_count": len(processed),
            "processed_task_ids": processed,
            "error_count": len(errors),
            "errors": errors,
        }
