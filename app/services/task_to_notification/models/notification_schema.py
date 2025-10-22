"""Notification schema models for AI processing"""
from typing import List
from datetime import datetime

from pydantic import BaseModel, Field


class NotificationBaseForAI(BaseModel):
    """AIが生成する通知の基本情報"""
    title: str = Field(description="通知のタイトル（簡潔で親しみやすく、日本語で記述）")
    content: str = Field(description="通知の本文（具体的で親しみやすく、150文字程度、日本語で記述）")
    due_date: datetime = Field(description="通知を送るタイミング（ISO形式: 2024-10-15T10:00:00）。タスクのdeadlineより前に設定すること")
    suggestions: List[str] = Field(
        description="具体的な行動提案のリスト（3つ程度）。実行可能なアクションを日本語で記述",
        min_items=1,
        max_items=5
    )


class NotificationListResponse(BaseModel):
    """通知のリスト"""
    notifications: List[NotificationBaseForAI] = Field(
        description="抽出された通知のリスト（1〜2個が適切）。通知が必要ない場合は空の配列"
    )

