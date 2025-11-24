"""Notification schema models for AI processing"""
from typing import List
from datetime import datetime

from pydantic import BaseModel, Field


class NotificationBaseForAI(BaseModel):
    """AIが生成する通知の基本情報"""
    title: str = Field(description="通知のタイトル（簡潔で親しみやすく、日本語で記述）")
    body: str = Field(description="ユーザーに表示される通知本文（手短で具体的、100-150文字程度、日本語で記述。すぐに実行できるアクションや問いかけを含める）")
    ai_context: str = Field(description="ユーザーに表示されない内部情報（通知生成の判断根拠、タスクの詳細分析、システム用のメタデータなど、日本語で記述）。due_dateの情報は含めないこと")
    due_date: datetime = Field(description="通知を送るタイミング（ISO形式: 2024-10-15T10:00:00）。タスクのdeadlineより前に設定すること")


class NotificationListResponse(BaseModel):
    """通知のリスト"""
    notifications: List[NotificationBaseForAI] = Field(
        description="抽出された通知のリスト（1〜2個が適切）。通知が必要ない場合は空の配列"
    )

