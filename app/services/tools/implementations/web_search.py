"""WebSearch Tool - searches the web via Gemini Google Search grounding."""
import logging
from typing import Dict, Any, Type, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from app.services.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Gemini client (uses GOOGLE_API_KEY env var by default)
_client = genai.Client()

SEARCH_MODEL = "gemini-2.5-flash"


class WebSearchArgs(BaseModel):
    """Web検索を実行する"""
    query: str = Field(description="検索クエリ")


class WebSearchTool(BaseTool):
    """Web search via Gemini Google Search grounding."""

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
            # Build search prompt with client datetime context
            search_prompt = query
            if context and context.get("client_datetime"):
                search_prompt = f"Current date and time: {context['client_datetime']}\n\n{query}"

            response = await _client.aio.models.generate_content(
                model=SEARCH_MODEL,
                contents=search_prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )

            result_text = response.text if response.text else "検索結果が見つかりませんでした。"

            # Extract grounding metadata (citations / sources)
            meta: Dict[str, Any] = {"web_search": {"query": query}}
            try:
                grounding = response.candidates[0].grounding_metadata
                if grounding and grounding.grounding_chunks:
                    sources = []
                    for chunk in grounding.grounding_chunks:
                        if chunk.web:
                            sources.append({
                                "title": chunk.web.title,
                                "uri": chunk.web.uri,
                            })
                    if sources:
                        meta["web_search"]["sources"] = sources
            except (IndexError, AttributeError):
                pass

            return ToolResult(
                tool_name=self.name,
                success=True,
                meta=meta,
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
