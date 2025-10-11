from pydantic import BaseModel
from typing import Optional, Dict

class ChatRequest(BaseModel):
    question: Optional[str] = ""
    notification_id: Optional[int] = None

class ChatMessage(BaseModel):
    id: int
    threadId: str
    role: str
    content: str
    meta: Dict
    createdAt: str

class ChatResponse(BaseModel):
    message: ChatMessage

