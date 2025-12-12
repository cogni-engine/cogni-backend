"""Completion notification response model for structured output"""
from pydantic import BaseModel, Field


class CompletionNotificationResponse(BaseModel):
    """Response model for completion notification generation with structured output"""
    title: str = Field(description="通知タイトル（例：「○○を終わらせました」のような完了通知、日本語で記述）")
    body: str = Field(description="通知本文（100-150文字程度、日本語で記述。完了した内容の概要や次のアクションを簡潔に）")
    ai_context: str = Field(description="ユーザーに表示されない内部情報（通知生成の判断根拠、タスクの詳細分析、システム用のメタデータなど、日本語で記述）")

