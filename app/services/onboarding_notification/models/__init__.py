"""Onboarding Notification Models"""
from pydantic import BaseModel

class TutorialTaskResponse(BaseModel):
    """AI response for tutorial task generation"""
    title: str
    description: str

class TutorialNotificationResponse(BaseModel):
    """AI response for tutorial notification generation"""
    title: str
    ai_context: str
    body: str | None = None
