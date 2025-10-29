from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import logging

from app.infra.supabase.repositories.notifications import NotificationRepository
from app.infra.supabase.client import get_supabase_client
from app.services.cogno.cogni_engine.engine_service import make_engine_decision, extract_timer_duration
from app.services.cogno.conversation.conversation_service import conversation_stream

router = APIRouter(prefix="/api/cogno", tags=["cogno"])


class ConversationStreamRequest(BaseModel):
    thread_id: int
    message: str
    notification_id: Optional[int] = None
    timer_completed: Optional[bool] = None


@router.post("/conversations/stream")
async def stream_conversation(request: ConversationStreamRequest):
    """
    Stream a conversation with Cogno AI.
    
    Flow:
    1. If notification_id provided: Skip engine decision, generate notification response
    2. Otherwise: Engine makes decision (focused_task_id, should_start_timer)
    3. If should_start_timer=true, extract timer duration
    4. Conversation AI responds with timer info in meta
    """
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
    
    # Make engine decision with current user message
    decision = await make_engine_decision(request.thread_id, request.message)
    logging.info(f"Engine decision: focused_task_id={decision.focused_task_id}, should_start_timer={decision.should_start_timer}")
    
    # If engine decided to start timer, extract duration
    timer_duration = None
    timer_started = False
    if decision.should_start_timer:
        timer_duration = extract_timer_duration(request.message)
        logging.info(f"Timer duration extraction result: {timer_duration} seconds" if timer_duration else "No duration found in message")
        if timer_duration:
            timer_started = True
            logging.info(f"✓ Timer will be started: {timer_duration} seconds for thread {request.thread_id}")
    
    # Ask for timer duration only if engine wants timer but we couldn't extract duration
    should_ask_timer = decision.should_start_timer and not timer_started
    logging.info(f"Conversation context: should_ask_timer={should_ask_timer}, timer_started={timer_started}, timer_duration={timer_duration}")
    
    # Stream conversation response with engine decision context
    # Timer info will be saved in AI message meta, not as separate system message
    return StreamingResponse(
        conversation_stream(
            thread_id=request.thread_id,
            user_message=request.message,
            focused_task_id=decision.focused_task_id,
            should_ask_timer=should_ask_timer,
            timer_started=timer_started,
            timer_duration=timer_duration
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
    since: Optional[int] = Query(None, description="Only return messages after this message ID")
):
    """Get messages for a specific thread (optionally since a given message ID)"""
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

