"""Notification schema models for AI processing"""
from typing import List
from datetime import datetime

from pydantic import BaseModel, Field


class NotificationBaseForAI(BaseModel):
    """AI-generated notification with think-first approach"""
    ai_context: str = Field(
        description="Think first (not shown to users): "
        "1) Read the task carefully - what is the user trying to achieve? "
        "2) What would genuinely help them right now? "
        "3) What type of notification is appropriate for this specific task? "
        "Use the same language as the task."
    )
    title: str = Field(
        description="Short title (under 15 chars). Based on your analysis. Same language as task."
    )
    body: str = Field(
        description="Body (50-80 chars). Based on your analysis - provide what the user actually needs. Same language as task."
    )
    due_date: datetime = Field(
        description="When to send (ISO format: 2024-10-15T10:00:00)"
    )


class NotificationListResponse(BaseModel):
    """List of notifications"""
    notifications: List[NotificationBaseForAI] = Field(
        description="Generated notifications (1-3). Empty array if none needed."
    )
