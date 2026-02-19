"""WebSearch Tool - searches the web via OpenAI Responses API."""
import logging
from typing import Dict, Any, Type, Optional
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from app.services.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class WebSearchArgs(BaseModel):
    """Web検索を実行する"""
    query: str = Field(description="検索クエリ")


class WebSearchTool(BaseTool):
    """Web search via OpenAI Responses API. Called as a custom tool by Gemini."""

    @property
    def name(self) -> str:
        return "WebSearchArgs"

    @property
    def description(self) -> str:
        return (
            "Search the web for current information. Use when the user asks about "
            "recent events, news, real-time data, or anything that requires up-to-date information."
        )

    @property
    def args_schema(self) -> Type[BaseModel]:
        return WebSearchArgs

    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        query = args["query"]
        logger.info(f"WebSearch executing: {query}")

        try:
            client = AsyncOpenAI()
            response = await client.responses.create(
                model="gpt-4.1-mini",
                tools=[{"type": "web_search_preview"}],
                input=query,
            )

            # Extract text from response output
            text_parts = []
            for item in response.output:
                if item.type == "message":
                    for block in item.content:
                        if hasattr(block, "text"):
                            text_parts.append(block.text)

            result_text = "\n".join(text_parts) if text_parts else "検索結果が見つかりませんでした。"
            logger.info(f"WebSearch result length: {len(result_text)} chars")

            return ToolResult(
                tool_name=self.name,
                success=True,
                meta={"web_search": {"query": query}},
                content_for_llm=f"[Web Search Results for: {query}]\n{result_text}",
            )

        except Exception as e:
            logger.error(f"WebSearch failed: {e}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                content_for_llm=f"[Web Search Failed: {e}]",
            )
