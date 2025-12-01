"""Organization domain model"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from enum import Enum


class SubscriptionPlanType(str, Enum):
    """Subscription plan type enum"""
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"


class OrganizationBase(BaseModel):
    """Base organization fields"""
    name: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_subscription_item_id: Optional[str] = None
    seat_count: int = 1
    active_member_count: int = 0
    plan_type: SubscriptionPlanType = SubscriptionPlanType.PRO
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: Optional[bool] = None


class OrganizationCreate(OrganizationBase):
    """Organization creation model"""
    pass


class OrganizationUpdate(BaseModel):
    """Organization update model - all fields optional"""
    name: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_subscription_item_id: Optional[str] = None
    seat_count: Optional[int] = None
    active_member_count: Optional[int] = None
    plan_type: Optional[SubscriptionPlanType] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: Optional[bool] = None


class Organization(OrganizationBase):
    """Complete organization model from database"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True



