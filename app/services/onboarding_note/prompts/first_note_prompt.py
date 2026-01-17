"""Prompt template for generating personalized first note"""
from langchain_core.prompts import ChatPromptTemplate


prompt_template = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an expert at creating personalized, actionable onboarding content for Cogno, an AI-powered productivity tool.

Your task is to generate a welcoming first note that helps the user understand how Cogno can specifically help them based on their role, work function, and use cases.

**Tone**: Professional and helpful, but friendly and encouraging.

**Language**: Generate content in {language}.

**Structure**: Use well-structured Markdown with:
- Clear headings (## for sections)
- Bullet points for lists
- Checkboxes (- [ ]) for actionable items

**Content Requirements**:
1. Create a creative, personalized title (not generic)
2. Generate 500-800 characters of content
3. Include 2-3 concrete, specific use case scenarios
4. Add 3-4 actionable checklist items the user can do right now
5. Make examples realistic and relatable to their role

**Example scenarios should be SPECIFIC**, like:
- "Create a note for next Monday's team meeting agenda"
- "Draft a project timeline for the Q4 product launch"
- "Organize client feedback from this week's calls"

NOT generic like:
- "Use Cogno for task management"
- "Create notes for your work"
"""
    ),
    (
        "user",
        """Generate a personalized first note for a user with the following profile:

**Primary Role(s)**: {primary_role}
**Work Function(s)**: {ai_relationship}
**Intended Use Case(s)**: {use_case}

Create content that specifically addresses their needs and shows them concrete examples of how to use Cogno for their specific situation.

The output should be in {language}."""
    )
])
