"""AI Notifications API endpoints"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.db import get_db
from app.middleware.auth import get_current_user_id
from app.features.ai_notifications.repository import AINotificationRepository
from app.features.ai_notifications.service import AINotificationService
from app.features.ai_notifications.domain import AINotification
from app.features.ai_notifications.schemas import (
    CompleteNotificationResponse,
    PostponeNotificationRequest,
    PostponeNotificationResponse,
    ReactedAINotification
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/ai-notifications", tags=["ai-notifications"])


@router.get("/past-due", response_model=List[AINotification])
async def get_past_due_notifications(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
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
        notifications = await repo.get_past_due_notifications_for_user(user_id)
        
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
    db: AsyncSession = Depends(get_db)
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
        result = await service.complete_notification(notification_id, user_id)
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
    db: AsyncSession = Depends(get_db)
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
        result = await service.postpone_notification(
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


@router.get("/workspace/{workspace_id}/reacted", response_model=List[ReactedAINotification])
async def get_reacted_notifications_by_workspace(
    workspace_id: int,
    workspace_member_ids: Optional[List[int]] = Query(None, description="Optional list of workspace_member_ids to filter by"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
) -> List[ReactedAINotification]:
    """
    Get all AI notifications that have been reacted on (reaction_text IS NOT NULL) for a workspace.
    
    Returns notifications with:
    - Note information (id and title)
    - User information (id, name, avatar_url) from workspace_member and user_profiles
    
    Args:
        workspace_id: The workspace ID to filter by
        workspace_member_ids: Optional list of workspace_member_ids to filter by
        
    Returns:
        List of ReactedAINotification with note and user information
    """
    try:
        service = AINotificationService(db)
        notifications = await service.get_reacted_notifications_by_workspace(
            workspace_id,
            workspace_member_ids,
            user_id
        )
        logger.info(f"Returning {len(notifications)} notifications for workspace {workspace_id}")
        
        return notifications
        
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"Failed to fetch reacted notifications: {str(e)}"
        error_traceback = traceback.format_exc()
        logger.error(f"{error_detail}\n{error_traceback}")
        raise HTTPException(
            status_code=500,
            detail=error_detail
        )