"""Type definitions for note AI editor service"""
from typing import TypedDict, Optional, List, Literal


class AISuggestionDict(TypedDict, total=True):
    """Type for AI suggestion dictionary"""
    block_id: str
    action: Literal["replace", "insert_after", "delete"]
    suggested_text: Optional[List[str]]

