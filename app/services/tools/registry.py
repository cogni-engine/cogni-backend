"""Tool Registry - manages tool registration and retrieval."""
import logging
from typing import Dict, List
from .base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Manages registration and retrieval of tools."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """Register a tool."""
        self._tools[tool.name] = tool
        logger.info(f"Tool registered: {tool.name}")

    def get_bind_tools_list(self) -> List:
        """Return Pydantic schemas list for bind_tools()."""
        return [t.args_schema for t in self._tools.values()]

    def get_tool(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has_tools(self) -> bool:
        """Check if any tools are registered."""
        return len(self._tools) > 0

    def get_tool_names(self) -> List[str]:
        """Get names of all registered tools."""
        return list(self._tools.keys())


# Global singleton
tool_registry = ToolRegistry()
