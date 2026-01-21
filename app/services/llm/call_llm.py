# pyproject.toml: add langchain-openai

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from typing import List, Dict, Type, TypeVar, cast, AsyncGenerator, Any, Union
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

class LLMService:
    def __init__(self, model: str = "gpt-4o", temperature: float = 0.7):
        """
        Initialize LLM Service.
        
        Args:
            model: Model name to use (default: "gpt-4o")
            temperature: Sampling temperature (default: 0.7)
        """
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=True
        )
    
    async def invoke(self, messages: List[Dict[str, str]], **kwargs) -> str:
        # Convert your dict format to LangChain messages
        lc_messages = [
            SystemMessage(content=msg["content"]) if msg["role"] == "system"
            else HumanMessage(content=msg["content"]) if msg["role"] == "user"
            else AIMessage(content=msg["content"])
            for msg in messages
        ]
        
        response = await self.llm.ainvoke(lc_messages)
        return str(response.content)
    
    async def stream_invoke(self, messages: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[str, None]:
        """
        Invoke the LLM with streaming response in SSE (Server-Sent Events) format.
        Supports both simple text messages and vision messages with image_url content.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
                     Content can be a string or an array of content objects (for vision)
            **kwargs: Additional arguments to pass to the LLM
            
        Yields:
            SSE-formatted chunks of the response as they arrive, followed by a [DONE] signal
        """
        # Convert your dict format to LangChain messages
        lc_messages = []
        for msg in messages:
            content = msg["content"]
            role = msg["role"]
            
            # Handle both string content and array content (for vision)
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                # For user messages, content might be an array (for vision)
                if isinstance(content, list):
                    # HumanMessage supports content arrays
                    lc_messages.append(HumanMessage(content=content))
                else:
                    lc_messages.append(HumanMessage(content=content))
            else:  # assistant
                lc_messages.append(AIMessage(content=content))
        
        # Stream the response with SSE formatting
        async for chunk in self.llm.astream(lc_messages):
            if chunk.content:
                yield f"data: {chunk.content}\n\n"


    async def structured_invoke(self, messages: List[Dict[str, str]], schema: Type[T], **kwargs) -> T:
        """
        Invoke the LLM with structured output parsing.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            schema: Pydantic model class to parse the response into
            **kwargs: Additional arguments to pass to the LLM
            
        Returns:
            Instance of the provided Pydantic model with parsed response
        """
        # Convert your dict format to LangChain messages
        lc_messages = [
            SystemMessage(content=msg["content"]) if msg["role"] == "system"
            else HumanMessage(content=msg["content"]) if msg["role"] == "user"
            else AIMessage(content=msg["content"])
            for msg in messages
        ]
        
        # Create a structured LLM with the schema
        structured_llm = self.llm.with_structured_output(schema, method="json_schema")
        
        # Invoke and get structured response
        response = await structured_llm.ainvoke(lc_messages)
        return cast(T, response)

