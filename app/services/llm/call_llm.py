import json
import logging

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from typing import List, Dict, Type, TypeVar, cast, AsyncGenerator, Any, Union
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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
    
    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List:
        """Convert dict format messages to LangChain message objects.
        Supports string content and array content (for vision).
        """
        lc_messages = []
        for msg in messages:
            content = msg["content"]
            role = msg["role"]
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            else:  # assistant
                lc_messages.append(AIMessage(content=content))
        return lc_messages

    async def invoke(self, messages: List[Dict[str, str]], **kwargs) -> str:
        lc_messages = self._convert_messages(messages)
        response = await self.llm.ainvoke(lc_messages)
        return str(response.content)

    async def stream_invoke(self, messages: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[str, None]:
        """
        Invoke the LLM with streaming response in SSE format.
        Supports both simple text messages and vision messages with image_url content.
        """
        lc_messages = self._convert_messages(messages)
        async for chunk in self.llm.astream(lc_messages):
            if chunk.content:
                yield f"data: {chunk.content}\n\n"

    async def stream_invoke_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming with tool calling support.
        - Text chunks -> yield as SSE
        - Responses API content blocks (web_search) -> extract text and yield
        - Custom tool_calls -> yield as special [TOOL_CALLS] event at the end
        """
        llm_with_tools = self.llm.bind_tools(tools)
        lc_messages = self._convert_messages(messages)

        full_message = None
        async for chunk in llm_with_tools.astream(lc_messages):
            if full_message is None:
                full_message = chunk
            else:
                full_message += chunk

            # content is str (normal text)
            if isinstance(chunk.content, str) and chunk.content:
                yield f"data: {chunk.content}\n\n"
            # content is list (Responses API content blocks, e.g. web_search)
            elif isinstance(chunk.content, list):
                for block in chunk.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            yield f"data: {text}\n\n"

        # Yield custom tool_calls as special event
        if full_message and hasattr(full_message, 'tool_calls') and full_message.tool_calls:
            tool_calls_data = [
                {"name": tc["name"], "args": tc["args"], "id": tc.get("id", "")}
                for tc in full_message.tool_calls
            ]
            logger.info(f"Tool calls detected: {[tc['name'] for tc in tool_calls_data]}")
            yield f"data: [TOOL_CALLS]{json.dumps(tool_calls_data)}\n\n"

    async def structured_invoke(self, messages: List[Dict[str, str]], schema: Type[T], **kwargs) -> T:
        """Invoke the LLM with structured output parsing."""
        lc_messages = self._convert_messages(messages)
        structured_llm = self.llm.with_structured_output(schema, method="json_schema")
        response = await structured_llm.ainvoke(lc_messages)
        return cast(T, response)

