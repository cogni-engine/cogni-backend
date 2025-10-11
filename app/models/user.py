"""User Profile domain model"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UserProfileBase(BaseModel):
    """Base user profile fields"""
    user_name: Optional[str] = None


class UserProfileCreate(UserProfileBase):
    """User profile creation model"""
    id: str  # UUID as string


class UserProfileUpdate(BaseModel):
    """User profile update model"""
    user_name: Optional[str] = None


class UserProfile(UserProfileBase):
    """Complete user profile model from database"""
    id: str  # UUID as string
    created_at: datetime
    
    class Config:
        from_attributes = True

