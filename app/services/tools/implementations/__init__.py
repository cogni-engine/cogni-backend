"""Tool implementations - register all tools at app startup."""
from app.services.tools.registry import tool_registry
from .start_timer import StartTimerTool
from .complete_task import CompleteTaskTool
from .web_search import WebSearchTool


def register_all_tools():
    """Register all tools to the global registry. Call at app startup."""
    tool_registry.register(StartTimerTool())
    tool_registry.register(CompleteTaskTool())
    tool_registry.register(WebSearchTool())
