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
    duration_seconds: int  # 秒単位に統一（必須）
    duration_minutes: Optional[float] = None  # 分単位（オプション、後方互換性用）
    started_at: str  # ISO format datetime
    ends_at: str  # ISO format datetime
    status: TimerStatus = TimerStatus.ACTIVE
    unit: str = "seconds"  # 秒単位に統一
    message_id: Optional[int] = None  # AI message that created this timer

