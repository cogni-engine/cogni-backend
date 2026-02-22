"""SQLAlchemy ORM model for user_profiles table"""

from sqlalchemy import Column, Boolean, Integer, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.base import Base


class UserProfile(Base):
    """
    SQLAlchemy ORM model for the user_profiles table.
    Maps to existing Supabase table structure.
    """
    __tablename__ = "user_profiles"

    # Primary key (references auth.users.id)
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)

    # User information
    name = Column(Text, nullable=True)
    avatar_url = Column(Text, nullable=True)

    # Settings
    enable_ai_suggestion = Column(Boolean, nullable=False, default=False)

    # Onboarding
    onboarding_status = Column(Text, nullable=True, default="not_started")
    onboarding_version = Column(Integer, nullable=True, default=1)

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
        return f"<UserProfile(id={self.id}, name='{self.name}')>"
