"""Task focus models for AI chat"""
from typing import Optional
from pydantic import BaseModel, Field


class FocusedTaskResponse(BaseModel):
    """LLM response for focused task determination"""
    focused_task_id: Optional[int] = Field(
        None, 
        description="ID of the task to focus on, or null if no suitable task"
    )

