"""AI Notifications feature module"""

from app.features.ai_notifications.api import router
from app.features.ai_notifications.repository import AINotificationRepository
from app.features.ai_notifications.service import AINotificationService
from app.features.ai_notifications.domain import (
    AINotification,
    AINotificationCreate,
    AINotificationUpdate,
    NotificationStatus,
    ReactionStatus,
    TaskResult,
    CompleteNotificationRequest,
    CompleteNotificationResponse,
    PostponeNotificationRequest,
    PostponeNotificationResponse,
)

__all__ = [
    "router",
    "AINotificationRepository",
    "AINotificationService",
    "AINotification",
    "AINotificationCreate",
    "AINotificationUpdate",
    "NotificationStatus",
    "ReactionStatus",
    "TaskResult",
    "CompleteNotificationRequest",
    "CompleteNotificationResponse",
    "PostponeNotificationRequest",
    "PostponeNotificationResponse",
]
