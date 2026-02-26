from fastapi import APIRouter, HTTPException
from app.config import supabase
from app.services.note_to_task import generate_tasks_from_note
from app.services.task_to_notification import generate_notifications_from_tasks_batch
from app.services.ai_task_executor import execute_ai_task
from app.services.ai_task_executor.completion_notification_service import generate_completion_notification
from app.infra.supabase.repositories.workspaces import WorkspaceRepository, WorkspaceMemberRepository
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.repositories.notifications import AINotificationRepository
from app.infra.supabase.repositories.task_results import TaskResultRepository
from app.models.task import TaskUpdate, Task
from app.models.notification import AINotificationCreate
from app.models.task_result import TaskResultCreate
from app.utils.recurrence_calculator import calculate_next_run_time
import asyncio
from typing import List, Optional, Tuple
from datetime import datetime, timezone, timedelta
import logging

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# 開発者のuser_id（本番・local両方で同じ）
DEV_USER_IDS = [
    "58e744e7-ec0f-45e1-a63a-bc6ed71e10de",
]


async def _process_notes_sync(
    minutes_ago: int,
    user_id_filter: Optional[List[str]] = None,
    exclude_user_ids: bool = False
) -> dict:
    """
    DEPRECATED: 旧ノート同期パイプライン。現在未使用。
    Memory Service（/api/memory/sync-events）に置き換え済み。
    削除予定。新規利用禁止。

    旧処理: ノート → generate_tasks_from_note → generate_notifications_from_tasks_batch
    新処理: ノート → SourceDiff → MemoryService.process_events (4ステップパイプライン)
    """
    from datetime import datetime, timedelta, timezone
    from app.infra.supabase.repositories.notes import NoteRepository
    import logging
    
    logger = logging.getLogger(__name__)
    
    filter_desc = ""
    if user_id_filter:
        if exclude_user_ids:
            filter_desc = " (excluding dev users)"
        else:
            filter_desc = " (dev users only)"
    
    logger.info(f"🔄 CRON: Starting sync-memories{filter_desc}")
    
    # 指定時間前からのデータを取得
    time_ago = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    
    note_repo = NoteRepository(supabase)
    
    # 更新されたノートのみ取得（user_idフィルタ適用）
    updated_notes = await note_repo.find_updated_since(
        time_ago, 
        user_id_filter=user_id_filter,
        exclude_user_ids=exclude_user_ids
    )
    
    logger.info(f"Found {len(updated_notes)} updated notes{filter_desc}")
    
    # セマフォで並列実行数を制限（10並列）
    semaphore = asyncio.Semaphore(10)
    
    # 統計情報
    total_tasks_generated = 0
    total_notifications_generated = 0
    
    # ノート処理関数
    async def process_note_with_limit(note):
        nonlocal total_tasks_generated, total_notifications_generated
        
        async with semaphore:
            try:
                # ワークスペース情報を取得
                workspace_repo = WorkspaceRepository(supabase)
                workspace = await workspace_repo.find_by_id(note.workspace_id)
                
                if not workspace:
                    return {"status": "error", "note_id": note.id, "reason": "workspace_not_found"}
                
                if not note.text:
                    return {"status": "skipped", "note_id": note.id, "reason": "empty_text"}
                
                # workspace typeに応じて(user_id, workspace_member_id)ペアを取得
                user_workspace_member_pairs: List[Tuple[str, Optional[int]]] = []
                
                if workspace.type == "personal":
                    # personal workspaceの場合: オーナーのuser_idとworkspace_member_idを取得
                    workspace_member_repo = WorkspaceMemberRepository(supabase)
                    members = await workspace_member_repo.find_by_workspace(note.workspace_id)
                    
                    if not members:
                        return {"status": "error", "note_id": note.id, "reason": "no_workspace_members"}
                    
                    user_workspace_member_pairs = [(members[0].user_id, members[0].id)]
                    
                elif workspace.type == "group":
                    # group workspaceの場合: assigneeの(user_id, workspace_member_id)ペアを取得
                    pairs = await note_repo.get_note_assignee_user_and_member_ids(note.id)
                    user_workspace_member_pairs = [(user_id, workspace_member_id) for user_id, workspace_member_id in pairs]
                    
                    if not user_workspace_member_pairs:
                        return {"status": "skipped", "note_id": note.id, "reason": "no_assignees"}
                
                # ノート→タスク生成（1回のLLM呼び出しで全ペア分のタスク生成）
                tasks = await generate_tasks_from_note(note.id, note.text, user_workspace_member_pairs, note.title)
                tasks_count = len(tasks)
                total_tasks_generated += tasks_count
                
                # タスクが生成されたら、即座に通知を生成
                notifications_count = 0
                if tasks:
                    notifications = await generate_notifications_from_tasks_batch(tasks)
                    notifications_count = len(notifications)
                    total_notifications_generated += notifications_count
                    
                    logger.info(f"✅ Note {note.id}: Generated {tasks_count} tasks and {notifications_count} notifications")
                else:
                    logger.info(f"✅ Note {note.id}: No tasks generated")
                
                return {
                    "status": "ok",
                    "note_id": note.id,
                    "tasks_count": tasks_count,
                    "notifications_count": notifications_count
                }
                
            except Exception as e:
                logger.error(f"❌ Error processing note {note.id}: {e}")
                return {"status": "error", "note_id": note.id, "error": str(e)}
    
    # ノートを並列処理
    results = await asyncio.gather(
        *[process_note_with_limit(note) for note in updated_notes],
        return_exceptions=True
    )
    
    # 結果集計
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "ok")
    
    logger.info(f"🎉 CRON completed: {success}/{len(updated_notes)} notes processed{filter_desc}")
    logger.info(f"📊 Generated {total_tasks_generated} tasks and ~{total_notifications_generated} notifications")
    
    return {
        "status": "ok",
        "notes_processed": success,
        "notes_total": len(updated_notes),
        "tasks_generated": total_tasks_generated,
        "notifications_generated": total_notifications_generated
    }


@router.post("/sync-memories")
async def sync_memories():
    """
    DEPRECATED: 旧本番用CRONエンドポイント。現在未使用。
    代替: /api/memory/sync-events（Memory Serviceベースの新パイプライン）
    """
    return await _process_notes_sync(
        minutes_ago=5,
        user_id_filter=DEV_USER_IDS,
        exclude_user_ids=True
    )


@router.post("/sync-memories-local")
async def sync_memories_local():
    """
    DEPRECATED: 旧ローカル開発用CRONエンドポイント。現在未使用。
    代替: /api/memory/sync-events（Memory Serviceベースの新パイプライン）
    """
    return await _process_notes_sync(
        minutes_ago=1,
        user_id_filter=DEV_USER_IDS,
        exclude_user_ids=False
    )


@router.post("/process-recurring-tasks")
async def process_recurring_tasks():
    """
    定期タスクの次回実行時刻を更新するエンドポイント（1日1回、午前0時に実行）
    
    処理内容:
    1. 昨日の午前0時〜今日の午前0時の範囲でnext_run_timeが該当するタスクを取得
    2. 各タスクのnext_run_timeを次回実行時刻に更新
    3. is_recurring_task_active=Trueのタスクについて、既存の通知を複製して次回分を作成
    """
    logger = logging.getLogger(__name__)
    logger.info("🔄 CRON: Starting process-recurring-tasks")
    
    # 昨日の午前0時と今日の午前0時を取得
    now = datetime.now(timezone.utc)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_midnight = today_midnight - timedelta(days=1)
    
    logger.info(f"Processing tasks with next_run_time between {yesterday_midnight} and {today_midnight}")
    
    # TaskRepositoryでタスクを取得
    task_repo = TaskRepository(supabase)
    notification_repo = AINotificationRepository(supabase)
    
    # next_run_timeが昨日の午前0時〜今日の午前0時の範囲にあるタスクを取得
    # recurrence_patternがNULLでないものが対象
    response = (
        supabase.table("tasks")
        .select("*")
        .gte("next_run_time", yesterday_midnight.isoformat())
        .lt("next_run_time", today_midnight.isoformat())
        .not_.is_("recurrence_pattern", "null")
        .execute()
    )
    
    recurring_tasks = response.data if response.data else []
    logger.info(f"Found {len(recurring_tasks)} recurring tasks to process")
    
    if not recurring_tasks:
        return {
            "status": "ok",
            "tasks_processed": 0,
            "notifications_created": 0
        }
    
    # セマフォで並列実行数を制限（10並列）
    semaphore = asyncio.Semaphore(10)
    
    # 統計情報
    tasks_updated = 0
    tasks_stopped = 0
    notifications_created = 0
    
    # タスク処理関数
    async def process_task_with_limit(task_data):
        nonlocal tasks_updated, tasks_stopped, notifications_created
        
        async with semaphore:
            try:
                task_id = task_data["id"]
                old_next_run_time = datetime.fromisoformat(task_data["next_run_time"].replace("Z", "+00:00"))
                recurrence_pattern = task_data["recurrence_pattern"]
                is_active = task_data.get("is_recurring_task_active", True)
                is_ai_task = task_data.get("is_ai_task", False)
                
                # is_ai_taskの場合、未解決の通知が3個以上あるかチェック
                if is_ai_task and is_active:
                    # statusが"resolved"でない通知を取得
                    response = (
                        supabase.table("ai_notifications")
                        .select("*")
                        .eq("task_id", task_id)
                        .neq("status", "resolved")
                        .execute()
                    )
                    unresolved_notifications = response.data if response.data else []
                    unresolved_count = len(unresolved_notifications)
                    
                    if unresolved_count >= 3:
                        # 未解決通知が3個以上ある場合、タスクを停止
                        update_data = TaskUpdate(is_recurring_task_active=False)
                        await task_repo.update(task_id, update_data)
                        tasks_stopped += 1
                        
                        logger.warning(
                            f"⚠️ Task {task_id}: Stopped due to {unresolved_count} unresolved notifications. "
                            f"is_recurring_task_active set to False."
                        )
                        
                        return {
                            "status": "stopped",
                            "task_id": task_id,
                            "reason": f"unresolved_notifications >= 3 ({unresolved_count})",
                            "notifications_created": 0
                        }
                
                # 新しいnext_run_timeを計算
                new_next_run_time = calculate_next_run_time(old_next_run_time, recurrence_pattern)
                
                # タスクのnext_run_timeを更新
                update_data = TaskUpdate(next_run_time=new_next_run_time)
                await task_repo.update(task_id, update_data)
                tasks_updated += 1
                
                logger.info(f"✅ Task {task_id}: Updated next_run_time from {old_next_run_time} to {new_next_run_time}")
                
                # is_recurring_task_active=Trueの場合のみ、通知を複製
                existing_notifications = []
                if is_active:
                    # 既存の通知を取得
                    existing_notifications = await notification_repo.find_by_filters({"task_id": task_id})
                    
                    if existing_notifications:
                        # 各通知を複製
                        for notification in existing_notifications:
                            # 元のdue_dateとold_next_run_timeの差分を計算
                            time_diff = notification.due_date - old_next_run_time
                            
                            # 新しいdue_dateを計算
                            new_due_date = new_next_run_time + time_diff
                            
                            # 新しい通知を作成
                            new_notification = AINotificationCreate(
                                title=notification.title,
                                body=notification.body,
                                due_date=new_due_date,
                                task_id=task_id,
                                workspace_id=notification.workspace_id,
                                workspace_member_id=notification.workspace_member_id,
                                status=notification.status
                            )
                            
                            await notification_repo.create(new_notification)
                            notifications_created += 1
                            
                            logger.info(f"📬 Task {task_id}: Created notification with due_date {new_due_date}")
                    else:
                        logger.info(f"ℹ️ Task {task_id}: No existing notifications to duplicate")
                else:
                    logger.info(f"ℹ️ Task {task_id}: is_recurring_task_active=False, skipping notification duplication")
                
                return {
                    "status": "ok",
                    "task_id": task_id,
                    "notifications_created": len(existing_notifications) if is_active else 0
                }
                
            except Exception as e:
                logger.error(f"❌ Error processing task {task_data.get('id')}: {e}")
                return {"status": "error", "task_id": task_data.get("id"), "error": str(e)}
    
    # タスクを並列処理
    results = await asyncio.gather(
        *[process_task_with_limit(task) for task in recurring_tasks],
        return_exceptions=True
    )
    
    # 結果集計
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "ok")
    
    logger.info(f"🎉 CRON completed: {success}/{len(recurring_tasks)} tasks processed")
    logger.info(f"📊 Tasks updated: {tasks_updated}, Tasks stopped: {tasks_stopped}, Notifications created: {notifications_created}")
    
    return {
        "status": "ok",
        "tasks_processed": tasks_updated,
        "tasks_stopped": tasks_stopped,
        "notifications_created": notifications_created
    }


async def _execute_ai_tasks_common(
    minutes_ahead: int,
    user_id_filter: Optional[List[str]] = None,
    exclude_user_ids: bool = False
) -> dict:
    """
    AIタスク自動実行の共通処理
    
    Args:
        minutes_ahead: 何分先までのタスクを実行するか
        user_id_filter: 指定されたuser_idのタスクのみ処理（Noneの場合は全て）
        exclude_user_ids: Trueの場合、user_id_filterに含まれるuser_idを除外
    
    Returns:
        処理結果の統計情報
    """
    logger = logging.getLogger(__name__)
    
    filter_desc = ""
    if user_id_filter:
        if exclude_user_ids:
            filter_desc = " (excluding dev users)"
        else:
            filter_desc = " (dev users only)"
    
    logger.info(f"🔄 CRON: Starting execute-ai-tasks{filter_desc}")
    
    # 現在時刻と指定分後の時刻を取得
    now = datetime.now(timezone.utc)
    target_time = now + timedelta(minutes=minutes_ahead)
    
    logger.info(f"Processing AI tasks with next_run_time between {now} and {target_time}{filter_desc}")
    
    # TaskResultRepositoryとAINotificationRepositoryを初期化
    task_result_repo = TaskResultRepository(supabase)
    notification_repo = AINotificationRepository(supabase)
    
    # 条件に合うタスクを取得
    # is_recurring_task_active=True AND is_ai_task=True AND
    # now < next_run_time <= target_time
    try:
        response = (
            supabase.table("tasks")
            .select("*")
            .eq("is_recurring_task_active", True)
            .eq("is_ai_task", True)
            .gt("next_run_time", now.isoformat())
            .lte("next_run_time", target_time.isoformat())
            .execute()
        )
        
        ai_tasks = response.data if response.data else []
        logger.info(f"Found {len(ai_tasks)} AI tasks to execute{filter_desc}")
        
    except Exception as e:
        logger.error(f"Failed to query AI tasks: {e}")
        return {
            "status": "error",
            "error": str(e),
            "tasks_executed": 0
        }
    
    # user_idフィルタリングを適用（workspace_member_note経由でassigneeのuser_idを取得）
    if user_id_filter and ai_tasks:
        from app.infra.supabase.repositories.notes import NoteRepository
        note_repo = NoteRepository(supabase)
        filtered_tasks = []
        for task in ai_tasks:
            note_id = task.get("source_note_id")
            if not note_id:
                if exclude_user_ids:
                    filtered_tasks.append(task)  # note無しはdev除外時は含める
                continue
            assignee_user_ids = await note_repo.get_note_assignee_user_ids(note_id)
            has_match = any(uid in user_id_filter for uid in assignee_user_ids)
            if exclude_user_ids and not has_match:
                filtered_tasks.append(task)
            elif not exclude_user_ids and has_match:
                filtered_tasks.append(task)
        ai_tasks = filtered_tasks
        logger.info(f"After user_id filtering: {len(ai_tasks)} AI tasks")
    
    if not ai_tasks:
        return {
            "status": "ok",
            "tasks_executed": 0,
            "results_saved": 0
        }
    
    # セマフォで並列実行数を制限（10並列）
    semaphore = asyncio.Semaphore(10)
    
    # 統計情報
    tasks_executed = 0
    results_saved = 0
    notifications_created = 0
    
    # タスク処理関数
    async def process_ai_task_with_limit(task_data):
        nonlocal tasks_executed, results_saved, notifications_created
        
        async with semaphore:
            try:
                # TaskデータをTaskモデルに変換
                task = Task(**task_data)
                
                logger.info(f"🤖 Executing AI task {task.id}: {task.title}")
                
                # AIタスクを実行（titleとtextの両方を取得）
                result_title, result_text = await execute_ai_task(task)
                tasks_executed += 1
                
                # 結果をtask_resultsに保存
                task_result_create = TaskResultCreate(
                    task_id=task.id,
                    result_title=result_title,
                    result_text=result_text,
                    executed_at=datetime.now(timezone.utc)
                )
                
                saved_result = await task_result_repo.create(task_result_create)
                results_saved += 1
                
                logger.info(f"✅ Task {task.id} executed and saved: result_id={saved_result.id}")
                
                # 完了通知を生成
                # due_dateはnext_run_timeを使用（AIタスクでは必須フィールド）
                if task.next_run_time:
                    due_date = task.next_run_time
                    
                    try:
                        notification_creates = await generate_completion_notification(
                            task=task,
                            result_title=result_title,
                            result_text=result_text,
                            due_date=due_date,
                        )

                        # 通知を保存（assigneeごと）
                        for notif_create in notification_creates:
                            saved_notification = await notification_repo.create(notif_create)
                            notifications_created += 1
                            logger.info(f"📬 Task {task.id}: Created completion notification {saved_notification.id} with due_date {due_date}")
                    except Exception as e:
                        logger.error(f"Failed to create completion notification for task {task.id}: {e}")
                else:
                    logger.warning(f"Task {task.id}: next_run_time is None, skipping notification creation")

                return {
                    "status": "ok",
                    "task_id": task.id,
                    "result_id": saved_result.id
                }
                
            except Exception as e:
                logger.error(f"❌ Error executing AI task {task_data.get('id')}: {e}")
                return {"status": "error", "task_id": task_data.get("id"), "error": str(e)}
    
    # タスクを並列処理
    results = await asyncio.gather(
        *[process_ai_task_with_limit(task) for task in ai_tasks],
        return_exceptions=True
    )
    
    # 結果集計
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "ok")
    
    logger.info(f"🎉 CRON completed: {success}/{len(ai_tasks)} AI tasks executed{filter_desc}")
    logger.info(f"📊 Tasks executed: {tasks_executed}, Results saved: {results_saved}, Notifications created: {notifications_created}")
    
    return {
        "status": "ok",
        "tasks_executed": tasks_executed,
        "results_saved": results_saved,
        "notifications_created": notifications_created
    }


@router.post("/execute-ai-tasks")
async def execute_ai_tasks():
    """
    本番用CRON実行エンドポイント（10分ごと）
    - 次の10分以内にnext_run_timeが来るタスクを実行
    - 開発者のタスクを除外
    """
    return await _execute_ai_tasks_common(
        minutes_ahead=10,
        user_id_filter=DEV_USER_IDS,
        exclude_user_ids=True
    )


@router.post("/execute-ai-tasks-local")
async def execute_ai_tasks_local():
    """
    ローカル開発用CRON実行エンドポイント（1分ごと）
    - 次の1分以内にnext_run_timeが来るタスクを実行
    - 開発者のタスクのみを処理
    """
    return await _execute_ai_tasks_common(
        minutes_ahead=1,
        user_id_filter=DEV_USER_IDS,
        exclude_user_ids=False
    )


@router.post("/execute-ai-task/{task_id}")
async def execute_ai_task_by_id(task_id: int):
    """
    特定のtask_idでAIタスクを実行するエンドポイント
    
    Args:
        task_id: 実行するタスクのID
    
    Returns:
        実行結果の統計情報
    """
    logger = logging.getLogger(__name__)
    logger.info(f"🔄 Executing AI task by ID: {task_id}")
    
    # TaskRepositoryとTaskResultRepository、AINotificationRepositoryを初期化
    task_repo = TaskRepository(supabase)
    task_result_repo = TaskResultRepository(supabase)
    notification_repo = AINotificationRepository(supabase)
    
    # タスクを取得
    task = await task_repo.find_by_id(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    # AIタスクかどうかチェック
    if not task.is_ai_task:
        raise HTTPException(
            status_code=400, 
            detail=f"Task {task_id} is not an AI task (is_ai_task=False)"
        )
    
    # アクティブかどうかチェック
    if not task.is_recurring_task_active:
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} is not active (is_recurring_task_active=False)"
        )
    
    try:
        logger.info(f"🤖 Executing AI task {task.id}: {task.title}")
        
        # AIタスクを実行
        result_title, result_text = await execute_ai_task(task)
        
        # 結果をtask_resultsに保存
        task_result_create = TaskResultCreate(
            task_id=task.id,
            result_title=result_title,
            result_text=result_text,
            executed_at=datetime.now(timezone.utc)
        )
        
        saved_result = await task_result_repo.create(task_result_create)
        logger.info(f"✅ Task {task.id} executed and saved: result_id={saved_result.id}")
        
        # 完了通知を生成
        notification_created = False
        if task.next_run_time:
            due_date = task.next_run_time
            
            try:
                notification_creates = await generate_completion_notification(
                    task=task,
                    result_title=result_title,
                    result_text=result_text,
                    due_date=due_date,
                )

                # 通知を保存（assigneeごと）
                for notif_create in notification_creates:
                    saved_notification = await notification_repo.create(notif_create)
                    notification_created = True
                    logger.info(f"📬 Task {task.id}: Created completion notification {saved_notification.id} with due_date {due_date}")
            except Exception as e:
                logger.error(f"Failed to create completion notification for task {task.id}: {e}")
        else:
            logger.warning(f"Task {task.id}: next_run_time is None, skipping notification creation")
        
        return {
            "status": "ok",
            "task_id": task.id,
            "task_title": task.title,
            "result_id": saved_result.id,
            "notification_created": notification_created
        }
        
    except Exception as e:
        logger.error(f"❌ Error executing AI task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to execute task: {str(e)}")