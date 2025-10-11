"""Domain models for the application"""
from .task import Task, TaskCreate, TaskUpdate, TaskUpdateRequest, TaskUpdateResponse
from .note import Note, NoteCreate, NoteUpdate
from .thread import Thread, ThreadCreate, ThreadUpdate
from .ai_message import AIMessage, AIMessageCreate, AIMessageUpdate
from .notification import Notification, NotificationCreate, NotificationUpdate, NotificationAnalysisRequest, NotificationAnalysisResponse, NotificationStatus, NotificationCreateRequest, NotificationUpdateStatusRequest
from .workspace import Workspace, WorkspaceCreate, WorkspaceUpdate, WorkspaceMember, WorkspaceMemberCreate, WorkspaceMemberUpdate
from .user import UserProfile, UserProfileCreate, UserProfileUpdate
from .chat import ChatRequest, ChatResponse, ChatMessage

__all__ = [
    'Task', 'TaskCreate', 'TaskUpdate',
    'Note', 'NoteCreate', 'NoteUpdate',
    'Thread', 'ThreadCreate', 'ThreadUpdate',
    'AIMessage', 'AIMessageCreate', 'AIMessageUpdate',
    'Notification', 'NotificationCreate', 'NotificationUpdate',
    'NotificationAnalysisRequest', 'NotificationAnalysisResponse',
    'NotificationStatus', 'NotificationCreateRequest', 'NotificationUpdateStatusRequest',
    'Workspace', 'WorkspaceCreate', 'WorkspaceUpdate',
    'WorkspaceMember', 'WorkspaceMemberCreate', 'WorkspaceMemberUpdate',
    'UserProfile', 'UserProfileCreate', 'UserProfileUpdate',
    'ChatRequest', 'ChatResponse', 'ChatMessage',
    'TaskUpdateRequest', 'TaskUpdateResponse',
]

