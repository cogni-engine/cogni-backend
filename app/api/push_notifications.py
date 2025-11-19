"""
Push Notification API Endpoints

Handles push notification webhook from Supabase
"""

from fastapi import APIRouter, HTTPException, Header, Depends
from typing import Optional
from datetime import datetime
import logging

from app.config import supabase, SUPABASE_SERVICE_ROLE_KEY
from app.models.push_notification import (
    SendNotificationRequest,
    SendPushNotificationResponse,
)
from app.services.push_notification_service import PushNotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/push-notifications", tags=["push-notifications"])

# Initialize push notification service
push_service = PushNotificationService(supabase)


async def verify_authorization(authorization: Optional[str] = Header(None)):
    """Verify request is authorized with service role key"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # Check if it's a Bearer token
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.replace("Bearer ", "")

    # Verify it matches service role key
    if token != SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    return token


@router.get("/health")
async def health_check():
    """Health check for push notification service"""
    return {
        "status": "healthy",
        "service": "push-notifications",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/send", response_model=SendPushNotificationResponse)
async def send_push_notification(
    request: SendNotificationRequest, _: str = Depends(verify_authorization)
):
    """
    Send push notification via Expo Push API

    This endpoint is called by Supabase Database Webhook when a new
    push_notification record is inserted.

    Args:
        request: SendNotificationRequest with notificationId
        _: Authorization token (verified by dependency)

    Returns:
        SendPushNotificationResponse with send results

    Raises:
        HTTPException: If notification not found or send fails
    """
    notification_id = request.notificationId

    try:
        logger.info(f"Processing push notification {notification_id}")
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

