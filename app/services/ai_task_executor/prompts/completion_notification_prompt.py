"""Prompt template for completion notification generation after AI task execution"""
from langchain_core.prompts import ChatPromptTemplate


completion_notification_prompt_template = ChatPromptTemplate.from_messages([
    (
        "system",
        "You generate completion notifications for AI task results. "
        "Create friendly, concise notifications that convey accomplishment. "
        "Match the language of the task and result content."
    ),
    (
        "user",
        """An AI task has been completed. Generate one notification.

Task title: {task_title}

Result summary: {result_title}

Result details:
{result_text}

Requirements:
- Match the language of the content above
- Title: completion format (e.g., "Finished [task]" or "○○を完了しました")
- Body: 50-100 chars, summarize what was done and suggest next action
- ai_context: your reasoning (not shown to user)
- Friendly tone that conveys accomplishment"""
    )
])

