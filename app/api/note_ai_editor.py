from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Literal

from app.services.note_ai_editor import get_ai_suggestions

router = APIRouter(prefix="/api/note-ai-editor", tags=["note-ai-editor"])


# Models for granular block-level suggestions
class AISuggestion(BaseModel):
    """A single AI-generated suggestion for editing a block"""
    block_id: str  # target block to modify
    action: Literal["replace", "insert_after", "delete"]
    suggested_text: Optional[List[str]] = None  # list of text blocks for replace/insert (allows multiple inserts for same block)


class AISuggestRequest(BaseModel):
    """Request for AI suggestions using anchor-based format
    
    Requires annotated markdown with block IDs:
    - note_content: Not used in anchor-based approach (kept for API compatibility)
    - annotated_note_content: Markdown with block ID comments (converted to simple IDs for AI)
    """
    annotated_note_content: str  # annotated markdown with block ID comments
    user_instruction: str
    file_contents: Optional[List[str]] = None


class AISuggestResponse(BaseModel):
    """Response containing list of targeted suggestions"""
    suggestions: List[AISuggestion]


@router.post("/suggest", response_model=AISuggestResponse)
async def ai_suggest_edits(request: AISuggestRequest):
    """Get AI suggestions for editing a note using anchor-based format
    
    This endpoint uses the anchor-based approach:
    1. Annotated markdown is converted to simple IDs (1, 2, 3...) for the AI
    2. AI outputs only changed blocks with anchors (edit/delete/insert operations)
    3. System maps simple IDs back to complex block IDs
    4. Returns block-level suggestions that can be applied in the editor
    """
    try:
        suggestions = await get_ai_suggestions(
            user_instruction=request.user_instruction,
            annotated_note_content=request.annotated_note_content,
            file_contents=request.file_contents,
        )
        
        return {
            "suggestions": suggestions,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get suggestions: {str(e)}")

