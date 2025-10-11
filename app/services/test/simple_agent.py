from typing import AsyncGenerator
from app.services.llm.call_llm import LLMService
from pydantic import BaseModel

# Request model for streaming test
class StreamTestRequest(BaseModel):
    prompt: str
    system_message: str = "You are a helpful assistant."



async def simple_agent_chat(
    system_message: str,
    user_prompt: str
) -> AsyncGenerator[str, None]:
    """
    Simple agent chat that streams LLM responses using LangGraph.
    
    Args:
        system_message: The system message to set context for the LLM
        user_prompt: The user's prompt/question
        stream_mode: How to stream - "messages" (default), "values", "updates", or "metadata"
        
    Yields:
        SSE-formatted chunks of the response
    """
    # Use LangGraph agent for stateful conversation management
    llm_service = LLMService()
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_prompt}
    ]
    # Stream the response through the LangGraph agent
    async for chunk in llm_service.stream_invoke(messages):
        yield chunk

    
