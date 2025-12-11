from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.config import supabase
from app.models import AINotification
from app.models.task import Task
from app.services.task import RecurringTaskService
from app.services.task_to_notification import generate_notifications_from_task as generate_notifications_from_task_ai

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# Request/Response models for CRUD operations
class ListTasksRequest(BaseModel):
    user_id: str


class CreateTaskRequest(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    status: Optional[str] = "pending"
    progress: Optional[int] = None
    source_note_id: Optional[int] = None
    assigner_id: Optional[str] = None
    recurrence_pattern: Optional[str] = None
    is_ai_task: Optional[bool] = False
    next_run_time: Optional[datetime] = None


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    status: Optional[str] = None
    progress: Optional[int] = None
    completed_at: Optional[datetime] = None
    recurrence_pattern: Optional[str] = None
    is_ai_task: Optional[bool] = None
    next_run_time: Optional[datetime] = None


class TaskResponse(BaseModel):
    task: Task


class TaskListResponse(BaseModel):
    tasks: List[Task]
    count: int


class DeleteResponse(BaseModel):
    success: bool
    message: str


# CRUD Endpoints
@router.get("", response_model=TaskListResponse)
async def list_recurring_tasks(user_id: str):
    """List all recurring tasks for a specific user"""
    service = RecurringTaskService(supabase)
    tasks = await service.get_recurring_tasks(user_id)
    
    return {
        "tasks": tasks,
        "count": len(tasks)
    }


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    """Get a single task by ID"""
    service = RecurringTaskService(supabase)
    task = await service.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"task": task}


@router.post("", response_model=TaskResponse)
async def create_task(request: CreateTaskRequest):
    """Create a new recurring task"""
    service = RecurringTaskService(supabase)
    
    task = await service.create_recurring_task(
        user_id=request.user_id,
        title=request.title,
        description=request.description,
        recurrence_pattern=request.recurrence_pattern,
        next_run_time=request.next_run_time,
        is_ai_task=request.is_ai_task or False,
        deadline=request.deadline,
        status=request.status,
        progress=request.progress,
        source_note_id=request.source_note_id,
        assigner_id=request.assigner_id,
    )
    
    return {"task": task}


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, request: UpdateTaskRequest):
    """Update an existing recurring task"""
    service = RecurringTaskService(supabase)
    
    task = await service.update_recurring_task(
        task_id=task_id,
        title=request.title,
        description=request.description,
        deadline=request.deadline,
        status=request.status,
        progress=request.progress,
        completed_at=request.completed_at,
        recurrence_pattern=request.recurrence_pattern,
        is_ai_task=request.is_ai_task,
        next_run_time=request.next_run_time,
    )
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"task": task}


@router.delete("/{task_id}", response_model=DeleteResponse)
async def delete_task(task_id: int):
    """Delete a recurring task"""
    service = RecurringTaskService(supabase)
    
    success = await service.delete_recurring_task(task_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"success": True, "message": "Task deleted successfully"}


# Existing AI notification endpoint
class GenerateNotificationsRequest(BaseModel):
    user_id: str


class GenerateNotificationsResponse(BaseModel):
    notifications: List[AINotification]
    count: int


@router.post("/{task_id}/notifications", response_model=GenerateNotificationsResponse)
async def generate_notifications_for_task(task_id: int, request: GenerateNotificationsRequest):
    """Generate AI notifications for a specific task"""
    service = RecurringTaskService(supabase)
    task = await service.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    notifications = await generate_notifications_from_task_ai(task)
    
    return {
        "notifications": notifications,
        "count": len(notifications)
    }

