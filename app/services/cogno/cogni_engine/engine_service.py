"""Cogni Engine Service - Makes decisions about task focus and timer activation"""
import json
import logging
import re
from typing import Optional, List, Dict, Any, Union

from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.repositories.threads import ThreadRepository
from app.infra.supabase.repositories.workspaces import WorkspaceMemberRepository
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.repositories.ai_messages import AIMessageRepository
from app.models.task import Task
from app.models.ai_message import AIMessage
from app.services.llm.call_llm import LLMService
from .models.engine_decision import EngineDecision
from .prompts.engine_prompt import ENGINE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def make_engine_decision(thread_id: int, current_user_message: str) -> EngineDecision:
    """
    Analyze chat history and tasks to make decisions:
    1. Which task to focus on
    2. Whether to start a timer
    
    Args:
        thread_id: Thread ID to analyze
        current_user_message: Current user message to include in analysis
        
    Returns:
        EngineDecision with focused_task_id and should_start_timer
    """
    supabase_client = get_supabase_client()
    
    # Initialize repositories
    thread_repo = ThreadRepository(supabase_client)
    workspace_member_repo = WorkspaceMemberRepository(supabase_client)
    task_repo = TaskRepository(supabase_client)
    ai_message_repo = AIMessageRepository(supabase_client)
    
    try:
        # Get thread and workspace info
        thread = await thread_repo.find_by_id(thread_id)
        if not thread or not thread.workspace_id:
            logger.warning(f"Thread {thread_id} not found or has no workspace_id")
            return EngineDecision(focused_task_id=None, should_start_timer=False)
        
        # Get user from workspace members
        workspace_members = await workspace_member_repo.find_by_workspace(thread.workspace_id)
        if not workspace_members:
            logger.warning(f"No workspace members found for workspace {thread.workspace_id}")
            return EngineDecision(focused_task_id=None, should_start_timer=False)
        user_id = workspace_members[0].user_id
        logger.info(f"Found user_id: {user_id} for thread {thread_id}")
        
        # Get user's tasks
        tasks = await task_repo.find_by_user(user_id)
        if not tasks:
            # No tasks, but still check for timer
            tasks = []
            logger.info(f"No tasks found for user {user_id}")
        else:
            logger.info(f"Found {len(tasks)} tasks for user {user_id}")
        
        # Get recent chat history (last 6 messages for better context)
        recent_messages = await ai_message_repo.get_recent_messages(thread_id, limit=6)
        logger.info(f"Found {len(recent_messages)} recent messages for thread {thread_id}")
        
        # Convert to LLM format
        chat_history = _convert_messages_to_dict(recent_messages)
        
        # Add current user message to chat history
        chat_history.append({"role": "user", "content": current_user_message})
        
        task_list = _convert_tasks_to_dict(tasks)
        
        # Make decision via LLM
        decision = await _call_llm_for_decision(chat_history, task_list)
        
        return decision
        
    except Exception as e:
        logger.error(f"Error making engine decision: {e}")
        return EngineDecision(focused_task_id=None, should_start_timer=False)


def _convert_messages_to_dict(messages: List[AIMessage]) -> List[Dict[str, str]]:
    """Convert AIMessage objects to dict format for LLM"""
    return [
        {"role": msg.role.value, "content": msg.content}
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


async def _call_llm_for_decision(
    chat_history: List[Dict[str, str]], 
    task_list: List[Dict[str, Any]]
) -> EngineDecision:
    """Call LLM to make engine decision (focus + timer)"""
    from app.utils.datetime_helper import get_current_datetime_ja

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
        llm_service = LLMService()
        decision = await llm_service.structured_invoke(messages, EngineDecision)
        logger.info(f"Engine decision: focused_task_id={decision.focused_task_id}, should_start_timer={decision.should_start_timer}")
        return decision
    except Exception as e:
        logger.error(f"Error calling LLM for engine decision: {e}")
        logger.error(f"Messages sent to LLM: {messages}")
        return EngineDecision(focused_task_id=None, should_start_timer=False)


def extract_timer_duration(message: str) -> Optional[Union[int, float]]:
    """
    Extract timer duration from user message.
    
    Args:
        message: User message to extract duration from
        
    Returns:
        Duration in minutes (int) or seconds (float), or None if no time pattern found
        
    Examples:
        "30分集中します" -> 30 (分)
        "1時間作業する" -> 60 (分)
        "30秒テスト" -> 30.0 (秒)
        "30" -> 30 (分として扱う)
    """
    # 正規表現で時間を検出: 数字 + (秒|分|時間|sec|min|hour) または 数字のみ
    time_match = re.search(r'(\d+)\s*(秒|分|時間|sec|min|hour)', message, re.IGNORECASE)
    
    if time_match:
        value = int(time_match.group(1))
        unit = time_match.group(2).lower()
        
        # 単位に応じて返す
        if unit in ['時間', 'hour']:
            return value * 60  # 分単位
        elif unit in ['秒', 'sec']:
            return float(value)  # 秒単位
        else:  # 分|min
            return value  # 分単位
    
    # 数字のみの場合（分として扱う）
    number_match = re.search(r'^(\d+)$', message.strip())
    if number_match:
        return int(number_match.group(1))  # 分単位
    
    return None

