"""SQLAlchemy ORM model for tasks table"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base import Base


class Task(Base):
    """
    SQLAlchemy ORM model for the tasks table.
    Maps to existing Supabase table structure.
    """
    __tablename__ = "tasks"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Task information
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=True)
    progress = Column(Integer, default=0, nullable=True)
    
    # Relationships
    source_note_id = Column(Integer, nullable=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    assigner_id = Column(UUID(as_uuid=True), nullable=True)
    workspace_member_id = Column(Integer, nullable=True)
    
    # Recurrence fields
    recurrence_pattern = Column(String, nullable=True)
    # next_run_timeはAI生成タスクでは必須だが、DBレベルでは既存データとの互換性のためnullable=True
    # 新規作成時はAIがNote内容とdeadlineから最適な実行タイミングを判断して設定する
    next_run_time = Column(DateTime(timezone=True), nullable=True)
    is_recurring_task_active = Column(Boolean, default=True, nullable=True)
    last_recurring_at = Column(DateTime(timezone=True), nullable=True)
    
    # AI task flag
    is_ai_task = Column(Boolean, default=False, nullable=True)
    
    # Timestamps
    created_at = Column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), 
        onupdate=func.now(), 
        nullable=True
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships (uncomment when other models are ready)
    # task_results = relationship("TaskResult", back_populates="task")
    # ai_notifications = relationship("AINotification", back_populates="task")
    
    def __repr__(self) -> str:
        return f"<Task(id={self.id}, title='{self.title}', status='{self.status}')>"
