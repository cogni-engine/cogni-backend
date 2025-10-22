"""AI Chat Service with streaming support"""
import logging
from typing import AsyncGenerator, List, Dict

from app.models.ai_message import AIMessage, AIMessageCreate, MessageRole
from app.infra.supabase.repositories.ai_messages import AIMessageRepository
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.client import get_supabase_client
from app.services.llm.call_llm import LLMService
from .prompts.chat_system_prompt import build_system_prompt_with_task
from .task_service import determine_focused_task

logger = logging.getLogger(__name__)


STREAM_CHAT_MODEL = "chatgpt-4o-latest"  


async def ai_chat_stream(
    thread_id: int,
    user_message: str,
) -> AsyncGenerator[str, None]:
    """
    Stream AI chat response based on thread history.
    Uses the latest available model for optimal performance.
    
    Args:
        thread_id: Thread ID for conversation history
        user_message: User's message content
        
    Yields:
        SSE-formatted stream chunks
    """
    supabase_client = get_supabase_client()
    ai_message_repo = AIMessageRepository(supabase_client)
    task_repo = TaskRepository(supabase_client)
    
    try:
        # Save user message
        user_msg_create = AIMessageCreate(
            content=user_message,
            thread_id=thread_id,
            role=MessageRole.USER
        )
        await ai_message_repo.create(user_msg_create)
        
        # Determine focused task
        focused_task_id = await determine_focused_task(thread_id)
        
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
        
        # Build system prompt with task context
        system_content = build_system_prompt_with_task(focused_task)
        messages.append({"role": "system", "content": system_content})
        logger.info(f"Using model: {STREAM_CHAT_MODEL}")
        print("==== AIに投げるmessages ====")
        for m in messages:
            print(m)
        print("================================")
        
        # Stream LLM response with latest model
        llm_service = LLMService(model=STREAM_CHAT_MODEL, temperature=0.7)
        full_response = ""
        
        async for chunk in llm_service.stream_invoke(messages):
            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                content = chunk[6:-2]  # Remove "data: " prefix and "\n\n" suffix
                full_response += content
            yield chunk
        
        # Save assistant response
        if full_response:
            assistant_msg_create = AIMessageCreate(
                content=full_response,
                thread_id=thread_id,
                role=MessageRole.ASSISTANT
            )
            await ai_message_repo.create(assistant_msg_create)
            
    except Exception as e:
        error_message = f"エラーが発生しました: {str(e)}"
        logger.error(f"AI chat error: {e}")
        yield f"data: {error_message}\n\n"
        yield "data: [DONE]\n\n"
        raise


def _convert_to_llm_format(messages: List[AIMessage]) -> List[Dict[str, str]]:
    """Convert AIMessage list to LLM format"""
    return [
        {"role": msg.role.value, "content": msg.content}
        for msg in messages
    ]
