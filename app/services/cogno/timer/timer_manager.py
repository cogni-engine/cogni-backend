"""Timer Manager - Manages timer lifecycle"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.repositories.ai_messages import AIMessageRepository
from app.models.ai_message import AIMessageCreate, AIMessageUpdate, MessageRole
from .models.timer_state import TimerState, TimerStatus
from app.services.cogno.conversation.conversation_service import conversation_stream

logger = logging.getLogger(__name__)


async def start_timer(
    thread_id: int,
    duration_seconds: int,
    message_id: Optional[int] = None
) -> TimerState:
    """
    Start a new timer for a thread.
    Stores timer info in AIMessage.meta
    
    Args:
        thread_id: Thread ID
        duration_seconds: Timer duration in seconds
        message_id: Optional AI message ID to attach timer to
        
    Returns:
        TimerState with timer information
    """
    supabase_client = get_supabase_client()
    ai_message_repo = AIMessageRepository(supabase_client)
    
    try:
        # Calculate timer times
        started_at = datetime.utcnow()
        ends_at = started_at + timedelta(seconds=duration_seconds)
        
        # Create timer state
        timer_state = TimerState(
            duration_seconds=duration_seconds,
            duration_minutes=duration_seconds / 60,  # 後方互換性のため
            started_at=started_at.isoformat(),
            ends_at=ends_at.isoformat(),
            status=TimerStatus.ACTIVE,
            unit="seconds",
            message_id=message_id
        )
        
        # Create a system message with timer info
        timer_msg_create = AIMessageCreate(
            content=f"タイマーを{duration_seconds}秒で設定しました。",
            thread_id=thread_id,
            role=MessageRole.ASSISTANT,
            meta={"timer": timer_state.dict()}
        )
        created_msg = await ai_message_repo.create(timer_msg_create)
        timer_state.message_id = created_msg.id
        
        logger.info(f"Timer started: {duration_seconds}sec for thread {thread_id}, ends at {ends_at}")
        return timer_state
        
    except Exception as e:
        logger.error(f"Error starting timer: {e}")
        raise


async def get_active_timer(thread_id: int) -> Optional[Dict[str, Any]]:
    """
    Get active timer for a thread.
    
    Args:
        thread_id: Thread ID
        
    Returns:
        Timer info with remaining time, or None if no active timer
    """
    supabase_client = get_supabase_client()
    ai_message_repo = AIMessageRepository(supabase_client)
    
    try:
        # Get recent messages to find active timer
        messages = await ai_message_repo.find_by_thread(thread_id)
        
        for msg in reversed(messages):  # Check most recent first
            if msg.meta and "timer" in msg.meta:
                timer_data = msg.meta["timer"]
                if timer_data.get("status") == TimerStatus.ACTIVE.value:
                    timer_state = TimerState(**timer_data)
                    
                    # Check if timer has ended
                    ends_at = datetime.fromisoformat(timer_state.ends_at)
                    EARLY_COMPLETION_SECONDS = 3
                    now = datetime.now(timezone.utc) + timedelta(seconds=EARLY_COMPLETION_SECONDS)
                    
                    if now >= ends_at:
                        # Timer has ended - mark as completed and trigger follow-up
                        await _complete_timer(thread_id, msg.id, timer_state)
                        return {
                            "timer_ended": True,
                            "timer": timer_state.dict()
                        }
                    else:
                        # Timer still active - calculate remaining time
                        remaining_seconds = int((ends_at - now).total_seconds())
                        return {
                            "timer_ended": False,
                            "timer": timer_state.dict(),
                            "remaining_seconds": remaining_seconds
                        }
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting active timer: {e}")
        return None


async def _complete_timer(thread_id: int, message_id: int, timer_state: TimerState):
    """
    Complete a timer and create follow-up message using conversation AI.
    
    Args:
        thread_id: Thread ID
        message_id: Message ID with timer
        timer_state: Timer state
    """
    supabase_client = get_supabase_client()
    ai_message_repo = AIMessageRepository(supabase_client)
    
    try:
        # Update timer status to completed
        timer_state.status = TimerStatus.COMPLETED
        update = AIMessageUpdate(meta={"timer": timer_state.dict()})
        await ai_message_repo.update(message_id, update)
        
        # Generate follow-up message using conversation AI
        # Stream all chunks to generate and save the AI response
        logger.info(f"Timer completed for thread {thread_id}, generating AI follow-up message")
        
        async for chunk in conversation_stream(
            thread_id=thread_id,
            user_message=None,
            timer_completed=True,
            is_ai_initiated=True
        ):
            # Just consume the stream - conversation_stream will save the message
            pass
        
        logger.info(f"Timer completion follow-up message generated for thread {thread_id}")
        
    except Exception as e:
        logger.error(f"Error completing timer: {e}")
        raise


async def cancel_timer(thread_id: int, message_id: int) -> bool:
    """
    Cancel an active timer.
    
    Args:
        thread_id: Thread ID
        message_id: Message ID with timer
        
    Returns:
        True if cancelled successfully
    """
    supabase_client = get_supabase_client()
    ai_message_repo = AIMessageRepository(supabase_client)
    
    try:
        message = await ai_message_repo.find_by_id(message_id)
        if not message or not message.meta or "timer" not in message.meta:
            return False
        
        timer_data = message.meta["timer"]
        timer_state = TimerState(**timer_data)
        timer_state.status = TimerStatus.CANCELLED
        
        update = AIMessageUpdate(meta={"timer": timer_state.dict()})
        await ai_message_repo.update(message_id, update)
        
        logger.info(f"Timer cancelled for message {message_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error cancelling timer: {e}")
        return False

