"""SQLAlchemy ORM model for task_results table"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base import Base


class TaskResult(Base):
    """
    SQLAlchemy ORM model for the task_results table.
    Maps to existing Supabase table structure.
    Stores results from AI task execution.
    """
    __tablename__ = "task_results"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key to tasks table
    task_id = Column(
        Integer, 
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False, 
        index=True
    )
    
    # Result information
    result_title = Column(String, nullable=False)
    result_text = Column(Text, nullable=False)
    
    # Execution timestamp
    executed_at = Column(DateTime(timezone=True), nullable=False)
    
    # Creation timestamp
    created_at = Column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    
    # Relationship (uncomment when needed)
    # task = relationship("Task", back_populates="task_results")
    # ai_notifications = relationship("AINotification", back_populates="task_result")
    
    def __repr__(self) -> str:
        return f"<TaskResult(id={self.id}, task_id={self.task_id}, title='{self.result_title}')>"
