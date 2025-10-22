"""Task to Notification AI service with LangChain"""
from typing import List
import logging

from langchain_openai import ChatOpenAI

from app.config import supabase
from app.infra.supabase.repositories.notifications import NotificationRepository
from app.infra.supabase.repositories.tasks import TaskRepository
from app.models.task import Task
from app.models.notification import Notification, NotificationCreate, NotificationStatus
from app.utils.datetime_helper import get_current_datetime_ja
from .models import NotificationListResponse
from .prompts import prompt_template, batch_prompt_template

logger = logging.getLogger(__name__)


# LLMの初期化（structured outputを有効化）
llm = ChatOpenAI(model="gpt-4o", temperature=0)
structured_llm = llm.with_structured_output(NotificationListResponse)


async def generate_notifications_from_task(task: Task) -> List[Notification]:
    """
    特定のTaskからAIで通知を生成してデータベースに保存する
    既存の同じtask_idから生成された通知は削除される
    
    Args:
        task: タスクオブジェクト
    
    Returns:
        保存された通知のリスト
    """
    # 既存の同じtask_idから生成された通知を削除
    notification_repo = NotificationRepository(supabase)
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
    # suggestionsをcontentに統合
    notifications_to_create = []
    for notif in result.notifications:
        # suggestionsをcontentに追加
        suggestions_text = "\n\n【行動提案】\n" + "\n".join([f"• {s}" for s in notif.suggestions])
        full_content = notif.content + suggestions_text
        
        notifications_to_create.append(
            NotificationCreate(
                title=notif.title,
                content=full_content,
                due_date=notif.due_date,
                task_id=task.id,
                user_id=task.user_id,
                status=NotificationStatus.SCHEDULED
            )
        )
    
    # NotificationRepositoryで通知を保存（既に上で初期化済み）
    saved_notifications: List[Notification] = []
    
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


async def generate_notifications_from_tasks_batch(tasks: List[Task]) -> List[Notification]:
    """
    複数のTaskからAIで通知を一括生成してデータベースに保存する
    既存のスキーマ（NotificationListResponse）を使用
    
    Args:
        tasks: タスクのリスト（同じsource_note_idのタスク群）
    
    Returns:
        保存された通知のリスト
    """
    if not tasks:
        return []
    
    # 既存の通知を一括削除
    notification_repo = NotificationRepository(supabase)
    task_ids = [task.id for task in tasks]
    deleted_count = await notification_repo.delete_by_tasks(task_ids)
    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} existing notifications from {len(tasks)} tasks")
    
    logger.info(f"Generating notifications for {len(tasks)} tasks from same note")
    
    # タスク情報をフォーマット
    tasks_info = []
    for task in tasks:
        task_info = f"""
タスクID: {task.id}
タイトル: {task.title}
説明: {task.description or "説明なし"}
期限: {task.deadline.isoformat() if task.deadline else "期限なし"}
ステータス: {task.status or "未設定"}
進捗: {task.progress if task.progress is not None else 0}%
"""
        tasks_info.append(task_info.strip())
    
    combined_tasks_info = "\n\n---\n\n".join(tasks_info)
    
    # 現在の日時を取得（日本時間）
    current_datetime = get_current_datetime_ja()
    
    # AI呼び出し（1回のみ）- 既存のNotificationListResponseを使用
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
    
    # 通知を保存（最小のtask_idに紐づける）
    # 複数タスクをまとめた通知も、最小のtask_idに紐づける
    saved_notifications: List[Notification] = []
    min_task_id = min(task.id for task in tasks)
    min_task = next(t for t in tasks if t.id == min_task_id)
    
    for notif in result.notifications:
        suggestions_text = "\n\n【行動提案】\n" + "\n".join([f"• {s}" for s in notif.suggestions])
        full_content = notif.content + suggestions_text
        
        try:
            notification_create = NotificationCreate(
                title=notif.title,
                content=full_content,
                due_date=notif.due_date,
                task_id=min_task_id,  # すべて最小のtask_idに紐づける
                user_id=min_task.user_id,
                status=NotificationStatus.SCHEDULED
            )
            saved_notification = await notification_repo.create(notification_create)
            saved_notifications.append(saved_notification)
            logger.info(f"Notification saved: {saved_notification.id} (linked to task {min_task_id})")
        except Exception as e:
            logger.error(f"Failed to save notification: {e}")
            continue
    
    return saved_notifications


async def process_task_queue_for_notifications(queue_data: dict[int, int]) -> None:
    """
    キューに溜まったタスクをsource_note_id単位でグループ化してバッチ処理
    
    Args:
        queue_data: {task_id: source_note_id} の辞書
    """
    if not queue_data:
        return
    
    print(f"🔄 Processing {len(queue_data)} tasks from queue")
    
    # source_note_idでグループ化
    groups: dict[int, list[int]] = {}
    for task_id, source_note_id in queue_data.items():
        if source_note_id not in groups:
            groups[source_note_id] = []
        groups[source_note_id].append(task_id)
    
    print(f"📊 Grouped into {len(groups)} note groups")
    
    # 各グループを処理
    task_repo = TaskRepository(supabase)
    
    for source_note_id, task_ids in groups.items():
        try:
            # タスクを取得
            tasks = []
            for task_id in task_ids:
                task = await task_repo.find_by_id(task_id)
                if task:
                    tasks.append(task)
            
            if not tasks:
                print(f"⚠️ No valid tasks found for source_note_id {source_note_id}")
                continue
            
            # バッチで通知生成
            notifications = await generate_notifications_from_tasks_batch(tasks)
            print(f"✅ Generated {len(notifications)} notifications for {len(tasks)} tasks (note {source_note_id})")
        except Exception as e:
            print(f"❌ Error processing task group {source_note_id}: {e}")
