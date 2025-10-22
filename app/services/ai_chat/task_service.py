"""Task Focus Service - Determines which task the user should focus on"""
import json
import logging
from typing import Optional, List, Dict, Any

from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.repositories.threads import ThreadRepository
from app.infra.supabase.repositories.workspaces import WorkspaceMemberRepository
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.repositories.ai_messages import AIMessageRepository
from app.models.task import Task
from app.models.ai_message import AIMessage
from app.services.llm.call_llm import LLMService
from .models.task_focus import FocusedTaskResponse
from .prompts.task_service import TASK_FOCUS_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def determine_focused_task(thread_id: int) -> Optional[int]:
    """
    Determine which task the user should focus on based on chat history.
    
    Args:
        thread_id: Thread ID to analyze
        
    Returns:
        Task ID to focus on, or None if no suitable task found
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
            return None
        
        # Get user from workspace members
        workspace_members = await workspace_member_repo.find_by_workspace(thread.workspace_id)
        if not workspace_members:
            return None
        user_id = workspace_members[0].user_id
        
        # Get user's tasks
        tasks = await task_repo.find_by_user(user_id)
        if not tasks:
            return None
        
        # Get recent chat history
        recent_messages = await ai_message_repo.get_recent_messages(thread_id, limit=4)
        
        # Convert to LLM format
        chat_history = _convert_messages_to_dict(recent_messages)
        task_list = _convert_tasks_to_dict(tasks)
        
        # Determine focused task via LLM
        focused_task_id = await _call_llm_for_focus(chat_history, task_list)
        
        return focused_task_id
        
    except Exception as e:
        logger.error(f"Error determining focused task: {e}")
        return None


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


async def _call_llm_for_focus(
    chat_history: List[Dict[str, str]], 
    task_list: List[Dict[str, Any]]
) -> Optional[int]:
    """Call LLM to determine which task to focus on"""
    from app.utils.datetime_helper import get_current_datetime_ja

    current_datetime = get_current_datetime_ja()
    messages = [
        {"role": "system", "content": TASK_FOCUS_SYSTEM_PROMPT},
        {
            "role": "user", 
            "content": f"現在の日時: {current_datetime}\n\n"
                      f"Chat history: {json.dumps(chat_history, ensure_ascii=False)}\n\n"
                      f"Tasks: {json.dumps(task_list, ensure_ascii=False)}"
        }
    ]

    try:
        llm_service = LLMService()
        response = await llm_service.structured_invoke(messages, FocusedTaskResponse)
        return response.focused_task_id
    except Exception as e:
        logger.error(f"Error calling LLM for focus: {e}")
        return None
