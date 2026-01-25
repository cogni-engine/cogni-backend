"""Stripe events repository"""
from typing import Optional

from supabase import Client  # type: ignore

from app.features.billing.models.stripe_event import StripeEvent, StripeEventCreate, StripeEventUpdate

from app.infra.supabase.repositories.base import BaseRepository


class StripeEventRepository(BaseRepository[StripeEvent, StripeEventCreate, StripeEventUpdate]):
    """Repository for Stripe event operations"""
    
    def __init__(self, client: Client):
        super().__init__(client, "stripe_events", StripeEvent)
    
    async def find_by_stripe_event_id(self, stripe_event_id: str) -> Optional[StripeEvent]:
        """Find Stripe event by Stripe event ID (for idempotency checking)"""
        results = await self.find_by_filters({"stripe_event_id": stripe_event_id}, limit=1)
        return results[0] if results else None
    
    async def mark_as_processed(self, stripe_event_id: str) -> Optional[StripeEvent]:
        """Mark a Stripe event as processed by updating processed_at timestamp"""
        from datetime import datetime, timezone
        
        event = await self.find_by_stripe_event_id(stripe_event_id)
        if not event:
            return None
        
        update_data = StripeEventUpdate(processed_at=datetime.now(timezone.utc))
        return await self.update(event.id, update_data)
