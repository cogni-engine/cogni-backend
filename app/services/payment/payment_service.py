"""Payment service for handling Stripe webhooks and subscription management"""
import logging
import json
from datetime import datetime, timezone
import stripe
from app.config import STRIPE_SECRET_KEY, STRIPE_PRICE_ID_PRO, STRIPE_PRICE_ID_BUSINESS, supabase
from app.infra.supabase.repositories.organizations import OrganizationRepository
from app.models.organization import OrganizationCreate, OrganizationUpdate, SubscriptionPlanType
from app.services.organizations import OrganizationService

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY


class PaymentService:
    """Service for handling Stripe payment and subscription webhooks"""
    
    def __init__(self, org_repo: OrganizationRepository):
        self.org_repo = org_repo
        self.org_service = OrganizationService(org_repo, supabase)
    
    def _get_plan_type_from_price_id(self, price_id: str | None) -> SubscriptionPlanType:
        """
        Determine plan type from Stripe price ID
        
        Args:
            price_id: Stripe price ID (can be None)
            
        Returns:
            SubscriptionPlanType based on price_id
        """
        if not price_id:
            print(f"   ⚠️  No price_id provided, defaulting to PRO")
            return SubscriptionPlanType.PRO
        
        print(f"   🔍 Determining plan type from price_id: {price_id}")
        
        if price_id == STRIPE_PRICE_ID_PRO:
            print(f"   ✅ Matched PRO plan")
            return SubscriptionPlanType.PRO
        elif price_id == STRIPE_PRICE_ID_BUSINESS:
            print(f"   ✅ Matched BUSINESS plan")
            return SubscriptionPlanType.BUSINESS
        else:
            print(f"   ⚠️  Unknown price_id, defaulting to PRO")
            logger.warning(f"PaymentService: Unknown price_id {price_id}, defaulting to PRO")
            return SubscriptionPlanType.PRO
    
    async def handle_webhook_event(self, event_type: str, event_data: dict) -> None:
        """
        Route webhook events to appropriate handlers
        
        Args:
            event_type: Stripe event type (e.g., 'checkout.session.completed')
            event_data: Stripe event data object
        """
        print(f"\n{'='*60}")
        print(f"🔔 PAYMENT SERVICE: Handling webhook event")
        print(f"   Event Type: {event_type}")
        print(f"   Event Data Keys: {list(event_data.keys())}")
        print(f"{'='*60}\n")
        
        logger.info(f"PaymentService: Handling webhook event {event_type}")
        logger.debug(f"Event data: {json.dumps(event_data, indent=2, default=str)}")
        
        try:
            if event_type == "checkout.session.completed":
                await self.handle_checkout_session_completed(event_data)
            
            elif event_type == "customer.subscription.created":
                # subscription.created fires on first checkout
                # Treat it the same as subscription.updated
                await self.handle_subscription_updated(event_data)
            
            elif event_type == "customer.subscription.updated":
                await self.handle_subscription_updated(event_data)
            
            elif event_type == "customer.subscription.deleted":
                await self.handle_subscription_deleted(event_data)
            
            elif event_type == "invoice.payment_succeeded":
                await self.handle_invoice_payment_succeeded(event_data)
            
            elif event_type == "invoice.payment_failed":
                await self.handle_invoice_payment_failed(event_data)
            
            else:
                print(f"⚠️  Unhandled event type: {event_type}")
                logger.info(f"PaymentService: Unhandled event type {event_type}")
        
        except Exception as e:
            print(f"\n❌ ERROR in PaymentService.handle_webhook_event:")
            print(f"   Event Type: {event_type}")
            print(f"   Error: {str(e)}")
            print(f"{'='*60}\n")
            logger.error(f"PaymentService: Error handling event {event_type}: {e}", exc_info=True)
            raise
    
    async def handle_checkout_session_completed(self, session: dict) -> None:
        """
        Handle checkout.session.completed - incomplete event
        
        Note: checkout.session.completed is an incomplete event.
        customer or subscription may be missing.
        The master event is subscription.updated, which will handle the actual processing.
        This handler only logs the event and creates a minimal organization if needed.
        """
        session_id = session.get('id', 'unknown')
        print(f"\n{'─'*60}")
        print(f"📝 Processing checkout.session.completed (incomplete event)")
        print(f"   Session ID: {session_id}")
        print(f"{'─'*60}")
        
        logger.info(f"PaymentService: Processing checkout.session.completed for session {session_id}")
        
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        
        print(f"   Customer ID: {customer_id}")
        print(f"   Subscription ID: {subscription_id}")
        
        # checkout.session.completed is incomplete - customer/subscription may be missing
        if not customer_id:
            print(f"   ⚠️  WARNING: No customer_id in checkout.session.completed")
            print(f"   ℹ️  This is expected - subscription.updated will handle the actual processing")
            logger.info(f"PaymentService: checkout.session.completed has no customer_id (incomplete event)")
            return
        
        if not subscription_id:
            print(f"   ⚠️  WARNING: No subscription_id in checkout.session.completed")
            print(f"   ℹ️  This is expected - subscription.updated will handle the actual processing")
            logger.info(f"PaymentService: checkout.session.completed has no subscription_id (incomplete event)")
            return
        
        # If we have both, check if organization exists, if not create a minimal one
        # The actual subscription details will be updated by subscription.updated
        print(f"   🔍 Checking if organization exists for customer {customer_id}...")
        org = await self.org_repo.find_by_stripe_customer_id(customer_id)
        
        if not org:
            print(f"   📝 Creating minimal organization (will be updated by subscription.updated)...")
            logger.info(f"PaymentService: Creating minimal organization for customer {customer_id}")
            
            # Create minimal organization - subscription.updated will fill in the details
            org_name = f"Organization {customer_id[:8]}"
            create_data = OrganizationCreate(
                name=org_name,
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
                seat_count=1,
                active_member_count=0,
                plan_type=SubscriptionPlanType.PRO  # Will be updated by subscription.updated
            )
            
            org = await self.org_repo.create(create_data)
            print(f"   ✅ Created minimal organization {org.id}")
            print(f"      - Name: {org.name}")
            print(f"      - Customer ID: {org.stripe_customer_id}")
            print(f"      - Subscription ID: {org.stripe_subscription_id}")
            print(f"   ℹ️  Full details will be updated by subscription.updated event")
            logger.info(f"PaymentService: Created minimal organization {org.id}, waiting for subscription.updated")
        else:
            print(f"   ✅ Organization already exists: ID={org.id}")
            print(f"   ℹ️  subscription.updated will update the details")
            logger.info(f"PaymentService: Organization {org.id} exists, subscription.updated will update it")
        
        print(f"{'─'*60}\n")
    
    async def handle_subscription_updated(self, subscription: dict) -> None:
        """
        Handle customer.subscription.updated and customer.subscription.created - MASTER EVENT
        
        This is the master event for subscription changes:
        - Initial subscription creation (subscription.created)
        - Plan changes
        - Seat/quantity changes
        - Cancellation scheduled
        - Status changes
        
        Note: Does NOT update current_period_end (that's handled by invoice.payment_succeeded)
        """
        subscription_id = subscription.get('id', 'unknown')
        print(f"\n{'─'*60}")
        print(f"📝 Processing customer.subscription.updated/created (MASTER EVENT)")
        print(f"   Subscription ID: {subscription_id}")
        print(f"{'─'*60}")
        
        logger.info(f"PaymentService: Processing customer.subscription.updated for subscription {subscription_id}")
        logger.debug(f"PaymentService: Subscription data: {json.dumps(subscription, indent=2, default=str)}")
        
        customer_id = subscription.get("customer")
        print(f"   Customer ID: {customer_id}")
        
        if not subscription_id:
            print(f"   ⚠️  WARNING: Missing subscription_id")
            logger.warning("PaymentService: Missing subscription_id in subscription update event")
            return
        
        # Find organization by subscription ID or customer ID
        print(f"   🔍 Looking up organization...")
        org = await self.org_repo.find_by_stripe_subscription_id(subscription_id)
        if not org and customer_id:
            print(f"   🔍 Not found by subscription_id, trying customer_id...")
            org = await self.org_repo.find_by_stripe_customer_id(customer_id)
        
        if not org:
            print(f"   ⚠️  WARNING: Organization not found for subscription {subscription_id}")
            print(f"   📝 Creating new organization...")
            logger.warning(f"PaymentService: Organization not found, creating new one for subscription {subscription_id}")
            
            # Create new organization if it doesn't exist
            org_name = f"Organization {customer_id[:8] if customer_id else subscription_id[:8]}"
            create_data = OrganizationCreate(
                name=org_name,
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
                seat_count=1,
                active_member_count=0,
                plan_type=SubscriptionPlanType.PRO  # Will be updated below
            )
            org = await self.org_repo.create(create_data)
            print(f"   ✅ Created organization {org.id}")
        
        print(f"   ✅ Found organization: ID={org.id}, Name={org.name}")
        
        # Extract updated information
        subscription_item_id = None
        seat_count = 1
        price_id = None
        
        if subscription.get("items", {}).get("data"):
            item = subscription["items"]["data"][0]
            subscription_item_id = item.get("id")
            seat_count = item.get("quantity", 1)
            price_id = item.get("price", {}).get("id")
            print(f"   Subscription Item ID: {subscription_item_id}")
            print(f"   Seat Count: {seat_count}")
            print(f"   Price ID: {price_id}")
        
        # Determine plan type from price_id (not metadata)
        plan_type = self._get_plan_type_from_price_id(price_id)
        print(f"   Plan Type: {plan_type.value}")
        
        # Check both cancel_at_period_end (old API) and cancel_at (new API)
        cancel_at_period_end = subscription.get("cancel_at_period_end")
        cancel_at = subscription.get("cancel_at")  # Unix timestamp for scheduled cancellation
        
        # Stripe uses cancel_at for Customer Portal cancellations
        # If cancel_at is set, treat it as cancel_at_period_end=True
        if cancel_at is not None:
            print(f"   Cancel At: {cancel_at} (scheduled cancellation detected)")
            cancel_at_period_end = True  # Override to True
        
        print(f"   Cancel at Period End: {cancel_at_period_end}")
        
        # Extract current_period_end from subscription
        # Try subscription level first, then fall back to item level
        current_period_end = None
        
        # Method 1: From subscription object directly
        if subscription.get("current_period_end"):
            current_period_end = datetime.fromtimestamp(
                subscription["current_period_end"], tz=timezone.utc
            )
            print(f"   Current Period End: {current_period_end} (from subscription)")
        # Method 2: From subscription items
        elif subscription.get("items", {}).get("data") and len(subscription["items"]["data"]) > 0:
            item_period_end = subscription["items"]["data"][0].get("current_period_end")
            if item_period_end:
                current_period_end = datetime.fromtimestamp(item_period_end, tz=timezone.utc)
                print(f"   Current Period End: {current_period_end} (from item)")
        
        if not current_period_end:
            print(f"   ⚠️  No current_period_end found in subscription or items")
        
        print(f"   📝 Updating organization...")
        update_data = OrganizationUpdate(
            stripe_subscription_id=subscription_id,  # Ensure it's set
            stripe_subscription_item_id=subscription_item_id,
            seat_count=seat_count,
            plan_type=plan_type,
            cancel_at_period_end=cancel_at_period_end,
            current_period_end=current_period_end  # Set from subscription
        )
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            print(f"   ✅ Successfully updated organization {org.id}")
            print(f"      - Subscription ID: {updated_org.stripe_subscription_id}")
            print(f"      - Seat Count: {updated_org.seat_count}")
            print(f"      - Plan Type: {updated_org.plan_type.value}")
            print(f"      - Cancel at Period End: {updated_org.cancel_at_period_end}")
            print(f"      - Current Period End: {updated_org.current_period_end}")
            logger.info(f"PaymentService: Updated organization {org.id} subscription details")
        else:
            print(f"   ❌ Failed to update organization")
            logger.error(f"PaymentService: Failed to update organization {org.id}")
        
        print(f"{'─'*60}\n")
    
    async def handle_subscription_deleted(self, subscription: dict) -> None:
        """
        Handle customer.subscription.deleted - cancellation completed
        
        Best practice (like Slack/Linear/Notion):
        - Set plan_type = FREE
        - Set seat_count = 1
        - Keep stripe_subscription_id for analytics
        - Clear subscription_item_id and cancel_at_period_end
        """
        subscription_id = subscription.get('id', 'unknown')
        print(f"\n{'─'*60}")
        print(f"📝 Processing customer.subscription.deleted")
        print(f"   Subscription ID: {subscription_id}")
        print(f"{'─'*60}")
        
        logger.info(f"PaymentService: Processing customer.subscription.deleted for subscription {subscription_id}")
        
        if not subscription_id:
            print(f"   ⚠️  WARNING: Missing subscription_id")
            logger.warning("PaymentService: Missing subscription_id in subscription deleted event")
            return
        
        print(f"   🔍 Looking up organization...")
        org = await self.org_repo.find_by_stripe_subscription_id(subscription_id)
        
        if not org:
            print(f"   ⚠️  WARNING: Organization not found for subscription {subscription_id}")
            logger.warning(f"PaymentService: Organization not found for subscription {subscription_id}")
            return
        
        print(f"   ✅ Found organization: ID={org.id}, Name={org.name}")
        print(f"   📝 Setting organization to FREE plan...")
        print(f"   ℹ️  Keeping current_period_end for UI display and analytics")
        
        # Set to FREE plan, keep subscription_id and current_period_end
        # current_period_end is KEPT because:
        # - Users can use the plan until period end
        # - UI needs to show "Your plan will end on 2025/10/01"
        # - Analytics needs it for period calculations
        # - Linear/Notion also keep it
        update_data = OrganizationUpdate(
            plan_type=SubscriptionPlanType.FREE,
            seat_count=1,
            stripe_subscription_item_id=None,  # Clear item ID
            cancel_at_period_end=False
            # stripe_subscription_id is KEPT for analytics
            # stripe_customer_id is KEPT for reactivation
            # current_period_end is KEPT for UI display and analytics
        )
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            print(f"   ✅ Successfully updated organization {org.id} to FREE plan")
            print(f"      - Plan Type: {updated_org.plan_type.value}")
            print(f"      - Seat Count: {updated_org.seat_count}")
            print(f"      - Subscription ID (kept): {updated_org.stripe_subscription_id}")
            print(f"      - Customer ID (kept): {updated_org.stripe_customer_id}")
            print(f"      - Current Period End (kept): {updated_org.current_period_end}")
            logger.info(f"PaymentService: Set organization {org.id} to FREE plan after subscription deletion")
            
            # Auto-deactivate all non-owner members (free plan = 1 seat = owner only)
            print(f"\n   🔄 Auto-deactivating non-owner members...")
            deactivated_count = await self.org_service.deactivate_non_owner_members(org.id)
            
            if deactivated_count > 0:
                print(f"   ✅ Deactivated {deactivated_count} non-owner member(s)")
                logger.info(f"PaymentService: Deactivated {deactivated_count} members for organization {org.id}")
            else:
                print(f"   ℹ️  No members to deactivate (organization only had owner)")
        else:
            print(f"   ❌ Failed to update organization")
            logger.error(f"PaymentService: Failed to update organization {org.id}")
        
        print(f"{'─'*60}\n")
    
    async def handle_invoice_payment_succeeded(self, invoice: dict) -> None:
        """
        Handle invoice.payment_succeeded - renewal success
        
        This handler ONLY updates current_period_end.
        Plan changes and seat changes are handled by subscription.updated.
        
        Correct Stripe field path:
        invoice["lines"]["data"][0]["period"]["end"]
        NOT invoice.period_end
        """
        invoice_id = invoice.get('id', 'unknown')
        print(f"\n{'─'*60}")
        print(f"📝 Processing invoice.payment_succeeded (renewal)")
        print(f"   Invoice ID: {invoice_id}")
        print(f"{'─'*60}")
        
        logger.info(f"PaymentService: Processing invoice.payment_succeeded for invoice {invoice_id}")
        
        subscription_id = invoice.get("subscription")
        print(f"   Subscription ID: {subscription_id}")
        
        if not subscription_id:
            print(f"   ℹ️  Invoice has no subscription (one-time payment), skipping")
            logger.info("PaymentService: Invoice has no subscription (one-time payment)")
            return
        
        print(f"   🔍 Looking up organization...")
        org = await self.org_repo.find_by_stripe_subscription_id(subscription_id)
        
        if not org:
            print(f"   ⚠️  WARNING: Organization not found for subscription {subscription_id}")
            logger.warning(f"PaymentService: Organization not found for subscription {subscription_id}")
            return
        
        print(f"   ✅ Found organization: ID={org.id}, Name={org.name}")
        
        # Extract period_end from correct Stripe field path
        # Correct: invoice["lines"]["data"][0]["period"]["end"]
        # Wrong: invoice.period_end
        period_end = None
        lines = invoice.get("lines", {}).get("data", [])
        
        if lines and len(lines) > 0:
            period = lines[0].get("period", {})
            period_end = period.get("end")
            print(f"   🔍 Extracted period_end from invoice.lines.data[0].period.end")
        else:
            print(f"   ⚠️  No lines data in invoice")
        
        if not period_end:
            # Fallback: try the wrong field (for backwards compatibility)
            period_end = invoice.get("period_end")
            if period_end:
                print(f"   ⚠️  Using fallback invoice.period_end (not recommended)")
                logger.warning(f"PaymentService: Using fallback invoice.period_end for invoice {invoice_id}")
        
        if period_end:
            current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
            print(f"   📝 Updating period end to: {current_period_end}")
            print(f"   ℹ️  Only updating current_period_end (plan/seat changes handled by subscription.updated)")
            
            update_data = OrganizationUpdate(
                current_period_end=current_period_end
            )
            
            updated_org = await self.org_repo.update(org.id, update_data)
            if updated_org:
                print(f"   ✅ Successfully updated period end for organization {org.id}")
                print(f"      - New Period End: {updated_org.current_period_end}")
                logger.info(f"PaymentService: Updated period end for organization {org.id}")
            else:
                print(f"   ❌ Failed to update organization")
                logger.error(f"PaymentService: Failed to update organization {org.id}")
        else:
            print(f"   ⚠️  No period_end found in invoice, skipping update")
            logger.warning(f"PaymentService: No period_end found in invoice {invoice_id}")
        
        print(f"{'─'*60}\n")
    
    async def handle_invoice_payment_failed(self, invoice: dict) -> None:
        """Handle invoice.payment_failed - payment failed"""
        invoice_id = invoice.get('id', 'unknown')
        print(f"\n{'─'*60}")
        print(f"⚠️  Processing invoice.payment_failed")
        print(f"   Invoice ID: {invoice_id}")
        print(f"{'─'*60}")
        
        logger.warning(f"PaymentService: Processing invoice.payment_failed for invoice {invoice_id}")
        
        subscription_id = invoice.get("subscription")
        customer_id = invoice.get("customer")
        
        print(f"   Subscription ID: {subscription_id}")
        print(f"   Customer ID: {customer_id}")
        
        if not subscription_id:
            print(f"   ℹ️  Invoice has no subscription, skipping")
            logger.info("PaymentService: Invoice has no subscription")
            return
        
        print(f"   🔍 Looking up organization...")
        org = await self.org_repo.find_by_stripe_subscription_id(subscription_id)
        if not org and customer_id:
            print(f"   🔍 Not found by subscription_id, trying customer_id...")
            org = await self.org_repo.find_by_stripe_customer_id(customer_id)
        
        if not org:
            print(f"   ⚠️  WARNING: Organization not found for subscription {subscription_id}")
            logger.warning(f"PaymentService: Organization not found for subscription {subscription_id}")
            return
        
        print(f"   ✅ Found organization: ID={org.id}, Name={org.name}")
        print(f"   ⚠️  PAYMENT FAILED for organization {org.id}")
        print(f"      - Subscription: {subscription_id}")
        print(f"      - Customer: {customer_id}")
        print(f"   💡 Note: Consider adding payment_failed_at field or status tracking")
        
        # Log payment failure - you might want to send notifications or update status
        logger.warning(f"PaymentService: Payment failed for organization {org.id}, subscription {subscription_id}")
        # Note: You might want to add a payment_failed_at field or status field to track this
        
        print(f"{'─'*60}\n")

