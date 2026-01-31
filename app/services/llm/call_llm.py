from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from typing import List, Dict, Type, TypeVar, cast, AsyncGenerator, Any, Union
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

class LLMService:
    def __init__(self, model: str = "gemini-3-flash-preview", temperature: float = 0.7):
        """
        Initialize LLM Service.

        Args:
            model: Model name to use (default: "gemini-3-flash-preview")
            temperature: Sampling temperature (default: 0.7)
        """
        # Check if using Gemini model
        if model.startswith("gemini"):
            self.llm = ChatGoogleGenerativeAI(
                model=model,
                temperature=temperature
            )
        else:
            # OpenAI models
            # Some models (like o1 series) don't support custom temperature
            # Only set temperature if the model supports it
            llm_kwargs = {
                "model": model,
                "streaming": True
            }

            # Only add temperature for models that support it
            # o1 models and some others only support temperature=1 (default)
            if not model.startswith("o1") and "gpt-5.1" not in model:
                llm_kwargs["temperature"] = temperature

            self.llm = ChatOpenAI(**llm_kwargs)
    
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

