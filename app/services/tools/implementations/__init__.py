"""Tool implementations - register all tools at app startup."""
from app.services.tools.registry import tool_registry
from .start_timer import StartTimerTool
from .web_search import WebSearchTool


def register_all_tools():
    """Register all tools to the global registry. Call at app startup."""
    tool_registry.register(StartTimerTool())
    tool_registry.register(WebSearchTool())
    # CompleteTaskTool: DB に status/completed_at カラム追加後に有効化
    # from .complete_task import CompleteTaskTool
    # tool_registry.register(CompleteTaskTool())
