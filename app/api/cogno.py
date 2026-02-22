from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

from app.infra.supabase.repositories.notifications import AINotificationRepository
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.client import get_supabase_client
from app.services.cogno.cogni_engine.engine_service import make_engine_decision, _convert_tasks_to_simple_dict
from app.services.cogno.conversation.conversation_service import conversation_stream
from app.models.ai_message import MessageRole
from typing import List
from app.auth import get_current_user_id

router = APIRouter(prefix="/api/cogno", tags=["cogno"])


class SimpleMessage(BaseModel):
    """Simple message model for API requests (without DB fields)"""
    role: MessageRole
    content: str
    meta: Optional[Dict[str, Any]] = None
    file_ids: Optional[List[int]] = None


class ConversationStreamRequest(BaseModel):
    thread_id: int
    messages: List[SimpleMessage]
    notification_id: Optional[int] = None
    timer_completed: Optional[bool] = None


@router.post("/conversations/stream")
async def stream_conversation(
    request: ConversationStreamRequest,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Stream a conversation with Cogno AI.

    Flow:
    1. If notification_id provided: Skip engine decision, generate notification response
    2. If timer_completed: Generate timer completion check-in
    3. Otherwise: Engine decides focused_task_id, Conversation LLM handles tool calling
       (timer, task completion, web search are all handled via Tool calling)
    """
    logging.info(f"current_user_id from JWT: {current_user_id}")

    # Handle notification trigger
    if request.notification_id:
        supabase_client = get_supabase_client()
        notification_repo = AINotificationRepository(supabase_client)
        notification = await notification_repo.find_by_id(request.notification_id)

        if notification:
            logging.info(f"Notification trigger: {request.notification_id} - {notification.title}")
            return StreamingResponse(
                conversation_stream(
                    thread_id=request.thread_id,
                    user_message=None,
                    notification_triggered=True,
                    notification_context=notification,
                    is_ai_initiated=True,
                    current_user_id=current_user_id,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            logging.error(f"Notification {request.notification_id} not found")
            raise HTTPException(status_code=404, detail="Notification not found")

    # Handle timer completion trigger
    if request.timer_completed:
        logging.info(f"Timer completion trigger for thread {request.thread_id}")
        return StreamingResponse(
            conversation_stream(
                thread_id=request.thread_id,
                user_message=None,
                timer_completed=True,
                is_ai_initiated=True,
                current_user_id=current_user_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    # Make engine decision (focused_task_id only; timer/task_complete are now Tool-based)
    decision, pending_tasks = await make_engine_decision(current_user_id, request.messages)
    logging.info(f"Engine decision: focused_task_id={decision.focused_task_id}, pending_tasks_count={len(pending_tasks)}")

    # Prepare task list for suggestion if no focused task
    task_list_for_suggestion = None
    if not decision.focused_task_id and pending_tasks:
        task_list_for_suggestion = _convert_tasks_to_simple_dict(pending_tasks)
        logging.info(f"Providing {len(task_list_for_suggestion)} tasks for suggestion")

    # Extract file_ids from the last user message
    file_ids = request.messages[-1].file_ids if request.messages and hasattr(request.messages[-1], 'file_ids') else None

    # Fetch focused task with description if focused_task_id exists
    focused_task_with_description = None
    if decision.focused_task_id:
        supabase_client = get_supabase_client()
        task_repo = TaskRepository(supabase_client)
        focused_task_with_description = await task_repo.find_by_id(decision.focused_task_id)
        if focused_task_with_description:
            logging.info(f"Fetched focused task with description: {decision.focused_task_id}")

    # Stream conversation response with engine decision context
    # Timer and task completion are handled via Tool calling by the Conversation LLM
    return StreamingResponse(
        conversation_stream(
            thread_id=request.thread_id,
            user_message=request.messages[-1].content,
            file_ids=file_ids,
            focused_task_with_description=focused_task_with_description,
            task_list_for_suggestion=task_list_for_suggestion,
            all_user_tasks=pending_tasks,
            message_history=request.messages,
            current_user_id=current_user_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: int,
    since: Optional[int] = Query(None, description="Only return messages after this message ID"),
    current_user_id: str = Depends(get_current_user_id)
):
    """Get messages for a specific thread (optionally since a given message ID)"""
    logging.info(f"current_user_id from JWT: {current_user_id}")

    from app.infra.supabase.repositories.ai_messages import AIMessageRepository
    from app.config import supabase

    ai_message_repo = AIMessageRepository(supabase)

    if since:
        messages = await ai_message_repo.find_since(thread_id, since)
    else:
        messages = await ai_message_repo.find_by_thread(thread_id)

    # Remove duplicate messages
    seen_ids = set()
    unique_messages = []
    for msg in messages:
        if msg.id not in seen_ids:
            seen_ids.add(msg.id)
            unique_messages.append(msg)
        else:
            logging.warning(f"Duplicate message ID {msg.id} detected and filtered")

    return {"messages": unique_messages}
