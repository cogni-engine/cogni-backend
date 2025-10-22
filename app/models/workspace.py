"""Workspace domain model"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from enum import Enum


class WorkspaceType(str, Enum):
    """Workspace type enum"""
    GROUP = "group"
    PERSONAL = "personal"


class WorkspaceRole(str, Enum):
    """Workspace member role enum"""
    OWNER = "owner"
    MEMBER = "member"


class WorkspaceBase(BaseModel):
    """Base workspace fields"""
    title: Optional[str] = None
    type: WorkspaceType = WorkspaceType.PERSONAL


class WorkspaceCreate(WorkspaceBase):
    """Workspace creation model"""
    pass


class WorkspaceUpdate(BaseModel):
    """Workspace update model - all fields optional"""
    title: Optional[str] = None
    type: Optional[WorkspaceType] = None


class Workspace(WorkspaceBase):
    """Complete workspace model from database"""
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# Workspace Member Models
class WorkspaceMemberBase(BaseModel):
    """Base workspace member fields"""
    user_id: str  # UUID as string
    workspace_id: int
    role: WorkspaceRole = WorkspaceRole.MEMBER


class WorkspaceMemberCreate(WorkspaceMemberBase):
    """Workspace member creation model"""
    pass


class WorkspaceMemberUpdate(BaseModel):
    """Workspace member update model"""
    role: Optional[WorkspaceRole] = None


class WorkspaceMember(WorkspaceMemberBase):
    """Complete workspace member model from database"""
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

