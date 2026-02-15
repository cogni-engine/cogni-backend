"""Note to Task AI service with LangChain"""
from typing import List, Optional, Tuple
import logging

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import supabase
from app.infra.supabase.repositories.tasks import TaskRepository
from app.models.task import Task, TaskCreate
from app.utils.datetime_helper import get_current_datetime_ja, convert_jst_to_utc
from .models import TaskListResponse
from .prompts import prompt_template

logger = logging.getLogger(__name__)


# LLMの初期化（structured outputを有効化）
llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0)
structured_llm = llm.with_structured_output(TaskListResponse)


async def generate_tasks_from_note(
    note_id: int, 
    note_text: str, 
    user_workspace_member_pairs: List[Tuple[str, Optional[int]]],
    note_title: Optional[str] = None
) -> List[Task]:
    """
    指定されたnoteのテキストからAIでタスクを生成してデータベースに保存する
    既存の同じnote_idから生成されたタスクは削除される
    複数の(user_id, workspace_member_id)ペアが指定された場合、同じタスクが各ユーザーに割り当てられる
    
    Args:
        note_id: ノートID（LLMの参照用）
        note_text: ノートのテキスト内容
        user_workspace_member_pairs: (user_id, workspace_member_id)のタプルのリスト
        note_title: ノートのタイトル（Noneの場合はテキストの最初の行から抽出）
    
    Returns:
        保存されたタスクのリスト
    """
    # noteのテキストが空の場合は空リストを返す
    if not note_text:
        return []
    
    # user_workspace_member_pairsが空の場合は空リストを返す
    if not user_workspace_member_pairs:
        return []
    
    # 既存の同じnote_idから生成されたタスクを削除
    task_repo = TaskRepository(supabase)
    deleted_count = await task_repo.delete_by_note(note_id)
    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} existing tasks from note {note_id}")
    
    # 現在の日時を取得（日本時間）
    current_datetime = get_current_datetime_ja()
    
    # ノートタイトルを決定（引数で渡された場合はそれを使用、なければテキストから抽出）
    if not note_title:
        # Legacy fallback: extract from first line of text
        note_lines = note_text.split('\n')
        note_title = note_lines[0].strip() if note_lines and note_lines[0].strip() else "Untitled"
    
    # LangChain チェーンの構築と実行（1回のみ）
    result: TaskListResponse = await (prompt_template | structured_llm).ainvoke({
        "current_datetime": current_datetime,
        "note_title": note_title,
        "_note_text": note_text
    })


    print(f"🕐 result: {result}")
    # TaskRepositoryでタスクを保存
    # タスクはノートごとに1つ作成（user_idはタスクに持たない）
    saved_tasks: List[Task] = []

    for task in result.tasks:
        # タスクデータを取得
        task_data = task.model_dump(exclude={'source_note_id'})

        # next_run_timeとdeadlineをJSTからUTCに変換
        if task_data.get('next_run_time'):
            original_next_run_time = task_data['next_run_time']
            task_data['next_run_time'] = convert_jst_to_utc(original_next_run_time)

        if task_data.get('deadline'):
            original_deadline = task_data['deadline']
            task_data['deadline'] = convert_jst_to_utc(original_deadline)

        task_create = TaskCreate(
            source_note_id=note_id,
            **task_data
        )
        try:
            saved_task = await task_repo.create(task_create)
            saved_tasks.append(saved_task)
            logger.info(f"Task saved successfully: {saved_task.id} - {saved_task.title}")
        except Exception as e:
            logger.error(f"Failed to save task: {task_create.title}. Error: {e}")
            continue

    return saved_tasks
