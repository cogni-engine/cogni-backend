"""Cogni Engine Service - Makes decisions about task focus and timer activation"""
import json
import logging
import re
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
from app.utils.datetime_helper import get_current_datetime_ja

logger = logging.getLogger(__name__)


class MessageLike(Protocol):
    """Protocol for any message-like object with role and content"""
    role: MessageRole
    content: str


async def make_engine_decision(current_user_id: str, messages: Sequence[MessageLike]) -> tuple[EngineDecision, List[Task]]:
    """
    Analyze chat history and tasks to make decisions:
    1. Which task to focus on
    2. Whether to start a timer
    3. Which task to complete
    
    Args:
        thread_id: Thread ID to analyze
        current_user_message: Current user message to include in analysis
        
    Returns:
        Tuple of (EngineDecision, pending_tasks_list)
    """
    supabase_client = get_supabase_client()
    
    # Initialize repositories
    task_repo = TaskRepository(supabase_client)
    
    try:
        
        # Get user's tasks (exclude completed, but include recently completed within 2 days)
        # Exclude description to reduce data size
        all_tasks = await task_repo.find_by_user(current_user_id, exclude_description=True)
        two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
        tasks = []
        for t in all_tasks:
            if t.status != "completed":
                tasks.append(t)
            elif t.completed_at:
                # Handle both timezone-aware and naive datetimes
                completed_at = t.completed_at
                if completed_at.tzinfo is None:
                    # If naive, assume UTC
                    completed_at = completed_at.replace(tzinfo=timezone.utc)
                if completed_at >= two_days_ago:
                    tasks.append(t)
        if not tasks:
            # No pending tasks, but still check for timer
            tasks = []
            logger.info(f"No pending tasks found for user {current_user_id} (total: {len(all_tasks)})")
        else:
            logger.info(f"Found {len(tasks)} pending tasks for user {current_user_id} (excluded {len(all_tasks) - len(tasks)} completed)")
        
        # Get recent chat history (last 6 messages for better context)
        # Convert to LLM format
        chat_history = _convert_messages_to_dict(messages[-6:])
        
        task_list = _convert_tasks_to_dict(tasks)
        
        # Make decision via LLM
        decision = await _call_llm_for_decision(chat_history, task_list)
        
        return decision, tasks
        
    except Exception as e:
        logger.error(f"Error making engine decision: {e}")
        return EngineDecision(focused_task_id=None, should_start_timer=False, task_to_complete_id=None), []


def _convert_messages_to_dict(messages: Sequence[MessageLike]) -> List[Dict[str, str]]:
    """Convert message-like objects to dict format for LLM"""
    return [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]


def _convert_tasks_to_dict(tasks: List[Task]) -> List[Dict[str, Any]]:
    """Convert Task objects to dict format for LLM"""
    task_list = [
        {
            "id": task.id,
            "title": task.title,
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "status": task.status,
            "progress": task.progress,
            "source_note_id": task.source_note_id,
            "created_at": task.created_at.isoformat(),
        }
        for task in tasks
    ]
    
    # Sort by source_note_id and id
    task_list.sort(key=lambda x: (x["source_note_id"] or 0, x["id"]))
    return task_list


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
    """Call LLM to make engine decision (focus + timer)"""

    current_datetime = get_current_datetime_ja()
    messages = [
        {"role": "system", "content": ENGINE_SYSTEM_PROMPT},
        {
            "role": "user", 
            "content": f"現在の日時: {current_datetime}\n\n"
                      f"Chat history: {json.dumps(chat_history, ensure_ascii=False)}\n\n"
                      f"Tasks: {json.dumps(task_list, ensure_ascii=False)}"
        }
    ]

    try:
        logger.info(f"Calling LLM with {len(chat_history)} messages and {len(task_list)} tasks")
        llm_service = LLMService(model="gpt-5-mini")
        decision = await llm_service.structured_invoke(messages, EngineDecision)
        logger.info(f"Engine decision: focused_task_id={decision.focused_task_id}, should_start_timer={decision.should_start_timer}")
        return decision
    except Exception as e:
        logger.error(f"Error calling LLM for engine decision: {e}")
        logger.error(f"Messages sent to LLM: {messages}")
        return EngineDecision(focused_task_id=None, should_start_timer=False, task_to_complete_id=None)


def extract_timer_duration(message: str) -> Optional[int]:
    """
    Extract timer duration from user message.
    
    Args:
        message: User message to extract duration from
        
    Returns:
        Duration in seconds (int), or None if no time pattern found
        
    Examples:
        "30分集中します" -> 1800 (秒)
        "1時間作業する" -> 3600 (秒)
        "30秒テスト" -> 30 (秒)
        "30" -> 1800 (秒、分として扱う)
        "1:30:45" -> 5445 (秒、時間:分:秒形式)
        "1:30" -> 5400 (秒、時間:分形式)
    """
    # 時間:分:秒形式 (例: "1:30:45" = 1時間30分45秒)
    time_pattern = r'(\d+):(\d+):(\d+)'
    time_match = re.search(time_pattern, message)
    if time_match:
        hours, minutes, seconds = map(int, time_match.groups())
        return hours * 3600 + minutes * 60 + seconds
    
    # 時間:分形式 (例: "1:30" = 1時間30分)
    hour_min_pattern = r'(\d+):(\d+)'
    hour_min_match = re.search(hour_min_pattern, message)
    if hour_min_match:
        hours, minutes = map(int, hour_min_match.groups())
        return hours * 3600 + minutes * 60
    
    # 正規表現で時間を検出: 数字 + (秒|分|時間|sec|min|hour) または 数字のみ
    time_match = re.search(r'(\d+)\s*(秒|分|時間|sec|min|hour)', message, re.IGNORECASE)
    
    if time_match:
        value = int(time_match.group(1))
        unit = time_match.group(2).lower()
        
        # 単位に応じて秒単位で返す
        if unit in ['時間', 'hour']:
            return value * 3600  # 秒単位
        elif unit in ['秒', 'sec']:
            return value  # 秒単位
        else:  # 分|min
            return value * 60  # 秒単位
    
    # 数字のみの場合（分として扱う）
    number_match = re.search(r'^(\d+)$', message.strip())
    if number_match:
        return int(number_match.group(1)) * 60  # 分を秒に変換
    
    return None

