"""Base classes for Tool abstraction layer."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Tool execution result. meta is merged into AI message's meta field."""
    tool_name: str
    success: bool
    meta: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    # If set, this content is fed back to the LLM for a follow-up response
    content_for_llm: Optional[str] = None


class BaseTool(ABC):
    """
    Base class for all tools.
    One tool = one class. Has args_schema compatible with LangChain bind_tools().
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool identifier name (bind_tools uses args_schema class name)"""

    @property
    @abstractmethod
    def description(self) -> str:
        """Description referenced by LLM when selecting tools"""

    @property
    @abstractmethod
    def args_schema(self) -> Type[BaseModel]:
        """Pydantic model. Argument definition passed to bind_tools()."""

    @abstractmethod
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Execute the tool and return result"""
