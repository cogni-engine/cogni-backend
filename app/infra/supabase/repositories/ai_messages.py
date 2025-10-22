"""AI Messages repository"""
from typing import List

from supabase import Client  # type: ignore

from app.models.ai_message import AIMessage, AIMessageCreate, AIMessageUpdate

from .base import BaseRepository


class AIMessageRepository(BaseRepository[AIMessage, AIMessageCreate, AIMessageUpdate]):
    """Repository for AI messages (linked to tasks as threads)"""
    
    def __init__(self, client: Client):
        super().__init__(client, "ai_messages", AIMessage)
    
    async def find_by_thread(self, thread_id: int) -> List[AIMessage]:
        """Find all messages in a thread"""
        query = (
            self._client.table(self._table_name)
            .select("*")
            .eq("thread_id", thread_id)
            .order("created_at", desc=False)
        )
        response = query.execute()
        return self._to_models(response.data)
    
    async def get_recent_messages(self, thread_id: int, limit: int = 50) -> List[AIMessage]:
        """Get recent messages from a thread"""
        query = (
            self._client.table(self._table_name)
            .select("*")
            .eq("thread_id", thread_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        response = query.execute()
        messages = self._to_models(response.data)
        return list(reversed(messages))  # Return in chronological order
    
    async def find_since(self, thread_id: int, since_id: int) -> List[AIMessage]:
        """Find messages in a thread since a specific message ID"""
        query = (
            self._client.table(self._table_name)
            .select("*")
            .eq("thread_id", thread_id)
            .gt("id", since_id)
            .order("created_at", desc=False)
        )
        response = query.execute()
        return self._to_models(response.data)

