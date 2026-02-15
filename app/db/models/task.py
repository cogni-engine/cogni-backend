"""SQLAlchemy ORM model for tasks table"""

from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

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

    # Relationships
    workspace_id = Column(Integer, nullable=False, index=True)
    source_type = Column(String, nullable=True)
    source_id = Column(Integer, nullable=True)

    # Assignees
    assignees = Column(JSONB, nullable=False, server_default='[]')

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, title='{self.title}')>"
