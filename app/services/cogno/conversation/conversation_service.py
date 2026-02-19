"""Conversation Service - User-facing AI chat with streaming"""
import logging
import json
from typing import AsyncGenerator, List, Dict, Optional, Protocol, Any, Tuple
from collections.abc import Sequence

from app.models.ai_message import AIMessageCreate, MessageRole
from app.models.notification import AINotification
from app.models.task import Task
from app.infra.supabase.repositories.ai_messages import AIMessageRepository
from app.infra.supabase.client import get_supabase_client
from app.services.llm.call_llm import LLMService
from app.services.file_processor.file_processor import build_file_context
from app.services.llm.message_builder import build_message_with_files
from app.services.tools.registry import tool_registry
from app.services.tools.executor import ToolExecutor
from .prompts.conversation_prompt import build_conversation_prompt

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
STREAM_CHAT_MODEL = "gemini-3-flash-preview"


class MessageLike(Protocol):
    """Protocol for any message-like object with role and content"""
    role: MessageRole
    content: str
    files: Optional[List[Any]]


# ---------------------------------------------------------------------------
# Tool Use Loop
# ---------------------------------------------------------------------------

async def _run_tool_loop(
    llm_service: LLMService,
    messages: List[Dict[str, Any]],
    bind_tools_list: List,
    executor: ToolExecutor,
) -> AsyncGenerator[Tuple[str, str, Dict[str, Any]], None]:
    """
    Tool Use Loop: stream LLM → detect tool_calls → execute → feed back → repeat.

    Yields SSE chunks (str) for the frontend.
    After the generator is exhausted, call .athrow() or read the final state
    from the returned values.

    Returns via a final special yield:
      (full_response, "FINAL", final_meta_dict)

    Normal yields:
      (sse_chunk, "CHUNK", {})
    """
    full_response = ""
    final_meta: Dict[str, Any] = {}

    for round_num in range(MAX_TOOL_ROUNDS + 1):
        round_response = ""
        tool_calls_detected: List[Dict] = []

        logger.info(f"[ToolLoop] round={round_num} start")

        async for chunk in llm_service.stream_invoke_with_tools(messages, bind_tools_list):
            if chunk.startswith("data: [TOOL_CALLS]"):
                tool_calls_json = chunk.removeprefix("data: [TOOL_CALLS]").removesuffix("\n\n")
                tool_calls_detected = json.loads(tool_calls_json)
            else:
                content = chunk.removeprefix("data: ").removesuffix("\n\n")
                wrapped = json.dumps({"data": content}, ensure_ascii=False)
                yield (f"data: {wrapped}\n\n", "CHUNK", {})
                round_response += content

        full_response = round_response or full_response

        if not tool_calls_detected:
            logger.info(f"[ToolLoop] round={round_num} no tools → done, response_len={len(full_response)}")
            break

        # Execute tools
        tool_names = [tc["name"] for tc in tool_calls_detected]
        logger.info(f"[ToolLoop] round={round_num} tools={tool_names}")
        results = await executor.execute_tool_calls(tool_calls_detected)

        # Collect meta + build feedback for next round
        tool_result_parts = []
        for result in results:
            logger.info(f"[ToolLoop]   {result.tool_name} success={result.success} meta_keys={list(result.meta.keys())}")
            if result.meta:
                final_meta.update(result.meta)
            if result.content_for_llm:
                tool_result_parts.append(result.content_for_llm)
            else:
                tool_result_parts.append(
                    f"[{result.tool_name} executed] {json.dumps(result.meta, ensure_ascii=False)}"
                )

        # Feed results back to LLM
        messages.append({"role": "assistant", "content": round_response or ""})
        messages.append({
            "role": "user",
            "content": "\n\n".join(tool_result_parts) + "\n\nこの結果を踏まえて、ユーザーに自然に応答してください。"
        })

    # Final yield carries accumulated state
    yield (full_response, "FINAL", final_meta)


# ---------------------------------------------------------------------------
# Main conversation stream
# ---------------------------------------------------------------------------

async def conversation_stream(
    thread_id: int,
    user_message: Optional[str] = None,
    file_ids: Optional[List[int]] = None,
    focused_task_with_description: Optional[Task] = None,
    timer_completed: bool = False,
    notification_triggered: bool = False,
    notification_context: Optional[AINotification] = None,
    daily_summary_context: Optional[str] = None,
    is_ai_initiated: bool = False,
    task_list_for_suggestion: Optional[List[Dict]] = None,
    all_user_tasks: Optional[List[Task]] = None,
    message_history: Optional[Sequence[MessageLike]] = None,
) -> AsyncGenerator[str, None]:
    """Stream conversation AI response with Tool Use Loop."""
    supabase_client = get_supabase_client()
    ai_message_repo = AIMessageRepository(supabase_client)

    try:
        # --- Save user message ---
        if user_message is not None:
            user_msg_create = AIMessageCreate(
                content=user_message,
                thread_id=thread_id,
                role=MessageRole.USER,
                file_ids=file_ids,
            )
            await ai_message_repo.create(user_msg_create)

        # --- Build context ---
        focused_task = focused_task_with_description
        related_tasks_info = _build_related_tasks(focused_task, all_user_tasks)

        messages = await _build_messages(
            message_history, ai_message_repo, thread_id, supabase_client
        )

        file_context = None
        if file_ids:
            file_context = await build_file_context(supabase_client, file_ids)

        system_content = build_conversation_prompt(
            focused_task=focused_task,
            related_tasks_info=related_tasks_info,
            timer_completed=timer_completed,
            notification_triggered=notification_triggered,
            notification_context=notification_context,
            daily_summary_context=daily_summary_context,
            task_list_for_suggestion=task_list_for_suggestion,
            file_context=file_context,
        )
        messages.append({"role": "system", "content": system_content})

        logger.info(f"[Conversation] model={STREAM_CHAT_MODEL} thread={thread_id} timer_completed={timer_completed} notification={notification_triggered}")

        # --- Stream with Tool Use Loop ---
        llm_service = LLMService(model=STREAM_CHAT_MODEL, temperature=0.7)
        full_response = ""
        final_meta: Dict[str, Any] = {}

        if tool_registry.has_tools():
            bind_tools_list = tool_registry.get_bind_tools_list()
            executor = ToolExecutor(tool_registry)

            async for chunk, kind, meta in _run_tool_loop(
                llm_service, messages, bind_tools_list, executor
            ):
                if kind == "CHUNK":
                    yield chunk
                elif kind == "FINAL":
                    full_response = chunk
                    final_meta = meta
        else:
            async for chunk in llm_service.stream_invoke(messages):
                content = chunk.removeprefix("data: ").removesuffix("\n\n")
                wrapped = json.dumps({"data": content}, ensure_ascii=False)
                yield f"data: {wrapped}\n\n"
                full_response += content

        # --- Save & finalize ---
        if notification_triggered:
            final_meta["notification_trigger"] = True
        final_meta["is_ai_initiated"] = is_ai_initiated

        if full_response:
            assistant_msg = AIMessageCreate(
                content=full_response,
                thread_id=thread_id,
                role=MessageRole.ASSISTANT,
                meta=final_meta,
            )
            await ai_message_repo.create(assistant_msg)
            logger.info(f"[Conversation] saved assistant msg, len={len(full_response)} meta_keys={list(final_meta.keys())}")
        else:
            logger.warning(f"[Conversation] empty response, nothing saved")

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"[Conversation] error: {e}", exc_info=True)
        error_msg = json.dumps({"data": f"エラーが発生しました: {str(e)}"}, ensure_ascii=False)
        yield f"data: {error_msg}\n\n"
        yield "data: [DONE]\n\n"
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_related_tasks(
    focused_task: Optional[Task],
    all_user_tasks: Optional[List[Task]],
) -> Optional[List[Dict]]:
    if not focused_task:
        return None
    if not focused_task.source_note_id or not all_user_tasks:
        return None
    return [
        {"title": t.title, "status": t.status or "pending"}
        for t in all_user_tasks
        if t.source_note_id == focused_task.source_note_id
    ]


async def _build_messages(
    message_history: Optional[Sequence[MessageLike]],
    ai_message_repo: AIMessageRepository,
    thread_id: int,
    supabase_client,
) -> List[Dict[str, Any]]:
    """Get message history and convert to LLM format."""
    MAX_HISTORY = 10

    if message_history is None:
        all_history = await ai_message_repo.find_by_thread(thread_id)
        history = list(all_history[-MAX_HISTORY:]) if len(all_history) > MAX_HISTORY else all_history
    else:
        history = list(message_history[-MAX_HISTORY:]) if len(message_history) > MAX_HISTORY else message_history

    logger.info(f"[Conversation] message_history={len(history)}")
    return await _convert_to_llm_format_with_files(history, supabase_client)


async def _convert_to_llm_format_with_files(
    messages: Sequence[MessageLike],
    supabase_client,
) -> List[Dict[str, Any]]:
    """Convert message-like objects to LLM format with file support."""
    llm_messages = []
    for msg in messages:
        has_files = hasattr(msg, 'files') and msg.files
        if has_files and msg.role == MessageRole.USER:
            file_ids = [file.id for file in msg.files]  # type: ignore
            llm_msg = await build_message_with_files(
                role=msg.role,
                content=msg.content,
                file_ids=file_ids,
                supabase_client=supabase_client,
            )
            llm_messages.append(llm_msg)
        else:
            llm_messages.append({"role": msg.role, "content": msg.content})
    return llm_messages
