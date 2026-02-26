"""Task to Notification service module

DEPRECATED: このサービスは旧パイプライン（webhooks.py の sync-memories）で使用されていたもの。
現在は Memory Service（app/services/memory/）の Step 2/3 で通知生成・最適化を行っている。
削除予定。新規利用禁止。
"""
from .task_to_notification_service import (
    generate_notifications_from_task,
    generate_notifications_from_tasks_batch,
)
from .models import NotificationBaseForAI, NotificationListResponse
from .prompts import prompt_template, batch_prompt_template

__all__ = [
    "generate_notifications_from_task",
    "generate_notifications_from_tasks_batch",
    "NotificationBaseForAI",
    "NotificationListResponse",
    "prompt_template",
    "batch_prompt_template",
]

