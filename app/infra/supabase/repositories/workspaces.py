"""Workspace repository"""
from typing import List
from supabase import Client

from app.models.workspace import (
    Workspace, WorkspaceCreate, WorkspaceUpdate, WorkspaceType,
    WorkspaceMember, WorkspaceMemberCreate, WorkspaceMemberUpdate
)
from .base import BaseRepository


class WorkspaceRepository(BaseRepository[Workspace, WorkspaceCreate, WorkspaceUpdate]):
    """Repository for workspace operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "workspace", Workspace)
    
    async def find_by_type(self, workspace_type: WorkspaceType) -> List[Workspace]:
        """Find workspaces by type"""
        return await self.find_by_filters({"type": workspace_type.value})
    
    async def find_user_workspaces(self, user_id: str) -> List[Workspace]:
        """Find all workspaces a user is a member of"""
        # This requires joining with workspace_member table
        query = (
            self._client.table(self._table_name)
            .select("*, workspace_member!inner(*)")
            .eq("workspace_member.user_id", user_id)
        )
        response = query.execute()
        return self._to_models(response.data)


class WorkspaceMemberRepository(BaseRepository[WorkspaceMember, WorkspaceMemberCreate, WorkspaceMemberUpdate]):
    """Repository for workspace member operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "workspace_member", WorkspaceMember)
    
    async def find_by_workspace(self, workspace_id: int) -> List[WorkspaceMember]:
        """Find all members of a workspace"""
        return await self.find_by_filters({"workspace_id": workspace_id})

