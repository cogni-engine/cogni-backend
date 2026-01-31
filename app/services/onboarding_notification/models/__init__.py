"""Onboarding Notification Models"""
from pydantic import BaseModel, Field


class TutorialTaskResultResponse(BaseModel):
    """AI response for tutorial task result generation (with web search)"""
    result_title: str = Field(
        description="Short title for the research result (max 30 chars)"
    )
    result_text: str = Field(
        description="Research summary in Markdown format (200-400 chars). Include relevant info and 1-2 reference links."
    )


class TutorialNotificationResponse(BaseModel):
    """AI response for tutorial notification generation"""
    title: str = Field(
        description="Notification title conveying completion (max 15 chars)"
    )
    body: str = Field(
        description="Notification body (50-100 chars). Summarize result and encourage next steps."
    )
    ai_context: str = Field(
        description="Internal reasoning (not shown to user)"
    )
