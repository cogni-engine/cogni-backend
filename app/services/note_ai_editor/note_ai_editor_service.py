"""AI Note Editor Service - Edit notes using AI based on user instructions"""
import logging
from typing import Optional, List

from langchain_google_genai import ChatGoogleGenerativeAI

from .prompts.anchor_suggestion_prompt import anchor_suggestion_prompt_template
from .anchored_markdown import (
    create_id_mapper_from_annotated_markdown,
    generate_ai_friendly_markdown
)
from .anchor_parser import parse_anchored_output_with_validation
from .types import AISuggestionDict

logger = logging.getLogger(__name__)

# Initialize LLM (lightweight model for fast editing)
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.3)



async def get_ai_suggestions(
    user_instruction: str,
    annotated_note_content: str,
    file_contents: Optional[List[str]] = None,
) -> List[AISuggestionDict]:
    """
    Get AI suggestions for editing a note using anchor-based format.
    
    The AI receives markdown with simple sequential IDs (1, 2, 3...) and outputs
    only the changed blocks with their anchors:
    - Edit: <!-- id="2" --> followed by new content
    - Delete: <!-- id="3" --> with empty content
    - Insert: <!-- id="2.1" --> for insertion after block 2
    
    Args:
        note_content: The plain note content (not used in anchor-based approach, kept for API compatibility)
        user_instruction: User's instruction for how to edit the note
        annotated_note_content: The note content with block ID comments
        file_contents: Optional list of file contents to use as context
    
    Returns:
        List of suggestions with block IDs, actions, and text changes
    """
    if not user_instruction:
        return []
    
    if not annotated_note_content:
        logger.warning("No annotated markdown provided, cannot process")
        return []
    
    # Build file context if files are provided
    file_context = ""
    if file_contents and len(file_contents) > 0:
        file_context = "【参考ファイル内容】\n"
        for i, content in enumerate(file_contents, 1):
            file_context += f"--- ファイル {i} ---\n{content}\n\n"
    
    try:
        logger.info("Getting AI suggestions for note using anchor-based approach")
        logger.info(f"User instruction: {user_instruction}")

        # Step 1: Create ID mapper from annotated markdown
        id_mapper = create_id_mapper_from_annotated_markdown(annotated_note_content)

        # Step 2: Generate AI-friendly markdown with simple IDs (1, 2, 3...)
        ai_friendly_markdown = generate_ai_friendly_markdown(
            annotated_note_content,
            id_mapper
        )

        logger.info(f"Generated AI-friendly markdown (length: {len(ai_friendly_markdown)} chars)")
        logger.info(f"AI-friendly markdown:\n{ai_friendly_markdown}")

        # Step 3: Send to AI with anchor-based prompt
        chain = anchor_suggestion_prompt_template | llm
        result = await chain.ainvoke({
            "note_content": ai_friendly_markdown,
            "user_instruction": user_instruction,
            "file_context": file_context,
        })

        ai_output = str(result.content).strip()
        logger.info(f"AI generated anchored output (length: {len(ai_output)} chars)")
        logger.info(f"Full AI output:\n{ai_output}")

        # Step 4: Parse anchored output to suggestions
        suggestions = parse_anchored_output_with_validation(
            ai_output=ai_output,
            id_mapper=id_mapper,
            original_annotated_markdown=annotated_note_content
        )

        logger.info(f"Generated {len(suggestions)} AI suggestions from anchored output")
        return suggestions
        
    except Exception as e:
        logger.error(f"Error getting AI suggestions: {e}")
        raise

