from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from app.services.note_ai_editor import edit_note_with_ai

router = APIRouter(prefix="/api/note-ai-editor", tags=["note-ai-editor"])


class AIEditRequest(BaseModel):
    note_content: str
    user_instruction: str
    file_contents: Optional[List[str]] = None


class AIEditResponse(BaseModel):
    edited_content: str
    original_content: str


@router.post("/edit", response_model=AIEditResponse)
async def ai_edit_note(request: AIEditRequest):
    """Edit a note using AI based on user instructions"""
    try:
        edited_content = await edit_note_with_ai(
            note_content=request.note_content,
            user_instruction=request.user_instruction,
            file_contents=request.file_contents,
        )
        
        return {
            "edited_content": edited_content,
            "original_content": request.note_content,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to edit note: {str(e)}")

