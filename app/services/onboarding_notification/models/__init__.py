"""Onboarding Notification Models"""
from pydantic import BaseModel, Field


class TutorialTaskResultResponse(BaseModel):
    """AI response for tutorial task result generation (with web search)"""
    result_title: str = Field(
        description="ユーザーの業界・トピックを表すタイトル（20-40文字）例: '📊 マーケティング業界の最新動向'"
    )
    result_text: str = Field(
        description="Markdown形式の詳細なリサーチレポート（600-1000文字）。見出し（###）、箇条書き、太字（**）、参考リンク（[タイトル](URL)）を含む。ユーザーの業界に特化した実用的な情報を提供。"
    )


class TutorialNotificationResponse(BaseModel):
    """AI response for tutorial notification generation"""
    title: str = Field(
        description="Notification title conveying completion (max 15 chars)"
    )
    body: str = Field(
        description="Notification body (50-100 chars). Summarize result and encourage next steps."
    )
    ai_context: str = Field(
        description="Internal reasoning (not shown to user)"
    )
