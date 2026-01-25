"""Task execution response model for structured output"""
from pydantic import BaseModel, Field


class TaskExecutionResponse(BaseModel):
    """Response model for AI task execution with structured output"""
    title: str = Field(description="Short summary of what was done (max 30 chars)")
    content: str = Field(description="The deliverable content in ready-to-use format")


class FormattedExecutionResponse(BaseModel):
    """Response model for formatting raw execution results with title and citations"""
    result_title: str = Field(
        description="Short title for the deliverable (max 30 chars). Examples: 'AI Market Report 2024', 'Email Draft Reply'"
    )
    result_text: str = Field(
        description=(
            "Well-formatted deliverable in Markdown. Use proper headings, bullet points, "
            "and formatting for readability. If sources were used, include a '## References' "
            "section at the end with linked citations."
        )
    )

