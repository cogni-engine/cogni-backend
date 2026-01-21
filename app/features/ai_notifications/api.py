"""AI Notifications API endpoints"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db import get_db
from app.middleware.auth import get_current_user_id
from app.features.ai_notifications.repository import AINotificationRepository
from app.features.ai_notifications.domain import AINotification


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
