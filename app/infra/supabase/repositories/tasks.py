"""Task repository"""
from datetime import datetime
from typing import List, Optional, Dict, Any

from supabase import Client  # type: ignore

from app.models.task import Task, TaskCreate, TaskUpdate

from .base import BaseRepository


class TaskRepository(BaseRepository[Task, TaskCreate, TaskUpdate]):
    """Repository for task operations"""

    def __init__(self, client: Client):
        super().__init__(client, "tasks", Task)

    async def find_by_user_notes(
        self, user_id: str, limit: Optional[int] = None, exclude_description: bool = False,
    ) -> List[Task]:
        """Find all tasks for a user via workspace_member_note assignee relationship.

        source_type='note' のタスクについて、source_id → notes → workspace_member_note 経由でユーザーを解決する。
        """
        # Step 1: ユーザーにアサインされたノートIDを取得
        notes_response = (
            self._client.table("notes")
            .select("id, workspace_member_note!inner(workspace_member!inner(user_id))")
            .eq("workspace_member_note.workspace_member.user_id", user_id)
            .eq("workspace_member_note.workspace_member_note_role", "assignee")
            .execute()
        )
        note_ids = [n["id"] for n in notes_response.data] if notes_response.data else []
        if not note_ids:
            return []

        # Step 2: source_type='note' かつ source_id がノートIDリストに含まれるタスクを取得
        select_cols = (
            "id, title, created_at, updated_at"
            if exclude_description
            else "*"
        )
        query = (
            self._client.table(self._table_name)
            .select(select_cols)
            .eq("source_type", "note")
            .in_("source_id", note_ids)
        )
        if limit:
            query = query.limit(limit)
        response = query.execute()

        results = response.data or []
        if exclude_description:
            for row in results:
                if "description" not in row:
                    row["description"] = ""
        return self._to_models(results)

    async def find_by_id_with_note(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Find a task by ID with note data (if source_type='note')."""
        task = await self.find_by_id(task_id)
        if not task:
            return None

        result = task.model_dump()

        if task.source_type == "note" and task.source_id:
            note_response = (
                self._client.table("notes")
                .select("id, text")
                .eq("id", task.source_id)
                .maybe_single()
                .execute()
            )
            result["notes"] = note_response.data
        else:
            result["notes"] = None

        return result

    async def find_by_id_with_note_and_members(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Find a task by ID with note, workspace, and workspace members data."""
        task = await self.find_by_id(task_id)
        if not task:
            return None

        result = task.model_dump()
        result["notes"] = None
        result["workspace"] = None
        result["workspace_members"] = []

        if task.source_type == "note" and task.source_id:
            note_response = (
                self._client.table("notes")
                .select("""
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
                """)
                .eq("id", task.source_id)
                .maybe_single()
                .execute()
            )
            if note_response.data:
                note = note_response.data
                result["notes"] = note
                if note.get("workspace"):
                    workspace = note["workspace"]
                    workspace_members = workspace.pop("workspace_member", [])
                    result["workspace"] = workspace
                    result["workspace_members"] = workspace_members

        return result

    async def find_by_source(self, source_type: str, source_id: int) -> List[Task]:
        """Find tasks by source_type and source_id"""
        return await self.find_by_filters({"source_type": source_type, "source_id": source_id})

    async def find_by_note(self, note_id: int) -> List[Task]:
        """Find tasks created from a specific note"""
        return await self.find_by_source("note", note_id)

    async def find_by_sources(self, source_type: str, source_ids: List[int]) -> List[Task]:
        """Find tasks by source_type and multiple source_ids"""
        if not source_ids:
            return []
        response = (
            self._client.table(self._table_name)
            .select("*")
            .eq("source_type", source_type)
            .in_("source_id", source_ids)
            .execute()
        )
        return self._to_models(response.data)

    async def find_by_notes(self, note_ids: List[int]) -> List[Task]:
        """Find tasks created from multiple notes"""
        return await self.find_by_sources("note", note_ids)

    async def find_by_ids(self, task_ids: List[int]) -> List[Task]:
        """Find tasks by multiple IDs in a single query"""
        if not task_ids:
            return []
        response = (
            self._client.table(self._table_name)
            .select("*")
            .in_("id", task_ids)
            .execute()
        )
        return self._to_models(response.data)

    async def delete_by_source(self, source_type: str, source_id: int) -> int:
        """Delete all tasks associated with a specific source."""
        response = (
            self._client.table(self._table_name)
            .delete()
            .eq("source_type", source_type)
            .eq("source_id", source_id)
            .execute()
        )
        return len(response.data) if response.data else 0

    async def delete_by_note(self, note_id: int) -> int:
        """Delete all tasks associated with a specific note"""
        return await self.delete_by_source("note", note_id)

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
