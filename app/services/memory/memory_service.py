"""Memory event processing service

SourceDiff / Reaction を受け取り、LLM を使って
タスク・通知・working_memory を管理するサービス。
API イベント型からの変換は API 層（api/memory.py）の責務。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from app.config import supabase
from app.infra.supabase.repositories.working_memory import WorkingMemoryRepository
from app.infra.supabase.repositories.tasks import TaskRepository
from app.infra.supabase.repositories.notifications import AINotificationRepository
from app.infra.supabase.repositories.workspaces import WorkspaceMemberRepository, WorkspaceRepository
from app.infra.supabase.repositories.notes import NoteRepository
from app.models.working_memory import WorkingMemory
from app.models.task import Task, TaskCreate, TaskUpdate
from app.models.notification import AINotification, AINotificationCreate, AINotificationUpdate
from app.utils.datetime_helper import get_current_datetime_ja, convert_jst_to_utc

from .schemas import SourceDiff, Reaction
from .llm import (
    task_resolve_chain,
    task_notification_chain,
    notification_optimize_chain,
    memory_summary_chain,
)

logger = logging.getLogger(__name__)


class MemoryService:
    """Memory を軸にしたイベント駆動型タスク・通知管理サービス"""

    def __init__(self):
        self._memory_repo = WorkingMemoryRepository(supabase)
        self._task_repo = TaskRepository(supabase)
        self._notification_repo = AINotificationRepository(supabase)
        self._workspace_member_repo = WorkspaceMemberRepository(supabase)
        self._workspace_repo = WorkspaceRepository(supabase)
        self._note_repo = NoteRepository(supabase)

    # ------------------------------------------------------------------
    # メインエントリポイント
    # ------------------------------------------------------------------

    async def process_events(
        self,
        workspace_id: int,
        source_diffs: List[SourceDiff],
        reactions: List[Reaction],
    ) -> Dict[str, Any]:
        """唯一のエントリポイント。SourceDiff + Reaction を受け取り Step 1-4 を実行。"""
        total_start = time.time()
        logger.info(
            "=" * 60 + "\n"
            f"[ORCHESTRATOR] START process_events\n"
            f"  workspace_id={workspace_id}\n"
            f"  source_diffs={len(source_diffs)}, reactions={len(reactions)}"
        )

        # ---- 共通データの一括取得 ----
        db_start = time.time()
        working_memory = await self.get_memory(workspace_id)
        members = await self._workspace_member_repo.find_by_workspace(workspace_id)

        existing_notifications: List[AINotification] = []
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(hours=24)
        response = (
            supabase.table("ai_notifications")
            .select("*")
            .eq("workspace_id", workspace_id)
            .eq("status", "scheduled")
            .gte("due_date", now.isoformat())
            .lte("due_date", window_end.isoformat())
            .execute()
        )
        if response.data:
            for row in response.data:
                existing_notifications.append(AINotification(**row))
        logger.info(f"[ORCHESTRATOR] DB bulk load done in {time.time() - db_start:.2f}s")

        # --- Step 1: タスク解決 ---
        step1_start = time.time()
        logger.info("-" * 40 + " STEP 1: _resolve_tasks " + "-" * 40)
        task_result = await self._resolve_tasks(
            workspace_id=workspace_id,
            source_diffs=source_diffs,
            reactions=reactions,
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
            source_diffs=source_diffs,
            reactions=reactions,
            working_memory=working_memory,
            tasks_created=task_result["tasks_created"],
            tasks_updated=task_result["tasks_updated"],
            final_notifications=final_notifications,
        )
        logger.info(
            f"[STEP 4 RESULT] {time.time() - step4_start:.2f}s | "
            f"content_len={len(memory_result.get('content', ''))}"
        )

        logger.info(
            "=" * 60 + "\n"
            f"[ORCHESTRATOR] DONE process_events in {time.time() - total_start:.2f}s\n"
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
    # Step 1: タスク解決（統一メソッド）
    # ------------------------------------------------------------------

    async def _resolve_tasks(
        self,
        workspace_id: int,
        source_diffs: List[SourceDiff],
        reactions: List[Reaction],
        working_memory: Optional[WorkingMemory],
        members: List,
    ) -> Dict[str, Any]:
        """全ソース差分 + リアクションを1回のLLM callでタスク解決する。"""
        if not members:
            logger.warning(f"[Step1] No workspace members for workspace {workspace_id}, SKIP")
            return {"tasks_created": 0, "tasks_updated": 0, "affected_tasks": [], "details": []}

        if not source_diffs and not reactions:
            logger.info("[Step1] SKIP: no source_diffs and no reactions")
            return {"tasks_created": 0, "tasks_updated": 0, "affected_tasks": [], "details": []}

        current_datetime = get_current_datetime_ja()
        wm_content = working_memory.content if working_memory and working_memory.content else "None"

        # --- 既存タスク収集 ---
        # source_diffs から find_by_sources
        existing_tasks: List[Task] = []
        if source_diffs:
            # source_type ごとにグループ化して一括取得
            sources_by_type: Dict[str, List[int]] = {}
            for sd in source_diffs:
                sources_by_type.setdefault(sd.source_type, []).append(sd.source_id)
            for st, sids in sources_by_type.items():
                existing_tasks.extend(await self._task_repo.find_by_sources(st, sids))

        # reactions から find_by_ids
        reaction_task_ids = [r.task_id for r in reactions]
        if reaction_task_ids:
            reaction_tasks = await self._task_repo.find_by_ids(reaction_task_ids)
            # dedup
            existing_ids = {t.id for t in existing_tasks}
            for t in reaction_tasks:
                if t.id not in existing_ids:
                    existing_tasks.append(t)
                    existing_ids.add(t.id)

        # --- タスク未作成ソースの特定 ---
        tasks_by_source: Dict[tuple, List[Task]] = {}
        for t in existing_tasks:
            key = (t.source_type or "", t.source_id or 0)
            tasks_by_source.setdefault(key, []).append(t)

        orphan_sources = [
            (sd.source_type, sd.source_id)
            for sd in source_diffs
            if (sd.source_type, sd.source_id) not in tasks_by_source
        ]

        # --- LLMコンテキスト組み立て ---
        # sources_info
        if source_diffs:
            sources_info = "\n\n---\n\n".join([
                f"SourceType: {sd.source_type}\n"
                f"SourceID: {sd.source_id}\n"
                f"Title: {sd.title or 'None'}\n"
                f"Content: {sd.content or ''}"
                for sd in source_diffs
            ])
        else:
            sources_info = "None (reaction event — no source changes)"

        # tasks_info
        if existing_tasks:
            tasks_info = "\n\n---\n\n".join([
                f"TaskID: {t.id}\nSourceType: {t.source_type or ''}\n"
                f"SourceID: {t.source_id}\n"
                f"Title: {t.title}\nDescription: {t.description or ''}"
                for t in existing_tasks
            ])
        else:
            tasks_info = "None"

        # sources_without_tasks
        if orphan_sources:
            sources_without_tasks = "\n".join(
                f"- source_type={st}, source_id={sid}" for st, sid in orphan_sources
            )
        else:
            sources_without_tasks = "None"

        # reactions_info
        reactions_info = "None"
        reaction_count = 0
        if existing_tasks:
            task_ids = [t.id for t in existing_tasks]
            reactions_info, reaction_count = await self._fetch_reactions_info(task_ids)

        logger.info(
            f"[Step1] Input:\n"
            f"  source_diffs={len(source_diffs)}, reactions={len(reactions)}\n"
            f"  existing_tasks={len(existing_tasks)} (ids={[t.id for t in existing_tasks]})\n"
            f"  orphan_sources={orphan_sources}\n"
            f"  reaction_count={reaction_count}\n"
            f"  current_datetime={current_datetime}"
        )

        # --- LLM 1回: task_resolve_chain ---
        logger.info(
            f"[Step1] LLM CALL: task_resolve_chain "
            f"(sources={len(source_diffs)}, tasks={len(existing_tasks)})"
        )
        llm_start = time.time()
        result = await task_resolve_chain.ainvoke({
            "current_datetime": current_datetime,
            "working_memory_content": wm_content,
            "source_count": len(source_diffs),
            "sources_info": sources_info,
            "task_count": len(existing_tasks),
            "tasks_info": tasks_info,
            "sources_without_tasks": sources_without_tasks,
            "reaction_count": reaction_count,
            "reactions_info": reactions_info,
        })
        logger.info(
            f"[Step1] LLM RESPONSE ({time.time() - llm_start:.2f}s): "
            f"updates={len(result.updates)}, creates={len(result.creates)}"
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

            assignees = await self._build_assignee_dicts(item.assignees, members)
            update_data = TaskUpdate(description=item.description, assignees=assignees)
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
        valid_orphan_sources = set(orphan_sources)
        for i, item in enumerate(result.creates):
            logger.info(
                f"[Step1] CREATE[{i}]: source_type={item.source_type}, source_id={item.source_id}, "
                f"title={item.title!r}, description_len={len(item.description)}"
            )
            if (item.source_type, item.source_id) not in valid_orphan_sources:
                logger.warning(
                    f"[Step1] INVALID source ({item.source_type}, {item.source_id}) from LLM, skipping"
                )
                continue

            assignees = await self._build_assignee_dicts(item.assignees, members)
            create_data = TaskCreate(
                title=item.title,
                workspace_id=workspace_id,
                description=item.description,
                source_type=item.source_type,
                source_id=item.source_id,
                assignees=assignees,
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

        logger.info(f"[Step1] DONE: created={tasks_created}, updated={tasks_updated}")
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

        # 全タスクをまとめてフォーマット（リアクション履歴を含む全文を渡す）
        tasks_info = "\n\n---\n\n".join([
            f"TaskID: {t.id}\nSourceType: {t.source_type or ''}\n"
            f"Title: {t.title}\nDescription: {t.description or ''}"
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
                f"due_date={notif.due_date.isoformat()}"
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

            # LLMは日本時間で返すのでUTCに変換してからDBに保存
            due_date_utc = convert_jst_to_utc(notif.due_date)
            reacted_at_utc = convert_jst_to_utc(notif.reacted_at) if notif.reacted_at else None

            # task.assignees から直接 workspace_member_id を取得
            assignees = task.assignees or []
            if not assignees:
                logger.warning(f"[Step2] No assignees for task {task.id}, skipping notification")
                continue

            for assignee in assignees:
                workspace_member_id = assignee.get("workspace_member_id")
                if not workspace_member_id:
                    continue
                saved = await self._notification_repo.create(
                    AINotificationCreate(
                        title=notif.title,
                        body=notif.body,
                        due_date=due_date_utc,
                        task_id=task_id,
                        workspace_id=task.workspace_id,
                        workspace_member_id=workspace_member_id,
                        reaction_choices=notif.reaction_choices,
                        reacted_at=reacted_at_utc,
                    )
                )
                created_notifications.append(saved)
                details.append({
                    "notification_id": saved.id,
                    "task_id": task_id,
                    "workspace_member_id": workspace_member_id,
                    "title": saved.title,
                    "body": saved.body,
                    "due_date": notif.due_date.isoformat(),
                })
                logger.info(
                    f"[Step2] DB CREATE notification {saved.id}: "
                    f"task_id={task_id}, wm={workspace_member_id}, title={saved.title!r}, due={notif.due_date.isoformat()}"
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
            f"WorkspaceMemberID: {n.workspace_member_id}\n"
            f"Title: {n.title}\n"
            f"Body: {n.body}\n"
            f"DueDate: {n.due_date.isoformat()}"
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
                update_data.due_date = convert_jst_to_utc(item.due_date)

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
    # Step 4: working_memory 更新（統一版）
    # ------------------------------------------------------------------

    async def _update_working_memory(
        self,
        workspace_id: int,
        source_diffs: List[SourceDiff],
        reactions: List[Reaction],
        working_memory: Optional[WorkingMemory],
        tasks_created: int,
        tasks_updated: int,
        final_notifications: List[AINotification],
    ) -> Dict[str, Any]:
        """SourceDiff + Reaction からサマリーを構築し、LLMでworking_memoryを更新する。"""
        current_datetime = get_current_datetime_ja()
        old_content = working_memory.content if working_memory and working_memory.content else ""

        notifications_schedule = "\n".join([
            f"- [{n.due_date.isoformat()}] {n.title}: {n.body} (task #{n.task_id})"
            for n in final_notifications
        ]) or "No scheduled notifications"

        # SourceDiff + Reaction から events_summary を組み立て
        parts = []
        for sd in source_diffs:
            s = f"Source updated ({sd.source_type}, id={sd.source_id})"
            if sd.title:
                s += f"\n  Title: {sd.title}"
            if sd.content:
                s += f"\n  Content: {sd.content}"
            parts.append(s)
        for r in reactions:
            desc = f'"{r.reaction_text}"' if r.reaction_text else "無視（反応なし）"
            parts.append(f"Notification reaction (id={r.notification_id})\n  Reaction: {desc}")

        events_summary = "\n\n".join(parts) or "No events"

        # Always include member list with task assignments for person-centric memory
        members = await self._workspace_member_repo.find_by_workspace(workspace_id)
        members_info = await self._build_enriched_members_info(workspace_id, members)

        logger.info(
            f"[Step4] Input:\n"
            f"  old_content_len={len(old_content)}\n"
            f"  source_diffs={len(source_diffs)}, reactions={len(reactions)}\n"
            f"  tasks_created={tasks_created}, tasks_updated={tasks_updated}\n"
            f"  final_notifications={len(final_notifications)}"
        )
        logger.info("[Step4] LLM CALL: memory_summary_chain")

        llm_start = time.time()
        result = await memory_summary_chain.ainvoke({
            "current_datetime": current_datetime,
            "current_content": old_content or "Empty (first event)",
            "members_info": members_info,
            "events_summary": events_summary,
            "notifications_schedule": notifications_schedule,
            "tasks_created": tasks_created,
            "tasks_updated": tasks_updated,
        })
        logger.info(
            f"[Step4] LLM RESPONSE ({time.time() - llm_start:.2f}s): "
            f"content_len={len(result.content)}"
        )

        await self._memory_repo.upsert_by_workspace(workspace_id, result.content)
        logger.info(f"[Step4] DB UPSERT working_memory for workspace={workspace_id} OK")

        return {"updated": True, "content": result.content}

    # ------------------------------------------------------------------
    # ヘルパー
    # ------------------------------------------------------------------

    async def _build_assignee_dicts(
        self, assignee_ids: List[int], members: List
    ) -> List[Dict[str, Any]]:
        """Convert LLM-determined workspace_member_id list to assignee dicts.

        Falls back to all members if assignee_ids is empty.
        """
        if not assignee_ids:
            # Fallback: assign to all members
            names = await self._fetch_member_names([m.id for m in members])
            return [
                {"workspace_member_id": m.id, "name": names.get(m.id, "")}
                for m in members
            ]

        # Validate against actual members
        valid_member_ids = {m.id for m in members}
        valid_ids = [mid for mid in assignee_ids if mid in valid_member_ids]

        if not valid_ids:
            logger.warning(
                f"[Step1] No valid assignee_ids from LLM ({assignee_ids}), "
                f"falling back to all members"
            )
            names = await self._fetch_member_names([m.id for m in members])
            return [
                {"workspace_member_id": m.id, "name": names.get(m.id, "")}
                for m in members
            ]

        names = await self._fetch_member_names(valid_ids)
        return [
            {"workspace_member_id": mid, "name": names.get(mid, "")}
            for mid in valid_ids
        ]

    async def _build_enriched_members_info(
        self, workspace_id: int, members: List
    ) -> str:
        """Build enriched members_info with per-member task assignments."""
        if not members:
            return "None"

        names = await self._fetch_member_names([m.id for m in members])

        # Get all tasks for this workspace
        response = (
            supabase.table("tasks")
            .select("id, title, source_type, assignees")
            .eq("workspace_id", workspace_id)
            .order("updated_at", desc=True)
            .execute()
        )
        all_tasks = response.data or []

        # Build per-member task list
        member_tasks: Dict[int, List[str]] = {}
        for task in all_tasks:
            for assignee in task.get("assignees") or []:
                mid = assignee.get("workspace_member_id")
                if mid:
                    label = f"[{task.get('source_type', 'unknown')}] {task.get('title', '')}"
                    member_tasks.setdefault(mid, []).append(label)

        lines: List[str] = []
        for m in members:
            mid = m.id
            name = names.get(mid, "Unknown")
            line = f"- id:{mid} {name}"
            tasks = member_tasks.get(mid, [])
            if tasks:
                line += f" (担当タスク {len(tasks)}件)"
                for t in tasks[:5]:
                    line += f"\n    - {t}"
                if len(tasks) > 5:
                    line += f"\n    - ...他 {len(tasks) - 5}件"
            else:
                line += " (担当タスクなし)"
            lines.append(line)

        return "\n".join(lines)

    async def _fetch_member_names(self, member_ids: List[int]) -> Dict[int, str]:
        """workspace_member ID リストから名前を取得する。"""
        if not member_ids:
            return {}
        response = (
            supabase.table("workspace_member")
            .select("id, user_profiles:user_id(name)")
            .in_("id", member_ids)
            .execute()
        )
        return {
            row["id"]: (row.get("user_profiles") or {}).get("name", "")
            for row in (response.data or [])
        }

    async def _fetch_reactions_info(self, task_ids: List[int]) -> tuple[str, int]:
        """タスクIDリストに紐づく通知のリアクション履歴を取得してフォーマットする。

        Returns:
            (reactions_info_text, reaction_count)
        """
        if not task_ids:
            return "None", 0

        response = (
            supabase.table("ai_notifications")
            .select("id, task_id, title, reaction_text, reaction_choices, reacted_at")
            .in_("task_id", task_ids)
            .not_.is_("reacted_at", "null")
            .order("reacted_at", desc=True)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return "None", 0

        parts = []
        for row in rows:
            task_id = row["task_id"]
            title = row.get("title", "")
            reaction_text = row.get("reaction_text")
            reacted_at = row.get("reacted_at", "")

            if reaction_text:
                reaction_desc = f'ユーザーの反応: "{reaction_text}"'
            else:
                reaction_desc = "反応なし（無視された）"

            parts.append(
                f"Task #{task_id} の通知 \"{title}\" (reacted_at={reacted_at}):\n"
                f"  → {reaction_desc}"
            )

        return "\n\n".join(parts), len(rows)

    async def get_memory(self, workspace_id: int) -> Optional[WorkingMemory]:
        """Workspace の working_memory を取得する。"""
        return await self._memory_repo.find_by_workspace(workspace_id)

    async def save_memory(self, workspace_id: int, content: str) -> WorkingMemory:
        """Workspace の working_memory を作成または更新する。"""
        return await self._memory_repo.upsert_by_workspace(workspace_id, content)
