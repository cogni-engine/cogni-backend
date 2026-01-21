"""SQLAlchemy ORM model for ai_notifications table"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


class NotificationStatus(str, enum.Enum):
    """Notification status enum matching Pydantic model"""
    SCHEDULED = "scheduled"
    SENT = "sent"
    RESOLVED = "resolved"


class AINotification(Base):
    """
    SQLAlchemy ORM model for the ai_notifications table.
    Maps to existing Supabase table structure.
    Stores AI-generated notifications for users.
    """
    __tablename__ = "ai_notifications"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Notification content
    title = Column(String, nullable=False)
    ai_context = Column(Text, nullable=False)
    body = Column(Text, nullable=True)
    
    # Scheduling
    due_date = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Foreign keys
    task_id = Column(
        Integer, 
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False, 
        index=True
    )
    task_result_id = Column(
        Integer, 
        ForeignKey("task_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # User information
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    workspace_member_id = Column(Integer, nullable=True)
    
    # Status (using String instead of Enum to avoid conversion issues)
    status = Column(
        String,
        default="scheduled",
        nullable=False,
        index=True
    )
    
    # Timestamps
    created_at = Column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now(), 
        nullable=False
    )
    
    # Relationships
    task_result = relationship("TaskResult", foreign_keys=[task_result_id])
    
    def __repr__(self) -> str:
        return f"<AINotification(id={self.id}, task_id={self.task_id}, status='{self.status.value}')>"
