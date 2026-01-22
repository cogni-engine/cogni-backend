"""Task schema models for AI processing"""
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.recurrence import validate_recurrence_pattern


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
                    "\n\n【ユーザーの意図・推測】\n"
                    "（ユーザーが何をしようとしているのか、Noteの内容から推測される目的や意図）"
                    "\n\n【AIがやるべきこと・できること】\n"
                    "（このタスクにおいて、AIが実行できること、事前に準備できること、支援できること。"
                    "情報収集、調査、原案作成、データ整理、要約、分析など、AIができることを具体的に列挙する。"
                    "AIができることがない場合は「なし」と明記する）"
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
    recurrence_pattern: Optional[str] = Field(None, description="定期実行のパターン（EVERY_DAY, EVERY_WEEK, EVERY_MONTH, EVERY_YEAR, EVERY_MONDAY, EVERY_TUESDAY, EVERY_WEDNESDAY, EVERY_THURSDAY, EVERY_FRIDAY, EVERY_SATURDAY, EVERY_SUNDAY）。複数曜日の場合はカンマ区切り。定期的に実行するタスクの場合のみ指定")
    next_run_time: Optional[datetime] = Field(None, description="次の実行時刻（ISO形式: 2024-10-15T00:00:00）。定期的に実行するタスクの場合のみ指定")
    is_ai_task: bool = Field(True, description="AIが自動実行するタスクかどうか。AIができることがある場合はtrue、AIができることが全くない場合のみfalseを設定する")
    
    @field_validator('recurrence_pattern')
    @classmethod
    def validate_recurrence_pattern_field(cls, v: Optional[str]) -> Optional[str]:
        """recurrence_patternのバリデーション"""
        return validate_recurrence_pattern(v)
    
    @model_validator(mode='after')
    def validate_recurrence_fields(self):
        """recurrence_patternとnext_run_timeのセットバリデーション"""
        has_pattern = self.recurrence_pattern is not None
        has_next_run = self.next_run_time is not None
        
        if has_pattern and not has_next_run:
            raise ValueError(
                "recurrence_patternが指定されている場合、next_run_timeも必須です"
            )
        
        if not has_pattern and has_next_run:
            raise ValueError(
                "next_run_timeが指定されている場合、recurrence_patternも必須です"
            )
        
        return self


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

