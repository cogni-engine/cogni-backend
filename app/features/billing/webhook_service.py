import logging
from datetime import datetime, timezone
import stripe
from app.config import STRIPE_SECRET_KEY, STRIPE_PRICE_ID_PRO, STRIPE_PRICE_ID_BUSINESS, supabase
from app.features.billing.repositories.organizations import OrganizationRepository
from app.features.billing.repositories.stripe_events import StripeEventRepository
from app.features.billing.models.organization import OrganizationUpdate
from app.features.billing.models.stripe_event import StripeEventCreate
from app.features.billing.domain import SubscriptionPlanType, SubscriptionStatus
from app.features.billing.services import OrganizationService

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY


class BillingWebhookService:
    
    def __init__(self, org_repo: OrganizationRepository, stripe_event_repo: StripeEventRepository):
        self.org_repo = org_repo
        self.stripe_event_repo = stripe_event_repo
        self.org_service = OrganizationService(org_repo, supabase)
    
    def _get_plan_type_from_price_id(self, price_id: str | None) -> SubscriptionPlanType:
        if not price_id:
            logger.error("BillingWebhookService: No price_id provided, defaulting to FREE (unknown price should not grant access)")
            return SubscriptionPlanType.FREE
        
        if price_id == STRIPE_PRICE_ID_PRO:
            return SubscriptionPlanType.PRO
        elif price_id == STRIPE_PRICE_ID_BUSINESS:
            return SubscriptionPlanType.BUSINESS
        else:
            logger.error(f"BillingWebhookService: Unknown price_id {price_id}, defaulting to FREE (unknown price should not grant access)")
            return SubscriptionPlanType.FREE
    
    async def _persist_raw_event(self, event_id: str, event_type: str, raw_event: dict) -> None:
        try:
            create_data = StripeEventCreate(
                stripe_event_id=event_id,
                type=event_type,
                payload=raw_event
            )
            await self.stripe_event_repo.create(create_data)
            logger.debug(f"BillingWebhookService: Persisted event {event_id} of type {event_type}")
        except Exception:
            logger.error("BillingWebhookService: Failed to persist Stripe event — aborting", exc_info=True)
            raise
    
    async def _check_idempotency(self, event_id: str) -> bool:
        existing_event = await self.stripe_event_repo.find_by_stripe_event_id(event_id)
        if existing_event and existing_event.processed_at:
            logger.info(f"BillingWebhookService: Event {event_id} already processed at {existing_event.processed_at}, skipping")
            return True
        return False
    
    async def _mark_event_processed(self, event_id: str) -> None:
        try:
            await self.stripe_event_repo.mark_as_processed(event_id)
            logger.debug(f"BillingWebhookService: Marked event {event_id} as processed")
        except Exception:
            logger.error(f"BillingWebhookService: Failed to mark event {event_id} as processed", exc_info=True)
            # Don't raise - if marking as processed fails, we still want to continue
            # The event was already handled successfully at this point
    
    async def handle_webhook_event(self, event_type: str, event_data: dict, event_id: str, raw_event: dict) -> None:
        logger.debug(f"BillingWebhookService: Handling webhook event {event_type} (ID: {event_id})")
        
        # Global Rule 2: Persist raw event first
        await self._persist_raw_event(event_id, event_type, raw_event)
        
        # Global Rule 3: Ensure idempotency
        if await self._check_idempotency(event_id):
            logger.debug(f"BillingWebhookService: Event {event_id} already processed, skipping")
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
                logger.debug(f"BillingWebhookService: Unhandled event type {event_type} (stored but ignored)")
            
            # Only mark as processed after successful handling
            await self._mark_event_processed(event_id)
        
        except Exception as e:
            logger.error(f"BillingWebhookService: Error handling event {event_type}: {e}", exc_info=True)
            raise
    
    async def handle_checkout_session_completed(self, session: dict) -> None:
        logger.info("BillingWebhookService: Processing checkout.session.completed")
        
        # Precondition: Session mode = subscription
        if session.get("mode") != "subscription":
            return
        
        # Step 1: Extract organization_id from metadata
        metadata = session.get("metadata", {})
        organization_id = metadata.get("organization_id")
        
        if not organization_id:
            logger.warning("BillingWebhookService: No organization_id in metadata, cannot process")
            return
        
        # Step 2: Retrieve the Subscription object from Stripe
        subscription_id = session.get("subscription")
        if not subscription_id:
            logger.warning("BillingWebhookService: No subscription_id in checkout session")
            return
        
        try:
            subscription = stripe.Subscription.retrieve(
                subscription_id,
                expand=["items.data.price"]
            )
        except Exception:
            logger.error("BillingWebhookService: Failed to retrieve subscription {subscription_id}: {e}")
            raise
        
        # Step 3: Read subscription data
        items = subscription.get("items", {}).get("data", [])
        if len(items) != 1:
            logger.error(f"BillingWebhookService: Unexpected subscription items layout for {subscription_id}: {len(items)} items")
            raise ValueError(f"Expected exactly 1 subscription item, found {len(items)}")
        
        item = items[0]
        price_id = item.get("price", {}).get("id")
        quantity = item.get("quantity", 1)
        
        # Extract current_period_end from subscription item (new API: 2025-11-17.clover)
        current_period_end = item.get("current_period_end")
        
        # Step 4: Map price.id → plan_type
        plan_type = self._get_plan_type_from_price_id(price_id)
        
        # Determine status - no trials, so always ACTIVE
        status = SubscriptionStatus.ACTIVE
        
        # Convert timestamps to datetime
        current_period_end_dt = None
        if current_period_end:
            current_period_end_dt = datetime.fromtimestamp(current_period_end, tz=timezone.utc)
        
        # Derive cancel_at_period_end from cancel_at timestamp (new API: 2025-11-17.clover)
        cancel_at = subscription.get("cancel_at")
        cancel_at_period_end = False
        if cancel_at and current_period_end and cancel_at == current_period_end:
            cancel_at_period_end = True
        
        # DB updates
        customer_id = session.get("customer")
        update_data = OrganizationUpdate(
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
            plan_type=plan_type,
            status=status,
            seat_count=quantity,
            current_period_end=current_period_end_dt,
            cancel_at_period_end=cancel_at_period_end
        )
        
        # Find organization by ID (from metadata)
        org = await self.org_repo.find_by_id(int(organization_id))
        if not org:
            logger.error(f"BillingWebhookService: Organization {organization_id} not found")
            return
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            logger.info(f"BillingWebhookService: Updated organization {org.id} from checkout.session.completed - plan={plan_type.value}, status={status.value}, seats={quantity}")
        else:
            logger.error(f"BillingWebhookService: Failed to update organization {org.id}")
            raise ValueError(f"Failed to update organization {org.id}")
    
    async def handle_invoice_payment_succeeded(self, invoice: dict) -> None:
        logger.debug("BillingWebhookService: Processing invoice.payment_succeeded")
        
        # Extract subscription_id from nested parent structure (new API) or top-level (legacy)
        # New: invoice["parent"]["subscription_details"]["subscription"]
        # Legacy: invoice["subscription"]
        parent = invoice.get("parent", {})
        subscription_details = parent.get("subscription_details", {})
        subscription_id = subscription_details.get("subscription")
        
        # Fallback to legacy top-level field if not found in parent
        if not subscription_id:
            subscription_id = invoice.get("subscription")
        
        if not subscription_id:
            logger.info("BillingWebhookService: Invoice has no subscription (one-time payment), skipping")
            return
        
        # Extract customer_id from invoice
        customer_id = invoice.get("customer")
        if not customer_id:
            logger.error("BillingWebhookService: Invoice has no customer_id")
            raise ValueError("Invoice missing customer_id")
        
        # Find organization by customer_id (more reliable than subscription_id due to webhook timing)
        org = await self.org_repo.find_by_stripe_customer_id(customer_id)
        if not org:
            logger.error(f"BillingWebhookService: Organization not found for customer {customer_id}")
            raise ValueError(f"Organization not found for customer {customer_id} - webhook may be out of order, will retry")
        
        # Extract period_end and subscription_item_id from correct Stripe field path
        # Correct: invoice["lines"]["data"][0]["period"]["end"]
        # Correct: invoice["lines"]["data"][0]["parent"]["subscription_item_details"]["subscription_item"]
        period_end = None
        subscription_item_id = None
        lines = invoice.get("lines", {}).get("data", [])
        if lines and len(lines) > 0:
            line_item = lines[0]
            period = line_item.get("period", {})
            period_end = period.get("end")
            # Extract subscription_item from nested parent structure
            parent = line_item.get("parent", {})
            subscription_item_details = parent.get("subscription_item_details", {})
            subscription_item_id = subscription_item_details.get("subscription_item")
        
        if not period_end:
            # Fallback: try the wrong field (for backwards compatibility)
            period_end = invoice.get("period_end")
            if period_end:
                logger.warning("BillingWebhookService: Using fallback invoice.period_end (not recommended)")
        
        current_period_end_dt = None
        if period_end:
            current_period_end_dt = datetime.fromtimestamp(period_end, tz=timezone.utc)
        
        # DB updates
        update_data = OrganizationUpdate(
            status=SubscriptionStatus.ACTIVE,
            current_period_end=current_period_end_dt,
            stripe_subscription_item_id=subscription_item_id
        )
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            logger.info(f"BillingWebhookService: Updated organization {org.id} status to active")
        else:
            logger.error(f"BillingWebhookService: Failed to update organization {org.id}")
    
    async def handle_invoice_payment_failed(self, invoice: dict) -> None:
        logger.warning("BillingWebhookService: Processing invoice.payment_failed")
        
        # Extract subscription_id from nested parent structure (new API) or top-level (legacy)
        parent = invoice.get("parent", {})
        subscription_details = parent.get("subscription_details", {})
        subscription_id = subscription_details.get("subscription")
        
        # Fallback to legacy top-level field if not found in parent
        if not subscription_id:
            subscription_id = invoice.get("subscription")
        
        if not subscription_id:
            logger.info("BillingWebhookService: Invoice has no subscription, skipping")
            return
        
        # Extract customer_id from invoice
        customer_id = invoice.get("customer")
        if not customer_id:
            logger.error("BillingWebhookService: Invoice has no customer_id")
            raise ValueError("Invoice missing customer_id")
        
        # Find organization by customer_id (more reliable than subscription_id due to webhook timing)
        org = await self.org_repo.find_by_stripe_customer_id(customer_id)
        if not org:
            logger.error(f"BillingWebhookService: Organization not found for customer {customer_id}")
            raise ValueError(f"Organization not found for customer {customer_id} - webhook may be out of order, will retry")
        
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
        logger.warning("BillingWebhookService: Processing invoice.payment_action_required")
        
        # Extract subscription_id from nested parent structure (new API) or top-level (legacy)
        parent = invoice.get("parent", {})
        subscription_details = parent.get("subscription_details", {})
        subscription_id = subscription_details.get("subscription")
        
        if not subscription_id:
            logger.info("BillingWebhookService: Invoice has no subscription, skipping")
            return
        
        # Extract customer_id from invoice
        customer_id = invoice.get("customer")
        if not customer_id:
            logger.error("BillingWebhookService: Invoice has no customer_id")
            raise ValueError("Invoice missing customer_id")
        
        # Find organization by customer_id (more reliable than subscription_id due to webhook timing)
        org = await self.org_repo.find_by_stripe_customer_id(customer_id)
        if not org:
            logger.error(f"BillingWebhookService: Organization not found for customer {customer_id}")
            raise ValueError(f"Organization not found for customer {customer_id} - webhook may be out of order, will retry")
        
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
        logger.debug("BillingWebhookService: Processing customer.subscription.updated")
        
        subscription_id = subscription.get("id")
        if not subscription_id:
            logger.warning("BillingWebhookService: Missing subscription_id in subscription update event")
            return
        
        # Find organization
        org = await self.org_repo.find_by_stripe_subscription_id(subscription_id)
        if not org:
            logger.warning(f"BillingWebhookService: Organization not found for subscription {subscription_id}")
            return
        
        # Guard against multiple subscription items
        items = subscription.get("items", {}).get("data", [])
        if len(items) != 1:
            logger.error(f"BillingWebhookService: Unexpected subscription items layout for {subscription_id}: {len(items)} items")
            return  # Skip update if unexpected layout
        
        item = items[0]
        quantity = item.get("quantity", 1)
        
        # Extract price_id to detect plan changes
        price = item.get("price", {})
        price_id = price.get("id")
        new_plan_type = self._get_plan_type_from_price_id(price_id)
        
        # Extract current_period_end from subscription item (new API: 2025-11-17.clover)
        current_period_end = item.get("current_period_end")
        
        current_period_end_dt = None
        if current_period_end:
            current_period_end_dt = datetime.fromtimestamp(current_period_end, tz=timezone.utc)
        
        # Derive cancel_at_period_end from cancel_at timestamp (new API: 2025-11-17.clover)
        # If cancel_at matches current_period_end, it means cancel at period end is enabled
        cancel_at = subscription.get("cancel_at")
        cancel_at_period_end = False
        if cancel_at and current_period_end and cancel_at == current_period_end:
            cancel_at_period_end = True
        
        # Check if plan changed from BUSINESS to PRO
        old_plan_type = org.plan_type
        plan_changed = old_plan_type != new_plan_type
        downgraded_to_pro = (old_plan_type == SubscriptionPlanType.BUSINESS and 
                             new_plan_type == SubscriptionPlanType.PRO)
        
        # DB updates (selective - only configuration)
        update_data = OrganizationUpdate(
            plan_type=new_plan_type,  # Include plan_type in updates
            cancel_at_period_end=cancel_at_period_end,
            current_period_end=current_period_end_dt,
            seat_count=quantity
        )
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            if plan_changed:
                logger.info(f"BillingWebhookService: Plan changed for organization {org.id}: {old_plan_type.value} → {new_plan_type.value}, seats={quantity}, cancel_at_period_end={cancel_at_period_end}")
            else:
                logger.info(f"BillingWebhookService: Updated organization {org.id} configuration - seats={quantity}, cancel_at_period_end={cancel_at_period_end}")
            
            # Handle downgrade from BUSINESS to PRO - deactivate excess members
            if downgraded_to_pro:
                logger.info(f"BillingWebhookService: Handling BUSINESS → PRO downgrade for organization {org.id}")
                deactivated_count = await self.org_service.deactivate_non_owner_members(org.id)
                if deactivated_count > 0:
                    logger.info(f"BillingWebhookService: Deactivated {deactivated_count} members for organization {org.id} after downgrade to PRO")
        else:
            logger.error(f"BillingWebhookService: Failed to update organization {org.id}")
            raise ValueError(f"Failed to update organization {org.id}")
    
    async def handle_subscription_deleted(self, subscription: dict) -> None:
        logger.info("BillingWebhookService: Processing customer.subscription.deleted - final downgrade")
        
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
            status=SubscriptionStatus.ACTIVE,
            plan_type=SubscriptionPlanType.FREE,
            seat_count=1,
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
            raise ValueError(f"Failed to update organization {org.id}")
    
    async def handle_charge_dispute_created(self, dispute: dict) -> None:
        logger.warning("BillingWebhookService: Processing charge.dispute.created")
        
        # Extract subscription_id via charge → invoice → subscription
        charge_id = dispute.get("charge")
        if not charge_id:
            logger.warning("BillingWebhookService: No charge_id in dispute")
            return
        
        try:
            charge = stripe.Charge.retrieve(charge_id, expand=["invoice"])
            invoice_id = charge.get("invoice")
            if not invoice_id:
                logger.warning("BillingWebhookService: No invoice_id in charge")
                return
            
            # If invoice is expanded, use it directly; otherwise retrieve
            if isinstance(invoice_id, dict):
                invoice = invoice_id
            else:
                invoice = stripe.Invoice.retrieve(invoice_id, expand=["subscription"])
            
            # Extract subscription_id from nested parent structure (new API) or top-level (legacy)
            parent = invoice.get("parent", {})
            subscription_details = parent.get("subscription_details", {})
            subscription_id = subscription_details.get("subscription")
            
            # Fallback to legacy top-level field if not found in parent
            if not subscription_id:
                subscription_id = invoice.get("subscription")
            
            if not subscription_id:
                logger.warning("BillingWebhookService: No subscription_id in invoice")
                return
            
            # Extract customer_id from invoice
            customer_id = invoice.get("customer")
            if not customer_id:
                logger.error("BillingWebhookService: Invoice has no customer_id")
                raise ValueError("Invoice missing customer_id")
        except Exception as e:
            logger.error(f"BillingWebhookService: Failed to retrieve charge/invoice: {e}", exc_info=True)
            raise
        
        # Find organization by customer_id (more reliable than subscription_id due to webhook timing)
        org = await self.org_repo.find_by_stripe_customer_id(customer_id)
        if not org:
            logger.error(f"BillingWebhookService: Organization not found for customer {customer_id}")
            raise ValueError(f"Organization not found for customer {customer_id} - webhook may be out of order, will retry")
        
        # DB updates
        update_data = OrganizationUpdate(
            status=SubscriptionStatus.RESTRICTED
        )
        
        updated_org = await self.org_repo.update(org.id, update_data)
        if updated_org:
            logger.warning(f"BillingWebhookService: Set organization {org.id} status to restricted due to dispute")
        else:
            logger.error(f"BillingWebhookService: Failed to update organization {org.id}")
            raise ValueError(f"Failed to update organization {org.id}")