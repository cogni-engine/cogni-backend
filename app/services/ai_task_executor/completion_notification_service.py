"""Completion notification service for AI task execution"""
import logging
from datetime import datetime

from langchain_openai import ChatOpenAI

from app.models.task import Task
from app.models.notification import AINotificationCreate, NotificationStatus
from .prompts.completion_notification_prompt import completion_notification_prompt_template
from .models.completion_notification_response import CompletionNotificationResponse

logger = logging.getLogger(__name__)


# LLMの初期化（structured outputを有効化）
llm = ChatOpenAI(model="gpt-5-mini", temperature=0.7)
structured_llm = llm.with_structured_output(CompletionNotificationResponse)


async def generate_completion_notification(
    task: Task,
    result_title: str,
    result_text: str,
    due_date: datetime,
    task_result_id: int
) -> AINotificationCreate:
    """
    AIタスク実行完了後の通知を生成する
    
    Args:
        task: 実行されたタスク
        result_title: 実行結果のタイトル
        result_text: 実行結果の詳細
        due_date: 通知の送信日時（next_run_timeまたはdeadline）
        task_result_id: 関連するtask_resultのID
    
    Returns:
        AINotificationCreate: 生成された通知
    """
    # LangChain チェーンの構築と実行
    chain = completion_notification_prompt_template | structured_llm
    
    try:
        result: CompletionNotificationResponse = await chain.ainvoke({
            "task_title": task.title,
            "result_title": result_title,
            "result_text": result_text
        })
        
        # AINotificationCreateを作成
        notification = AINotificationCreate(
            title=result.title,
            ai_context=result.ai_context,
            body=result.body,
            due_date=due_date,
            task_id=task.id,
            task_result_id=task_result_id,
            user_id=task.user_id,
            workspace_member_id=task.workspace_member_id,
            status=NotificationStatus.SCHEDULED
        )
        
        logger.info(f"Completion notification generated for task {task.id}")
        return notification
        
    except Exception as e:
        logger.error(f"Failed to generate completion notification for task {task.id}: {e}")
        # エラー時はデフォルトの通知を返す
        return AINotificationCreate(
            title=f"{task.title}を終わらせました",
            ai_context=f"通知生成エラー: {str(e)}",
            body=f"{task.title}の実行が完了しました。",
            due_date=due_date,
            task_id=task.id,
            task_result_id=task_result_id,
            user_id=task.user_id,
            workspace_member_id=task.workspace_member_id,
            status=NotificationStatus.SCHEDULED
        )

