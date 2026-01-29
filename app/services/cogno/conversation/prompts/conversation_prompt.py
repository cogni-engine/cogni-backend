"""System prompt for conversation AI"""
from typing import Optional, List, Dict
from app.models.task import Task
from app.models.notification import AINotification
from app.utils.datetime_helper import get_current_datetime_ja, format_datetime_ja


CONVERSATION_BASE_PROMPT = """You are Cogno, a task assistant. Respond in the user's language."""


TIMER_REQUEST_ADDITION = """
[Timer Setup]
The user seems about to start a task or activity.
Ask how long it will take so you can set a timer and check in when done.
Example: "How long do you think it will take? I'll set a timer."
"""


TIMER_STARTED_ADDITION = """
[Timer Set: {duration_display}]
A timer has been set. Encourage the user and mention you'll check in when time's up.
If the task is unclear, ask them to clarify what they're working on.
Summarize what needs to be done and point out any potential challenges.
"""


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


TASK_COMPLETION_CONFIRMATION_ADDITION = """
[Completion Check: {task_title}]
Description: {task_description}
Deadline: {task_deadline}

The user indicated this task may be complete.
- Check the description for remaining items
- If something remains, suggest completing it together
- If everything is done, confirm completion and move to next steps
Don't rush - be thorough before marking complete.
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
    should_ask_timer: bool = False,
    timer_started: bool = False,
    timer_duration: Optional[int] = None,  # 秒単位に統一
    timer_completed: bool = False,
    notification_triggered: bool = False,
    notification_context: Optional[AINotification] = None,
    daily_summary_context: Optional[str] = None,
    task_list_for_suggestion: Optional[List[Dict]] = None,  # Focused Task=Noneの場合のタスクリスト
    task_to_complete: Optional[Task] = None,  # 完了確認対象タスク
    task_completion_confirmed: bool = False,  # 完了確定フラグ
    file_context: Optional[str] = None,  # File attachments context
) -> str:
    """
    Build conversation AI system prompt.

    Args:
        focused_task: Task to focus on, or None
        related_tasks_info: List of task info dictionaries with 'title' and 'status'
        should_ask_timer: Whether to ask user about timer duration
        timer_started: Whether timer was just started
        timer_duration: Duration of started timer in seconds
        timer_completed: Whether timer has just completed (triggers management check-in)
        notification_triggered: Whether notification was triggered
        notification_context: Single notification context (for click)
        daily_summary_context: Daily summary of multiple notifications
        task_list_for_suggestion: Task list when no focused task exists
        task_to_complete: Task currently pending completion confirmation
        task_completion_confirmed: Whether completion is confirmed
        file_context: Additional context generated from attached files

    Returns:
        Complete system prompt string
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
    
    # Add timer request if needed
    if should_ask_timer:
        base_prompt += TIMER_REQUEST_ADDITION
    
    # Add timer started confirmation if needed
    if timer_started and timer_duration:
        def format_duration(seconds: int) -> str:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            remaining_seconds = seconds % 60

            parts = []
            if hours > 0:
                parts.append(f"{hours}h")
            if minutes > 0:
                parts.append(f"{minutes}m")
            if remaining_seconds > 0:
                parts.append(f"{remaining_seconds}s")

            return " ".join(parts) if parts else "0s"

        duration_display = format_duration(timer_duration)
        base_prompt += TIMER_STARTED_ADDITION.format(duration_display=duration_display)
    
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
    
    # Add task completion confirmation prompt if needed
    if task_to_complete and not task_completion_confirmed:
        task_deadline_str = format_datetime_ja(task_to_complete.deadline) if task_to_complete.deadline else "Not set"
        task_description_str = task_to_complete.description or "No description"
        base_prompt += TASK_COMPLETION_CONFIRMATION_ADDITION.format(
            task_title=task_to_complete.title,
            task_description=task_description_str,
            task_deadline=task_deadline_str
        )
    
    return base_prompt

