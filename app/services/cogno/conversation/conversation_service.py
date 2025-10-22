"""Conversation Service - User-facing AI chat with streaming"""
import logging
from typing import AsyncGenerator, List, Dict, Optional, Union

from app.models.ai_message import AIMessage, AIMessageCreate, MessageRole
from app.models.task import Task
from app.models.notification import Notification
from app.infra.supabase.repositories.ai_messages import AIMessageRepository
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.client import get_supabase_client
from app.services.llm.call_llm import LLMService
from .prompts.conversation_prompt import build_conversation_prompt

logger = logging.getLogger(__name__)

STREAM_CHAT_MODEL = "chatgpt-4o-latest"


async def conversation_stream(
    thread_id: int,
    user_message: Optional[str] = None,
    focused_task_id: Optional[int] = None,
    should_ask_timer: bool = False,
    timer_started: bool = False,
    timer_duration: Optional[Union[int, float]] = None,
    timer_duration_display: Optional[str] = None,
    timer_completed: bool = False,
    notification_triggered: bool = False,
    notification_context: Optional[Notification] = None,
    daily_summary_context: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream conversation AI response.
    
    Args:
        thread_id: Thread ID for conversation history
        user_message: User's message content (None for system triggers)
        focused_task_id: Task ID to focus on (from engine decision)
        should_ask_timer: Whether to ask user about timer duration (from engine decision)
        timer_started: Whether timer was just started
        timer_duration: Duration of started timer in minutes
        timer_completed: Whether timer has just completed (triggers management check-in)
        notification_triggered: Whether notification was triggered (click or daily)
        notification_context: Notification object for single notification click
        daily_summary_context: Daily summary text for multiple notifications
        
    Yields:
        SSE-formatted stream chunks
    """
    supabase_client = get_supabase_client()
    ai_message_repo = AIMessageRepository(supabase_client)
    task_repo = TaskRepository(supabase_client)
    
    try:
        # Save user message (skip if None - e.g., timer completion trigger)
        if user_message is not None:
            user_msg_create = AIMessageCreate(
                content=user_message,
                thread_id=thread_id,
                role=MessageRole.USER
            )
            await ai_message_repo.create(user_msg_create)
        
        # Get focused task details
        focused_task = None
        if focused_task_id:
            focused_task = await task_repo.find_by_id(focused_task_id)
            if focused_task:
                logger.info(f"Focused task: {focused_task_id} - {focused_task.title}")
            else:
                logger.info(f"Focused task: {focused_task_id} (not found)")
        else:
            logger.info("No focused task")
        
        # Get message history
        message_history = await ai_message_repo.find_by_thread(thread_id)
        
        # Convert to LLM format
        messages = _convert_to_llm_format(message_history)
        
        # Build system prompt with task context and timer request if needed
        system_content = build_conversation_prompt(
            focused_task=focused_task,
            should_ask_timer=should_ask_timer,
            timer_started=timer_started,
            timer_duration=timer_duration,
            timer_duration_display=timer_duration_display,
            timer_completed=timer_completed,
            notification_triggered=notification_triggered,
            notification_context=notification_context,
            daily_summary_context=daily_summary_context
        )
        messages.append({"role": "system", "content": system_content})
        
        logger.info(f"Using model: {STREAM_CHAT_MODEL}")
        logger.info(f"should_ask_timer: {should_ask_timer}, timer_started: {timer_started}, timer_duration: {timer_duration}, timer_completed: {timer_completed}, notification_triggered: {notification_triggered}")
        
        # Stream LLM response
        llm_service = LLMService(model=STREAM_CHAT_MODEL, temperature=0.7)
        full_response = ""
        
        async for chunk in llm_service.stream_invoke(messages):
            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                content = chunk[6:-2]  # Remove "data: " prefix and "\n\n" suffix
                full_response += content
            yield chunk
        
        # Save assistant response
        if full_response:
            meta = None
            
            # Add timer info if timer was started
            if timer_started and timer_duration:
                from datetime import datetime, timedelta
                
                started_at = datetime.utcnow()
                
                # timer_durationが秒単位か分単位かを判定
                if isinstance(timer_duration, float):
                    # 秒単位の場合
                    ends_at = started_at + timedelta(seconds=timer_duration)
                    duration_display = f"{int(timer_duration)}秒"
                    unit = "seconds"
                else:
                    # 分単位の場合
                    ends_at = started_at + timedelta(minutes=timer_duration)
                    duration_display = f"{timer_duration}分"
                    unit = "minutes"
                
                # timer_duration_displayが既に設定されている場合はそれを使用
                if timer_duration_display:
                    duration_display = timer_duration_display
                
                meta = {
                    "timer": {
                        "duration_minutes": timer_duration if isinstance(timer_duration, int) else timer_duration / 60,
                        "duration_seconds": timer_duration if isinstance(timer_duration, float) else timer_duration * 60,
                        "started_at": started_at.isoformat() + 'Z',
                        "ends_at": ends_at.isoformat() + 'Z',
                        "status": "active",
                        "unit": unit
                    }
                }
                logger.info(f"Timer meta added to AI message: {duration_display}, ends_at: {ends_at.isoformat()}")
            
            # Add notification_trigger flag to meta if notification was triggered
            elif notification_triggered:
                meta = {"notification_trigger": True}
            
            assistant_msg_create = AIMessageCreate(
                content=full_response,
                thread_id=thread_id,
                role=MessageRole.ASSISTANT,
                meta=meta
            )
            await ai_message_repo.create(assistant_msg_create)
            
    except Exception as e:
        error_message = f"エラーが発生しました: {str(e)}"
        logger.error(f"Conversation error: {e}")
        yield f"data: {error_message}\n\n"
        yield "data: [DONE]\n\n"
        raise


def _convert_to_llm_format(messages: List[AIMessage]) -> List[Dict[str, str]]:
    """Convert AIMessage list to LLM format"""
    return [
        {"role": msg.role.value, "content": msg.content}
        for msg in messages
    ]

