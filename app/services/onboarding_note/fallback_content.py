"""Fallback content for when LLM generation fails"""
from .models.first_note_response import FirstNoteContent


def get_fallback_content(locale: str) -> FirstNoteContent:
    """
    Return default content when LLM generation fails.
    Defaults to English.
    """
    if locale.startswith("ja"):
        return FirstNoteContent(
            title="Cognoへようこそ",
            content="""## はじめに

Cognoへようこそ！このノートでは、基本的な使い方をご紹介します。

## できること

- **ノート作成**: アイデアやタスクをメモ
- **AI活用**: ノートから自動的にタスクを生成
- **チーム連携**: ワークスペースでチームと共有

## 最初のステップ

- [ ] このノートを編集してみる
- [ ] 新しいノートを作成する
- [ ] タスクを追加してみる

さあ、始めましょう！"""
        )
    else:
        return FirstNoteContent(
            title="Welcome to Cogno",
            content="""## Getting Started

Welcome to Cogno! This note will help you get started.

## What You Can Do

- **Create Notes**: Capture ideas and tasks
- **Use AI**: Automatically generate tasks from notes
- **Collaborate**: Share with your team in workspaces

## First Steps

- [ ] Edit this note
- [ ] Create a new note
- [ ] Add your first task

Let's get started!"""
        )
