"""Domain models for Billing feature"""

from enum import Enum


class SubscriptionPlanType(str, Enum):
    """Subscription plan type enum"""
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"


class SubscriptionStatus(str, Enum):
    """Subscription status enum"""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    GRACE_PERIOD = "grace_period"
    RESTRICTED = "restricted"
