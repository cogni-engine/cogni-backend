"""Notes repository"""
from datetime import datetime
from typing import List, Optional, Tuple

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
    
    async def find_updated_since(
        self, 
        since: datetime, 
        user_id_filter: Optional[List[str]] = None,
        exclude_user_ids: bool = False
    ) -> List[Note]:
        """
        指定時刻以降に更新されたノートを取得
        
        Args:
            since: この時刻以降に更新されたノートを取得
            user_id_filter: 指定されたuser_idのworkspaceのノートのみ取得（Noneの場合は全て）
            exclude_user_ids: Trueの場合、user_id_filterに含まれるuser_idを除外
        """
        if user_id_filter:
            # workspace_memberと結合してuser_idでフィルタリング
            query = (
                self._client.table(self._table_name)
                .select("*, workspace!inner(id, workspace_member!inner(user_id))")
                .gte("updated_at", since.isoformat())
            )
            
            if exclude_user_ids:
                # user_idを除外
                for user_id in user_id_filter:
                    query = query.neq("workspace.workspace_member.user_id", user_id)
            else:
                # user_idでフィルタ
                query = query.in_("workspace.workspace_member.user_id", user_id_filter)
            
            query = query.order("updated_at", desc=False)
            response = query.execute()
            
            # ネストされたデータから notes だけを抽出
            notes_data = []
            for item in response.data:
                # workspace情報を削除してnoteのデータのみを残す
                note_data = {k: v for k, v in item.items() if k != 'workspace'}
                notes_data.append(note_data)
            
            return self._to_models(notes_data)
        else:
            # フィルタなしの場合は既存の動作
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
    
    async def get_note_assignee_user_and_member_ids(self, note_id: int) -> List[Tuple[str, int]]:
        """Get (user_id, workspace_member_id) tuples for all assignees of a note"""
        response = (
            self._client.table("workspace_member_note")
            .select("workspace_member_id, workspace_member!inner(user_id)")
            .eq("note_id", note_id)
            .eq("workspace_member_note_role", "assignee")
            .execute()
        )
        return [
            (item["workspace_member"]["user_id"], item["workspace_member_id"])
            for item in response.data
        ]