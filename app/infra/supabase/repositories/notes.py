"""Notes repository"""
from datetime import datetime
from typing import List

from supabase import Client  # type: ignore

from app.models.note import Note, NoteCreate, NoteUpdate

from .base import BaseRepository


class NoteRepository(BaseRepository[Note, NoteCreate, NoteUpdate]):
    """Repository for notes operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "notes", Note)
    
    async def find_by_workspace(self, workspace_id: int) -> List[Note]:
        """Find all notes in a workspace"""
        return await self.find_by_filters({"workspace_id": workspace_id})
    
    async def find_updated_since(self, since: datetime) -> List[Note]:
        """指定時刻以降に更新されたノートを取得"""
        query = (
            self._client.table(self._table_name)
            .select("*")
            .gte("updated_at", since.isoformat())
            .order("updated_at", desc=False)
        )
        response = query.execute()
        return self._to_models(response.data)

    async def get_note_assignee_user_ids(self, note_id: int) -> List[str]:
        """Get user IDs of all assignees for a note"""
        response = (
            self._client.table("workspace_member_note")
            .select("workspace_member!inner(user_id)")
            .eq("note_id", note_id)
            .eq("workspace_member_note_role", "assignee")
            .execute()
        )
        return [item["workspace_member"]["user_id"] for item in response.data]