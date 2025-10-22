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
    duration_minutes: float  # float型に変更（秒単位のTimer対応）
    duration_seconds: Optional[int] = None  # 秒単位のTimer用
    started_at: str  # ISO format datetime
    ends_at: str  # ISO format datetime
    status: TimerStatus = TimerStatus.ACTIVE
    unit: str = "minutes"  # "minutes" or "seconds"
    message_id: Optional[int] = None  # AI message that created this timer

