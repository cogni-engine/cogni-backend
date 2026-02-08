"""Working memory repository"""
from typing import Optional

from supabase import Client  # type: ignore

from app.models.working_memory import WorkingMemory, WorkingMemoryCreate, WorkingMemoryUpdate

from .base import BaseRepository


class WorkingMemoryRepository(BaseRepository[WorkingMemory, WorkingMemoryCreate, WorkingMemoryUpdate]):
    """Repository for working memory operations"""

    def __init__(self, client: Client):
        super().__init__(client, "working_memory", WorkingMemory)

    async def find_by_workspace(self, workspace_id: int) -> Optional[WorkingMemory]:
        """Find working memory for a workspace (1:1 relationship)"""
        response = (
            self._client.table(self._table_name)
            .select("*")
            .eq("workspace_id", workspace_id)
            .execute()
        )

        if not response.data:
            return None

        return self._to_model(response.data[0])

    async def upsert_by_workspace(self, workspace_id: int, content: str) -> WorkingMemory:
        """Create or update working memory for a workspace.

        Uses workspace_id unique constraint for upsert.
        """
        response = (
            self._client.table(self._table_name)
            .upsert(
                {"workspace_id": workspace_id, "content": content},
                on_conflict="workspace_id",
            )
            .execute()
        )

        if not response.data:
            raise ValueError("Failed to upsert working memory")

        return self._to_model(response.data[0])
