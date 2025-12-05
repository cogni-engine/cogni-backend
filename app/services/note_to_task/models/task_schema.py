"""Task schema models for AI processing"""
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class TaskBaseForAI(BaseModel):
    """AIが生成するタスクの基本情報"""
    title: str = Field(description="タスクのタイトル（多言語可）")
    description: Optional[str] = Field(
        None, 
        description="タスクの詳細説明（多言語可）。必ず以下の構造化された形式で記述すること："
                    "\n\n【Note内容】\n"
                    "（Noteに書かれた内容を一言一句そのまま全て転記。抜け漏れ厳禁）"
                    "\n\n【理由・目的】\n"
                    "（なぜこのタスクを実行するのか）"
                    "\n\n【方法・手順】\n"
                    "（どのようにこのタスクを実行するのか。できれば複数のアプローチや手段を提示する）"
                    "\n\n"
                    "長くなることは推奨される。どんな言語で書かれていてもその言語のまま全て含める。"
                    "情報を省略・要約してはいけない。"
    )
    deadline: Optional[datetime] = Field(None, description="期限（ISO形式: 2024-10-15T00:00:00）")
    status: Optional[str] = Field("pending", description="ステータス（pending または completed のいずれか）")
    progress: Optional[int] = Field(None, ge=0, le=100, description="進捗率（0-100）")
    source_note_id: int = Field(description="元となったNoteのID（必須）")
    recurring_cron: Optional[str] = Field(None, description="定期実行のcron式（例: '0 9 * * 1-5' = 平日9時）。定期的に実行するタスクの場合のみ指定")
    is_ai_task: bool = Field(False, description="AIが自動実行するタスクかどうか。true=AIが実行、false=人間が実行")


class TaskListResponse(BaseModel):
    """タスクのリスト"""
    tasks: List[TaskBaseForAI] = Field(
        description="抽出されたタスクのリスト。タスク分割の基準に従って適切に分割すること："
                    "1) 実行タイミングが異なる → 分ける"
                    "2) 異なる目的や成果物 → 分ける"
                    "3) 異なるスキル・責任者 → 分ける"
                    "4) 依存関係がある → 分ける"
                    "5) 同じタイミング・同じ人が実行可能 → まとめる。"
                    "タスクが見つからない場合は空の配列。"
    )

