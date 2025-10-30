"""Conversation Service - User-facing AI chat with streaming"""
import logging
from typing import AsyncGenerator, List, Dict, Optional

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
    timer_duration: Optional[int] = None,  # 秒単位に統一
    timer_completed: bool = False,
    notification_triggered: bool = False,
    notification_context: Optional[Notification] = None,
    daily_summary_context: Optional[str] = None,
    is_ai_initiated: bool = False,  # AI起点メッセージフラグ（見た目用）
    task_list_for_suggestion: Optional[List[Dict]] = None,  # Focused Task=Noneの場合のタスクリスト
    task_to_complete_id: Optional[int] = None,  # 完了候補タスクID
    task_completion_confirmed: bool = False,  # 完了確定フラグ
) -> AsyncGenerator[str, None]:
    """
    Stream conversation AI response.
    
    Args:
        thread_id: Thread ID for conversation history
        user_message: User's message content (None for system triggers)
        focused_task_id: Task ID to focus on (from engine decision)
        should_ask_timer: Whether to ask user about timer duration (from engine decision)
        timer_started: Whether timer was just started
        timer_duration: Duration of started timer in seconds
        timer_completed: Whether timer has just completed (triggers management check-in)
        notification_triggered: Whether notification was triggered (click or daily)
        notification_context: Notification object for single notification click
        daily_summary_context: Daily summary text for multiple notifications
        is_ai_initiated: Whether this message is initiated by AI (for styling purposes)
        task_list_for_suggestion: Task list for suggestion when no focused task
        task_to_complete_id: Task ID to potentially complete
        task_completion_confirmed: Whether task completion is confirmed (2nd time)
        
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
        
        # Get task for completion confirmation if needed
        task_to_complete = None
        if task_to_complete_id and not task_completion_confirmed:
            task_to_complete = await task_repo.find_by_id(task_to_complete_id)
            if task_to_complete:
                logger.info(f"Task to complete (confirmation): {task_to_complete_id} - {task_to_complete.title}")
        
        # Build system prompt with task context and timer request if needed
        system_content = build_conversation_prompt(
            focused_task=focused_task,
            should_ask_timer=should_ask_timer,
            timer_started=timer_started,
            timer_duration=timer_duration,
            timer_completed=timer_completed,
            notification_triggered=notification_triggered,
            notification_context=notification_context,
            daily_summary_context=daily_summary_context,
            task_list_for_suggestion=task_list_for_suggestion,
            task_to_complete=task_to_complete,
            task_completion_confirmed=task_completion_confirmed
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
                ends_at = started_at + timedelta(seconds=timer_duration)
                
                # 時間・分・秒の表示用文字列を生成
                def format_duration(seconds: int) -> str:
                    hours = seconds // 3600
                    minutes = (seconds % 3600) // 60
                    remaining_seconds = seconds % 60
                    
                    parts = []
                    if hours > 0:
                        parts.append(f"{hours}時間")
                    if minutes > 0:
                        parts.append(f"{minutes}分")
                    if remaining_seconds > 0:
                        parts.append(f"{remaining_seconds}秒")
                    
                    return "".join(parts) if parts else "0秒"
                
                duration_display = format_duration(timer_duration)
                
                meta = {
                    "timer": {
                        "duration_seconds": timer_duration,
                        "started_at": started_at.isoformat() + 'Z',
                        "ends_at": ends_at.isoformat() + 'Z',
                        "status": "active",
                        "unit": "seconds"
                    }
                }
                logger.info(f"Timer meta added to AI message: {duration_display}, ends_at: {ends_at.isoformat()}")
            
            # Add notification_trigger flag to meta if notification was triggered
            elif notification_triggered:
                meta = {"notification_trigger": True}
            
            # Prepare meta data
            final_meta = {}
            if meta:
                final_meta.update(meta)
            final_meta["is_ai_initiated"] = is_ai_initiated
            
            # Save task_to_complete_id to meta for tracking
            if task_to_complete_id:
                final_meta["task_to_complete_id"] = task_to_complete_id
            
            assistant_msg_create = AIMessageCreate(
                content=full_response,
                thread_id=thread_id,
                role=MessageRole.ASSISTANT,
                meta=final_meta
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

