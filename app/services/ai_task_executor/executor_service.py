"""AI Task Executor service with LangChain"""
import logging
from typing import Tuple

from langchain_openai import ChatOpenAI

from app.models.task import Task
from app.utils.datetime_helper import get_current_datetime_ja
from .prompts import executor_prompt_template

logger = logging.getLogger(__name__)


# LLMの初期化（web_searchツール付き）
llm = ChatOpenAI(model="gpt-5.1", use_responses_api=True)

tool = {"type": "web_search_preview"}
llm_with_tools = llm.bind_tools([tool])


async def execute_ai_task(task: Task) -> Tuple[str, str]:
    """
    AIがタスクを実行し、調査・分析結果を返す
    
    Args:
        task: 実行するタスク
    
    Returns:
        Tuple[str, str]: (title, text) のタプル
        - title: 空文字列（使用しない）
        - text: 成果物本体
    """
    # 現在の日時を取得（日本時間）
    current_datetime = get_current_datetime_ja()
    
    # タスク情報を整形
    task_deadline = task.deadline.strftime("%Y-%m-%d %H:%M") if task.deadline else "指定なし"
    
    # LangChain チェーンの構築と実行（web_searchツール付き）
    chain = executor_prompt_template | llm_with_tools
    
    try:
        result = await chain.ainvoke({
            "task_title": task.title,
            "task_description": task.description or "詳細なし",
            "task_deadline": task_deadline,
            "current_datetime": current_datetime
        })
        
        # LLMの応答からcontentを取得（AIMessageオブジェクトから）
        content = result.content
        
        logger.info(f"AI task executed successfully: task_id={task.id}, title={task.title}")
        return ("", content)
        
    except Exception as e:
        logger.error(f"Failed to execute AI task: task_id={task.id}, error={e}")
        error_text = f"タスクの実行中にエラーが発生しました: {str(e)}"
        return ("", error_text)

