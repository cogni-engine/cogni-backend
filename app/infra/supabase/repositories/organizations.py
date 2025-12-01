"""Organization repository"""
from typing import Optional

from supabase import Client  # type: ignore

from app.models.organization import (
    Organization,
    OrganizationCreate,
    OrganizationUpdate,
)

from .base import BaseRepository


class OrganizationRepository(BaseRepository[Organization, OrganizationCreate, OrganizationUpdate]):
    """Repository for organization operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "organizations", Organization)
    
    async def find_by_stripe_customer_id(self, stripe_customer_id: str) -> Optional[Organization]:
        """Find organization by Stripe customer ID"""
        results = await self.find_by_filters({"stripe_customer_id": stripe_customer_id}, limit=1)
        return results[0] if results else None
    
    async def find_by_stripe_subscription_id(self, stripe_subscription_id: str) -> Optional[Organization]:
        """Find organization by Stripe subscription ID"""
        results = await self.find_by_filters({"stripe_subscription_id": stripe_subscription_id}, limit=1)
        return results[0] if results else None



