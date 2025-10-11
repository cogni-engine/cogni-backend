"""Repository factory and exports"""
from supabase import Client
from .tasks import TaskRepository
from .notes import NoteRepository
from .threads import ThreadRepository
from .ai_messages import AIMessageRepository
from .notifications import NotificationRepository
from .workspaces import WorkspaceRepository, WorkspaceMemberRepository


class RepositoryFactory:
    """Factory for creating repository instances"""
    
    def __init__(self, client: Client):
        self._client = client
        self._tasks: TaskRepository = None
        self._notes: NoteRepository = None
        self._threads: ThreadRepository = None
        self._ai_messages: AIMessageRepository = None
        self._notifications: NotificationRepository = None
        self._workspaces: WorkspaceRepository = None
        self._workspace_members: WorkspaceMemberRepository = None
    
    @property
    def tasks(self) -> TaskRepository:
        """Get task repository"""
        if self._tasks is None:
            self._tasks = TaskRepository(self._client)
        return self._tasks
    
    @property
    def notes(self) -> NoteRepository:
        """Get notes repository"""
        if self._notes is None:
            self._notes = NoteRepository(self._client)
        return self._notes
    
    @property
    def threads(self) -> ThreadRepository:
        """Get threads repository"""
        if self._threads is None:
            self._threads = ThreadRepository(self._client)
        return self._threads
    
    @property
    def ai_messages(self) -> AIMessageRepository:
        """Get AI messages repository"""
        if self._ai_messages is None:
            self._ai_messages = AIMessageRepository(self._client)
        return self._ai_messages
    
    @property
    def notifications(self) -> NotificationRepository:
        """Get notifications repository"""
        if self._notifications is None:
            self._notifications = NotificationRepository(self._client)
        return self._notifications
    
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
    'TaskRepository',
    'NoteRepository',
    'ThreadRepository',
    'AIMessageRepository',
    'NotificationRepository',
    'WorkspaceRepository',
    'WorkspaceMemberRepository',
    'UserProfileRepository',
]

