"""CompleteTask Tool - marks a task as completed.

NOTE: DB に status/completed_at カラムが追加されるまで未登録。
登録は implementations/__init__.py で有効化する。
"""
from typing import Dict, Any, Type
from pydantic import BaseModel, Field
from app.services.tools.base import BaseTool, ToolResult


class CompleteTaskArgs(BaseModel):
    """Mark a task as completed."""
    task_id: int = Field(description="ID of the task to complete")


class CompleteTaskTool(BaseTool):
    """Marks a task as completed. Requires DB migration to add status/completed_at columns."""

    @property
    def name(self) -> str:
        return "CompleteTaskArgs"

    @property
    def description(self) -> str:
        return (
            "Mark a task as completed. Use ONLY when the user explicitly indicates "
            "task completion with phrases like 'finished', 'completed', 'done'. "
            "Do NOT use for mere progress reports or casual 'worked on it'."
        )

    @property
    def args_schema(self) -> Type[BaseModel]:
        return CompleteTaskArgs

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        # TODO: DB migration 後に実際の更新ロジックを実装
        task_id = args["task_id"]
        return ToolResult(
            tool_name=self.name,
            success=True,
            meta={"task_completed": {"task_id": task_id}},
        )
