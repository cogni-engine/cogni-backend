from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
import logging

from app.services.onboarding_note import generate_first_note_content, get_fallback_content

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


class GenerateFirstNoteResponse(BaseModel):
    title: str
    content: str


@router.post("/generate-first-note", response_model=GenerateFirstNoteResponse)
async def generate_first_note(request: GenerateFirstNoteRequest):
    """
    Generate personalized first note content based on onboarding answers.
    Falls back to default content if LLM fails.
    """
    try:
        result = await generate_first_note_content(
            primary_role=request.primary_role,
            ai_relationship=request.ai_relationship,
            use_case=request.use_case,
            locale=request.locale,
            user_id=request.user_id,
            workspace_id=request.workspace_id
        )
        return result
    except Exception as e:
        logger.error(f"Failed to generate first note: {e}")
        return get_fallback_content(request.locale)
