"""Subscription seat management service"""
import logging
import stripe
from app.config import STRIPE_SECRET_KEY
from app.infra.supabase.repositories.organizations import OrganizationRepository
from app.models.organization import Organization

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY


class SubscriptionSeatManager:
    """Service for managing subscription seat counts"""
    
    def __init__(self, org_repo: OrganizationRepository):
        self.org_repo = org_repo
    
    async def sync_seats_with_members(self, organization_id: int) -> bool:
        """
        Sync Stripe subscription seats with actual member count
        
        This should be called when:
        - A member is added to the organization
        - A member is activated
        - A member leaves (optional - most SaaS keep seats contracted)
        
        Args:
            organization_id: Organization ID
            
        Returns:
            True if seats were updated, False if no update needed
        """
        print(f"\n{'─'*60}")
        print(f"🔄 Syncing seats for organization {organization_id}")
        print(f"{'─'*60}")
        
        # Get organization
        org = await self.org_repo.find_by_id(organization_id)
        if not org:
            print(f"❌ Organization not found: {organization_id}")
            logger.error(f"Organization not found: {organization_id}")
            return False
        
        print(f"✅ Organization: {org.name}")
        print(f"   Plan: {org.plan_type}")
        print(f"   Active members: {org.active_member_count}")
        print(f"   Current seat count: {org.seat_count}")
        
        # Only sync for Business plan
        if org.plan_type != "business":
            print(f"ℹ️  Skipping: Not a Business plan")
            return False
        
        # Check if organization has active subscription
        if not org.stripe_subscription_id or not org.stripe_subscription_item_id:
            print(f"❌ No active subscription found")
            logger.warning(f"Organization {organization_id} has no active subscription")
            return False
        
        # Check if seat count needs to increase
        if org.active_member_count <= org.seat_count:
            print(f"ℹ️  No update needed: members ({org.active_member_count}) <= seats ({org.seat_count})")
            return False
        
        # Update needed
        new_seat_count = org.active_member_count
        print(f"📝 Updating Stripe seats: {org.seat_count} → {new_seat_count}")
        
        try:
            # Update Stripe subscription quantity
            updated_subscription = stripe.Subscription.modify(
                org.stripe_subscription_id,
                items=[
                    {
                        "id": org.stripe_subscription_item_id,
                        "quantity": new_seat_count,
                    }
                ],
                proration_behavior="create_prorations",  # Pro-rate the change
            )
            
            print(f"✅ Stripe subscription updated")
            print(f"   New quantity: {updated_subscription['items']['data'][0]['quantity']}")
            print(f"   Status: {updated_subscription['status']}")
            print(f"   ⏳ Webhook will update DB seat_count")
            print(f"{'─'*60}\n")
            
            logger.info(f"Updated seats for organization {organization_id}: {org.seat_count} → {new_seat_count}")
            
            return True
            
        except stripe.error.StripeError as e:
            print(f"❌ Stripe update failed: {e}")
            logger.error(f"Failed to update Stripe seats for organization {organization_id}: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            logger.error(f"Unexpected error syncing seats for organization {organization_id}: {e}", exc_info=True)
            return False
    
    async def should_increase_seats(self, org: Organization) -> bool:
        """
        Check if seats should be increased based on member count
        
        Args:
            org: Organization object
            
        Returns:
            True if seats should be increased
        """
        # Only for Business plan
        if org.plan_type != "business":
            return False
        
        # Only if has active subscription
        if not org.stripe_subscription_id or not org.stripe_subscription_item_id:
            return False
        
        # Only if members exceed seats
        return org.active_member_count > org.seat_count


