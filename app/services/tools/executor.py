"""Tool Executor - dispatches tool_calls to corresponding Tool.execute()."""
import logging
from typing import List, Dict, Optional
from .base import ToolResult
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Receives LLM tool_calls and dispatches to the corresponding Tool's execute()."""

    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    async def execute_tool_calls(
        self, tool_calls: List[Dict], context: Optional[Dict] = None
    ) -> List[ToolResult]:
        """Execute custom tools only. Builtins (web_search etc.) are skipped."""
        results = []
        for tc in tool_calls:
            name = tc["name"]
            args = tc["args"]
            tool = self._registry.get_tool(name)
            if tool:
                try:
                    result = await tool.execute(args, context=context)
                    results.append(result)
                    logger.info(f"Tool executed: {name}, success={result.success}")
                except Exception as e:
                    logger.error(f"Tool execution failed: {name}, error={e}")
                    results.append(ToolResult(
                        tool_name=name, success=False, error=str(e)
                    ))
            else:
                logger.debug(f"No handler for tool: {name} (may be builtin)")
        return results
