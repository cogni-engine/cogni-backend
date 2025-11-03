"""Note to Task AI service with LangChain"""
from typing import List
import logging

from langchain_openai import ChatOpenAI

from app.config import supabase
from app.infra.supabase.repositories.tasks import TaskRepository
from app.models.task import Task, TaskCreate
from app.utils.datetime_helper import get_current_datetime_ja
from .models import TaskListResponse
from .prompts import prompt_template

logger = logging.getLogger(__name__)


# LLMの初期化（structured outputを有効化）
llm = ChatOpenAI(model="gpt-4o", temperature=0)
structured_llm = llm.with_structured_output(TaskListResponse)


async def generate_tasks_from_note(note_id: int, note_text: str, user_ids: List[str]) -> List[Task]:
    """
    指定されたnoteのテキストからAIでタスクを生成してデータベースに保存する
    既存の同じnote_idから生成されたタスクは削除される
    複数のuser_idsが指定された場合、同じタスクが各ユーザーに割り当てられる
    
    Args:
        note_id: ノートID（LLMの参照用）
        note_text: ノートのテキスト内容
        user_ids: タスクを割り当てるユーザーIDのリスト
    
    Returns:
        保存されたタスクのリスト
    """
    # noteのテキストが空の場合は空リストを返す
    if not note_text:
        return []
    
    # user_idsが空の場合は空リストを返す
    if not user_ids:
        return []
    
    # 既存の同じnote_idから生成されたタスクを削除
    task_repo = TaskRepository(supabase)
    deleted_count = await task_repo.delete_by_note(note_id)
    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} existing tasks from note {note_id}")
    
    # 現在の日時を取得（日本時間）
    current_datetime = get_current_datetime_ja()
    
    # LangChain チェーンの構築と実行（1回のみ）
    result: TaskListResponse = await (prompt_template | structured_llm).ainvoke({
        "current_datetime": current_datetime,
        "_note_text": note_text
    })
    
    # TaskRepositoryでタスクを保存
    # 各タスク × 各user_idで保存
    saved_tasks: List[Task] = []
    
    for task in result.tasks:
        for user_id in user_ids:
            task_create = TaskCreate(
                user_id=user_id,
                source_note_id=note_id,
                **task.model_dump(exclude={'source_note_id'})
            )
            try:
                saved_task = await task_repo.create(task_create)
                saved_tasks.append(saved_task)
                logger.info(f"Task saved successfully: {saved_task.id} - {saved_task.title} (user: {user_id})")
            except Exception as e:
                logger.error(f"Failed to save task: {task_create.title} for user {user_id}. Error: {e}")
                # 失敗したタスクはスキップして続行
                continue
    
    return saved_tasks
