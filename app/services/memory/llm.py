"""LLM初期化 + チェーン構築

memory service 専用のLLMインスタンスとチェーンを定義。
他のserviceモジュールには依存しない。
"""
from langchain_google_genai import ChatGoogleGenerativeAI

from .schemas import (
    TaskResolveResponse,
    TaskNotificationListResponse,
    NotificationOptimizeResponse,
    WorkingMemorySummaryResponse,
)
from .prompts import (
    task_resolve_prompt,
    task_notification_prompt,
    notification_optimize_prompt,
    working_memory_summary_prompt,
)

# LLM初期化
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)

# Step 1: workspace内の全ノート差分 → タスク更新/作成
task_resolve_chain = task_resolve_prompt | llm.with_structured_output(TaskResolveResponse)

# Step 2
task_notification_chain = task_notification_prompt | llm.with_structured_output(TaskNotificationListResponse)

# Step 3
notification_optimize_chain = notification_optimize_prompt | llm.with_structured_output(NotificationOptimizeResponse)

# Step 4
memory_summary_chain = working_memory_summary_prompt | llm.with_structured_output(WorkingMemorySummaryResponse)
