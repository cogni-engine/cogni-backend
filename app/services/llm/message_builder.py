"""Message builder for LLM with file/image support"""
from typing import List, Dict, Any, Optional
import logging
from supabase import Client

logger = logging.getLogger(__name__)


async def build_message_with_files(
    role: str,
    content: str,
    file_ids: Optional[List[int]],
    supabase_client: Client
) -> Dict[str, Any]:
    """
    Build a message object with optional file attachments for OpenAI API.
    
    For GPT-4o Vision, images are included as image_url objects in the content array.
    Format: https://platform.openai.com/docs/guides/vision
    
    Args:
        role: Message role ("user", "assistant", "system")
        content: Text content
        file_ids: Optional list of workspace_file_ids
        supabase_client: Supabase client to fetch file data
    
    Returns:
        Message dict formatted for OpenAI API
    """
    if not file_ids:
        # Simple text message
        return {"role": role, "content": content}
    
    # Fetch file metadata
    try:
        response = supabase_client.table("workspace_files").select(
            "id, file_path, mime_type"
        ).in_("id", file_ids).execute()
        
        if not response.data:
            logger.warning(f"No files found for ids: {file_ids}")
            return {"role": role, "content": content}
        
        files = response.data
        
        # Build content array with text and images
        content_parts: List[Dict[str, Any]] = []
        
        # Add text content first
        if content.strip():
            content_parts.append({"type": "text", "text": content})
        
        # Add images
        for file in files:
            mime_type = file.get("mime_type", "")
            file_path = file.get("file_path", "")
            
            # Only include images in the message content for vision
            if mime_type.startswith("image/"):
                # Generate signed URL for the image
                signed_url = await get_signed_url(supabase_client, file_path)
                
                if signed_url:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": signed_url,
                            "detail": "auto"  # Can be "low", "high", or "auto"
                        }
                    })
                    logger.info(f"Added image to message: {file_path}")
        
        # Return message with content array
        return {"role": role, "content": content_parts}
        
    except Exception as e:
        logger.error(f"Error building message with files: {e}")
        # Fallback to simple text message
        return {"role": role, "content": content}


async def get_signed_url(supabase_client: Client, file_path: str, expires_in: int = 3600) -> Optional[str]:
    """
    Get a signed URL for a file in Supabase Storage.
    
    Args:
        supabase_client: Supabase client
        file_path: Path to file in storage bucket
        expires_in: URL expiration time in seconds (default 1 hour)
    
    Returns:
        Signed URL or None if error
    """
    try:
        result = supabase_client.storage.from_("workspace-files").create_signed_url(
            file_path, expires_in
        )
        
        if result and "signedURL" in result:
            return result["signedURL"]
        
        logger.warning(f"Could not generate signed URL for: {file_path}")
        return None
        
    except Exception as e:
        logger.error(f"Error generating signed URL for {file_path}: {e}")
        return None

