"""Task to Notification service module"""
from .task_to_notification_service import (
    generate_notifications_from_task,
    generate_notifications_from_tasks_batch,
    process_task_queue_for_notifications
)
from .models import NotificationBaseForAI, NotificationListResponse
from .prompts import prompt_template, batch_prompt_template

__all__ = [
    "generate_notifications_from_task",
    "generate_notifications_from_tasks_batch",
    "process_task_queue_for_notifications",
    "NotificationBaseForAI",
    "NotificationListResponse",
    "prompt_template",
    "batch_prompt_template",
]

