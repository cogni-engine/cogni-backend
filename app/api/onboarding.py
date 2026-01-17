from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import logging

from app.services.onboarding_note import generate_first_note_and_create
from app.models.note import Note

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
async def generate_first_note(request: GenerateFirstNoteRequest):
    """
    Generate personalized first note content and create it in Supabase.
    Returns the created Note model with id, title, text, workspace_id, created_at, updated_at.
    Also updates onboarding_sessions.context.firstNote with noteId.
    Falls back to default content if LLM fails, but note is still created.
    """
    try:
        note = await generate_first_note_and_create(
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
