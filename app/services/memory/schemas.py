"""LLM出力用Pydanticスキーマ

各ステップでLLMが返すstructured outputの型定義。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Step 1: タスク解決
# ------------------------------------------------------------------

class TaskUpdateItem(BaseModel):
    """1つのタスクに対する更新内容"""
    task_id: int = Field(description="更新対象のTaskID")
    title: Optional[str] = Field(None, description="更新後タイトル。変更不要ならNone")
    description: str = Field(description="整理・統合された説明文。全情報を保持")


class NewTaskItem(BaseModel):
    """1つの新規タスク"""
    note_id: int = Field(description="紐づくnote_id")
    title: str = Field(description="明確で実行可能なタスクタイトル（50文字以内）")
    description: str = Field(description="構造化されたタスク説明文")


class TaskResolveResponse(BaseModel):
    """workspace内の全ノート差分に対するタスク解決結果"""
    ai_context: str = Field(description="思考プロセス（非表示）")
    updates: List[TaskUpdateItem] = Field(
        description="既存タスクの更新リスト。更新不要なら空配列"
    )
    creates: List[NewTaskItem] = Field(
        description="新規作成タスクのリスト。作成不要なら空配列"
    )


# ------------------------------------------------------------------
# Step 2: タスク通知生成
# ------------------------------------------------------------------

class NotificationItemForTask(BaseModel):
    """タスクから生成される1つの通知"""
    ai_context: str = Field(
        description=(
            "Think first (not shown to users): "
            "1) このタスクでユーザーは何を達成しようとしている？ "
            "2) 今何が一番助けになる？ "
            "3) どんな種類の通知が適切？ "
            "タスクと同じ言語で"
        )
    )
    title: str = Field(description="短いタイトル（15文字以内）。タスクと同じ言語")
    body: str = Field(description="本文（50-80文字）。具体的で実用的な内容。タスクと同じ言語")
    due_date: datetime = Field(description="送信時刻（ISO format）")
    task_id: int = Field(description="紐づくタスクのID")


class TaskNotificationListResponse(BaseModel):
    """全タスクに対する通知リスト"""
    notifications: List[NotificationItemForTask] = Field(
        description="全タスク合計で1-5件の通知。タスクごとに1-3件。不要なら空配列"
    )


# ------------------------------------------------------------------
# Step 3: 通知最適化
# ------------------------------------------------------------------

class NotificationDeleteItem(BaseModel):
    """削除すべき通知"""
    notification_id: int = Field(description="削除対象の通知ID")
    reason: str = Field(description="削除理由")


class NotificationMergeItem(BaseModel):
    """統合・更新すべき通知"""
    notification_id: int = Field(description="更新対象の通知ID（統合先として残す通知）")
    absorb_ids: List[int] = Field(
        description="この通知に統合して削除する通知IDのリスト。統合元がなければ空配列"
    )
    title: str = Field(description="統合後のタイトル（15文字以内）")
    body: str = Field(description="統合後の本文（50-80文字）")
    due_date: Optional[datetime] = Field(
        None, description="変更後の送信時刻。変更不要ならNone"
    )
    reason: str = Field(description="統合・更新理由")


class NotificationOptimizeResponse(BaseModel):
    """通知最適化結果"""
    ai_context: str = Field(description="思考プロセス（非表示）")
    delete_notifications: List[NotificationDeleteItem] = Field(
        description="単純に削除すべき通知のリスト。不要なら空配列"
    )
    merge_notifications: List[NotificationMergeItem] = Field(
        description="統合・更新すべき通知のリスト。不要なら空配列"
    )


# ------------------------------------------------------------------
# Step 4: working_memory 更新
# ------------------------------------------------------------------

class WorkingMemorySummaryResponse(BaseModel):
    """working_memory の更新内容"""
    ai_context: str = Field(description="思考プロセス（非表示）")
    content: str = Field(description="更新されたworking_memory content（2000文字以内のmarkdown）")
