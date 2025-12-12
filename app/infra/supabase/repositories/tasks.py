"""Task repository"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from supabase import Client  # type: ignore

from app.models.task import Task, TaskCreate, TaskUpdate

from .base import BaseRepository


class TaskRepository(BaseRepository[Task, TaskCreate, TaskUpdate]):
    """Repository for task operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "tasks", Task)
    
    async def find_by_user(self, user_id: str, limit: Optional[int] = None, exclude_description: bool = False) -> List[Task]:
        """Find all tasks for a specific user
        
        Args:
            user_id: User ID to find tasks for
            limit: Optional limit on number of tasks
            exclude_description: If True, excludes the description field to reduce data size
        """
        if exclude_description:
            query = self._client.table(self._table_name).select(
                "id, title, deadline, status, progress, source_note_id, user_id, created_at, updated_at, completed_at"
            ).eq("user_id", user_id)
            
            if limit:
                query = query.limit(limit)
            
            response = query.execute()
            # Fill in description with empty string for excluded fields
            for item in response.data:
                item['description'] = ""
            return self._to_models(response.data)
        else:
            return await self.find_by_filters({"user_id": user_id}, limit=limit)
    
    async def find_recurring_by_user(self, user_id: str) -> List[Task]:
        """Find all recurring tasks for a user (where recurrence_pattern is not null)
        
        Args:
            user_id: User ID to find recurring tasks for
            
        Returns:
            List of recurring tasks for the user
        """
        response = (
            self._client.table(self._table_name)
            .select("*")
            .eq("user_id", user_id)
            .not_.is_("recurrence_pattern", "null")
            .execute()
        )
        return self._to_models(response.data)
    
    async def mark_completed(self, task_id: int) -> Optional[Task]:
        """Mark a task as completed"""
        update_data = TaskUpdate(completed_at=datetime.now(timezone.utc), status="completed", progress=100)
        return await self.update(task_id, update_data)

    async def mark_pending(self, task_id: int) -> Optional[Task]:
        """Mark a task as pending (reopen task)"""
        update_data = TaskUpdate(status="pending", progress=0, completed_at=None)
        return await self.update(task_id, update_data)
    
    async def find_by_id_with_note(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Find a task by ID with joined note data
        
        Returns a dict with task data and optional 'source_note' key containing note data
        """
        response = (
            self._client.table(self._table_name)
            .select("*, notes:source_note_id(id, text)")
            .eq("id", task_id)
            .execute()
        )
        
        if not response.data:
            return None
        
        return response.data[0]
    
    async def find_by_id_with_note_and_members(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Find a task by ID with joined note, workspace, and workspace members data
        
        Returns a dict with:
        - task data (all fields)
        - 'notes': note data (id, text, workspace_id) or None
        - 'workspace': workspace data (id, title, type) or None  
        - 'workspace_members': list of workspace members with user profiles or []
        
        This is useful for mention functionality where we need to know all workspace members.
        """
        response = (
            self._client.table(self._table_name)
            .select("""
                *,
                notes:source_note_id(
                    id,
                    text,
                    workspace_id,
                    workspace:workspace_id(
                        id,
                        title,
                        type,
                        workspace_member(
                            id,
                            user_id,
                            role,
                            user_profiles:user_id(
                                id,
                                name,
                                avatar_url
                            )
                        )
                    )
                )
            """)
            .eq("id", task_id)
            .execute()
        )
        
        if not response.data:
            return None
        
        result = response.data[0]
        
        # Restructure to flatten workspace and members at the top level
        if result.get('notes'):
            note = result['notes']
            if note.get('workspace'):
                workspace = note['workspace']
                # Extract workspace members and flatten
                workspace_members = workspace.pop('workspace_member', [])
                
                # Add workspace and members as top-level keys
                result['workspace'] = workspace
                result['workspace_members'] = workspace_members
            else:
                result['workspace'] = None
                result['workspace_members'] = []
        else:
            result['workspace'] = None
            result['workspace_members'] = []
        
        return result
    
    async def find_by_note(self, note_id: int) -> List[Task]:
        """Find tasks created from a specific note"""
        return await self.find_by_filters({"source_note_id": note_id})
    
    async def delete_by_note(self, note_id: int) -> int:
        """Delete all tasks associated with a specific note
        
        Args:
            note_id: The note ID to delete tasks for
            
        Returns:
            Number of deleted tasks
        """
        response = self._client.table(self._table_name).delete().eq("source_note_id", note_id).execute()
        return len(response.data) if response.data else 0
    
    async def find_updated_since(self, since: datetime) -> List[Task]:
        """指定時刻以降に更新されたタスクを取得"""
        query = (
            self._client.table(self._table_name)
            .select("*")
            .gte("updated_at", since.isoformat())
            .order("updated_at", desc=False)
        )
        response = query.execute()
        return self._to_models(response.data)

