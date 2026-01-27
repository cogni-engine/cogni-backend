"""Domain models for Billing feature"""

from enum import Enum


class SubscriptionPlanType(str, Enum):
    """Subscription plan type enum"""
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"


class SubscriptionStatus(str, Enum):
    """Subscription status enum"""
    FREE = "free"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    RESTRICTED = "restricted"
