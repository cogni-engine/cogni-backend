"""Webhook service for handling Stripe webhooks and subscription management"""
import logging
import json
from datetime import datetime, timezone
from typing import Optional
import stripe
from app.config import STRIPE_SECRET_KEY, STRIPE_PRICE_ID_PRO, STRIPE_PRICE_ID_BUSINESS, supabase
from app.features.billing.repositories.organizations import OrganizationRepository
from app.features.billing.repositories.stripe_events import StripeEventRepository
from app.features.billing.models.organization import OrganizationCreate, OrganizationUpdate
from app.features.billing.models.stripe_event import StripeEventCreate
from app.features.billing.domain import SubscriptionPlanType, SubscriptionStatus
from app.features.billing.services import OrganizationService

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY


class BillingWebhookService:
    """Service for handling Stripe payment and subscription webhooks"""
    
    def __init__(self, org_repo: OrganizationRepository, stripe_event_repo: StripeEventRepository):
        self.org_repo = org_repo
        self.stripe_event_repo = stripe_event_repo
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
            logger.warning(f"BillingWebhookService: No price_id provided, defaulting to PRO")
            return SubscriptionPlanType.PRO
        
        if price_id == STRIPE_PRICE_ID_PRO:
            return SubscriptionPlanType.PRO
        elif price_id == STRIPE_PRICE_ID_BUSINESS:
            return SubscriptionPlanType.BUSINESS
        else:
            logger.warning(f"BillingWebhookService: Unknown price_id {price_id}, defaulting to PRO")
            return SubscriptionPlanType.PRO
    
    async def _persist_raw_event(self, event_id: str, event_type: str, raw_event: dict) -> None:
        """
        Global Rule 2: Persist raw event first
        
        Args:
            event_id: Stripe event ID
            event_type: Stripe event type
            raw_event: Full Stripe event object
        """
        try:
            create_data = StripeEventCreate(
                stripe_event_id=event_id,
                type=event_type,
                payload=raw_event
            )
            await self.stripe_event_repo.create(create_data)
            logger.debug(f"BillingWebhookService: Persisted event {event_id} of type {event_type}")
        except Exception as e:
            # Log but don't fail - idempotency check will handle duplicates
            logger.warning(f"BillingWebhookService: Failed to persist event {event_id}: {e}")
    
    async def _check_idempotency(self, event_id: str) -> bool:
        """
        Global Rule 3: Ensure idempotency using stripe_event_id
        
        Returns:
            True if event was already processed, False otherwise
        """
        existing_event = await self.stripe_event_repo.find_by_stripe_event_id(event_id)
        if existing_event and existing_event.processed_at:
            logger.info(f"BillingWebhookService: Event {event_id} already processed at {existing_event.processed_at}, skipping")
            return True
        return False
    
    async def _mark_event_processed(self, event_id: str) -> None:
        """Mark event as processed by updating processed_at timestamp"""
        try:
            await self.stripe_event_repo.mark_as_processed(event_id)
            logger.debug(f"BillingWebhookService: Marked event {event_id} as processed")
        except Exception as e:
            logger.warning(f"BillingWebhookService: Failed to mark event {event_id} as processed: {e}")
    
    async def handle_webhook_event(self, event_type: str, event_data: dict, event_id: str, raw_event: dict) -> None:
        """
        Route webhook events to appropriate handlers
        
        Args:
            event_type: Stripe event type (e.g., 'checkout.session.completed')
            event_data: Stripe event data object
            event_id: Stripe event ID for idempotency
            raw_event: Full Stripe event object for persistence
        """
        logger.info(f"BillingWebhookService: Handling webhook event {event_type} (ID: {event_id})")
        
        # Global Rule 2: Persist raw event first
        await self._persist_raw_event(event_id, event_type, raw_event)
        
        # Global Rule 3: Ensure idempotency
        if await self._check_idempotency(event_id):
            logger.info(f"BillingWebhookService: Event {event_id} already processed, skipping")
            return
        
        try:
            if event_type == "checkout.session.completed":
                await self.handle_checkout_session_completed(event_data)
            
            elif event_type == "invoice.payment_succeeded":
                await self.handle_invoice_payment_succeeded(event_data)
            
            elif event_type == "invoice.payment_failed":
                await self.handle_invoice_payment_failed(event_data)
            
            elif event_type == "invoice.payment_action_required":
                await self.handle_invoice_payment_action_required(event_data)
            
            elif event_type == "customer.subscription.updated":
                await self.handle_subscription_updated(event_data)
            
            elif event_type == "customer.subscription.deleted":
                await self.handle_subscription_deleted(event_data)
            
            elif event_type == "charge.dispute.created":
                await self.handle_charge_dispute_created(event_data)
            
            else:
                # Global Rule 6: Return 200 even for ignored events
                logger.info(f"BillingWebhookService: Unhandled event type {event_type} (stored but ignored)")
        
        except Exception as e:
            logger.error(f"BillingWebhookService: Error handling event {event_type}: {e}", exc_info=True)
            raise
        finally:
            # Mark event as processed
            await self._mark_event_processed(event_id)
    
    async def handle_checkout_session_completed(self, session: dict) -> None:
        """
        Handle checkout.session.completed - Initial subscription creation
        
        This is the FIRST moment billing state is allowed to change.
        
        Preconditions:
        - Event has not been processed before (handled by idempotency check)
        - Session mode = subscription
        """
        logger.info(f"BillingWebhookService: Processing checkout.session.completed")
        
        # Precondition: Session mode = subscription
        if session.get("mode") != "subscription":
            logger.info(f"BillingWebhookService: Session mode is not 'subscription', skipping")
            return
        
        # Step 1: Extract organization_id from metadata
        metadata = session.get("metadata", {})
        organization_id = metadata.get("organization_id")
        
        if not organization_id:
            logger.warning(f"BillingWebhookService: No organization_id in metadata, cannot process")
            return
        
        # Step 2: Retrieve the Subscription object from Stripe
        subscription_id = session.get("subscription")
        if not subscription_id:
            logger.warning(f"BillingWebhookService: No subscription_id in checkout session")
            return
        
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
        except Exception as e:
            logger.error(f"BillingWebhookService: Failed to retrieve subscription {subscription_id}: {e}")
            raise
        
        # Step 3: Read subscription data
        price_id = subscription.get("items", {}).get("data", [{}])[0].get("price", {}).get("id")
        trial_end = subscription.get("trial_end")
        current_period_end = subscription.get("current_period_end")
        
        # Step 4: Map price.id → plan_type
        plan_type = self._get_plan_type_from_price_id(price_id)
        
        # Determine status
        if trial_end and trial_end > datetime.now(timezone.utc).timestamp():
            status = SubscriptionStatus.TRIALING
        else:
            status = SubscriptionStatus.ACTIVE
        
        # Convert timestamps to datetime
        trial_end_dt = None
        if trial_end:
            trial_end_dt = datetime.fromtimestamp(trial_end, tz=timezone.utc)
        
        current_period_end_dt = None
        if current_period_end:
            current_period_end_dt = datetime.fromtimestamp(current_period_end, tz=timezone.utc)
        
        # DB updates
        customer_id = session.get("customer")
        update_data = OrganizationUpdate(
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
            plan_type=plan_type,
            status=status,
            trial_end=trial_end_dt,
            current_period_end=current_period_end_dt,
            cancel_at_period_end=False
        )
        
        # Find organization by ID (from metadata)
        org = await self.org_repo.find_by_id(int(organization_id))
        if not org:
            logger.error(f"BillingWebhookService: Organization {organization_id} not found")
            return
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            logger.info(f"BillingWebhookService: Updated organization {org.id} from checkout.session.completed")
        else:
            logger.error(f"BillingWebhookService: Failed to update organization {org.id}")
    
    async def handle_invoice_payment_succeeded(self, invoice: dict) -> None:
        """
        Handle invoice.payment_succeeded - Confirms subscription is healthy
        
        This event is the ONLY authority that restores access after failure.
        
        Explicitly do NOT:
        - Change plan_type
        - Change seat_count
        - Assume this is the first payment
        """
        logger.info(f"BillingWebhookService: Processing invoice.payment_succeeded")
        
        subscription_id = invoice.get("subscription")
        if not subscription_id:
            logger.info("BillingWebhookService: Invoice has no subscription (one-time payment), skipping")
            return
        
        # Find organization
        org = await self.org_repo.find_by_stripe_subscription_id(subscription_id)
        if not org:
            logger.warning(f"BillingWebhookService: Organization not found for subscription {subscription_id}")
            return
        
        # Extract period_end from correct Stripe field path
        # Correct: invoice["lines"]["data"][0]["period"]["end"]
        period_end = None
        lines = invoice.get("lines", {}).get("data", [])
        if lines and len(lines) > 0:
            period = lines[0].get("period", {})
            period_end = period.get("end")
        
        if not period_end:
            # Fallback: try the wrong field (for backwards compatibility)
            period_end = invoice.get("period_end")
            if period_end:
                logger.warning(f"BillingWebhookService: Using fallback invoice.period_end (not recommended)")
        
        current_period_end_dt = None
        if period_end:
            current_period_end_dt = datetime.fromtimestamp(period_end, tz=timezone.utc)
        
        # DB updates
        update_data = OrganizationUpdate(
            status=SubscriptionStatus.ACTIVE,
            current_period_end=current_period_end_dt
        )
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            logger.info(f"BillingWebhookService: Updated organization {org.id} status to active")
        else:
            logger.error(f"BillingWebhookService: Failed to update organization {org.id}")
    
    async def handle_invoice_payment_failed(self, invoice: dict) -> None:
        """
        Handle invoice.payment_failed - Signals payment problem
        
        This event only WARNS, it does not punish.
        
        Explicitly do NOT:
        - Cancel the subscription
        - Downgrade the plan
        - Remove access immediately
        """
        logger.warning(f"BillingWebhookService: Processing invoice.payment_failed")
        
        subscription_id = invoice.get("subscription")
        if not subscription_id:
            logger.info("BillingWebhookService: Invoice has no subscription, skipping")
            return
        
        # Find organization
        org = await self.org_repo.find_by_stripe_subscription_id(subscription_id)
        if not org:
            logger.warning(f"BillingWebhookService: Organization not found for subscription {subscription_id}")
            return
        
        # DB updates
        update_data = OrganizationUpdate(
            status=SubscriptionStatus.PAST_DUE
        )
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            logger.info(f"BillingWebhookService: Updated organization {org.id} status to past_due")
        else:
            logger.error(f"BillingWebhookService: Failed to update organization {org.id}")
    
    async def handle_invoice_payment_action_required(self, invoice: dict) -> None:
        """
        Handle invoice.payment_action_required - Payment requires user action (3DS / SCA)
        
        Same handling as invoice.payment_failed
        
        UX expectation: User must fix payment via Checkout or Portal.
        """
        logger.warning(f"BillingWebhookService: Processing invoice.payment_action_required")
        
        subscription_id = invoice.get("subscription")
        if not subscription_id:
            logger.info("BillingWebhookService: Invoice has no subscription, skipping")
            return
        
        # Find organization
        org = await self.org_repo.find_by_stripe_subscription_id(subscription_id)
        if not org:
            logger.warning(f"BillingWebhookService: Organization not found for subscription {subscription_id}")
            return
        
        # DB updates
        update_data = OrganizationUpdate(
            status=SubscriptionStatus.PAST_DUE
        )
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            logger.info(f"BillingWebhookService: Updated organization {org.id} status to past_due")
        else:
            logger.error(f"BillingWebhookService: Failed to update organization {org.id}")
    
    async def handle_subscription_updated(self, subscription: dict) -> None:
        """
        Handle customer.subscription.updated - Configuration changes only
        
        This event reflects CONFIGURATION changes, not payment health.
        This event is often misused. Be careful.
        
        Explicitly do NOT:
        - Set status = active
        - Set status = canceled
        - React to price changes unless you intend to support plan switching
        """
        logger.info(f"BillingWebhookService: Processing customer.subscription.updated")
        
        subscription_id = subscription.get("id")
        if not subscription_id:
            logger.warning("BillingWebhookService: Missing subscription_id in subscription update event")
            return
        
        # Find organization
        org = await self.org_repo.find_by_stripe_subscription_id(subscription_id)
        if not org:
            logger.warning(f"BillingWebhookService: Organization not found for subscription {subscription_id}")
            return
        
        # Extract configuration data
        cancel_at_period_end = subscription.get("cancel_at_period_end", False)
        current_period_end = subscription.get("current_period_end")
        quantity = subscription.get("items", {}).get("data", [{}])[0].get("quantity", 1)
        
        current_period_end_dt = None
        if current_period_end:
            current_period_end_dt = datetime.fromtimestamp(current_period_end, tz=timezone.utc)
        
        # DB updates (selective - only configuration)
        update_data = OrganizationUpdate(
            cancel_at_period_end=cancel_at_period_end,
            current_period_end=current_period_end_dt,
            seat_count=quantity
        )
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            logger.info(f"BillingWebhookService: Updated organization {org.id} configuration")
        else:
            logger.error(f"BillingWebhookService: Failed to update organization {org.id}")
    
    async def handle_subscription_deleted(self, subscription: dict) -> None:
        """
        Handle customer.subscription.deleted - Subscription has ended
        
        This is the ONLY event that performs final downgrade.
        
        Explicitly do NOT:
        - Wait for another event
        - Keep paid access
        
        This is final.
        """
        logger.info(f"BillingWebhookService: Processing customer.subscription.deleted")
        
        subscription_id = subscription.get("id")
        if not subscription_id:
            logger.warning("BillingWebhookService: Missing subscription_id in subscription deleted event")
            return
        
        # Find organization
        org = await self.org_repo.find_by_stripe_subscription_id(subscription_id)
        if not org:
            logger.warning(f"BillingWebhookService: Organization not found for subscription {subscription_id}")
            return
        
        # DB updates - final downgrade
        update_data = OrganizationUpdate(
            status=SubscriptionStatus.CANCELED,
            plan_type=SubscriptionPlanType.FREE,
            seat_count=1,
            trial_end=None,
            current_period_end=None,
            cancel_at_period_end=False
        )
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            logger.info(f"BillingWebhookService: Set organization {org.id} to FREE plan after subscription deletion")
            
            # Auto-deactivate all non-owner members
            deactivated_count = await self.org_service.deactivate_non_owner_members(org.id)
            if deactivated_count > 0:
                logger.info(f"BillingWebhookService: Deactivated {deactivated_count} members for organization {org.id}")
        else:
            logger.error(f"BillingWebhookService: Failed to update organization {org.id}")
    
    async def handle_charge_dispute_created(self, dispute: dict) -> None:
        """
        Handle charge.dispute.created - Financial risk detected
        
        Notes:
        - Access should be read-only
        - Manual review may be required
        """
        logger.warning(f"BillingWebhookService: Processing charge.dispute.created")
        
        # Extract subscription_id via charge → invoice → subscription
        charge_id = dispute.get("charge")
        if not charge_id:
            logger.warning("BillingWebhookService: No charge_id in dispute")
            return
        
        try:
            charge = stripe.Charge.retrieve(charge_id)
            invoice_id = charge.get("invoice")
            if not invoice_id:
                logger.warning("BillingWebhookService: No invoice_id in charge")
                return
            
            invoice = stripe.Invoice.retrieve(invoice_id)
            subscription_id = invoice.get("subscription")
            if not subscription_id:
                logger.warning("BillingWebhookService: No subscription_id in invoice")
                return
        except Exception as e:
            logger.error(f"BillingWebhookService: Failed to retrieve charge/invoice: {e}")
            return
        
        # Find organization
        org = await self.org_repo.find_by_stripe_subscription_id(subscription_id)
        if not org:
            logger.warning(f"BillingWebhookService: Organization not found for subscription {subscription_id}")
            return
        
        # DB updates
        update_data = OrganizationUpdate(
            status=SubscriptionStatus.RESTRICTED
        )
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            logger.info(f"BillingWebhookService: Set organization {org.id} status to restricted")
        else:
            logger.error(f"BillingWebhookService: Failed to update organization {org.id}")
