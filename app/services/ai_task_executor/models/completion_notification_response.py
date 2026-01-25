"""Completion notification response model for structured output"""
from pydantic import BaseModel, Field


class CompletionNotificationResponse(BaseModel):
    """Response model for completion notification generation with structured output"""
    title: str = Field(
        description="Notification title conveying completion (under 15 chars). Match the content language."
    )
    body: str = Field(
        description="Notification body (50-100 chars). Summarize result and suggest next action. Match the content language."
    )
    ai_context: str = Field(
        description="Internal reasoning (not shown to user). Your analysis of the task and notification strategy."
    )

