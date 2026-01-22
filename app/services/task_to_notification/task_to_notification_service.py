"""Task to Notification AI service with LangChain"""
from typing import List
import logging

from langchain_openai import ChatOpenAI

from app.config import supabase
from app.infra.supabase.repositories.notifications import AINotificationRepository
from app.models.task import Task
from app.models.notification import AINotification, AINotificationCreate, NotificationStatus
from app.utils.datetime_helper import get_current_datetime_ja
from .models import NotificationListResponse
from .prompts import prompt_template, batch_prompt_template

logger = logging.getLogger(__name__)


# LLMの初期化（structured outputを有効化）
llm = ChatOpenAI(model="gpt-5-mini", temperature=0)
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
    task_progress = task.progress if task.progress is not None else 0
    
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
        "task_progress": task_progress,
    })
    
    logger.info(f"AI generated {len(result.notifications)} notifications")
    
    # 通知が生成されない場合は空リストを返す
    if not result.notifications:
        logger.info(f"No notifications generated for task {task.id}")
        return []
    
    # NotificationCreateモデルに変換
    notifications_to_create = []
    for notif in result.notifications:
        notifications_to_create.append(
            AINotificationCreate(
                title=notif.title,
                ai_context=notif.ai_context,
                body=notif.body,
                due_date=notif.due_date,
                task_id=task.id,
                user_id=task.user_id,
                workspace_member_id=task.workspace_member_id,
                status=NotificationStatus.SCHEDULED
            )
        )
    
    # AINotificationRepositoryで通知を保存（既に上で初期化済み）
    saved_notifications: List[AINotification] = []
    
    for notification_create in notifications_to_create:
        try:
            saved_notification = await notification_repo.create(notification_create)
            saved_notifications.append(saved_notification)
            logger.info(f"Notification saved successfully: {saved_notification.id} - {saved_notification.title}")
        except Exception as e:
            logger.error(f"Failed to save notification: {notification_create.title}. Error: {e}")
            # 失敗した通知はスキップして続行
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
ステータス: {task.status or "未設定"}
進捗: {task.progress if task.progress is not None else 0}%"""
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
    
    # 通知を保存（各タスクのuser_idごとに保存）
    saved_notifications: List[AINotification] = []
    
    # 各タスクのuser_idを取得（重複を除く）
    user_ids = list(set(task.user_id for task in tasks))
    
    for notif in result.notifications:
        # 各ユーザーごとに通知を保存
        for user_id in user_ids:
            # そのユーザーのタスクを取得
            user_tasks = [t for t in tasks if t.user_id == user_id]
            if not user_tasks:
                continue
            
            # 最初のタスクに紐づける
            primary_task = user_tasks[0]
        
            try:
                notification_create = AINotificationCreate(
                    title=notif.title,
                    ai_context=notif.ai_context,
                    body=notif.body,
                    due_date=notif.due_date,
                    task_id=primary_task.id,
                    user_id=user_id,
                    workspace_member_id=primary_task.workspace_member_id,
                    status=NotificationStatus.SCHEDULED
                )
                saved_notification = await notification_repo.create(notification_create)
                saved_notifications.append(saved_notification)
                logger.info(f"Notification saved: {saved_notification.id} (task {primary_task.id}, user {user_id})")
            except Exception as e:
                logger.error(f"Failed to save notification for user {user_id}: {e}")
                continue
    
    return saved_notifications
