"""AI Notifications API endpoints"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db import get_db
from app.middleware.auth import get_current_user_id
from app.features.ai_notifications.repository import AINotificationRepository
from app.features.ai_notifications.service import AINotificationService
from app.features.ai_notifications.domain import (
    AINotification,
    CompleteNotificationResponse,
    PostponeNotificationRequest,
    PostponeNotificationResponse
)


router = APIRouter(prefix="/api/ai-notifications", tags=["ai-notifications"])


@router.get("/past-due", response_model=List[AINotification])
async def get_past_due_notifications(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Get all past due notifications for the authenticated user.
    
    A notification is considered past due if:
    - Its due_date is in the past
    
    Returns:
        List of past due notifications, ordered by due_date (oldest first)
    """
    try:
        repo = AINotificationRepository(db)
        notifications = repo.get_past_due_notifications_for_user(user_id)
        
        return notifications
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch past due notifications: {str(e)}"
        )


@router.post("/{notification_id}/complete", response_model=CompleteNotificationResponse)
async def complete_notification(
    notification_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Complete a notification and resolve all previous notifications from the same task.
    
    When a user completes a notification, this endpoint:
    1. Marks the specified notification as "completed"
    2. Marks all notifications from the same task with due dates <= this notification as "resolved"
    
    This is useful when a user addresses a task, making earlier reminders obsolete.
    
    Args:
        notification_id: The ID of the notification to complete
        
    Returns:
        CompleteNotificationResponse with IDs of affected notifications
        
    Raises:
        404: Notification not found or user doesn't have access
        500: Server error during processing
    """
    try:
        service = AINotificationService(db)
        result = service.complete_notification(notification_id, user_id)
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete notification: {str(e)}"
        )


@router.post("/{notification_id}/postpone", response_model=PostponeNotificationResponse)
async def postpone_notification(
    notification_id: int,
    request: PostponeNotificationRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Postpone a notification with user's reaction text and resolve all previous notifications from the same task.
    
    When a user postpones a notification, this endpoint:
    1. Marks the specified notification as "postponed"
    2. Stores the user's reaction_text (reason for postponement)
    3. Marks all notifications from the same task with due dates <= this notification as "resolved"
    
    This is useful when a user acknowledges a reminder but decides to address it later.
    
    Args:
        notification_id: The ID of the notification to postpone
        request: PostponeNotificationRequest containing reaction_text
        
    Returns:
        PostponeNotificationResponse with IDs of affected notifications
        
    Raises:
        404: Notification not found or user doesn't have access
        500: Server error during processing
    """
    try:
        service = AINotificationService(db)
        result = service.postpone_notification(
            notification_id, 
            user_id, 
            request.reaction_text
        )
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to postpone notification: {str(e)}"
        )