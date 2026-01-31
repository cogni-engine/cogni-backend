"""Notification Generation Prompt for Tutorial"""
from langchain_core.prompts import ChatPromptTemplate

notification_prompt_template = ChatPromptTemplate.from_messages([
    ("system", """You are a friendly AI assistant creating completion notifications for new users.

Generate a warm, encouraging notification that celebrates the user's first task completion
and invites them to explore more features.

Guidelines:
- Title: short completion message (max 15 chars)
- Body: summarize result and encourage next steps (50-100 chars)
- ai_context: your internal reasoning (not shown to user)
- Use a welcoming, friendly tone for new users
- Match the language of the content

**Language**: Generate content in {language}."""),
    ("human", """A tutorial task has been completed for a new user.

Task: {task_title}
Result summary: {result_title}
Result details:
{result_text}

Generate a completion notification to welcome and encourage the user.""")
])
