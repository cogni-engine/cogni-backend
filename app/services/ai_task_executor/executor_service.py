"""AI Task Executor service with LangChain"""
import logging
from datetime import datetime
from typing import Tuple

from langchain_openai import ChatOpenAI

from app.models.task import Task
from app.utils.datetime_helper import get_current_datetime_ja
from .prompts import executor_prompt_template
from .models import TaskExecutionResponse

logger = logging.getLogger(__name__)


# LLMの初期化（structured outputを有効化）
llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
structured_llm = llm.with_structured_output(TaskExecutionResponse)


async def execute_ai_task(task: Task) -> Tuple[str, str]:
    """
    AIがタスクを実行し、調査・分析結果を返す
    
    Args:
        task: 実行するタスク
    
    Returns:
        Tuple[str, str]: (title, text) のタプル
        - title: やったことの短い概要
        - text: 成果物本体
    """
    # 現在の日時を取得（日本時間）
    current_datetime = get_current_datetime_ja()
    
    # タスク情報を整形
    task_deadline = task.deadline.strftime("%Y-%m-%d %H:%M") if task.deadline else "指定なし"
    
    # LangChain チェーンの構築と実行
    chain = executor_prompt_template | structured_llm
    
    try:
        result: TaskExecutionResponse = await chain.ainvoke({
            "task_title": task.title,
            "task_description": task.description or "詳細なし",
            "task_deadline": task_deadline,
            "current_datetime": current_datetime
        })
        
        logger.info(f"AI task executed successfully: task_id={task.id}, title={task.title}")
        return (result.title, result.content)
        
    except Exception as e:
        logger.error(f"Failed to execute AI task: task_id={task.id}, error={e}")
        error_title = "エラー"
        error_text = f"タスクの実行中にエラーが発生しました: {str(e)}"
        return (error_title, error_text)

