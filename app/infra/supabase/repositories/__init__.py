"""Repository factory and exports"""
from supabase import Client  # type: ignore

from .notes import NoteRepository
from .workspaces import WorkspaceMemberRepository, WorkspaceRepository
# OrganizationRepository moved to app.features.billing.repositories


class RepositoryFactory:
    """Factory for creating repository instances"""
    
    def __init__(self, client: Client):
        self._client = client
        self._notes: NoteRepository | None = None
        self._workspaces: WorkspaceRepository | None = None
        self._workspace_members: WorkspaceMemberRepository | None = None

    
    @property
    def notes(self) -> NoteRepository:
        """Get notes repository"""
        if self._notes is None:
            self._notes = NoteRepository(self._client)
        return self._notes
    
    @property
    def workspaces(self) -> WorkspaceRepository:
        """Get workspaces repository"""
        if self._workspaces is None:
            self._workspaces = WorkspaceRepository(self._client)
        return self._workspaces
    
    @property
    def workspace_members(self) -> WorkspaceMemberRepository:
        """Get workspace members repository"""
        if self._workspace_members is None:
            self._workspace_members = WorkspaceMemberRepository(self._client)
        return self._workspace_members



__all__ = [
    'RepositoryFactory',
    'NoteRepository',
    'WorkspaceRepository',
    'WorkspaceMemberRepository',
]
