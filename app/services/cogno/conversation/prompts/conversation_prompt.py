"""System prompt for conversation AI"""
from typing import Optional, List, Dict
from app.models.task import Task
from app.models.notification import AINotification
from app.utils.datetime_helper import get_current_datetime_ja, format_datetime_ja


CONVERSATION_BASE_PROMPT = """You are Cogno, a task assistant. Respond in the user's language."""


TIMER_COMPLETED_ADDITION = """
[Timer Complete]
The timer has finished. Check on the user's progress:
- If done: praise and suggest the next step
- If still working: discuss remaining work or offer to extend time
- If stuck: offer support and alternatives
- If plans changed: discuss priorities and next actions
"""


NOTIFICATION_TRIGGERED_ADDITION = """
[Notification Trigger]
Convey the notification content briefly and conversationally.
- Start with a one-line summary
- Check status or progress if relevant
- Ask about priority, deadline, or next action
Keep it short and actionable (about 5 lines).
"""


SUGGEST_IMPORTANT_TASKS_ADDITION = """
[Available Tasks]
{task_list_str}

Suggest tasks to work on based on approaching deadlines or importance.
Keep suggestions natural and conversational.
"""


FOCUSED_TASK_ADDITION = """
[Current Task]
"{task_title}"
Deadline: {deadline_str}
{description_section}{status_section}

Your goal: Help the user actually complete this task.

Approach:
- Break large tasks into small steps, complete one step per conversation
- Propose specific, actionable next steps
- Create templates, examples, or drafts when helpful
- Ask clarifying questions when needed
- Track progress and adjust priorities based on deadline

Communication style:
- Be friendly but specific and actionable
- Don't repeat yourself, always move the conversation forward
- Say "Let's do this" or "Next step is..." to drive action
"""


RELATED_TASKS_ADDITION = """
[Related Tasks]
{formatted_tasks_list}

These are from the same source. Confirm the current task is complete before moving to the next.
"""


def _format_task_list_for_suggestion(tasks: List[Dict]) -> str:
    """Format task list for suggestion prompt (simple list format)"""
    lines = []
    for task in tasks[:5]:  # Limit to top 5 tasks
        title = task.get('title', '')
        deadline = task.get('deadline')
        if deadline:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
                deadline_str = f"Due: {dt.month}/{dt.day}"
            except (ValueError, AttributeError):
                deadline_str = "No deadline"
        else:
            deadline_str = "No deadline"
        lines.append(f"- {title} ({deadline_str})")
    return "\n".join(lines)


def build_conversation_prompt(
    focused_task: Optional[Task] = None,
    related_tasks_info: Optional[List[Dict[str, str]]] = None,
    timer_completed: bool = False,
    notification_triggered: bool = False,
    notification_context: Optional[AINotification] = None,
    daily_summary_context: Optional[str] = None,
    task_list_for_suggestion: Optional[List[Dict]] = None,
    file_context: Optional[str] = None,
) -> str:
    """
    Build conversation AI system prompt.
    Timer start and task completion are now handled via Tool calling.
    """
    base_prompt = CONVERSATION_BASE_PROMPT

    # Add current time
    current_time = get_current_datetime_ja()
    base_prompt += f"\n\nCurrent time: {current_time}"

    # Add file context if available
    if file_context:
        base_prompt += "\n\n" + file_context

    # Add task context if available
    if focused_task:
        deadline_str = format_datetime_ja(focused_task.deadline) if focused_task.deadline else "Not set"

        description_section = f"Description: {focused_task.description}\n" if focused_task.description else ""
        status_section = f"Status: {focused_task.status}\n" if focused_task.status else ""

        task_context = FOCUSED_TASK_ADDITION.format(
            task_title=focused_task.title,
            deadline_str=deadline_str,
            description_section=description_section,
            status_section=status_section
        )

        base_prompt += "\n\n" + task_context

        # Add related tasks if available
        if related_tasks_info:
            formatted_tasks = []
            for task_info in related_tasks_info:
                status = task_info.get("status", "pending")
                checkbox = "☑" if status == "completed" else "☐"
                formatted_tasks.append(f"{checkbox} {task_info['title']}")

            formatted_tasks_list = "\n".join(formatted_tasks)
            base_prompt += RELATED_TASKS_ADDITION.format(
                formatted_tasks_list=formatted_tasks_list
            )

    # Add timer completion management instructions if needed
    if timer_completed:
        base_prompt += TIMER_COMPLETED_ADDITION

    # Add notification-triggered instructions if needed
    if notification_triggered:
        base_prompt += NOTIFICATION_TRIGGERED_ADDITION

        # Add specific notification context if single notification click
        if notification_context:
            deadline_str = format_datetime_ja(notification_context.due_date)
            notification_detail = f"\n\nNotification: {notification_context.title}\n"
            notification_detail += f"Deadline: {deadline_str}\n"
            base_prompt += notification_detail

        # Add daily summary if provided
        if daily_summary_context:
            daily_context = f"\n\n[Today's Important Items]\n{daily_summary_context}\n"
            base_prompt += daily_context

    # Add task suggestion prompt if no focused task but tasks exist
    if task_list_for_suggestion and not focused_task:
        task_list_str = _format_task_list_for_suggestion(task_list_for_suggestion)
        base_prompt += SUGGEST_IMPORTANT_TASKS_ADDITION.format(
            task_list_str=task_list_str
        )

    return base_prompt
