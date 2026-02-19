"""CompleteTask Tool - marks a task as completed via ai_notifications."""
import logging
from typing import Dict, Any, Type, Optional
from pydantic import BaseModel, Field
from app.services.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class CompleteTaskArgs(BaseModel):
    """Mark a task as completed."""
    task_id: int = Field(description="ID of the task to complete")


class CompleteTaskTool(BaseTool):
    """Marks a task as completed by updating ai_notifications reaction_status."""

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

    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        from app.db.session import SessionLocal
        from app.features.ai_notifications.service import AINotificationService
        from app.features.ai_notifications.repository import AINotificationRepository
        from app.db.models.ai_notification import AINotification as AINotificationORM, NotificationStatus
        from app.db.models.workspace_member import WorkspaceMember as WorkspaceMemberORM
        from sqlalchemy import select, cast, String, and_

        task_id = args["task_id"]
        user_id = context.get("user_id") if context else None

        if not user_id:
            logger.warning(f"[CompleteTask] no user_id in context")
            return ToolResult(
                tool_name=self.name,
                success=False,
                meta={"task_completed": {"task_id": task_id, "error": "no_user_context"}},
                error="User context not available",
            )

        try:
            async with SessionLocal() as db:
                # Find the latest unresolved notification for this task + user
                wm_stmt = select(WorkspaceMemberORM.id).where(WorkspaceMemberORM.user_id == user_id)
                wm_result = await db.execute(wm_stmt)
                wm_ids = [row[0] for row in wm_result.all()]

                if not wm_ids:
                    logger.warning(f"[CompleteTask] no workspace_members for user={user_id}")
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        meta={"task_completed": {"task_id": task_id, "error": "no_workspace_member"}},
                        error="No workspace member found for user",
                    )

                notif_stmt = (
                    select(AINotificationORM.id)
                    .where(
                        and_(
                            AINotificationORM.task_id == task_id,
                            AINotificationORM.workspace_member_id.in_(wm_ids),
                            cast(AINotificationORM.status, String) != "resolved",
                        )
                    )
                    .order_by(AINotificationORM.due_date.desc())
                    .limit(1)
                )
                notif_result = await db.execute(notif_stmt)
                notification_row = notif_result.scalar_one_or_none()

                if not notification_row:
                    logger.info(f"[CompleteTask] no active notification for task_id={task_id}")
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        meta={"task_completed": {"task_id": task_id, "note": "no_active_notification"}},
                        content_for_llm=f"[CompleteTaskArgs executed] task_id={task_id} のタスクに対応する未処理の通知はありませんでしたが、完了の意思は記録しました。",
                    )

                notification_id = notification_row

                # Use existing service to complete notification
                service = AINotificationService(db)
                result = await service.complete_notification(notification_id, user_id)

                logger.info(
                    f"[CompleteTask] task_id={task_id} notification_id={notification_id} completed, "
                    f"resolved={len(result.resolved_notification_ids)} previous notifications"
                )
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    meta={"task_completed": {"task_id": task_id, "notification_id": notification_id}},
                )

        except Exception as e:
            logger.error(f"[CompleteTask] failed task_id={task_id}: {e}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                meta={"task_completed": {"task_id": task_id, "error": str(e)}},
                error=str(e),
            )
