"""Thread repository"""
from typing import List

from supabase import Client  # type: ignore

from app.models.thread import Thread, ThreadCreate, ThreadUpdate

from .base import BaseRepository


class ThreadRepository(BaseRepository[Thread, ThreadCreate, ThreadUpdate]):
    """Repository for thread operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "thread", Thread)
    
    async def find_by_workspace(self, workspace_id: int) -> List[Thread]:
        """Find all threads in a workspace"""
        return await self.find_by_filters({"workspace_id": workspace_id})
    
    async def get_recent_threads(self, workspace_id: int, limit: int = 20) -> List[Thread]:
        """Get recent threads from a workspace"""
        query = (
            self._client.table(self._table_name)
            .select("*")
            .eq("workspace_id", workspace_id)
            .order("updated_at", desc=True)
            .limit(limit)
        )
        response = query.execute()
        return self._to_models(response.data)
    
    async def search_by_title(self, workspace_id: int, search_term: str) -> List[Thread]:
        """Search threads by title"""
        query = (
            self._client.table(self._table_name)
            .select("*")
            .eq("workspace_id", workspace_id)
            .ilike("title", f"%{search_term}%")
        )
        response = query.execute()
        return self._to_models(response.data)

