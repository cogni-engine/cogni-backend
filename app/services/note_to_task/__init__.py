"""Note to Task service module

DEPRECATED: このサービスは旧パイプライン（webhooks.py の sync-memories）で使用されていたもの。
現在は Memory Service（app/services/memory/）に置き換え済み。
Memory Service は SourceDiff/Reaction ベースのイベント駆動でタスク・通知を管理する。
削除予定。新規利用禁止。
"""
from .note_to_task_service import generate_tasks_from_note
from .models import TaskBaseForAI, TaskListResponse
from .prompts import prompt_template

__all__ = [
    "generate_tasks_from_note",
    "TaskBaseForAI",
    "TaskListResponse",
    "prompt_template",
]

