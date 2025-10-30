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
    task_to_complete_id: Optional[int] = Field(
        None,
        description=(
            "ID of the task to mark as completed. "
            "Set ONLY when user explicitly indicates task completion with phrases like "
            "'終わった' (finished), '完了した' (completed), 'できた' (done). "
            "Do NOT set for mere progress reports or casual 'やった' (did it). "
            "Be strict in judgment."
        )
    )
    next_task_id: Optional[int] = Field(
        None,
        description="ID of the next recommended task after current focused task is completed"
    )

