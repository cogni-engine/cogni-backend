"""Completion notification service for AI task execution"""
import logging
from datetime import datetime
from typing import List

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import supabase
from app.infra.supabase.repositories.notes import NoteRepository
from app.models.task import Task
from app.models.notification import AINotificationCreate, NotificationStatus
from .prompts.completion_notification_prompt import completion_notification_prompt_template
from .models.completion_notification_response import CompletionNotificationResponse

logger = logging.getLogger(__name__)


# LLMの初期化（structured outputを有効化）
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.7)
structured_llm = llm.with_structured_output(CompletionNotificationResponse)


async def generate_completion_notification(
    task: Task,
    result_title: str,
    result_text: str,
    due_date: datetime,
    task_result_id: int | None = None
) -> List[AINotificationCreate]:
    """
    AIタスク実行完了後の通知を生成する。
    タスクのsource_note_idからassigneeを取得し、各assigneeに通知を作成する。

    Args:
        task: 実行されたタスク
        result_title: 実行結果のタイトル
        result_text: 実行結果の詳細
        due_date: 通知の送信日時（next_run_timeまたはdeadline）
        task_result_id: (unused, kept for API compatibility)

    Returns:
        List[AINotificationCreate]: 生成された通知リスト（assigneeごと）
    """
    # assignee取得
    assignees = []
    if task.source_note_id:
        note_repo = NoteRepository(supabase)
        assignees = await note_repo.get_note_assignee_user_and_member_ids(task.source_note_id)
    if not assignees:
        logger.warning(f"No assignees found for task {task.id} (source_note_id={task.source_note_id})")
        return []

    # LangChain チェーンの構築と実行
    chain = completion_notification_prompt_template | structured_llm

    try:
        result: CompletionNotificationResponse = await chain.ainvoke({
            "task_title": task.title,
            "result_title": result_title,
            "result_text": result_text
        })

        notifications = []
        for _user_id, workspace_member_id in assignees:
            notifications.append(AINotificationCreate(
                title=result.title,
                body=result.body,
                due_date=due_date,
                task_id=task.id,
                workspace_id=task.workspace_id,
                workspace_member_id=workspace_member_id,
                status=NotificationStatus.SCHEDULED
            ))

        logger.info(f"Completion notification generated for task {task.id} ({len(notifications)} assignees)")
        return notifications

    except Exception as e:
        logger.error(f"Failed to generate completion notification for task {task.id}: {e}")
        notifications = []
        for _user_id, workspace_member_id in assignees:
            notifications.append(AINotificationCreate(
                title=f"{task.title}を終わらせました",
                body=f"{task.title}の実行が完了しました。",
                due_date=due_date,
                task_id=task.id,
                workspace_id=task.workspace_id,
                workspace_member_id=workspace_member_id,
                status=NotificationStatus.SCHEDULED
            ))
        return notifications

