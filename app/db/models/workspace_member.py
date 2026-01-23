"""SQLAlchemy ORM model for workspace_member table"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base import Base


class WorkspaceMember(Base):
    """
    SQLAlchemy ORM model for the workspace_member table.
    Maps to existing Supabase table structure.
    """
    __tablename__ = "workspace_member"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    user_id = Column(UUID(as_uuid=True), nullable=True)
    workspace_id = Column(Integer, ForeignKey("workspace.id"), nullable=True)
    agent_id = Column(UUID(as_uuid=True), nullable=True)
    
    # Member information
    role = Column(String, nullable=False, default="member")
    
    # Timestamps
    created_at = Column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    
    # Relationships
    # Note: user_id references auth.users.id, and user_profiles.id also references auth.users.id
    # Since there's no direct FK, we'll query UserProfile manually in the repository
    # user_profile relationship is not defined here to avoid FK constraint issues
    
    def __repr__(self) -> str:
        return f"<WorkspaceMember(id={self.id}, user_id={self.user_id}, workspace_id={self.workspace_id})>"
