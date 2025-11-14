"""AI Messages repository"""
from typing import List, Dict, Any
import logging

from supabase import Client  # type: ignore

from app.models.ai_message import AIMessage, AIMessageCreate, AIMessageUpdate, MessageFile

from .base import BaseRepository

logger = logging.getLogger(__name__)


class AIMessageRepository(BaseRepository[AIMessage, AIMessageCreate, AIMessageUpdate]):
    """Repository for AI messages (linked to tasks as threads)"""
    
    def __init__(self, client: Client):
        super().__init__(client, "ai_messages", AIMessage)
    
    async def create(self, data: AIMessageCreate) -> AIMessage:
        """Create AI message with optional file attachments"""
        # Extract file_ids before creating message
        file_ids = data.file_ids if hasattr(data, 'file_ids') else None
        
        # Create message without file_ids (not a DB column)
        message_dict = data.model_dump(exclude={'file_ids'})
        response = self._client.table(self._table_name).insert(message_dict).execute()
        
        if not response.data:
            raise Exception("Failed to create AI message")
        
        message_data = response.data[0]
        message_id = message_data['id']
        
        # Link files if provided
        if file_ids:
            try:
                file_links = [
                    {"ai_message_id": message_id, "workspace_file_id": file_id}
                    for file_id in file_ids
                ]
                self._client.table("ai_message_files").insert(file_links).execute()
                logger.info(f"Linked {len(file_ids)} files to message {message_id}")
            except Exception as e:
                logger.error(f"Error linking files to message {message_id}: {e}")
                # Don't fail message creation if file linking fails
        
        # Return message with files
        return await self.find_by_id(message_id)
    
    async def find_by_id(self, message_id: int) -> AIMessage:
        """Find a single message by ID with files"""
        query = self._client.table(self._table_name).select(self._build_select_with_files()).eq("id", message_id).single()
        response = query.execute()
        return self._transform_message_with_files(response.data)
    
    async def find_by_thread(self, thread_id: int) -> List[AIMessage]:
        """Find all messages in a thread with file attachments"""
        query = (
            self._client.table(self._table_name)
            .select(self._build_select_with_files())
            .eq("thread_id", thread_id)
            .order("created_at", desc=False)
        )
        response = query.execute()
        return self._transform_messages_with_files(response.data)
    
    async def get_recent_messages(self, thread_id: int, limit: int = 50) -> List[AIMessage]:
        """Get recent messages from a thread with file attachments"""
        query = (
            self._client.table(self._table_name)
            .select(self._build_select_with_files())
            .eq("thread_id", thread_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        response = query.execute()
        messages = self._transform_messages_with_files(response.data)
        return list(reversed(messages))  # Return in chronological order
    
    async def find_since(self, thread_id: int, since_id: int) -> List[AIMessage]:
        """Find messages in a thread since a specific message ID with file attachments"""
        query = (
            self._client.table(self._table_name)
            .select(self._build_select_with_files())
            .eq("thread_id", thread_id)
            .gt("id", since_id)
            .order("created_at", desc=False)
        )
        response = query.execute()
        return self._transform_messages_with_files(response.data)
    
    def _build_select_with_files(self) -> str:
        """Build select query string with file joins"""
        return """
            *,
            ai_message_files(
                id,
                workspace_file_id,
                workspace_file:workspace_file_id(
                    id,
                    orginal_file_name,
                    file_path,
                    mime_type,
                    file_size
                )
            )
        """
    
    def _transform_message_with_files(self, data: Dict[str, Any]) -> AIMessage:
        """Transform a single message with file data"""
        if not data:
            return None
        
        files = []
        if data.get('ai_message_files'):
            for file_link in data['ai_message_files']:
                if file_link.get('workspace_file'):
                    wf = file_link['workspace_file']
                    files.append(MessageFile(
                        id=wf['id'],
                        original_filename=wf['orginal_file_name'],
                        file_path=wf['file_path'],
                        mime_type=wf['mime_type'],
                        file_size=wf['file_size']
                    ))
        
        # Remove join fields and create AIMessage
        message_data = {k: v for k, v in data.items() if k != 'ai_message_files'}
        message_data['files'] = files if files else None
        
        return AIMessage(**message_data)
    
    def _transform_messages_with_files(self, data: List[Dict[str, Any]]) -> List[AIMessage]:
        """Transform multiple messages with file data"""
        return [self._transform_message_with_files(row) for row in data]

