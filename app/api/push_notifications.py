"""
Push Notification API Endpoints

Handles push notification webhook from Supabase
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime
import logging

from app.config import supabase
from app.models.push_notification import (
    SendPushNotificationResponse,
    SupabaseWebhookPayload,
)
from app.services.push_notification_service import PushNotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/push-notifications", tags=["push-notifications"])

# Initialize push notification service
push_service = PushNotificationService(supabase)


@router.get("/health")
async def health_check():
    """Health check for push notification service"""
    return {
        "status": "healthy",
        "service": "push-notifications",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/send", response_model=SendPushNotificationResponse)
async def send_push_notification(request: SupabaseWebhookPayload):
    """
    Send push notification via Expo Push API

    This endpoint is called by Supabase Database Webhook when a new
    push_notification record is inserted.

    Args:
        request: SupabaseWebhookPayload with the inserted record

    Returns:
        SendPushNotificationResponse with send results

    Raises:
        HTTPException: If notification not found or send fails
    """
    # Extract notification ID from the webhook payload
    notification_id = request.record.id

    try:
        logger.info(f"Processing push notification {notification_id} from webhook")
        result = await push_service.send_notification(notification_id)
        logger.info(
            f"Push notification {notification_id} processed: "
            f"sent={result.get('sent', 0)}, failed={result.get('failed', 0)}"
        )
        return result

    except ValueError as e:
        logger.error(f"Notification {notification_id} not found: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        logger.error(f"Error sending push notification {notification_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

