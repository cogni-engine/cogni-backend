"""AI Note Editor Service - Edit notes using AI based on user instructions"""
import logging
from typing import Optional, List

from langchain_openai import ChatOpenAI

from .prompts import prompt_template

logger = logging.getLogger(__name__)

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0.3)


async def edit_note_with_ai(
    note_content: str,
    user_instruction: str,
    file_contents: Optional[List[str]] = None,
) -> str:
    """
    Edit a note using AI based on user instructions.
    
    Args:
        note_content: The current content of the note (markdown)
        user_instruction: User's instruction for how to edit the note
        file_contents: Optional list of file contents to use as context
    
    Returns:
        The edited note content (markdown)
    """
    if not note_content:
        note_content = ""
    
    if not user_instruction:
        return note_content
    
    # Build file context if files are provided
    file_context = ""
    if file_contents and len(file_contents) > 0:
        file_context = "【参考ファイル内容】\n"
        for i, content in enumerate(file_contents, 1):
            file_context += f"--- ファイル {i} ---\n{content}\n\n"
    
    try:
        # Create the chain and invoke
        chain = prompt_template | llm
        result = await chain.ainvoke({
            "note_content": note_content,
            "user_instruction": user_instruction,
            "file_context": file_context,
        })
        
        edited_content = str(result.content).strip()
        
        logger.info(f"Successfully edited note. Original length: {len(note_content)}, Edited length: {len(edited_content)}")
        
        return edited_content
        
    except Exception as e:
        logger.error(f"Error editing note with AI: {e}")
        raise

