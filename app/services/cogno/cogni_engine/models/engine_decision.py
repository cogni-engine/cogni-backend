"""Engine decision models - minimal fields for speed"""
from typing import Optional
from pydantic import BaseModel, Field


class EngineDecision(BaseModel):
    """
    Cogni Engine's decision output.
    Minimal fields for maximum speed.
    Timer and task completion are now handled by Tool calling.
    """
    focused_task_id: Optional[int] = Field(
        None,
        description="ID of the task to focus on, or null if no suitable task"
    )
