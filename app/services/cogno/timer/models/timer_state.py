"""Timer state models"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class TimerStatus(str, Enum):
    """Timer status"""
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TimerState(BaseModel):
    """Timer state stored in AIMessage.meta"""
    duration_minutes: int
    started_at: str  # ISO format datetime
    ends_at: str  # ISO format datetime
    status: TimerStatus = TimerStatus.ACTIVE
    message_id: Optional[int] = None  # AI message that created this timer

