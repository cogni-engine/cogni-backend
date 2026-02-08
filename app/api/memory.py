"""Working memory event processing API"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.memory import WorkingMemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])


# --- Event Models (discriminated union) ---


class NoteEventDiff(BaseModel):
    """ノートの差分データ"""
    title: Optional[str] = None
    text: Optional[str] = None


class NoteEventRequest(BaseModel):
    """ノート変更イベント"""
    event_type: Literal["note_updated"]
    note_id: int
    diff: NoteEventDiff


class ChatEventDiff(BaseModel):
    """チャットメッセージの差分データ"""
    content: str
    role: str = "user"


class ChatEventRequest(BaseModel):
    """チャットメッセージイベント"""
    event_type: Literal["chat_message"]
    thread_id: int
    message_id: Optional[int] = None
    diff: ChatEventDiff


EventRequest = Annotated[
    Union[NoteEventRequest, ChatEventRequest],
    Field(discriminator="event_type"),
]


# --- Response Models ---


class ProcessEventResponse(BaseModel):
    """イベント処理レスポンス"""
    status: str
    tasks_created: int = 0
    tasks_updated: int = 0
    notifications_created: int = 0
    notifications_deleted: int = 0
    memory_updated: bool = False


class WorkingMemoryResponse(BaseModel):
    """Working memory取得/更新レスポンス"""
    id: int
    workspace_id: int
    content: Optional[str] = None


class WorkingMemoryUpdateRequest(BaseModel):
    """Working memory直接更新リクエスト"""
    content: str


# --- Endpoints ---


@router.get("/{workspace_id}", response_model=WorkingMemoryResponse)
async def get_working_memory(workspace_id: int):
    """Working memoryを取得する"""
    service = WorkingMemoryService()
    memory = await service.get_memory(workspace_id)

    if memory is None:
        raise HTTPException(status_code=404, detail="Working memory not found")

    return WorkingMemoryResponse(
        id=memory.id,
        workspace_id=memory.workspace_id,
        content=memory.content,
    )


@router.put("/{workspace_id}", response_model=WorkingMemoryResponse)
async def update_working_memory(workspace_id: int, body: WorkingMemoryUpdateRequest):
    """Working memoryを直接更新(upsert)する"""
    service = WorkingMemoryService()
    memory = await service.save_memory(workspace_id, body.content)

    return WorkingMemoryResponse(
        id=memory.id,
        workspace_id=memory.workspace_id,
        content=memory.content,
    )


@router.post("/{workspace_id}/events", response_model=ProcessEventResponse)
async def process_event(workspace_id: int, body: EventRequest):
    """
    フロントエンドからイベントを受信し、working_memoryに基づいて
    タスク・通知を賢く管理する。

    フロー:
    1. resolve_tasks_from_event   — タスクの更新/追記/新規作成
    2. generate_task_notifications — 通知生成
    3. optimize_notifications      — 24h以内の通知を最適化
    4. update_working_memory       — working_memory更新
    """
    service = WorkingMemoryService()

    try:
        result = await service.process_event(
            workspace_id=workspace_id,
            event=body,
        )
        return result
    except Exception as e:
        logger.error(f"Error processing event for workspace {workspace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-notes")
async def sync_notes():
    """
    過去10分以内に更新されたノートを取得し、
    note_versions から差分を検知して、変更があったノートのみ処理する。
    user_id制限なし。
    """
    from app.config import supabase as sb
    from app.infra.supabase.repositories.notes import NoteRepository

    logger.info("sync-notes: starting")

    time_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
    note_repo = NoteRepository(sb)
    updated_notes = await note_repo.find_updated_since(time_ago)

    logger.info(f"sync-notes: found {len(updated_notes)} updated notes")

    service = WorkingMemoryService()
    results = []
    skipped = 0

    for note in updated_notes:
        try:
            # note_versions から最新2件を取得して差分検知
            versions_resp = (
                sb.table("note_versions")
                .select("version, title, text, created_at")
                .eq("note_id", note.id)
                .order("version", desc=True)
                .limit(2)
                .execute()
            )
            versions = versions_resp.data or []

            if len(versions) < 1:
                skipped += 1
                continue

            latest = versions[0]

            # 最新バージョンが sync 対象期間外ならスキップ（既に処理済み）
            latest_created = latest.get("created_at", "")
            if latest_created and latest_created < time_ago.isoformat():
                skipped += 1
                logger.info(f"sync-notes: note {note.id} latest version is old, skipped")
                continue

            if len(versions) == 1:
                # 初版 → 全文が差分
                diff_title = latest.get("title")
                diff_text = latest.get("text") or ""
            else:
                prev = versions[1]
                new_text = latest.get("text") or ""
                old_text = prev.get("text") or ""
                new_title = latest.get("title")
                old_title = prev.get("title")

                # テキストもタイトルも同じなら処理不要
                if new_text == old_text and new_title == old_title:
                    skipped += 1
                    logger.info(f"sync-notes: note {note.id} no diff, skipped")
                    continue

                # タイトル差分: 変わっていれば新しい方、同じなら None
                diff_title = new_title if new_title != old_title else None

                # テキスト差分: 追記なら追記分のみ、それ以外は全文
                if new_text.startswith(old_text) and len(new_text) > len(old_text):
                    diff_text = new_text[len(old_text):].strip()
                else:
                    diff_text = new_text

            if not diff_text and not diff_title:
                skipped += 1
                continue

            event = NoteEventRequest(
                event_type="note_updated",
                note_id=note.id,
                diff=NoteEventDiff(title=diff_title, text=diff_text),
            )
            result = await service.process_event(
                workspace_id=note.workspace_id,
                event=event,
            )
            results.append({
                "note_id": note.id,
                "workspace_id": note.workspace_id,
                "diff_sent": {"title": diff_title, "text": diff_text},
                **result,
            })
            logger.info(f"sync-notes: note {note.id} processed (diff detected)")
        except Exception as e:
            logger.error(f"sync-notes: note {note.id} error: {e}")
            results.append({"note_id": note.id, "status": "error", "error": str(e)})

    return {
        "status": "ok",
        "notes_processed": len(results),
        "notes_skipped": skipped,
        "summary": {
            "tasks_created": sum(r.get("tasks_created", 0) for r in results),
            "tasks_updated": sum(r.get("tasks_updated", 0) for r in results),
            "notifications_created": sum(r.get("notifications_created", 0) for r in results),
            "notifications_deleted": sum(r.get("notifications_deleted", 0) for r in results),
        },
        "notes": results,
    }
