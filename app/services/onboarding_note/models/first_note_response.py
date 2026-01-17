"""Response model for first note generation"""
from pydantic import BaseModel, Field


class FirstNoteContent(BaseModel):
    """Generated first note with title and content"""
    title: str = Field(description="Creative, personalized title for the note")
    content: str = Field(description="Structured markdown content with use case examples and action items")
