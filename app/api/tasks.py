from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from app.config import supabase
from app.models import Notification
from app.services.task_to_notification import generate_notifications_from_task as generate_notifications_from_task_ai

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class GenerateNotificationsRequest(BaseModel):
    user_id: str


class GenerateNotificationsResponse(BaseModel):
    notifications: List[Notification]
    count: int


@router.post("/{task_id}/notifications", response_model=GenerateNotificationsResponse)
async def generate_notifications_for_task(task_id: int, request: GenerateNotificationsRequest):
    """Generate AI notifications for a specific task"""
    from app.infra.supabase.repositories.tasks import TaskRepository
    
    task_repo = TaskRepository(supabase)
    task = await task_repo.find_by_id(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    notifications = await generate_notifications_from_task_ai(task)
    
    return {
        "notifications": notifications,
        "count": len(notifications)
    }

