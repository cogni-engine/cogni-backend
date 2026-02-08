"""Working memory event processing service

イベント駆動型でタスク・通知を管理するサービス。
フロントエンドからの型付きイベントを受け取り、
LLM（Gemini）を使って working_memory の内容を基にタスク・通知を賢く管理する。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Union, TYPE_CHECKING

from app.config import supabase
from app.infra.supabase.repositories.working_memory import WorkingMemoryRepository
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.repositories.notifications import AINotificationRepository
from app.infra.supabase.repositories.workspaces import WorkspaceMemberRepository
from app.models.working_memory import WorkingMemory
from app.models.task import Task, TaskCreate, TaskUpdate
from app.models.notification import AINotification, AINotificationCreate, AINotificationUpdate
from app.utils.datetime_helper import get_current_datetime_ja

from .llm import (
    task_resolve_chain,
    task_notification_chain,
    notification_optimize_chain,
    memory_summary_chain,
)

if TYPE_CHECKING:
    from app.api.memory import NoteEventRequest, ChatEventRequest

logger = logging.getLogger(__name__)

# 型エイリアス
Event = Union["NoteEventRequest", "ChatEventRequest"]


class WorkingMemoryService:
    """Working memory を軸にしたイベント駆動型タスク・通知管理サービス"""

    def __init__(self):
        self._memory_repo = WorkingMemoryRepository(supabase)
        self._task_repo = TaskRepository(supabase)
        self._notification_repo = AINotificationRepository(supabase)
        self._workspace_member_repo = WorkspaceMemberRepository(supabase)

    # ------------------------------------------------------------------
    # メインエントリポイント
    # ------------------------------------------------------------------

    async def process_event(
        self,
        workspace_id: int,
        event: Event,
    ) -> Dict[str, Any]:
        """イベント処理のオーケストレーター。

        フロー:
        1. resolve_tasks_from_event    — タスクの更新/新規作成（LLM 1回）
        2. generate_task_notifications — 変更タスクに通知生成（LLM）
        3. optimize_notifications      — 配信予定通知を選別（LLM）
        4. update_working_memory       — working_memory更新（LLM）
        """
        total_start = time.time()
        logger.info(
            "=" * 60 + "\n"
            f"[ORCHESTRATOR] START process_event\n"
            f"  workspace_id={workspace_id}\n"
            f"  event_type={event.event_type}"
        )

        # ---- 共通データの一括取得（DB読み込み3回） ----
        db_start = time.time()
        working_memory = await self.get_memory(workspace_id)
        logger.info(
            f"[ORCHESTRATOR] DB[1/3] working_memory loaded: "
            f"exists={working_memory is not None}, "
            f"content_len={len(working_memory.content) if working_memory and working_memory.content else 0}"
        )

        members = await self._workspace_member_repo.find_by_workspace(workspace_id)
        logger.info(
            f"[ORCHESTRATOR] DB[2/3] members loaded: count={len(members)}, "
            f"user_ids={[m.user_id for m in members]}"
        )

        # 24h以内のscheduled通知を一括取得
        existing_notifications: List[AINotification] = []
        if members:
            now = datetime.now(timezone.utc)
            window_end = now + timedelta(hours=24)
            response = (
                supabase.table("ai_notifications")
                .select("*")
                .eq("user_id", members[0].user_id)
                .eq("status", "scheduled")
                .gte("due_date", now.isoformat())
                .lte("due_date", window_end.isoformat())
                .execute()
            )
            if response.data:
                for row in response.data:
                    existing_notifications.append(AINotification(**row))
        logger.info(
            f"[ORCHESTRATOR] DB[3/3] existing_notifications loaded: "
            f"count={len(existing_notifications)}, "
            f"ids={[n.id for n in existing_notifications]}"
        )
        logger.info(f"[ORCHESTRATOR] DB bulk load done in {time.time() - db_start:.2f}s")

        # --- Step 1: タスク解決 ---
        step1_start = time.time()
        logger.info("-" * 40 + " STEP 1: _resolve_tasks_from_event " + "-" * 40)
        task_result = await self._resolve_tasks_from_event(
            workspace_id=workspace_id,
            event=event,
            working_memory=working_memory,
            members=members,
        )
        logger.info(
            f"[STEP 1 RESULT] {time.time() - step1_start:.2f}s | "
            f"created={task_result['tasks_created']}, updated={task_result['tasks_updated']}, "
            f"affected_tasks={[t.id for t in task_result['affected_tasks']]}"
        )

        # --- Step 2: タスク通知生成 ---
        step2_start = time.time()
        logger.info("-" * 40 + " STEP 2: _generate_task_notifications " + "-" * 40)
        notification_result = await self._generate_task_notifications(
            affected_tasks=task_result["affected_tasks"],
            working_memory=working_memory,
        )
        created_notifications = notification_result.get("created_notifications", [])
        logger.info(
            f"[STEP 2 RESULT] {time.time() - step2_start:.2f}s | "
            f"notifications_created={notification_result['notifications_created']}, "
            f"ids={[n.id for n in created_notifications]}"
        )

        # --- Step 3: 通知最適化 ---
        step3_start = time.time()
        logger.info("-" * 40 + " STEP 3: _optimize_notifications " + "-" * 40)
        optimize_result = await self._optimize_notifications(
            working_memory=working_memory,
            existing_notifications=existing_notifications,
            created_notifications=created_notifications,
        )
        final_notifications = optimize_result.get("final_notifications", [])
        logger.info(
            f"[STEP 3 RESULT] {time.time() - step3_start:.2f}s | "
            f"deleted={optimize_result['notifications_deleted']}, "
            f"updated={optimize_result.get('notifications_updated', 0)}, "
            f"final_count={len(final_notifications)}, "
            f"final_ids={[n.id for n in final_notifications]}"
        )

        # --- Step 4: working_memory 更新 ---
        step4_start = time.time()
        logger.info("-" * 40 + " STEP 4: _update_working_memory " + "-" * 40)
        memory_result = await self._update_working_memory(
            workspace_id=workspace_id,
            event=event,
            working_memory=working_memory,
            processing_result={
                "task_result": task_result,
                "notification_result": notification_result,
                "optimize_result": optimize_result,
            },
            final_notifications=final_notifications,
        )
        logger.info(
            f"[STEP 4 RESULT] {time.time() - step4_start:.2f}s | "
            f"content_len={len(memory_result.get('content', ''))}"
        )

        logger.info(
            "=" * 60 + "\n"
            f"[ORCHESTRATOR] DONE process_event in {time.time() - total_start:.2f}s\n"
            f"  tasks: created={task_result['tasks_created']}, updated={task_result['tasks_updated']}\n"
            f"  notifications: created={notification_result['notifications_created']}, "
            f"deleted={optimize_result['notifications_deleted']}, "
            f"updated={optimize_result.get('notifications_updated', 0)}\n"
            f"  final_notifications={len(final_notifications)}\n"
            f"  memory_updated={memory_result.get('updated', False)}"
        )

        return {
            "status": "ok",
            "tasks_created": task_result["tasks_created"],
            "tasks_updated": task_result["tasks_updated"],
            "notifications_created": notification_result["notifications_created"],
            "notifications_deleted": optimize_result["notifications_deleted"],
            "notifications_updated": optimize_result.get("notifications_updated", 0),
            "memory_updated": memory_result.get("updated", False),
            # 詳細情報
            "task_details": task_result.get("details", []),
            "notifications_created_details": notification_result.get("details", []),
            "notifications_deleted_details": optimize_result.get("deleted_details", []),
            "notifications_updated_details": optimize_result.get("updated_details", []),
            "working_memory_content": memory_result.get("content"),
        }

    # ------------------------------------------------------------------
    # Step 1: タスク解決（workspace単位・task_resolve_chain 1回）
    # ------------------------------------------------------------------

    async def _resolve_tasks_from_event(
        self,
        workspace_id: int,
        event: Event,
        working_memory: Optional[WorkingMemory],
        members: List,
    ) -> Dict[str, Any]:
        """event + working_memory を見て、LLMで既存タスクを更新 or 新規作成する。

        task_resolve_chain に全情報を渡し、updates / creates を1回のLLM callで解決する。
        """
        if event.event_type != "note_updated":
            logger.info(f"[Step1] SKIP: unsupported event_type={event.event_type}")
            return {"tasks_created": 0, "tasks_updated": 0, "affected_tasks": [], "details": []}

        if not members:
            logger.warning(f"[Step1] No workspace members for workspace {workspace_id}, SKIP")
            return {"tasks_created": 0, "tasks_updated": 0, "affected_tasks": [], "details": []}

        note_id = event.note_id
        diff = event.diff
        current_datetime = get_current_datetime_ja()
        wm_content = working_memory.content if working_memory and working_memory.content else "None"

        # ノート情報をフォーマット（バッチ対応: 現在は1件）
        notes_info = (
            f"NoteID: {note_id}\n"
            f"Title: {diff.title or 'None'}\n"
            f"Text: {diff.text or ''}"
        )

        # このノートに紐づく既存タスクを検索
        existing_tasks = await self._task_repo.find_by_note(note_id)

        if existing_tasks:
            tasks_info = "\n\n---\n\n".join([
                f"TaskID: {t.id}\nSourceNoteID: {t.source_note_id}\n"
                f"Title: {t.title}\nDescription: {t.description or ''}"
                for t in existing_tasks
            ])
            orphan_note_ids = "None"
        else:
            tasks_info = "None"
            orphan_note_ids = str(note_id)

        logger.info(
            f"[Step1] Input:\n"
            f"  note_id={note_id}\n"
            f"  diff.title={diff.title!r}\n"
            f"  diff.text={diff.text!r}\n"
            f"  existing_tasks={len(existing_tasks)} (ids={[t.id for t in existing_tasks]})\n"
            f"  orphan_note_ids={orphan_note_ids}\n"
            f"  current_datetime={current_datetime}\n"
            f"  working_memory_content_len={len(wm_content)}"
        )

        # --- LLM 1回: task_resolve_chain ---
        logger.info(
            f"[Step1] LLM CALL: task_resolve_chain\n"
            f"  note_count=1, task_count={len(existing_tasks)}"
        )
        llm_start = time.time()
        result = await task_resolve_chain.ainvoke({
            "current_datetime": current_datetime,
            "working_memory_content": wm_content,
            "note_count": 1,
            "notes_info": notes_info,
            "task_count": len(existing_tasks),
            "tasks_info": tasks_info,
            "orphan_note_ids": orphan_note_ids,
        })
        logger.info(
            f"[Step1] LLM RESPONSE ({time.time() - llm_start:.2f}s):\n"
            f"  ai_context={result.ai_context!r}\n"
            f"  updates={len(result.updates)}, creates={len(result.creates)}"
        )

        affected_tasks: List[Task] = []
        details: List[Dict[str, Any]] = []
        tasks_created = 0
        tasks_updated = 0

        # --- 既存タスク更新 ---
        valid_task_ids = {t.id for t in existing_tasks}
        for i, item in enumerate(result.updates):
            logger.info(
                f"[Step1] UPDATE[{i}]: task_id={item.task_id}, "
                f"title={item.title!r}, description_len={len(item.description)}"
            )
            if item.task_id not in valid_task_ids:
                logger.warning(f"[Step1] INVALID task_id={item.task_id} from LLM, skipping")
                continue

            update_data = TaskUpdate(description=item.description)
            if item.title:
                update_data.title = item.title

            updated = await self._task_repo.update(item.task_id, update_data)
            if updated:
                affected_tasks.append(updated)
                tasks_updated += 1
                details.append({
                    "action": "updated",
                    "task_id": item.task_id,
                    "title": updated.title,
                    "description_after": item.description,
                })
                logger.info(f"[Step1] DB UPDATE task {item.task_id} OK")

        # --- 新規タスク作成 ---
        member = members[0]
        for i, item in enumerate(result.creates):
            logger.info(
                f"[Step1] CREATE[{i}]: note_id={item.note_id}, "
                f"title={item.title!r}, description_len={len(item.description)}"
            )

            create_data = TaskCreate(
                title=item.title,
                description=item.description,
                source_note_id=item.note_id,
                user_id=member.user_id,
                workspace_member_id=member.id,
                status="pending",
            )
            created = await self._task_repo.create(create_data)
            affected_tasks.append(created)
            tasks_created += 1
            details.append({
                "action": "created",
                "task_id": created.id,
                "title": item.title,
                "description": item.description,
            })
            logger.info(f"[Step1] DB CREATE task {created.id} OK")

        return {
            "tasks_created": tasks_created,
            "tasks_updated": tasks_updated,
            "affected_tasks": affected_tasks,
            "details": details,
        }

    # ------------------------------------------------------------------
    # Step 2: タスク通知生成
    # ------------------------------------------------------------------

    async def _generate_task_notifications(
        self,
        affected_tasks: List[Task],
        working_memory: Optional[WorkingMemory] = None,
    ) -> Dict[str, Any]:
        """全affected_tasksをまとめてLLMに渡し、1回のcallで全通知を生成する。"""
        if not affected_tasks:
            logger.info("[Step2] SKIP: no affected_tasks")
            return {"notifications_created": 0, "details": [], "created_notifications": []}

        current_datetime = get_current_datetime_ja()
        wm_content = working_memory.content if working_memory and working_memory.content else "None"

        # 全タスクをまとめてフォーマット
        tasks_info = "\n\n---\n\n".join([
            f"TaskID: {t.id}\nTitle: {t.title}\n"
            f"Description: {(t.description or '')[:200]}\n"
            f"Deadline: {t.deadline.isoformat() if t.deadline else 'None'}\n"
            f"Status: {t.status or 'pending'}\nProgress: {t.progress or 0}%"
            for t in affected_tasks
        ])

        logger.info(
            f"[Step2] Input:\n"
            f"  affected_tasks={[t.id for t in affected_tasks]}\n"
            f"  tasks_info_len={len(tasks_info)}\n"
            f"  working_memory_content_len={len(wm_content)}"
        )
        logger.info(f"[Step2] LLM CALL: task_notification_chain ({len(affected_tasks)} tasks)")

        llm_start = time.time()
        result = await task_notification_chain.ainvoke({
            "current_datetime": current_datetime,
            "working_memory_content": wm_content,
            "tasks_info": tasks_info,
            "task_count": len(affected_tasks),
        })
        logger.info(
            f"[Step2] LLM RESPONSE ({time.time() - llm_start:.2f}s): "
            f"{len(result.notifications)} notifications generated"
        )
        for i, notif in enumerate(result.notifications):
            logger.info(
                f"[Step2] LLM notif[{i}]: task_id={notif.task_id}, "
                f"title={notif.title!r}, body={notif.body!r}, "
                f"due_date={notif.due_date.isoformat()}, "
                f"ai_context={notif.ai_context!r}"
            )

        # 生成された通知をDBに保存 & メモリ上でも保持
        created_notifications: List[AINotification] = []
        details: List[Dict[str, Any]] = []
        valid_task_ids = {t.id for t in affected_tasks}

        for notif in result.notifications:
            # task_idの検証 — フォールバック
            task_id = notif.task_id if notif.task_id in valid_task_ids else affected_tasks[0].id
            if notif.task_id not in valid_task_ids:
                logger.warning(
                    f"[Step2] FALLBACK: LLM task_id={notif.task_id} invalid, "
                    f"using {affected_tasks[0].id}"
                )
            task = next(t for t in affected_tasks if t.id == task_id)

            saved = await self._notification_repo.create(
                AINotificationCreate(
                    title=notif.title,
                    ai_context=notif.ai_context,
                    body=notif.body,
                    due_date=notif.due_date,
                    task_id=task_id,
                    user_id=task.user_id,
                    workspace_member_id=task.workspace_member_id,
                )
            )
            created_notifications.append(saved)
            details.append({
                "notification_id": saved.id,
                "task_id": task_id,
                "title": saved.title,
                "body": saved.body,
                "due_date": notif.due_date.isoformat(),
            })
            logger.info(
                f"[Step2] DB CREATE notification {saved.id}: "
                f"task_id={task_id}, title={saved.title!r}, due={notif.due_date.isoformat()}"
            )

        return {
            "notifications_created": len(created_notifications),
            "details": details,
            "created_notifications": created_notifications,
        }

    # ------------------------------------------------------------------
    # Step 3: 通知最適化
    # ------------------------------------------------------------------

    async def _optimize_notifications(
        self,
        working_memory: Optional[WorkingMemory],
        existing_notifications: List[AINotification],
        created_notifications: List[AINotification],
    ) -> Dict[str, Any]:
        """配信予定の通知リスト + working_memory → LLMが削除・統合・更新を判断する。"""
        # メモリ上で通知リストを結合（DB読み込みなし）
        all_notifications = existing_notifications + created_notifications

        logger.info(
            f"[Step3] Input:\n"
            f"  existing_notifications={len(existing_notifications)} (ids={[n.id for n in existing_notifications]})\n"
            f"  created_notifications={len(created_notifications)} (ids={[n.id for n in created_notifications]})\n"
            f"  total={len(all_notifications)}"
        )

        if not all_notifications:
            logger.info("[Step3] SKIP: no notifications to optimize")
            return {
                "notifications_deleted": 0, "notifications_updated": 0,
                "deleted_details": [], "updated_details": [],
                "final_notifications": [],
            }

        current_datetime = get_current_datetime_ja()
        wm_content = working_memory.content if working_memory and working_memory.content else "None"

        # 通知リストをフォーマット
        notifications_info = "\n\n".join([
            f"NotificationID: {n.id}\n"
            f"TaskID: {n.task_id}\n"
            f"Title: {n.title}\n"
            f"Body: {n.body}\n"
            f"DueDate: {n.due_date.isoformat()}\n"
            f"AIContext: {n.ai_context}"
            for n in all_notifications
        ])

        logger.info(
            f"[Step3] LLM CALL: notification_optimize_chain "
            f"({len(all_notifications)} notifications)\n"
            f"  notifications_info_len={len(notifications_info)}"
        )

        llm_start = time.time()
        result = await notification_optimize_chain.ainvoke({
            "current_datetime": current_datetime,
            "working_memory_content": wm_content,
            "notifications_info": notifications_info,
            "total_notifications": len(all_notifications),
        })
        logger.info(
            f"[Step3] LLM RESPONSE ({time.time() - llm_start:.2f}s):\n"
            f"  ai_context={result.ai_context!r}\n"
            f"  delete_count={len(result.delete_notifications)}\n"
            f"  merge_count={len(result.merge_notifications)}"
        )

        valid_ids = {n.id for n in all_notifications}
        notif_by_id = {n.id: n for n in all_notifications}
        deleted_ids: set = set()
        deleted_details: List[Dict[str, Any]] = []
        updated_details: List[Dict[str, Any]] = []

        # --- 単純削除 ---
        for i, item in enumerate(result.delete_notifications):
            logger.info(
                f"[Step3] DELETE[{i}]: notification_id={item.notification_id}, "
                f"reason={item.reason!r}"
            )
            if item.notification_id in valid_ids:
                await self._notification_repo.delete(item.notification_id)
                deleted_ids.add(item.notification_id)
                deleted_details.append({
                    "notification_id": item.notification_id,
                    "reason": item.reason,
                })
                logger.info(f"[Step3] DB DELETE notification {item.notification_id} OK")
            else:
                logger.warning(
                    f"[Step3] INVALID notification_id={item.notification_id} from LLM, skipping"
                )

        # --- 統合・更新 ---
        for i, item in enumerate(result.merge_notifications):
            logger.info(
                f"[Step3] MERGE[{i}]: target_id={item.notification_id}, "
                f"absorb_ids={item.absorb_ids}, "
                f"new_title={item.title!r}, new_body={item.body!r}, "
                f"new_due_date={item.due_date}, reason={item.reason!r}"
            )
            if item.notification_id not in valid_ids:
                logger.warning(
                    f"[Step3] INVALID merge target notification_id={item.notification_id}, skipping"
                )
                continue

            # 統合元（absorb_ids）を削除
            absorbed = []
            for absorb_id in item.absorb_ids:
                if absorb_id in valid_ids and absorb_id not in deleted_ids:
                    await self._notification_repo.delete(absorb_id)
                    deleted_ids.add(absorb_id)
                    absorbed.append(absorb_id)
                    logger.info(
                        f"[Step3] DB DELETE absorbed notification {absorb_id} "
                        f"-> merged into {item.notification_id}"
                    )
                else:
                    logger.warning(
                        f"[Step3] SKIP absorb_id={absorb_id} "
                        f"(valid={absorb_id in valid_ids}, already_deleted={absorb_id in deleted_ids})"
                    )

            # 統合先を更新
            update_data = AINotificationUpdate(
                title=item.title,
                body=item.body,
            )
            if item.due_date:
                update_data.due_date = item.due_date

            updated = await self._notification_repo.update(item.notification_id, update_data)
            if updated:
                notif_by_id[item.notification_id] = updated
                logger.info(
                    f"[Step3] DB UPDATE notification {item.notification_id}: "
                    f"title={item.title!r}, body={item.body!r}"
                )
            else:
                logger.warning(f"[Step3] DB UPDATE notification {item.notification_id} FAILED")

            updated_details.append({
                "notification_id": item.notification_id,
                "absorbed_ids": absorbed,
                "new_title": item.title,
                "new_body": item.body,
                "reason": item.reason,
            })

        # final_notifications = 全通知 - 削除分（統合先は更新済みオブジェクトを使用）
        final_notifications = [
            notif_by_id.get(n.id, n)
            for n in all_notifications
            if n.id not in deleted_ids
        ]

        logger.info(
            f"[Step3] SUMMARY: deleted={len(deleted_ids)}, "
            f"updated={len(updated_details)}, "
            f"remaining={len(final_notifications)}, "
            f"final_ids={[n.id for n in final_notifications]}"
        )

        return {
            "notifications_deleted": len(deleted_ids),
            "notifications_updated": len(updated_details),
            "deleted_details": deleted_details,
            "updated_details": updated_details,
            "final_notifications": final_notifications,
        }

    # ------------------------------------------------------------------
    # Step 4: working_memory 更新
    # ------------------------------------------------------------------

    async def _update_working_memory(
        self,
        workspace_id: int,
        event: Event,
        working_memory: Optional[WorkingMemory],
        processing_result: Dict[str, Any],
        final_notifications: List[AINotification],
    ) -> Dict[str, Any]:
        """final_notifications + event + 元のmemoryからLLMで要約を生成する。"""
        current_datetime = get_current_datetime_ja()
        old_content = working_memory.content if working_memory and working_memory.content else ""

        # 通知予定をフォーマット（DB取得なし）
        notifications_schedule = "\n".join([
            f"- [{n.due_date.isoformat()}] {n.title}: {n.body} (task #{n.task_id})"
            for n in final_notifications
        ]) or "No scheduled notifications"

        # イベント情報を events_summary として構築
        if event.event_type == "note_updated":
            events_summary = f"Note updated (note_id={event.note_id})"
            if event.diff.title:
                events_summary += f"\n  Title: {event.diff.title}"
            if event.diff.text:
                events_summary += f"\n  Text: {event.diff.text}"
        elif event.event_type == "chat_message":
            events_summary = f"Chat message (thread_id={event.thread_id})"
            if event.diff.content:
                events_summary += f"\n  Content: {event.diff.content}"
        else:
            events_summary = f"Unknown event: {event.event_type}"

        # 処理結果
        tr = processing_result.get("task_result", {})

        logger.info(
            f"[Step4] Input:\n"
            f"  old_content_len={len(old_content)}\n"
            f"  events_summary={events_summary!r}\n"
            f"  tasks_created={tr.get('tasks_created', 0)}\n"
            f"  tasks_updated={tr.get('tasks_updated', 0)}\n"
            f"  final_notifications={len(final_notifications)}\n"
            f"  notifications_schedule:\n{notifications_schedule}"
        )
        logger.info("[Step4] LLM CALL: memory_summary_chain")

        llm_start = time.time()
        result = await memory_summary_chain.ainvoke({
            "current_datetime": current_datetime,
            "current_content": old_content or "Empty (first event)",
            "events_summary": events_summary,
            "notifications_schedule": notifications_schedule,
            "tasks_created": tr.get("tasks_created", 0),
            "tasks_updated": tr.get("tasks_updated", 0),
        })
        logger.info(
            f"[Step4] LLM RESPONSE ({time.time() - llm_start:.2f}s):\n"
            f"  ai_context={result.ai_context!r}\n"
            f"  content_len={len(result.content)}\n"
            f"  content_preview={result.content[:200]!r}..."
        )

        await self._memory_repo.upsert_by_workspace(workspace_id, result.content)
        logger.info(f"[Step4] DB UPSERT working_memory for workspace={workspace_id} OK")

        return {"updated": True, "content": result.content}

    # ------------------------------------------------------------------
    # ヘルパー
    # ------------------------------------------------------------------

    async def get_memory(self, workspace_id: int) -> Optional[WorkingMemory]:
        """Workspace の working_memory を取得する。"""
        return await self._memory_repo.find_by_workspace(workspace_id)

    async def save_memory(self, workspace_id: int, content: str) -> WorkingMemory:
        """Workspace の working_memory を作成または更新する。"""
        return await self._memory_repo.upsert_by_workspace(workspace_id, content)
