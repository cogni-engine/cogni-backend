"""Working memory event processing API"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Annotated, Dict, List, Literal, Optional, Tuple, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.memory import MemoryService
from app.services.memory.schemas import SourceDiff, Reaction

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


class NotificationReactionEventRequest(BaseModel):
    """通知リアクションイベント"""
    event_type: Literal["notification_reacted"]
    notification_id: int
    reaction_text: Optional[str] = None  # None = 無視された
    reacted_at: datetime


EventRequest = Annotated[
    Union[NoteEventRequest, ChatEventRequest, NotificationReactionEventRequest],
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


class BatchEventsRequest(BaseModel):
    """バッチイベント処理リクエスト"""
    events: List[EventRequest]


class WorkingMemoryUpdateRequest(BaseModel):
    """Working memory直接更新リクエスト"""
    content: str


# --- Event → SourceDiff/Reaction 変換 ---


async def _classify_events(
    events: List[EventRequest],
) -> Tuple[List[SourceDiff], List[Reaction]]:
    """APIイベント型を SourceDiff/Reaction に変換する。"""
    from app.config import supabase

    source_diffs: List[SourceDiff] = []
    reactions: List[Reaction] = []

    for event in events:
        if event.event_type == "note_updated":
            source_diffs.append(SourceDiff(
                source_type="note",
                source_id=event.note_id,
                title=event.diff.title,
                content=event.diff.text,
            ))
        elif event.event_type == "notification_reacted":
            resp = (
                supabase.table("ai_notifications")
                .select("task_id, title")
                .eq("id", event.notification_id)
                .single()
                .execute()
            )
            if resp.data:
                reactions.append(Reaction(
                    notification_id=event.notification_id,
                    task_id=resp.data["task_id"],
                    notification_title=resp.data.get("title"),
                    reaction_text=event.reaction_text,
                ))
        # chat_message → スキップ

    return source_diffs, reactions


# --- Endpoints ---


@router.get("/{workspace_id}", response_model=WorkingMemoryResponse)
async def get_working_memory(workspace_id: int):
    """Working memoryを取得する"""
    service = MemoryService()
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
    service = MemoryService()
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
    """
    service = MemoryService()

    try:
        source_diffs, reactions = await _classify_events([body])
        result = await service.process_events(workspace_id, source_diffs, reactions)
        return result
    except Exception as e:
        logger.error(f"Error processing event for workspace {workspace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/events/batch")
async def process_events_batch(workspace_id: int, body: BatchEventsRequest):
    """
    ワークスペース内の複数イベントをまとめてバッチ処理する。
    """
    service = MemoryService()

    try:
        source_diffs, reactions = await _classify_events(body.events)
        result = await service.process_events(workspace_id, source_diffs, reactions)
        return result
    except Exception as e:
        logger.error(f"Error processing batch events for workspace {workspace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-notes")
async def sync_notes():
    """Deprecated: Use /sync-events instead. Kept for backward compatibility."""
    return await sync_events()


@router.post("/sync-events")
async def sync_events():
    """
    過去10分以内のnote_versionsとnotification reactionsを取得し、
    SourceDiff/Reactionに直接変換してバッチ処理する。
    """
    from app.config import supabase as sb

    logger.info("sync-events: starting")

    now = datetime.now(timezone.utc)
    time_ago = now - timedelta(minutes=10)

    # --- Poll 1: 直近10分のnote_versions → SourceDiff ---
    versions_resp = (
        sb.table("note_versions")
        .select("note_id, version, title, text, created_at, notes:note_id(workspace_id)")
        .gte("created_at", time_ago.isoformat())
        .order("created_at", desc=True)
        .execute()
    )
    all_versions = versions_resp.data or []
    logger.info(f"sync-events: found {len(all_versions)} recent note_versions")

    # note_idごとに最新バージョンだけ残す
    seen_note_ids: set = set()
    workspace_data: Dict[int, Tuple[List[SourceDiff], List[Reaction]]] = defaultdict(
        lambda: ([], [])
    )
    note_entries: List[Dict] = []

    for v in all_versions:
        note_id = v["note_id"]
        if note_id in seen_note_ids:
            continue
        seen_note_ids.add(note_id)

        title = v.get("title")
        text = v.get("text") or ""
        workspace_id = v.get("notes", {}).get("workspace_id") if v.get("notes") else None

        if not workspace_id or (not text and not title):
            continue

        workspace_data[workspace_id][0].append(SourceDiff(
            source_type="note",
            source_id=note_id,
            title=title,
            content=text,
        ))
        note_entries.append({
            "note_id": note_id,
            "workspace_id": workspace_id,
            "content_sent": {"title": title, "text": text[:200]},
        })
        logger.info(f"sync-events: note {note_id} queued for workspace {workspace_id}")

    # --- Poll 2: 直近10分のnotification reactions → Reaction ---
    reactions_resp = (
        sb.table("ai_notifications")
        .select("id, task_id, reaction_text, reacted_at, workspace_member!inner(workspace_id)")
        .gte("reacted_at", time_ago.isoformat())
        .lte("reacted_at", now.isoformat())
        .execute()
    )
    all_reactions = reactions_resp.data or []
    logger.info(f"sync-events: found {len(all_reactions)} notification reactions")

    reaction_entries: List[Dict] = []
    for r in all_reactions:
        ws_id = r.get("workspace_member", {}).get("workspace_id") if r.get("workspace_member") else None
        if not ws_id:
            continue

        workspace_data[ws_id][1].append(Reaction(
            notification_id=r["id"],
            task_id=r["task_id"],
            notification_title=None,
            reaction_text=r.get("reaction_text"),
        ))
        reaction_entries.append({
            "notification_id": r["id"],
            "workspace_id": ws_id,
            "reaction_text": r.get("reaction_text"),
        })
        logger.info(f"sync-events: reaction on notification {r['id']} queued for workspace {ws_id}")

    # Phase 2: ワークスペースごとにバッチ処理
    service = MemoryService()
    results = []

    for ws_id, (ws_source_diffs, ws_reactions) in workspace_data.items():
        try:
            event_count = len(ws_source_diffs) + len(ws_reactions)
            logger.info(f"sync-events: processing workspace {ws_id} with {event_count} events")
            result = await service.process_events(ws_id, ws_source_diffs, ws_reactions)
            results.append({
                "workspace_id": ws_id,
                "events_count": event_count,
                **result,
            })
            logger.info(f"sync-events: workspace {ws_id} processed ({event_count} events)")
        except Exception as e:
            logger.error(f"sync-events: workspace {ws_id} error: {e}")
            results.append({"workspace_id": ws_id, "status": "error", "error": str(e)})

    return {
        "status": "ok",
        "workspaces_processed": len(results),
        "notes_queued": len(note_entries),
        "reactions_queued": len(reaction_entries),
        "summary": {
            "tasks_created": sum(r.get("tasks_created", 0) for r in results),
            "tasks_updated": sum(r.get("tasks_updated", 0) for r in results),
            "notifications_created": sum(r.get("notifications_created", 0) for r in results),
            "notifications_deleted": sum(r.get("notifications_deleted", 0) for r in results),
        },
        "workspaces": results,
        "notes": note_entries,
        "reactions": reaction_entries,
    }
