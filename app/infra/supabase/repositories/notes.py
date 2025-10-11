"""Notes repository"""
from typing import List
from supabase import Client

from app.models.note import Note, NoteCreate, NoteUpdate
from .base import BaseRepository


class NoteRepository(BaseRepository[Note, NoteCreate, NoteUpdate]):
    """Repository for notes operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "notes", Note)
    
    async def find_by_workspace(self, workspace_id: int) -> List[Note]:
        """Find all notes in a workspace"""
        return await self.find_by_filters({"workspace_id": workspace_id})
