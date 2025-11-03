from fastapi import APIRouter
from app.config import supabase
from app.services.note_to_task import generate_tasks_from_note
from app.services.task_to_notification import generate_notifications_from_tasks_batch
from app.infra.supabase.repositories.workspaces import WorkspaceRepository, WorkspaceMemberRepository
import asyncio

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/sync-memories")
async def sync_memories():
    """
    1分ごとのCRON実行用エンドポイント
    - 1分前から現在までに更新されたノートのみを処理
    - ノート→タスク生成→通知生成（一連の流れを完結）
    """
    from datetime import datetime, timedelta, timezone
    from app.infra.supabase.repositories.notes import NoteRepository
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info("🔄 CRON: Starting sync-memories")
    
    # 1分前からのデータを取得
    one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
    
    note_repo = NoteRepository(supabase)
    
    # 更新されたノートのみ取得（タスクは追跡しない）
    updated_notes = await note_repo.find_updated_since(one_minute_ago)
    
    logger.info(f"Found {len(updated_notes)} updated notes")
    
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
    
    logger.info(f"🎉 CRON completed: {success}/{len(updated_notes)} notes processed")
    logger.info(f"📊 Generated {total_tasks_generated} tasks and ~{total_notifications_generated} notifications")
    
    return {
        "status": "ok",
        "notes_processed": success,
        "notes_total": len(updated_notes),
        "tasks_generated": total_tasks_generated,
        "notifications_generated": total_notifications_generated
    }