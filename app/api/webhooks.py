from fastapi import APIRouter
from app.config import supabase
from app.services.note_to_task import generate_tasks_from_note
from app.services.task_to_notification import generate_notifications_from_tasks_batch
from app.infra.supabase.repositories.workspaces import WorkspaceRepository, WorkspaceMemberRepository
import asyncio
from typing import List, Optional

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
    ノート同期の共通処理
    
    Args:
        minutes_ago: 何分前から更新されたノートを取得するか
        user_id_filter: 指定されたuser_idのworkspaceのノートのみ処理（Noneの場合は全て）
        exclude_user_ids: Trueの場合、user_id_filterに含まれるuser_idを除外
    
    Returns:
        処理結果の統計情報
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
                
                # workspace typeに応じてuser_idsを取得
                user_ids = []
                
                if workspace.type == "personal":
                    # personal workspaceの場合: オーナーのuser_idを取得
                    workspace_member_repo = WorkspaceMemberRepository(supabase)
                    members = await workspace_member_repo.find_by_workspace(note.workspace_id)
                    
                    if not members:
                        return {"status": "error", "note_id": note.id, "reason": "no_workspace_members"}
                    
                    user_ids = [members[0].user_id]
                    
                elif workspace.type == "group":
                    # group workspaceの場合: assigneeのuser_idsを取得
                    user_ids = await note_repo.get_note_assignee_user_ids(note.id)
                    
                    if not user_ids:
                        return {"status": "skipped", "note_id": note.id, "reason": "no_assignees"}
                
                # ノート→タスク生成（1回のLLM呼び出しで全user_ids分のタスク生成）
                tasks = await generate_tasks_from_note(note.id, note.text, user_ids)
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
    本番用CRON実行エンドポイント（5分ごと）
    - 5分前から現在までに更新されたノートのみを処理
    - 開発者のworkspaceを除外
    - ノート→タスク生成→通知生成（一連の流れを完結）
    """
    return await _process_notes_sync(
        minutes_ago=5,
        user_id_filter=DEV_USER_IDS,
        exclude_user_ids=True
    )


@router.post("/sync-memories-local")
async def sync_memories_local():
    """
    ローカル開発用CRON実行エンドポイント（1分ごと）
    - 1分前から現在までに更新されたノートのみを処理
    - 開発者のworkspaceのみを処理
    - ノート→タスク生成→通知生成（一連の流れを完結）
    """
    return await _process_notes_sync(
        minutes_ago=1,
        user_id_filter=DEV_USER_IDS,
        exclude_user_ids=False
    )