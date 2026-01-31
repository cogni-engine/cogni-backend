"""Onboarding First Note Generation Service"""
import logging
from typing import List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from .models.first_note_response import FirstNoteContent
from .prompts.first_note_prompt import prompt_template
from .fallback_content import get_fallback_content
from app.infra.supabase.repositories.notes import NoteRepository
from app.infra.supabase.client import get_supabase_client
from app.models.note import Note, NoteCreate

logger = logging.getLogger(__name__)

# Initialize LLM with structured output (lightweight model for onboarding)
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.7)
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


async def generate_first_note_and_create(
    primary_role: Optional[List[str]],
    ai_relationship: Optional[List[str]],
    use_case: Optional[List[str]],
    locale: str,
    user_id: str,
    workspace_id: int,
    onboarding_session_id: str
) -> Note:
    """
    Generate personalized first note content and create it in Supabase.
    Also updates onboarding_sessions.context.firstNote with noteId.
    
    Args:
        primary_role: User's primary roles (can be multiple)
        ai_relationship: User's work functions (can be multiple)
        use_case: User's intended use cases (can be multiple)
        locale: User's locale (e.g., "ja", "en-US")
        user_id: User ID
        workspace_id: Tutorial workspace ID
        onboarding_session_id: Onboarding session ID
        
    Returns:
        Note model with id, title, text, workspace_id, created_at, updated_at
    """
    try:
        # 1. Generate first note content using AI
        first_note_content = await generate_first_note_content(
            primary_role=primary_role,
            ai_relationship=ai_relationship,
            use_case=use_case,
            locale=locale,
            user_id=user_id,
            workspace_id=workspace_id
        )
        
        # 2. Create note in Supabase
        supabase_client = get_supabase_client()
        note_repo = NoteRepository(supabase_client)
        
        note_create = NoteCreate(
            title=first_note_content.title,
            text=first_note_content.content,
            workspace_id=workspace_id
        )
        
        note = await note_repo.create(note_create)
        logger.info(f"Created first note {note.id} for user {user_id} in workspace {workspace_id}")
        
        # 3. Update onboarding_sessions.context.firstNote = {noteId: note.id}
        try:
            # Get current context
            response = supabase_client.table('onboarding_sessions').select('context').eq('id', onboarding_session_id).execute()
            
            if response.data and len(response.data) > 0:
                current_context = response.data[0].get('context') or {}
                
                # Update context with firstNote
                updated_context = {
                    **current_context,
                    'firstNote': {
                        'noteId': note.id
                    }
                }
                
                # Update onboarding session (Supabase client uses synchronous execute)
                update_response = supabase_client.table('onboarding_sessions').update({
                    'context': updated_context
                }).eq('id', onboarding_session_id).execute()
                
                if update_response.data:
                    logger.info(f"Updated onboarding_sessions.context.firstNote.noteId = {note.id}")
                else:
                    logger.warning(f"Failed to update onboarding_sessions.context for session {onboarding_session_id}")
            else:
                logger.warning(f"Onboarding session {onboarding_session_id} not found, skipping context update")
        except Exception as e:
            logger.error(f"Failed to update onboarding_sessions.context: {e}")
            # Continue even if context update fails (note is already created)
        
        return note
        
    except Exception as e:
        logger.error(f"Error in generate_first_note_and_create: {e}")
        # If note creation fails, we can't return a Note, so we need to raise
        raise
