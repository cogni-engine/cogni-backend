"""Onboarding Tutorial Notification Service

Generates Task (fixed), TaskResult (AI + web search), and Notification (AI) for onboarding.
"""
import logging
from typing import Tuple
from datetime import datetime, timezone, timedelta

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import supabase
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.repositories.task_results import TaskResultRepository
from app.infra.supabase.repositories.notifications import AINotificationRepository
from app.infra.supabase.repositories.notes import NoteRepository
from app.models.task import Task, TaskCreate
from app.models.task_result import TaskResult, TaskResultCreate
from app.models.notification import AINotification, AINotificationCreate, NotificationStatus
from .models import TutorialTaskResultResponse, TutorialNotificationResponse
from .prompts import task_result_prompt_template, notification_prompt_template

logger = logging.getLogger(__name__)

# Fixed task content (no LLM needed)
TUTORIAL_TASK_CONTENT = {
    "ja": {
        "title": "ノートの内容を調べる",
        "description": "チュートリアルノートに書かれた内容について調査し、関連情報をまとめます。"
    },
    "en": {
        "title": "Research note content",
        "description": "Research the content written in your tutorial note and compile related information."
    }
}

# Initialize LLM (lightweight model for onboarding)
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.7)



async def generate_tutorial_task_and_notification(
    onboarding_session_id: str,
    user_id: str,
    locale: str,
) -> Tuple[Task, AINotification]:
    """
    Generate a task, task_result, and notification for onboarding tutorial.

    Flow:
    1. Task: Fixed content (no LLM)
    2. TaskResult: AI generated with web search (gemini-2.5-flash-lite)
    3. Notification: AI generated (gemini-2.5-flash-lite)

    Args:
        onboarding_session_id: The onboarding session ID
        user_id: The user ID
        locale: User's locale (e.g., "ja", "en-US")

    Returns:
        Tuple of (Task, AINotification)
    """
    try:
        # 1. Get onboarding session context
        response = supabase.table('onboarding_sessions').select('context').eq('id', onboarding_session_id).execute()

        if not response.data or len(response.data) == 0:
            raise ValueError(f"Onboarding session {onboarding_session_id} not found")

        context = response.data[0].get('context', {})
        first_note = context.get('firstNote', {})
        note_id = first_note.get('noteId')
        workspace_id = context.get('tutorialWorkspaceId')
        boss_workspace_member_id = context.get('bossWorkspaceMemberId')

        if not note_id:
            raise ValueError("First note ID not found in onboarding context")

        if not workspace_id:
            raise ValueError("Tutorial workspace ID not found in onboarding context")

        # 2. Get the note content
        note_repo = NoteRepository(supabase)
        note = await note_repo.find_by_id(note_id)

        if not note:
            raise ValueError(f"Note {note_id} not found")

        note_content = note.text or ""
        note_title = note.title or "Tutorial Note"

        # Determine language
        is_japanese = locale.startswith("ja")
        language = "Japanese" if is_japanese else "English"
        task_content = TUTORIAL_TASK_CONTENT["ja" if is_japanese else "en"]

        # Current time
        current_datetime = datetime.now(timezone.utc)

        # 3. Create Task (fixed content, no LLM)
        task_repo = TaskRepository(supabase)
        next_run_time = current_datetime + timedelta(seconds=5)

        task_create = TaskCreate(
            title=task_content["title"],
            workspace_id=workspace_id,
            description=task_content["description"],
            recurrence_pattern=None,
            next_run_time=next_run_time,
            is_ai_task=True,
            status="pending",
            deadline=None,
            source_note_id=note_id,
            assigner_id=None,
        )

        task = await task_repo.create(task_create)

        # 4. Generate TaskResult (AI)
        task_result_structured = llm.with_structured_output(TutorialTaskResultResponse)
        task_result_chain = task_result_prompt_template | task_result_structured

        task_result_response: TutorialTaskResultResponse = await task_result_chain.ainvoke({
            "language": language,
            "note_title": note_title,
            "note_content": note_content,
            "current_datetime": current_datetime.isoformat(),
        })

        # Save TaskResult to DB
        task_result_repo = TaskResultRepository(supabase)
        task_result_create = TaskResultCreate(
            task_id=task.id,
            result_title=task_result_response.result_title,
            result_text=task_result_response.result_text,
            executed_at=current_datetime,
        )
        task_result = await task_result_repo.create(task_result_create)

        # 5. Generate Notification (AI)
        notification_structured = llm.with_structured_output(TutorialNotificationResponse)
        notification_chain = notification_prompt_template | notification_structured

        notification_response: TutorialNotificationResponse = await notification_chain.ainvoke({
            "language": language,
            "task_title": task.title,
            "result_title": task_result_response.result_title,
            "result_text": task_result_response.result_text,
        })

        # Save Notification to DB
        notification_repo = AINotificationRepository(supabase)
        due_date = current_datetime + timedelta(seconds=5)

        notification_create = AINotificationCreate(
            title=notification_response.title,
            body=notification_response.body,
            due_date=due_date,
            task_id=task.id,
            workspace_id=workspace_id,
            workspace_member_id=boss_workspace_member_id,
            status=NotificationStatus.SCHEDULED
        )

        notification = await notification_repo.create(notification_create)

        return (task, notification)

    except Exception as e:
        logger.error(f"Error generating tutorial task and notification: {e}")
        raise
