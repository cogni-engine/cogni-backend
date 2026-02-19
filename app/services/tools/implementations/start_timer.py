"""StartTimer Tool - starts a timer for the user."""
from datetime import datetime, timedelta
from typing import Dict, Any, Type
from pydantic import BaseModel, Field
from app.services.tools.base import BaseTool, ToolResult


class StartTimerArgs(BaseModel):
    """Start a timer for the user."""
    duration_seconds: int = Field(description="Timer duration in seconds")


class StartTimerTool(BaseTool):
    """Starts a timer. Previously handled by Engine Decision + regex extraction."""

    @property
    def name(self) -> str:
        return "StartTimerArgs"

    @property
    def description(self) -> str:
        return (
            "Start a timer for the user. Use when the user is about to begin "
            "a focused activity (studying, working out, cooking, meeting, etc.) "
            "or explicitly asks for a timer."
        )

    @property
    def args_schema(self) -> Type[BaseModel]:
        return StartTimerArgs

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        duration = args["duration_seconds"]
        started_at = datetime.utcnow()
        ends_at = started_at + timedelta(seconds=duration)
        return ToolResult(
            tool_name=self.name,
            success=True,
            meta={"timer": {
                "duration_seconds": duration,
                "started_at": started_at.isoformat() + "Z",
                "ends_at": ends_at.isoformat() + "Z",
                "status": "active",
            }}
        )
