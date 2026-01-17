"""Onboarding First Note Generation Service"""
import logging
from typing import List, Optional

from langchain_openai import ChatOpenAI
from .models.first_note_response import FirstNoteContent
from .prompts.first_note_prompt import prompt_template
from .fallback_content import get_fallback_content

logger = logging.getLogger(__name__)

# Initialize LLM with structured output
llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
structured_llm = llm.with_structured_output(FirstNoteContent)


async def generate_first_note_content(
    primary_role: Optional[List[str]],
    ai_relationship: Optional[List[str]],
    use_case: Optional[List[str]],
    locale: str,
    user_id: str,
    workspace_id: int
) -> FirstNoteContent:
    """
    Generate personalized first note content based on onboarding answers.
    
    Args:
        primary_role: User's primary roles (can be multiple)
        ai_relationship: User's work functions (can be multiple)
        use_case: User's intended use cases (can be multiple)
        locale: User's locale (e.g., "ja", "en-US")
        user_id: User ID
        workspace_id: Tutorial workspace ID
        
    Returns:
        FirstNoteContent with title and content
    """
    try:
        # Determine target language
        language = "Japanese" if locale.startswith("ja") else "English"
        
        # Format user inputs for prompt
        roles_str = ", ".join(primary_role) if primary_role else "Not specified"
        functions_str = ", ".join(ai_relationship) if ai_relationship else "Not specified"
        use_cases_str = ", ".join(use_case) if use_case else "Not specified"
        
        logger.info(f"Generating first note for user {user_id} in {language}")
        
        result: FirstNoteContent = await (prompt_template | structured_llm).ainvoke({
            "language": language,
            "primary_role": roles_str,
            "ai_relationship": functions_str,
            "use_case": use_cases_str
        })
        
        logger.info(f"Successfully generated first note: {result.title}")
        return result
        
    except Exception as e:
        logger.error(f"Error generating first note with LLM: {e}")
        # Return fallback content (don't raise exception)
        return get_fallback_content(locale)
