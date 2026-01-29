"""Conversation Service - User-facing AI chat with streaming"""
import logging
import json
from typing import AsyncGenerator, List, Dict, Optional, Protocol, Any
from collections.abc import Sequence

from app.models.ai_message import AIMessageCreate, MessageRole
from app.models.notification import AINotification
from app.models.task import Task
from app.infra.supabase.repositories.ai_messages import AIMessageRepository
from app.infra.supabase.client import get_supabase_client
from app.services.llm.call_llm import LLMService
from app.services.file_processor.file_processor import build_file_context
from app.services.llm.message_builder import build_message_with_files
from .prompts.conversation_prompt import build_conversation_prompt

logger = logging.getLogger(__name__)


class MessageLike(Protocol):
    """Protocol for any message-like object with role and content"""
    role: MessageRole
    content: str
    files: Optional[List[Any]]

STREAM_CHAT_MODEL = "gpt-5.1-chat-latest"


async def conversation_stream(
    thread_id: int,
    user_message: Optional[str] = None,
    file_ids: Optional[List[int]] = None,  # File attachments
    focused_task_with_description: Optional[Task] = None,  # Focused task with description
    should_ask_timer: bool = False,
    timer_started: bool = False,
    timer_duration: Optional[int] = None,  # 秒単位に統一
    timer_completed: bool = False,
    notification_triggered: bool = False,
    notification_context: Optional[AINotification] = None,
    daily_summary_context: Optional[str] = None,
    is_ai_initiated: bool = False,  # AI起点メッセージフラグ（見た目用）
    task_list_for_suggestion: Optional[List[Dict]] = None,  # Focused Task=Noneの場合のタスクリスト
    task_to_complete_id: Optional[int] = None,  # 完了候補タスクID
    task_completion_confirmed: bool = False,  # 完了確定フラグ
    all_user_tasks: Optional[List[Task]] = None,  # All tasks for the user (from engine)
    message_history: Optional[Sequence[MessageLike]] = None,  # Message history (to avoid refetching)
) -> AsyncGenerator[str, None]:
    """
    Stream conversation AI response.

    Args:
        thread_id: Thread ID for conversation history
        user_message: User's message content (None for system triggers)
        focused_task_with_description: Focused task with full description
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
        all_user_tasks: All tasks for the user (from engine, to avoid refetching)
        message_history: Message history (to avoid refetching)

    Yields:
        SSE-formatted stream chunks
    """
    supabase_client = get_supabase_client()
    ai_message_repo = AIMessageRepository(supabase_client)
    
    try:
        # Save user message (skip if None - e.g., timer completion trigger)
        if user_message is not None:
            user_msg_create = AIMessageCreate(
                content=user_message,
                thread_id=thread_id,
                role=MessageRole.USER,
                file_ids=file_ids  # NEW: Include file attachments
            )
            await ai_message_repo.create(user_msg_create)
        
        # Get focused task and related tasks
        focused_task = focused_task_with_description
        related_tasks_info = None

        if focused_task:
            # Get related tasks from the same source note
            if focused_task.source_note_id and all_user_tasks:
                related_tasks = [
                    task for task in all_user_tasks
                    if task.source_note_id == focused_task.source_note_id
                ]
                related_tasks_info = [
                    {
                        "title": task.title,
                        "status": task.status or "pending"
                    }
                    for task in related_tasks
                ]
        else:
            logger.info("No focused task")

        # Get message history (use passed history if available, otherwise fetch)
        # Limit to most recent 10 messages to avoid token overflow
        final_message_history: Sequence[MessageLike]
        if message_history is None:
            all_history = await ai_message_repo.find_by_thread(thread_id)
            # Take only the most recent 10 messages
            final_message_history = list(all_history[-10:]) if len(all_history) > 10 else all_history
            logger.info(f"Fetched message history: {len(all_history)} total, using {len(final_message_history)} most recent")
        else:
            # Limit passed history as well
            if len(message_history) > 10:
                final_message_history = list(message_history[-10:])
                logger.info(f"Limited message history: {len(message_history)} total, using {len(final_message_history)} most recent")
            else:
                final_message_history = message_history
                logger.info(f"Using passed message history: {len(final_message_history)} messages")
        
        # Convert to LLM format (with file support for images)
        messages = await _convert_to_llm_format_with_files(final_message_history, supabase_client)
        
        # Get task for completion confirmation if needed (from cached pending tasks)
        task_to_complete = None
        if task_to_complete_id and not task_completion_confirmed and all_user_tasks:
            # Find task from already-fetched pending tasks
            task_to_complete = next((task for task in all_user_tasks if task.id == task_to_complete_id), None)
            if task_to_complete:
                logger.info(f"Task to complete (confirmation): {task_to_complete_id} - {task_to_complete.title} (from cached tasks)")
            else:
                logger.info(f"Task to complete {task_to_complete_id} not found in cached tasks")
        
        # Build file context if files are attached
        file_context = None
        if file_ids:
            file_context = await build_file_context(supabase_client, file_ids)
            if file_context:
                logger.info(f"Built file context for {len(file_ids)} files")

        # Build system prompt with task context and timer request if needed
        system_content = build_conversation_prompt(
            focused_task=focused_task,
            related_tasks_info=related_tasks_info,
            should_ask_timer=should_ask_timer,
            timer_started=timer_started,
            timer_duration=timer_duration,
            timer_completed=timer_completed,
            notification_triggered=notification_triggered,
            notification_context=notification_context,
            daily_summary_context=daily_summary_context,
            task_list_for_suggestion=task_list_for_suggestion,
            task_to_complete=task_to_complete,
            task_completion_confirmed=task_completion_confirmed,
            file_context=file_context,
        )
        
        # Print system prompt in a visible way with emojis
        print("=" * 80)
        print("📝 SYSTEM PROMPT 📝")
        print("=" * 80)
        print(system_content)
        print("=" * 80)
        
        messages.append({"role": "system", "content": system_content})
        
        logger.info(f"Using model: {STREAM_CHAT_MODEL}")
        logger.info(f"should_ask_timer: {should_ask_timer}, timer_started: {timer_started}, timer_duration: {timer_duration}, timer_completed: {timer_completed}, notification_triggered: {notification_triggered}")
        
        # Stream LLM response
        llm_service = LLMService(model=STREAM_CHAT_MODEL, temperature=0.7)
        full_response = ""
        
        async for chunk in llm_service.stream_invoke(messages):
            content = chunk.removeprefix("data: ").removesuffix("\n\n")
            wrapped_chunk = json.dumps({"data": content}, ensure_ascii=False)
            yield f"data: {wrapped_chunk}\n\n"
            full_response += content
        
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


def _convert_to_llm_format(messages: Sequence[MessageLike]) -> List[Dict[str, str]]:
    """Convert message-like objects to LLM format (simple version)"""
    return [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]


async def _convert_to_llm_format_with_files(
    messages: Sequence[MessageLike],
    supabase_client
) -> List[Dict[str, Any]]:
    """
    Convert message-like objects to LLM format with file support.
    For user messages with image attachments, includes images in content array.
    """
    llm_messages = []
    
    for msg in messages:
        # Check if message has files (only AIMessage has this attribute)
        has_files = hasattr(msg, 'files') and msg.files
        
        if has_files and msg.role == MessageRole.USER:
            # User message with files - use message builder
            file_ids = [file.id for file in msg.files]  # type: ignore
            llm_msg = await build_message_with_files(
                role=msg.role,
                content=msg.content,
                file_ids=file_ids,
                supabase_client=supabase_client
            )
            llm_messages.append(llm_msg)
        else:
            # Simple text message
            llm_messages.append({"role": msg.role, "content": msg.content})
    
    return llm_messages

