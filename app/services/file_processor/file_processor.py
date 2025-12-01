"""File content extraction service"""
import logging
from typing import List, Dict, Any, Optional
from supabase import Client

logger = logging.getLogger(__name__)


async def build_file_context(client: Client, file_ids: List[int]) -> Optional[str]:
    """
    Build context string from uploaded files
    
    Args:
        client: Supabase client
        file_ids: List of workspace_file_ids
    
    Returns:
        Formatted context string with file information
    """
    if not file_ids:
        return None
    
    try:
        # Fetch file metadata
        response = client.table("workspace_files").select(
            "id, original_file_name, file_path, mime_type, file_size"
        ).in_("id", file_ids).execute()
        
        if not response.data:
            logger.warning(f"No files found for ids: {file_ids}")
            return None
        
        files = response.data
        context_parts = ["📎 User has attached the following files:\n"]
        
        for file in files:
            filename = file.get("original_file_name", "unknown")
            mime_type = file.get("mime_type", "unknown")
            file_size = file.get("file_size", 0)
            
            # Format file size
            size_str = format_file_size(file_size)
            
            # Describe file based on type
            file_type_desc = get_file_type_description(mime_type)
            
            context_parts.append(f"  - {filename} ({file_type_desc}, {size_str})")
            
            # TODO: For future enhancement - extract text content from files
            # if mime_type.startswith('text/'):
            #     content = await extract_text_content(client, file)
            #     context_parts.append(f"    Content preview: {content[:200]}...")
            # elif mime_type == 'application/pdf':
            #     content = await extract_pdf_content(client, file)
            #     context_parts.append(f"    Content preview: {content[:200]}...")
        
        context_parts.append("\nPlease reference these files in your response as needed.")
        return "\n".join(context_parts)
        
    except Exception as e:
        logger.error(f"Error building file context: {e}")
        return None


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f}GB"


def get_file_type_description(mime_type: str) -> str:
    """Get human-readable file type description"""
    type_map = {
        "image/": "Image",
        "text/": "Text file",
        "application/pdf": "PDF document",
        "application/json": "JSON file",
        "application/javascript": "JavaScript file",
        "application/zip": "Archive",
        "video/": "Video",
        "audio/": "Audio",
    }
    
    for key, desc in type_map.items():
        if mime_type.startswith(key) or mime_type == key:
            return desc
    
    return "File"


# Future enhancement: Extract text content from files
async def extract_text_content(client: Client, file: Dict[str, Any]) -> Optional[str]:
    """
    Extract text content from text files
    
    TODO: Implement file download from Supabase storage and text extraction
    """
    pass


async def extract_pdf_content(client: Client, file: Dict[str, Any]) -> Optional[str]:
    """
    Extract text content from PDF files using PyPDF2
    
    TODO: Implement PDF text extraction
    - Download file from Supabase storage
    - Use PyPDF2 to extract text
    - Return extracted text
    """
    pass



