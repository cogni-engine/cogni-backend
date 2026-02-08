"""ChatPromptTemplate定義

各ステップで使用するプロンプトテンプレート。
"""
from langchain_core.prompts import ChatPromptTemplate

# ------------------------------------------------------------------
# Step 1: workspace内の全ノート差分からタスクを解決
# ------------------------------------------------------------------

task_resolve_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a task management assistant for a workspace. "
        "You receive multiple note updates from the same workspace at once, "
        "along with existing tasks linked to those notes. "
        "Your job is to:\n"
        "1. UPDATE existing tasks: integrate new note information into their descriptions\n"
        "2. CREATE new tasks: for notes that have no linked tasks yet\n\n"
        "Rules:\n"
        "- Preserve ALL existing information in task descriptions — never lose data\n"
        "- Each note update is independent — match updates to the correct tasks by note_id\n"
        "- For updates: only set title if it truly needs changing (otherwise null)\n"
        "- For creates: title max 50 chars, description structured and comprehensive\n"
        "- ONLY use task_ids from the provided existing tasks\n"
        "- ONLY use note_ids from the provided note updates\n"
        "- Respond in the SAME LANGUAGE as the input content",
    ),
    (
        "human",
        "Current datetime: {current_datetime}\n"
        "Working Memory (workspace context):\n{working_memory_content}\n\n"
        "---\n\n"
        "Note Updates ({note_count} notes):\n{notes_info}\n\n"
        "---\n\n"
        "Existing Tasks linked to these notes ({task_count} tasks):\n{tasks_info}\n\n"
        "---\n\n"
        "Notes with NO existing tasks (need new tasks): {orphan_note_ids}\n\n"
        "---\n\n"
        "Instructions:\n"
        "- For each existing task, decide how to integrate the new note information\n"
        "- For each orphan note, create a new task\n"
        "- Match information to tasks by their source_note_id\n"
        "- Respond in the same language as the content",
    ),
])

# ------------------------------------------------------------------
# Step 2: タスク通知生成
# ------------------------------------------------------------------

task_notification_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a notification scheduler for a task management app. "
        "You generate helpful, well-timed notifications for tasks. "
        "Rules:\n"
        "- Each notification should be actionable and specific\n"
        "- Use the working memory context to make notifications more relevant\n"
        "- ONLY use task_ids from the provided tasks list\n"
        "- Respond in the SAME LANGUAGE as the task content\n"
        "- Title: max 15 characters\n"
        "- Body: 50-80 characters, specific and practical",
    ),
    (
        "human",
        "Current datetime: {current_datetime}\n"
        "Working Memory (context):\n{working_memory_content}\n\n"
        "---\n\n"
        "Tasks ({task_count} tasks):\n{tasks_info}\n\n"
        "---\n\n"
        "Guidelines:\n"
        "- Generate 1-3 notifications per task (total 1-5 notifications)\n"
        "- Each notification must include the corresponding task_id\n"
        "- First notification: 5 minutes to 2 hours from now\n"
        "- Spacing: at least 2-4 hours between notifications for the same task\n"
        "- If a task has a deadline, schedule a final reminder before it\n"
        "- Use working memory context to make notifications specific and helpful\n"
        "- Respond in the same language as the tasks",
    ),
])

# ------------------------------------------------------------------
# Step 3: 通知最適化
# ------------------------------------------------------------------

notification_optimize_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a notification optimizer. "
        "You review scheduled notifications and can: delete, merge, or update them. "
        "Rules:\n"
        "- DELETE: Remove notifications that are outdated, irrelevant, or completely redundant\n"
        "- MERGE: Combine similar notifications (same task, overlapping content, close timing) "
        "into one better notification. Set notification_id to the one to keep, "
        "absorb_ids to the ones to delete after merging their content\n"
        "- UPDATE: Improve a notification's content without merging (set absorb_ids to empty). "
        "Use this when the content is outdated but the notification itself is still needed\n"
        "- When in doubt, keep notifications as-is\n"
        "- Respond in the SAME LANGUAGE as the notification content",
    ),
    (
        "human",
        "Current datetime: {current_datetime}\n"
        "Working Memory (context):\n{working_memory_content}\n\n"
        "---\n\n"
        "Scheduled Notifications ({total_notifications} total):\n{notifications_info}\n\n"
        "---\n\n"
        "Review these notifications and optimize them:\n\n"
        "1. DELETE notifications that are:\n"
        "   - Completely outdated or irrelevant\n"
        "   - Exact duplicates (prefer merging over deleting if content differs)\n\n"
        "2. MERGE notifications that are:\n"
        "   - For the same task with overlapping content → combine into one\n"
        "   - Scheduled too close together (within 1 hour) for the same task → merge into one\n"
        "   - Set notification_id = the one to keep, absorb_ids = ones to remove\n"
        "   - Write a new title/body that combines the best of both\n\n"
        "3. UPDATE notifications that are:\n"
        "   - Still needed but have outdated or improvable content\n"
        "   - Set absorb_ids to empty, just update title/body/due_date\n\n"
        "Return empty lists if no changes are needed. "
        "Respond in the same language as the notifications.",
    ),
])

# ------------------------------------------------------------------
# Step 4: working_memory 更新
# ------------------------------------------------------------------

working_memory_summary_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a working memory manager for a workspace in a task management app. "
        "You maintain a concise, up-to-date summary of the ENTIRE workspace context. "
        "Rules:\n"
        "- Output in markdown format\n"
        "- Max 2000 characters\n"
        "- Include: workspace overview, active tasks across all notes, recent changes, "
        "scheduled notifications\n"
        "- Merge new information with existing content — don't just append\n"
        "- Remove outdated information\n"
        "- This memory represents the WHOLE workspace, not a single note\n"
        "- Respond in the SAME LANGUAGE as the existing content (or the event content if new)",
    ),
    (
        "human",
        "Current datetime: {current_datetime}\n\n"
        "Current Working Memory:\n{current_content}\n\n"
        "---\n\n"
        "New Events (processed in this batch):\n{events_summary}\n\n"
        "Processing Results:\n"
        "- Tasks created: {tasks_created}\n"
        "- Tasks updated: {tasks_updated}\n\n"
        "Scheduled Notifications:\n{notifications_schedule}\n\n"
        "---\n\n"
        "Update the working memory to reflect ALL new information. "
        "This should give a complete picture of the workspace state. "
        "Merge with existing content, remove outdated info, keep it concise (max 2000 chars). "
        "Use markdown format. Respond in the same language as the existing content.",
    ),
])
