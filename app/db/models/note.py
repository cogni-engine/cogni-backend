"""SQLAlchemy ORM model for notes table"""

from sqlalchemy import Column, Integer, DateTime, Text, ForeignKey
from sqlalchemy.sql import func

from app.db.base import Base


class Note(Base):
    """
    SQLAlchemy ORM model for the notes table.
    Maps to existing Supabase table structure.
    """
    __tablename__ = "notes"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Note content
    title = Column(Text, nullable=True)
    text = Column(Text, nullable=False, default="")
    
    # Foreign keys
    workspace_id = Column(Integer, ForeignKey("workspace.id"), nullable=False)
    note_folder_id = Column(Integer, ForeignKey("note_folders.id"), nullable=True)
    
    # Yjs document state
    ydoc_state = Column(Text, nullable=True)
    
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
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self) -> str:
        return f"<Note(id={self.id}, title='{self.title}', workspace_id={self.workspace_id})>"
