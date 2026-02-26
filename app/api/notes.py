from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from app.config import supabase
from app.models import Task
from app.services.note_to_task import generate_tasks_from_note

router = APIRouter(prefix="/api/notes", tags=["notes"])


class GenerateTasksRequest(BaseModel):
    user_id: str


class GenerateTasksResponse(BaseModel):
    tasks: List[Task]
    count: int


@router.post("/{note_id}/tasks", response_model=GenerateTasksResponse)
async def generate_tasks_for_note(note_id: int, request: GenerateTasksRequest):
    """DEPRECATED: 旧パイプラインでのタスク生成。現在未使用。
    代替: /api/memory/{workspace_id}/events（Memory Serviceベースの新パイプライン）
    """
    from app.infra.supabase.repositories.notes import NoteRepository
    
    note_repo = NoteRepository(supabase)
    note = await note_repo.find_by_id(note_id)
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    tasks = await generate_tasks_from_note(note_id, note.text, [request.user_id], note.title)
    
    return {
        "tasks": tasks,
        "count": len(tasks)
    }
