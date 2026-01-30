from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import logging

from app.services.onboarding_note import generate_first_note_and_create
from app.services.onboarding_notification import generate_tutorial_task_and_notification
from app.models.note import Note
from app.models.task import Task
from app.models.notification import AINotification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class GenerateFirstNoteRequest(BaseModel):
    primary_role: Optional[List[str]] = None
    ai_relationship: Optional[List[str]] = None  
    use_case: Optional[List[str]] = None
    user_id: str
    workspace_id: int
    onboarding_session_id: str
    locale: str = "en"  # Default to English


@router.post("/generate-first-note", response_model=Note)
def generate_first_note(request: GenerateFirstNoteRequest):
    """
    Generate personalized first note content and create it in Supabase.
    Returns the created Note model with id, title, text, workspace_id, created_at, updated_at.
    Also updates onboarding_sessions.context.firstNote with noteId.
    Falls back to default content if LLM fails, but note is still created.
    """
    try:
        note = generate_first_note_and_create(
            primary_role=request.primary_role,
            ai_relationship=request.ai_relationship,
            use_case=request.use_case,
            locale=request.locale,
            user_id=request.user_id,
            workspace_id=request.workspace_id,
            onboarding_session_id=request.onboarding_session_id
        )
        return note
    except Exception as e:
        logger.error(f"Failed to generate and create first note: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create first note: {str(e)}")


class GenerateTutorialNotificationRequest(BaseModel):
    onboarding_session_id: str
    user_id: str
    locale: str = "en"  # Default to English


class GenerateTutorialNotificationResponse(BaseModel):
    task: Task
    notification: AINotification


@router.post("/generate-tutorial-notification", response_model=GenerateTutorialNotificationResponse)
async def generate_tutorial_notification(request: GenerateTutorialNotificationRequest):
    """
    Generate a task and notification from the tutorial note for onboarding.
    Uses the edited tutorial note content as context.
    
    Request:
    - onboarding_session_id: Onboarding session ID
    - user_id: User ID
    - locale: User's locale (e.g., "ja", "en-US")
    
    Response:
    - task: Full Task model with id, title, description, etc.
    - notification: Full AINotification model with id, task_id, etc.
    """
    print(f"[API] POST /generate-tutorial-notification - session_id={request.onboarding_session_id}, user_id={request.user_id}, locale={request.locale}")
    
    try:
        task, notification = await generate_tutorial_task_and_notification(
            onboarding_session_id=request.onboarding_session_id,
            user_id=request.user_id,
            locale=request.locale
        )
        
        print(f"[API] ✅ Response: task_id={task.id}, notification_id={notification.id}")
        
        return {
            "task": task,
            "notification": notification
        }
    except Exception as e:
        print(f"[API] ❌ Failed to generate tutorial notification: {e}")
        logger.error(f"[API] Failed to generate tutorial notification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate tutorial notification: {str(e)}")
