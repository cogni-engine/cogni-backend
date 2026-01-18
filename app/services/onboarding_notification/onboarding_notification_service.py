"""Onboarding Tutorial Notification Service"""
import logging
from typing import Tuple
from datetime import datetime, timezone, timedelta

from langchain_openai import ChatOpenAI

from app.config import supabase
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.repositories.notifications import AINotificationRepository
from app.infra.supabase.repositories.notes import NoteRepository
from app.models.task import Task, TaskCreate
from app.models.notification import AINotification, AINotificationCreate, NotificationStatus
from .models import TutorialTaskResponse, TutorialNotificationResponse
from .prompts import task_prompt_template, notification_prompt_template

logger = logging.getLogger(__name__)

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0.7)

async def generate_tutorial_task_and_notification(
    onboarding_session_id: str,
    user_id: str,
    locale: str,
) -> Tuple[Task, AINotification]:
    """
    Generate a task and notification from the onboarding tutorial note.
    
    Args:
        onboarding_session_id: The onboarding session ID
        user_id: The user ID
        locale: User's locale (e.g., "ja", "en-US")
        
    Returns:
        Tuple of (Task, AINotification)
    """
    try:
        print(f"[Tutorial Notification] Starting generation for session {onboarding_session_id}, user {user_id}, locale {locale}")
        
        # 1. Get onboarding session context
        response = supabase.table('onboarding_sessions').select('context').eq('id', onboarding_session_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise ValueError(f"Onboarding session {onboarding_session_id} not found")
        
        context = response.data[0].get('context', {})
        first_note = context.get('firstNote', {})
        note_id = first_note.get('noteId')
        workspace_id = context.get('tutorialWorkspaceId')
        boss_workspace_member_id = context.get('bossWorkspaceMemberId')
        
        print(f"[Tutorial Notification] Session context loaded: note_id={note_id}, workspace_id={workspace_id}, boss_member_id={boss_workspace_member_id}")
        
        if not note_id:
            raise ValueError("First note ID not found in onboarding context")
        
        if not workspace_id:
            raise ValueError("Tutorial workspace ID not found in onboarding context")
        
        # 2. Get the note content (user may have edited it)
        note_repo = NoteRepository(supabase)
        note = await note_repo.find_by_id(note_id)
        
        if not note:
            raise ValueError(f"Note {note_id} not found")
        
        note_content = note.text or ""
        note_title = note.title or "Tutorial Note"
        
        print(f"[Tutorial Notification] Note loaded: id={note_id}, title='{note_title}', content_length={len(note_content)}")
        
        # Determine target language
        language = "Japanese" if locale.startswith("ja") else "English"
        print(f"[Tutorial Notification] Target language: {language}")
        
        # 3. Generate task using AI
        task_llm = llm.with_structured_output(TutorialTaskResponse)
        task_chain = task_prompt_template | task_llm
        
        # Use current time
        current_datetime = datetime.now(timezone.utc)
        
        task_result: TutorialTaskResponse = await task_chain.ainvoke({
            "language": language,
            "note_title": note_title,
            "note_content": note_content,
            "current_datetime": current_datetime.isoformat(),
        })
        
        print(f"[Tutorial Notification] ✅ AI generated task:")
        print(f"  - Title: {task_result.title}")
        print(f"  - Description: {task_result.description[:100]}..." if len(task_result.description) > 100 else f"  - Description: {task_result.description}")
        
        # 4. Create task in database
        task_repo = TaskRepository(supabase)
        
        # Calculate next_run_time (set to now + 5 seconds for immediate notification)
        next_run_time = current_datetime + timedelta(seconds=5)
        
        task_create = TaskCreate(
            user_id=user_id,
            title=task_result.title,
            description=task_result.description,
            recurrence_pattern=None,  # One-time task for tutorial
            next_run_time=next_run_time,
            is_ai_task=True,
            status="pending",
            deadline=None,
            progress=0,
            source_note_id=note_id,
            assigner_id=None,
            workspace_member_id=boss_workspace_member_id,
        )
        
        task = await task_repo.create(task_create)
        print(f"[Tutorial Notification] ✅ Task saved to DB:")
        print(f"  - Task ID: {task.id}")
        print(f"  - User ID: {task.user_id}")
        print(f"  - Workspace Member ID: {task.workspace_member_id}")
        print(f"  - Source Note ID: {task.source_note_id}")
        
        # 5. Generate notification using AI
        notification_llm = llm.with_structured_output(TutorialNotificationResponse)
        notification_chain = notification_prompt_template | notification_llm
        
        notification_result: TutorialNotificationResponse = await notification_chain.ainvoke({
            "language": language,
            "task_title": task.title,
            "task_description": task.description or "",
            "note_content": note_content,
            "current_datetime": current_datetime.isoformat(),
        })
        
        print(f"[Tutorial Notification] ✅ AI generated notification:")
        print(f"  - Title: {notification_result.title}")
        print(f"  - Body: {notification_result.body}")
        print(f"  - AI Context: {notification_result.ai_context[:100]}..." if notification_result.ai_context and len(notification_result.ai_context) > 100 else f"  - AI Context: {notification_result.ai_context}")
        
        # 6. Create notification in database (due date = now + 5 seconds for immediate display)
        notification_repo = AINotificationRepository(supabase)
        
        # Set due_date to now + 5 seconds so it appears after redirect
        due_date = current_datetime + timedelta(seconds=5)
        
        notification_create = AINotificationCreate(
            title=notification_result.title,
            ai_context=notification_result.ai_context,
            body=notification_result.body,
            due_date=due_date,
            task_id=task.id,
            user_id=user_id,
            workspace_member_id=boss_workspace_member_id,
            status=NotificationStatus.SCHEDULED
        )
        
        notification = await notification_repo.create(notification_create)
        print(f"[Tutorial Notification] ✅ Notification saved to DB:")
        print(f"  - Notification ID: {notification.id}")
        print(f"  - Task ID: {notification.task_id}")
        print(f"  - User ID: {notification.user_id}")
        print(f"  - Due Date: {notification.due_date.isoformat()}")
        print(f"  - Status: {notification.status}")
        
        print(f"[Tutorial Notification] 🎉 SUCCESS! Task {task.id} and Notification {notification.id} created")
        
        return (task, notification)
        
    except Exception as e:
        logger.error(f"Error generating tutorial task and notification: {e}")
        raise
