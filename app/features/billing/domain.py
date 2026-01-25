"""Domain models for Billing feature"""

from enum import Enum


class SubscriptionPlanType(str, Enum):
    """Subscription plan type enum"""
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"
