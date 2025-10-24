from fastapi import APIRouter, Request, Header, HTTPException
from app.config import supabase, WEBHOOK_SECRET
from app.services.note_to_task import generate_tasks_from_note
from app.services.task_to_notification import process_task_queue_for_notifications
from app.infra.supabase.repositories.workspaces import WorkspaceRepository
import asyncio
import json
from typing import Dict, Optional

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Task notification queue
task_notification_queue: Dict[int, int] = {}
queue_lock = asyncio.Lock()
processing_task: Optional[asyncio.Task] = None
DEBOUNCE_SECONDS = 10


async def process_task_notification_queue():
    """Wait 10 seconds, then process the queue"""
    global task_notification_queue
    
    await asyncio.sleep(DEBOUNCE_SECONDS)
    
    async with queue_lock:
        if not task_notification_queue:
            return
        queue_copy = task_notification_queue.copy()
        task_notification_queue.clear()
    
    await process_task_queue_for_notifications(queue_copy)


@router.post("/notes")
async def handle_notes_webhook(
    request: Request,
    x_webhook_secret: str = Header(None)
):
    """Handle Supabase webhook for note changes (personal workspaces only)"""
    
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized webhook call")
    
    body = await request.json()
    print("✅ Webhook received:", json.dumps(body, indent=2))
    
    record = body.get("record") or {}
    note_id = record.get("id")
    note_text = record.get("text", "")
    workspace_id = record.get("workspace_id")

    if not note_id:
        raise HTTPException(status_code=400, detail="Missing note_id in payload")
    
    if not workspace_id:
        raise HTTPException(status_code=400, detail="Missing workspace_id in payload")
    
    workspace_repo = WorkspaceRepository(supabase)
    workspace = await workspace_repo.find_by_id(workspace_id)
    
    if not workspace:
        print(f"❌ Workspace {workspace_id} not found")
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    if workspace.type != "personal":
        print(f"🚫 Skipped webhook for workspace_id={workspace_id}, type={workspace.type}")
        return {"status": "ignored", "reason": "Not personal workspace"}
    
    if not note_text:
        print(f"⚠️ Note {note_id} has no text, skipping task generation")
        return {"status": "skipped", "reason": "empty_note"}
    
    # TODO: Get user_id from workspace_id
    user_id = "58e744e7-ec0f-45e1-a63a-bc6ed71e10de"
    
    try:
        tasks = await generate_tasks_from_note(note_id, note_text, user_id)
        print(f"🧠 Generated {len(tasks)} tasks from note {note_id}")
        return {"status": "ok", "generated_count": len(tasks)}
    except Exception as e:
        print(f"❌ Error generating tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Task generation failed: {str(e)}")


@router.post("/tasks")
async def handle_tasks_webhook(
    request: Request,
    x_webhook_secret: str = Header(None)
):
    """Handle Supabase webhook for task changes"""
    global processing_task
    
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized webhook call")
    
    body = await request.json()
    record = body.get("record") or {}
    
    task_id = record.get("id")
    source_note_id = record.get("source_note_id")
    
    if not task_id or not source_note_id:
        print(f"⚠️ Invalid webhook payload: task_id={task_id}, source_note_id={source_note_id}")
        return {"status": "ignored", "reason": "missing_required_fields"}
    
    async with queue_lock:
        task_notification_queue[task_id] = source_note_id
        
        if processing_task and not processing_task.done():
            processing_task.cancel()
        
        processing_task = asyncio.create_task(process_task_notification_queue())
    
    print(f"📝 Task {task_id} added to queue (total: {len(task_notification_queue)})")
    return {"status": "queued", "task_id": task_id}

