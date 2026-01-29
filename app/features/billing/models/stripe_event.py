"""Stripe event domain model"""
from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel


class StripeEventBase(BaseModel):
    """Base Stripe event fields"""
    stripe_event_id: str
    type: str
    payload: Dict[str, Any]


class StripeEventCreate(StripeEventBase):
    """Stripe event creation model"""
    pass


class StripeEventUpdate(BaseModel):
    """Stripe event update model - all fields optional"""
    processed_at: Optional[datetime] = None


class StripeEvent(StripeEventBase):
    """Complete Stripe event model from database"""
    id: int
    received_at: datetime
    processed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
