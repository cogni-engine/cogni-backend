"""Engine decision models - minimal fields for speed"""
from typing import Optional
from pydantic import BaseModel, Field


class EngineDecision(BaseModel):
    """
    Cogni Engine's decision output.
    Minimal fields for maximum speed.
    """
    focused_task_id: Optional[int] = Field(
        None,
        description="ID of the task to focus on, or null if no suitable task"
    )
    should_start_timer: bool = Field(
        False,
        description=(
            "Whether to start a timer. "
            "Set to true if user is about to start a long activity where they cannot chat with AI "
            "(gym, cooking, meeting, studying, etc.). "
            "Also true if user explicitly asks for a timer. "
            "False for simple questions or ongoing conversations."
        )
    )

