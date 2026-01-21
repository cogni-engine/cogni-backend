"""AI Notifications feature module"""

from app.features.ai_notifications.api import router
from app.features.ai_notifications.repository import AINotificationRepository
from app.features.ai_notifications.domain import (
    AINotification,
    AINotificationCreate,
    AINotificationUpdate,
    NotificationStatus,
    TaskResult,
)

__all__ = [
    "router",
    "AINotificationRepository",
    "AINotification",
    "AINotificationCreate",
    "AINotificationUpdate",
    "NotificationStatus",
    "TaskResult",
]
