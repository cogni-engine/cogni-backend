from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Cookie
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

from app.infra.supabase.repositories.notifications import NotificationRepository
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.client import get_supabase_client
from app.services.cogno.cogni_engine.engine_service import make_engine_decision, extract_timer_duration, _convert_tasks_to_simple_dict
from app.services.cogno.conversation.conversation_service import conversation_stream
from app.models.ai_message import MessageRole
from typing import List

router = APIRouter(prefix="/api/cogno", tags=["cogno"])


class SimpleMessage(BaseModel):
    """Simple message model for API requests (without DB fields)"""
    role: MessageRole
    content: str
    meta: Optional[Dict[str, Any]] = None


def get_previous_task_to_complete_from_messages(messages: List[SimpleMessage]) -> Optional[int]:
    """Get previous task_to_complete_id from last assistant message in the message history"""
    # Find the last assistant message
    for msg in reversed(messages):
        if msg.role == MessageRole.ASSISTANT:
            # Check if message has meta with task_to_complete_id
            if msg.meta:
                return msg.meta.get("task_to_complete_id")
            break
    return None


async def complete_task_background(task_id: int):
    """Background task to mark task as completed"""
    try:
        supabase_client = get_supabase_client()
        task_repo = TaskRepository(supabase_client)
        await task_repo.mark_completed(task_id)
        logging.info(f"✓ Task {task_id} marked as completed (background)")
    except Exception as e:
        logging.error(f"Error completing task {task_id} in background: {e}")


class ConversationStreamRequest(BaseModel):
    thread_id: int
    messages: List[SimpleMessage]
    notification_id: Optional[int] = None
    timer_completed: Optional[bool] = None


@router.post("/conversations/stream")
async def stream_conversation(
    request: ConversationStreamRequest, 
    background_tasks: BackgroundTasks,
    current_user_id: Optional[str] = Cookie(None)
):
    """
    Stream a conversation with Cogno AI.
    
    Flow:
    1. If notification_id provided: Skip engine decision, generate notification response
    2. Otherwise: Engine makes decision (focused_task_id, should_start_timer, task_to_complete_id)
    3. If should_start_timer=true, extract timer duration
    4. If task_to_complete_id: Check if 2nd consecutive -> complete task in background
    5. Conversation AI responds with timer info in meta
    """
    logging.info(f"current_user_id from cookie: {current_user_id}")
    
    # Handle notification trigger
    if request.notification_id:
        supabase_client = get_supabase_client()
        notification_repo = NotificationRepository(supabase_client)
        notification = await notification_repo.find_by_id(request.notification_id)
        
        if notification:
            logging.info(f"Notification trigger: {request.notification_id} - {notification.title}")
            return StreamingResponse(
                conversation_stream(
                    thread_id=request.thread_id,
                    user_message=None,
                    notification_triggered=True,
                    notification_context=notification,
                    is_ai_initiated=True
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
                is_ai_initiated=True
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    if not current_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Make engine decision with current user message (also returns pending tasks)
    decision, pending_tasks = await make_engine_decision(current_user_id, request.messages)
    logging.info(f"Engine decision: focused_task_id={decision.focused_task_id}, should_start_timer={decision.should_start_timer}, task_to_complete_id={decision.task_to_complete_id}, pending_tasks_count={len(pending_tasks)}")
    
    # If engine decided to start timer, extract duration
    timer_duration = None
    timer_started = False
    if decision.should_start_timer:
        timer_duration = extract_timer_duration(request.messages[-1].content)
        logging.info(f"Timer duration extraction result: {timer_duration} seconds" if timer_duration else "No duration found in message")
        if timer_duration:
            timer_started = True
            logging.info(f"✓ Timer will be started: {timer_duration} seconds for thread {request.thread_id}")
    
    # Ask for timer duration only if engine wants timer but we couldn't extract duration
    should_ask_timer = decision.should_start_timer and not timer_started
    logging.info(f"Conversation context: should_ask_timer={should_ask_timer}, timer_started={timer_started}, timer_duration={timer_duration}")
    
    # Check for task completion (2-stage confirmation)
    task_completion_confirmed = False
    if decision.task_to_complete_id:
        previous_task_to_complete = get_previous_task_to_complete_from_messages(request.messages)
        if previous_task_to_complete == decision.task_to_complete_id:
            # 2nd consecutive time -> confirm and complete
            task_completion_confirmed = True
            background_tasks.add_task(complete_task_background, decision.task_to_complete_id)
            logging.info(f"✓ Task {decision.task_to_complete_id} completion confirmed (2nd time), will complete in background")
        else:
            # 1st time -> ask for confirmation
            logging.info(f"Task {decision.task_to_complete_id} completion suggested (1st time), asking for confirmation")
    
    # Prepare task list for suggestion if no focused task
    task_list_for_suggestion = None
    if not decision.focused_task_id and pending_tasks:
        # Reuse pending tasks already fetched by engine
        task_list_for_suggestion = _convert_tasks_to_simple_dict(pending_tasks)
        logging.info(f"Providing {len(task_list_for_suggestion)} tasks for suggestion")
    
    # Stream conversation response with engine decision context
    # Timer info will be saved in AI message meta, not as separate system message
    return StreamingResponse(
        conversation_stream(
            thread_id=request.thread_id,
            user_message=request.messages[-1].content,
            focused_task_id=decision.focused_task_id,
            should_ask_timer=should_ask_timer,
            timer_started=timer_started,
            timer_duration=timer_duration,
            task_list_for_suggestion=task_list_for_suggestion,
            task_to_complete_id=decision.task_to_complete_id,
            task_completion_confirmed=task_completion_confirmed,
            all_user_tasks=pending_tasks,
            message_history=request.messages
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
    current_user_id: Optional[str] = Cookie(None)
):
    """Get messages for a specific thread (optionally since a given message ID)"""
    logging.info(f"current_user_id from cookie: {current_user_id}")
    
    from app.infra.supabase.repositories.ai_messages import AIMessageRepository
    from app.config import supabase
    
    ai_message_repo = AIMessageRepository(supabase)
    
    if since:
        messages = await ai_message_repo.find_since(thread_id, since)
    else:
        messages = await ai_message_repo.find_by_thread(thread_id)
    
    # Timer auto-completion is now handled by the client via stream trigger
    
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

