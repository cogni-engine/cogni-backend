"""Task to Notification AI service with LangChain"""
from typing import List, Dict
import logging

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import supabase
from app.infra.supabase.repositories.notifications import AINotificationRepository
from app.infra.supabase.repositories.notes import NoteRepository
from app.models.task import Task
from app.models.notification import AINotification, AINotificationCreate, NotificationStatus
from app.utils.datetime_helper import get_current_datetime_ja
from .models import NotificationListResponse
from .prompts import prompt_template, batch_prompt_template

logger = logging.getLogger(__name__)


# LLMの初期化（structured outputを有効化）
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
structured_llm = llm.with_structured_output(NotificationListResponse)


async def generate_notifications_from_task(task: Task) -> List[AINotification]:
    """
    特定のTaskからAIで通知を生成してデータベースに保存する
    既存の同じtask_idから生成された通知は削除される

    Args:
        task: タスクオブジェクト

    Returns:
        保存された通知のリスト
    """
    # Skip AI tasks - they have their own completion notifications
    if task.is_ai_task:
        logger.info(f"Skipping AI task {task.id}: notifications handled by completion service")
        return []

    # 既存の同じtask_idから生成された通知を削除
    notification_repo = AINotificationRepository(supabase)
    deleted_count = await notification_repo.delete_by_task(task.id)
    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} existing notifications from task {task.id}")
    
    logger.info(f"Generating notifications for task {task.id}: {task.title}")
    
    # タスク情報を準備
    task_title = task.title
    task_description = task.description or "説明なし"
    task_deadline = task.deadline.isoformat() if task.deadline else "期限なし"
    task_status = task.status or "未設定"
    # 現在の日時を取得（日本時間）
    current_datetime = get_current_datetime_ja()
    
    # LangChain チェーンの構築と実行
    chain = prompt_template | structured_llm
    result: NotificationListResponse = await chain.ainvoke({
        "current_datetime": current_datetime,
        "task_title": task_title,
        "task_description": task_description,
        "task_deadline": task_deadline,
        "task_status": task_status,
    })
    
    logger.info(f"AI generated {len(result.notifications)} notifications")
    
    # 通知が生成されない場合は空リストを返す
    if not result.notifications:
        logger.info(f"No notifications generated for task {task.id}")
        return []
    
    # assignee取得
    assignees = []
    if task.source_note_id:
        note_repo = NoteRepository(supabase)
        assignees = await note_repo.get_note_assignee_user_and_member_ids(task.source_note_id)
    if not assignees:
        logger.warning(f"No assignees found for task {task.id}, skipping notification creation")
        return []

    # NotificationCreateモデルに変換（assigneeごとに展開）
    saved_notifications: List[AINotification] = []

    for notif in result.notifications:
        for _user_id, workspace_member_id in assignees:
            notification_create = AINotificationCreate(
                title=notif.title,
                body=notif.body,
                due_date=notif.due_date,
                task_id=task.id,
                workspace_id=task.workspace_id,
                workspace_member_id=workspace_member_id,
                status=NotificationStatus.SCHEDULED
            )
            try:
                saved_notification = await notification_repo.create(notification_create)
                saved_notifications.append(saved_notification)
                logger.info(f"Notification saved successfully: {saved_notification.id} - {saved_notification.title} (wm: {workspace_member_id})")
            except Exception as e:
                logger.error(f"Failed to save notification: {notification_create.title}. Error: {e}")
                continue

    return saved_notifications


async def generate_notifications_from_tasks_batch(tasks: List[Task]) -> List[AINotification]:
    """
    複数のTaskからAIで通知を一括生成してデータベースに保存する

    Args:
        tasks: タスクのリスト（同じsource_note_idのタスク群）

    Returns:
        保存された通知のリスト
    """
    if not tasks:
        return []

    # Filter out AI tasks - they have their own completion notifications
    human_tasks = [t for t in tasks if not t.is_ai_task]
    if not human_tasks:
        logger.info("No human tasks to generate notifications for (all tasks are AI tasks)")
        return []
    tasks = human_tasks  # Use filtered list

    # 既存の通知を一括削除
    notification_repo = AINotificationRepository(supabase)
    task_ids = [task.id for task in tasks]
    deleted_count = await notification_repo.delete_by_tasks(task_ids)
    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} existing notifications from {len(tasks)} tasks")
    
    logger.info(f"Generating notifications for {len(tasks)} tasks from same note")
    
    # タスク情報をフォーマット
    tasks_info = []
    for task in tasks:
        task_info = f"""タスクID: {task.id}
タイトル: {task.title}
説明: {task.description or "説明なし"}
期限: {task.deadline.isoformat() if task.deadline else "期限なし"}
ステータス: {task.status or "未設定"}"""
        tasks_info.append(task_info)
    
    combined_tasks_info = "\n\n---\n\n".join(tasks_info)
    
    # AI呼び出し（1回）
    current_datetime = get_current_datetime_ja()
    structured_llm_batch = llm.with_structured_output(NotificationListResponse)
    chain = batch_prompt_template | structured_llm_batch
    result: NotificationListResponse = await chain.ainvoke({
        "current_datetime": current_datetime,
        "tasks_info": combined_tasks_info
    })
    
    logger.info(f"AI generated {len(result.notifications)} notifications for {len(tasks)} tasks")
    
    if not result.notifications:
        logger.info("No notifications generated for task batch")
        return []
    
    # assigneeをタスクのsource_note_idから取得してキャッシュ
    note_repo = NoteRepository(supabase)
    assignee_cache: Dict[int, list] = {}
    for task in tasks:
        if task.source_note_id and task.source_note_id not in assignee_cache:
            assignee_cache[task.source_note_id] = await note_repo.get_note_assignee_user_and_member_ids(task.source_note_id)

    saved_notifications: List[AINotification] = []

    for notif in result.notifications:
        # 最初のタスクに紐づける
        primary_task = tasks[0]

        assignees = assignee_cache.get(primary_task.source_note_id, []) if primary_task.source_note_id else []
        if not assignees:
            logger.warning(f"No assignees for task {primary_task.id}, skipping notification")
            continue

        for _user_id, workspace_member_id in assignees:
            try:
                notification_create = AINotificationCreate(
                    title=notif.title,
                    body=notif.body,
                    due_date=notif.due_date,
                    task_id=primary_task.id,
                    workspace_id=primary_task.workspace_id,
                    workspace_member_id=workspace_member_id,
                    status=NotificationStatus.SCHEDULED
                )
                saved_notification = await notification_repo.create(notification_create)
                saved_notifications.append(saved_notification)
                logger.info(f"Notification saved: {saved_notification.id} (task {primary_task.id}, wm {workspace_member_id})")
            except Exception as e:
                logger.error(f"Failed to save notification for wm {workspace_member_id}: {e}")
                continue

    return saved_notifications
