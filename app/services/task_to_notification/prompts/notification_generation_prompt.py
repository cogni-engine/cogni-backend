"""Prompt template for notification generation from tasks"""
from langchain_core.prompts import ChatPromptTemplate


prompt_template = ChatPromptTemplate.from_messages([
    (
        "system",
        "You generate thoughtful notifications from tasks. "
        "Read the task carefully and think about what the user actually wants to achieve. "
        "Based on that understanding, decide what kind of notification would genuinely help them. "
        "Match the task's language in all outputs."
    ),
    (
        "user",
        """Generate notifications for this task.

Current datetime: {current_datetime}

Task:
- Title: {task_title}
- Description: {task_description}
- Deadline: {task_deadline}
- Status: {task_status}
- Progress: {task_progress}%

Guidelines:
- Generate 1-3 notifications based on task complexity
- First notification: 5 min to 2 hours from now
- Spacing: 2-4+ hours between notifications
- Final: before deadline if exists

For each notification, think first:
1. ai_context: What is the user trying to achieve? What would actually help them?
2. title: Based on your analysis (<15 chars)
3. body: Based on your analysis - what the user needs (50-80 chars)

Use task details to make notifications specific and relevant.
Return empty array if no notifications needed."""
    )
])


batch_prompt_template = ChatPromptTemplate.from_messages([
    (
        "system",
        "You generate thoughtful notifications from multiple tasks. "
        "Read the tasks carefully and think about what the user actually wants to achieve. "
        "Based on that understanding, decide what kind of notification would genuinely help them. "
        "Consolidate related tasks. Match the tasks' language in all outputs."
    ),
    (
        "user",
        """Generate notifications for these tasks.

Current datetime: {current_datetime}

Tasks:
{tasks_info}

Guidelines:
- Generate 1-3 notifications total (consolidate related tasks)
- First notification: 5 min to 2 hours from now
- Spacing: 2-4+ hours between notifications
- Final: before earliest deadline

For each notification, think first:
1. ai_context: What is the user trying to achieve? How do tasks relate? What would help?
2. title: Based on your analysis (<15 chars)
3. body: Based on your analysis - what the user needs (50-80 chars)

Use task details to make notifications specific and relevant.
Return empty array if no notifications needed."""
    )
])
