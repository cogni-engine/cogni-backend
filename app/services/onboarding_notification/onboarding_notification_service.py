"""Onboarding Tutorial Notification Service

Generates Task (fixed), TaskResult (AI + web search), and Notification (AI) for onboarding.
"""
import logging
from typing import Tuple, List, Optional
from datetime import datetime, timezone, timedelta

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from google.ai.generativelanguage_v1beta.types import Tool as GenAITool

from app.config import supabase
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.repositories.task_results import TaskResultRepository
from app.infra.supabase.repositories.notifications import AINotificationRepository
from app.infra.supabase.repositories.notes import NoteRepository
from app.models.task import Task, TaskCreate
from app.models.task_result import TaskResult, TaskResultCreate
from app.models.notification import AINotification, AINotificationCreate, NotificationStatus, ReactionStatus
from .models import TutorialTaskResultResponse, TutorialNotificationResponse
from .prompts import task_result_prompt_template, web_search_prompt_template, notification_prompt_template

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

# Initialize LLMs
# Web search LLM (gemini-2.5-flash with Google Search grounding for quality)
search_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.5)
# Fast LLM for notifications (gemini-2.5-flash-lite for speed)
fast_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.7)



async def generate_tutorial_task_and_notification(
    onboarding_session_id: str,
    user_id: str,
    locale: str,
) -> Tuple[List[Task], List[AINotification]]:
    """
    Generate tasks, task_results, and notifications for onboarding tutorial.
    Creates entries for both Mike and Lisa agents.

    Flow:
    1. Task: Fixed content (no LLM)
    2. TaskResult: AI generated (gemini-2.5-flash with Google Search grounding)
       - Searches for user's industry/role-specific news and insights
    3. Notification: AI generated (gemini-2.5-flash-lite for speed) with reaction

    Args:
        onboarding_session_id: The onboarding session ID
        user_id: The user ID
        locale: User's locale (e.g., "ja", "en-US")

    Returns:
        Tuple of (List[Task], List[AINotification])
    """
    try:
        # 1. Get onboarding session context (includes user's domain info)
        response = supabase.table('onboarding_sessions').select('context').eq('id', onboarding_session_id).execute()

        if not response.data or len(response.data) == 0:
            raise ValueError(f"Onboarding session {onboarding_session_id} not found")

        context = response.data[0].get('context', {})

        first_note = context.get('firstNote', {})
        note_id = first_note.get('noteId')
        workspace_id = context.get('tutorialWorkspaceId')

        # Get user's domain information from context (stored during onboarding)
        # Answers are nested under 'answers' key in OnboardingContext
        answers = context.get('answers', {})
        user_role = answers.get('primaryRole', [])
        user_function = answers.get('aiRelationship', [])
        user_use_case = answers.get('useCase', [])

        # Format user domain info for search
        user_role_str = ", ".join(user_role) if user_role else ""
        user_function_str = ", ".join(user_function) if user_function else ""
        user_use_case_str = ", ".join(user_use_case) if user_use_case else ""

        logger.info(f"User domain: role={user_role_str}, function={user_function_str}, use_case={user_use_case_str}")

        # Get Mike and Lisa workspace member IDs
        mike_workspace_member_id = context.get('mikeWorkspaceMemberId')
        lisa_workspace_member_id = context.get('lisaWorkspaceMemberId')

        if not note_id:
            raise ValueError("First note ID not found in onboarding context")

        if not workspace_id:
            raise ValueError("Tutorial workspace ID not found in onboarding context")

        if not mike_workspace_member_id or not lisa_workspace_member_id:
            raise ValueError("Mike or Lisa workspace member ID not found in onboarding context")

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

        # Initialize repositories
        task_repo = TaskRepository(supabase)
        task_result_repo = TaskResultRepository(supabase)
        notification_repo = AINotificationRepository(supabase)

        tasks = []
        notifications = []

        # 3. Create single Task (fixed content, no LLM)
        next_run_time = current_datetime + timedelta(seconds=5)

        task_create = TaskCreate(
            user_id=user_id,
            title=task_content["title"],
            description=task_content["description"],
            recurrence_pattern=None,
            next_run_time=next_run_time,
            is_ai_task=True,
            status="pending",
            deadline=None,
            progress=0,
            source_note_id=note_id,
            assigner_id=None,
            workspace_member_id=mike_workspace_member_id,  # Assign to Mike
        )

        task = await task_repo.create(task_create)
        tasks.append(task)

        # 4. Generate single TaskResult (AI with Web Search for user's domain)
        # Step 4a: Web search for user's industry/role-specific information
        search_prompt = web_search_prompt_template.format(
            user_role=user_role_str or "ビジネスプロフェッショナル",
            user_function=user_function_str or "業務効率化",
            user_use_case=user_use_case_str or "タスク管理",
            note_title=note_title,
            note_content=note_content,
            language=language,
            current_datetime=current_datetime.isoformat(),
        )

        try:
            # Invoke with Google Search grounding for user's domain
            search_response = await search_llm.ainvoke(
                [HumanMessage(content=search_prompt)],
                tools=[GenAITool(google_search={})],
            )

            search_result = search_response.content

            # Extract sources from grounding metadata
            grounding_metadata = search_response.response_metadata.get('grounding_metadata', {})
            grounding_chunks = grounding_metadata.get('groundingChunks', [])

            # Format sources for the prompt (get up to 5 sources for better coverage)
            sources_text = ""
            if grounding_chunks:
                sources_list = []
                for chunk in grounding_chunks[:5]:
                    web = chunk.get('web', {})
                    uri = web.get('uri', '')
                    title = web.get('title', 'Reference')
                    if uri:
                        sources_list.append(f"- [{title}]({uri})")
                sources_text = "\n".join(sources_list) if sources_list else "参考ソースなし"
            else:
                sources_text = "参考ソースなし"

            logger.info(f"Web search for user domain completed with {len(grounding_chunks)} sources")

        except Exception as e:
            logger.warning(f"Web search failed, using fallback: {e}")
            # Fallback: provide generic but helpful content based on user's role
            if is_japanese:
                search_result = f"{user_role_str or 'ビジネスプロフェッショナル'}として、効率的な業務管理のポイントをまとめました。"
            else:
                search_result = f"As a {user_role_str or 'business professional'}, here are key points for efficient work management."
            sources_text = "参考ソースなし" if is_japanese else "No sources available"

        # Step 4b: Format the result with structured output
        task_result_structured = search_llm.with_structured_output(TutorialTaskResultResponse)
        task_result_chain = task_result_prompt_template | task_result_structured

        task_result_response: TutorialTaskResultResponse = await task_result_chain.ainvoke({
            "language": language,
            "user_role": user_role_str or "ビジネスプロフェッショナル",
            "user_function": user_function_str or "業務効率化",
            "user_use_case": user_use_case_str or "タスク管理",
            "note_title": note_title,
            "note_content": note_content,
            "search_result": search_result,
            "sources": sources_text,
            "current_date": current_datetime.strftime("%Y年%m月%d日") if is_japanese else current_datetime.strftime("%B %d, %Y"),
        })

        # Save TaskResult to DB
        task_result_create = TaskResultCreate(
            task_id=task.id,
            result_title=task_result_response.result_title,
            result_text=task_result_response.result_text,
            executed_at=current_datetime,
        )
        task_result = await task_result_repo.create(task_result_create)

        # 5. Generate single Notification content (AI - using fast model for speed)
        notification_structured = fast_llm.with_structured_output(TutorialNotificationResponse)
        notification_chain = notification_prompt_template | notification_structured

        notification_response: TutorialNotificationResponse = await notification_chain.ainvoke({
            "language": language,
            "task_title": task.title,
            "result_title": task_result_response.result_title,
            "result_text": task_result_response.result_text,
        })

        due_date = current_datetime + timedelta(seconds=5)

        # 6. Create user's notification (NO reaction - user will interact with this)
        user_notification_create = AINotificationCreate(
            title=notification_response.title,
            ai_context=notification_response.ai_context,
            body=notification_response.body,
            due_date=due_date,
            task_id=task.id,
            task_result_id=task_result.id,
            user_id=user_id,
            workspace_member_id=mike_workspace_member_id,
            status=NotificationStatus.SCHEDULED,
            reaction_status=ReactionStatus.NONE,  # Explicitly set to "None" (not NULL) for query to find it
        )
        user_notification = await notification_repo.create(user_notification_create)
        notifications.append(user_notification)  # This goes first for frontend compatibility

        # 7. Create Activity display notifications (WITH reactions - for Activity drawer)
        activity_agents = [
            {
                "name": "Mike",
                "workspace_member_id": mike_workspace_member_id,
                "reaction_text": "確認しました！" if is_japanese else "I've reviewed this!",
            },
            {
                "name": "Lisa",
                "workspace_member_id": lisa_workspace_member_id,
                "reaction_text": "私も見ました！素晴らしい内容ですね。" if is_japanese else "I've seen this too! Great content.",
            },
        ]

        for agent in activity_agents:
            activity_notification_create = AINotificationCreate(
                title=notification_response.title,
                ai_context=notification_response.ai_context,
                body=notification_response.body,
                due_date=due_date,
                task_id=task.id,
                task_result_id=task_result.id,
                user_id=user_id,
                workspace_member_id=agent["workspace_member_id"],
                status=NotificationStatus.SCHEDULED,
                reaction_status=ReactionStatus.COMPLETED,
                reaction_text=agent["reaction_text"],
            )
            activity_notification = await notification_repo.create(activity_notification_create)
            notifications.append(activity_notification)

        return (tasks, notifications)

    except Exception as e:
        logger.error(f"Error generating tutorial task and notification: {e}")
        raise
