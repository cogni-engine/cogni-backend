"""Task execution response model for structured output"""
from pydantic import BaseModel, Field


class TaskExecutionResponse(BaseModel):
    """Response model for AI task execution with structured output"""
    title: str = Field(description="やったことの短い概要（30文字程度）")
    content: str = Field(description="成果物本体（そのまま使える形式）")

