"""Cogni Engine Service - Makes decisions about task focus"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Protocol
from collections.abc import Sequence

from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.repositories.tasks import TaskRepository
from app.models.task import Task
from app.models.ai_message import MessageRole
from app.services.llm.call_llm import LLMService
from .models.engine_decision import EngineDecision
from .prompts.engine_prompt import ENGINE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class MessageLike(Protocol):
    """Protocol for any message-like object with role and content"""
    role: MessageRole
    content: str


async def make_engine_decision(current_user_id: str, messages: Sequence[MessageLike]) -> tuple[EngineDecision, List[Task]]:
    """
    Analyze chat history and tasks to decide which task to focus on.
    Timer and task completion are now handled by Tool calling.

    Returns:
        Tuple of (EngineDecision, relevant_tasks_list)
    """
    supabase_client = get_supabase_client()
    
    # Initialize repositories
    task_repo = TaskRepository(supabase_client)
    
    try:

        # Get user's tasks (exclude description to reduce data size)
        all_tasks = await task_repo.find_by_user_notes(current_user_id, exclude_description=True)

        now = datetime.now(timezone.utc)
        one_week_ago = now - timedelta(days=7)
        deadline_start = now - timedelta(days=3)
        deadline_end = now + timedelta(days=3)
        two_days_ago = now - timedelta(days=2)

        def _normalize_datetime(dt: Optional[datetime]) -> Optional[datetime]:
            """Ensure datetime is timezone-aware (UTC)"""
            if dt is None:
                return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        def _is_relevant_task(t: Task) -> bool:
            """Check if task is relevant for Cogni Engine context"""
            # Exclude old completed tasks (keep recently completed within 2 days)
            if t.status == "completed":
                completed_at = _normalize_datetime(t.completed_at)
                if not completed_at or completed_at < two_days_ago:
                    return False

            updated_at = _normalize_datetime(t.updated_at)
            deadline = _normalize_datetime(t.deadline)

            # Include if: updated in last week OR deadline within 3 days
            is_recently_updated = updated_at and updated_at >= one_week_ago
            is_deadline_near = deadline and deadline_start <= deadline <= deadline_end

            return is_recently_updated or is_deadline_near

        # Filter and sort by updated_at (newest first)
        tasks = [t for t in all_tasks if _is_relevant_task(t)]
        tasks.sort(key=lambda t: t.updated_at or now, reverse=True)

        logger.info(
            f"Cogni Engine context: {len(tasks)} relevant tasks "
            f"(from {len(all_tasks)} total, filtered by: updated_in_1week OR deadline_within_3days)"
        )

        # Get recent chat history (last 6 messages for better context)
        # Convert to LLM format
        chat_history = _convert_messages_to_dict(messages[-6:])
        
        task_list = _convert_tasks_to_dict(tasks)
        
        # Make decision via LLM
        decision = await _call_llm_for_decision(chat_history, task_list)
        
        return decision, tasks
        
    except Exception as e:
        logger.error(f"Error making engine decision: {e}")
        return EngineDecision(focused_task_id=None), []


def _convert_messages_to_dict(messages: Sequence[MessageLike]) -> List[Dict[str, str]]:
    """Convert message-like objects to dict format for LLM"""
    return [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]


def _convert_tasks_to_dict(tasks: List[Task]) -> List[Dict[str, Any]]:
    """Convert Task objects to minimal dict format for LLM decision"""
    return [
        {
            "id": task.id,
            "title": task.title,
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "status": task.status,
        }
        for task in tasks
    ]


def _convert_tasks_to_simple_dict(tasks: List[Task]) -> List[Dict[str, Any]]:
    """Convert Task objects to simple dict (without description) for conversation"""
    return [
        {
            "id": task.id,
            "title": task.title,
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "status": task.status,
            "created_at": task.created_at.isoformat(),
        }
        for task in tasks
    ]


async def _call_llm_for_decision(
    chat_history: List[Dict[str, str]],
    task_list: List[Dict[str, Any]]
) -> EngineDecision:
    """Call LLM to make engine decision (focused_task_id only)"""

    current_datetime = datetime.now(timezone.utc).isoformat()
    messages = [
        {"role": "system", "content": ENGINE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Current datetime (UTC): {current_datetime}\n\n"
                      f"Chat history: {json.dumps(chat_history, ensure_ascii=False)}\n\n"
                      f"Tasks: {json.dumps(task_list, ensure_ascii=False)}"
        }
    ]

    try:
        logger.info(f"Calling LLM with {len(chat_history)} messages and {len(task_list)} tasks")
        llm_service = LLMService(model="gemini-2.5-flash-lite", temperature=0.3)
        decision = await llm_service.structured_invoke(messages, EngineDecision)
        logger.info(f"Engine decision: focused_task_id={decision.focused_task_id}")
        return decision
    except Exception as e:
        logger.error(f"Error calling LLM for engine decision: {e}")
        logger.error(f"Messages sent to LLM: {messages}")
        return EngineDecision(focused_task_id=None)

