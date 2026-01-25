"""Billing API endpoints for subscription management and Stripe webhooks"""
import logging
import json
from fastapi import APIRouter, Depends, Request, HTTPException, Header
from fastapi.responses import Response
import stripe

from app.config import (
    supabase,
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
    CLIENT_URL,
)
from app.auth import get_current_user_id
from app.features.billing.repositories.organizations import OrganizationRepository
from app.features.billing.repositories.stripe_events import StripeEventRepository
from app.features.billing.service import BillingService
from app.features.billing.webhook_service import BillingWebhookService
from app.features.billing.schemas import (
    UpgradeToBusinessRequest,
    UpgradeToBusinessResponse,
    UpdateSeatsRequest,
    UpdateSeatsResponse,
    PurchasePlanRequest,
    PurchasePlanResponse,
    CreatePortalSessionRequest,
    CreatePortalSessionResponse,
)

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY

# Create routers
billing_router = APIRouter(prefix="/api/billing", tags=["billing"])
stripe_router = APIRouter(prefix="/api/stripe", tags=["stripe"])


# ============================================================================
# STRIPE WEBHOOK ENDPOINT
# ============================================================================

async def verify_webhook_signature(payload: bytes, signature: str) -> dict:
    """Verify Stripe webhook signature"""
    print(f"\n{'='*60}")
    print(f"🔐 Verifying webhook signature...")
    print(f"{'='*60}")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, STRIPE_WEBHOOK_SECRET
        )
        print(f"✅ Signature verified successfully")
        print(f"   Event ID: {event.get('id', 'unknown')}")
        logger.info(f"Stripe webhook signature verified for event {event.get('id')}")
        return event
    except ValueError as e:
        print(f"❌ Invalid payload: {e}")
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        print(f"❌ Invalid signature: {e}")
        logger.error(f"Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")


@stripe_router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="stripe-signature")
):
    """
    Stripe webhook endpoint to handle subscription events
    
    Handles:
    - checkout.session.completed: Initial subscription confirmed
    - invoice.payment_succeeded: Payment succeeded
    - invoice.payment_failed: Payment failed
    - invoice.payment_action_required: Payment action required
    - customer.subscription.updated: Configuration changes
    - customer.subscription.deleted: Subscription deleted
    - charge.dispute.created: Dispute created
    """
    print(f"\n\n{'#'*60}")
    print(f"# STRIPE WEBHOOK RECEIVED")
    print(f"{'#'*60}")
    
    # Get raw payload
    payload = await request.body()
    print(f"📦 Payload size: {len(payload)} bytes")
    logger.info(f"Received Stripe webhook request (payload size: {len(payload)} bytes)")
    
    # Verify webhook signature
    try:
        event = await verify_webhook_signature(payload, stripe_signature)
    except HTTPException as e:
        print(f"❌ Signature verification failed: {e.detail}")
        raise
    
    event_type = event["type"]
    event_data = event["data"]["object"]
    event_id = event.get("id", "unknown")
    
    print(f"\n📋 Event Details:")
    print(f"   Event ID: {event_id}")
    print(f"   Event Type: {event_type}")
    print(f"   Created: {event.get('created', 'unknown')}")
    print(f"   Livemode: {event.get('livemode', 'unknown')}")
    
    logger.info(f"Processing Stripe webhook event: {event_type} (ID: {event_id})")
    logger.debug(f"Full event data: {json.dumps(event, indent=2, default=str)}")
    
    # Initialize webhook service
    org_repo = OrganizationRepository(supabase)
    stripe_event_repo = StripeEventRepository(supabase)
    webhook_service = BillingWebhookService(org_repo, stripe_event_repo)
    
    try:
        # Delegate to webhook service (pass event_id and raw_event)
        await webhook_service.handle_webhook_event(event_type, event_data, event_id, event)
        
        print(f"\n✅ Webhook processed successfully")
        print(f"{'#'*60}\n\n")
        logger.info(f"Successfully processed webhook event {event_type} (ID: {event_id})")
        
        return Response(status_code=200)
    
    except Exception as e:
        print(f"\n❌ ERROR processing webhook:")
        print(f"   Event Type: {event_type}")
        print(f"   Event ID: {event_id}")
        print(f"   Error: {str(e)}")
        print(f"   Error Type: {type(e).__name__}")
        print(f"{'#'*60}\n\n")
        
        logger.error(
            f"Error processing webhook {event_type} (ID: {event_id}): {e}",
            exc_info=True
        )
        
        # Return 200 to prevent Stripe from retrying
        # In production, you might want to log to a monitoring service
        # and return appropriate status codes based on error type
        return Response(status_code=200)


# ============================================================================
# BILLING ENDPOINTS
# ============================================================================

@billing_router.post("/upgrade-to-business", response_model=UpgradeToBusinessResponse)
async def upgrade_to_business(
    req: UpgradeToBusinessRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Upgrade from Pro to Business plan
    
    This endpoint:
    1. Validates the organization has a Pro subscription
    2. Updates the Stripe subscription to Business plan with current member count
    3. Stripe automatically handles proration
    4. Webhook (customer.subscription.updated) will update the DB
    
    Flow:
    - Pro (1 seat) → Business (N seats where N = active_member_count)
    - Stripe price change + quantity change in one API call
    
    Requires: Owner or Admin role
    """
    print(f"\n{'='*60}")
    print(f"🚀 Business Plan Upgrade Request")
    print(f"   User ID: {user_id}")
    print(f"   Organization ID: {req.organization_id}")
    print(f"{'='*60}")
    
    logger.info(f"Processing Business upgrade for organization {req.organization_id}")
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    billing_service = BillingService(org_repo, supabase)
    
    # Authorization & validation using single-responsibility methods
    org = await billing_service.get_organization_or_404(req.organization_id)
    print(f"✅ Organization: {org.name}")
    
    await billing_service.verify_user_is_owner_or_admin(req.organization_id, user_id)
    print(f"✅ User authorized")
    
    billing_service.validate_plan_type(
        org, "pro", 
        f"Can only upgrade from Pro plan. Current plan: {org.plan_type}"
    )
    billing_service.validate_subscription_exists(org)
    billing_service.validate_seat_count(org, req.seat_count)
    
    # Get Business plan price ID
    price_id = billing_service.get_price_id("business")
    
    # Update Stripe subscription (validated to exist by validate_subscription_exists)
    assert org.stripe_subscription_id is not None
    assert org.stripe_subscription_item_id is not None
    billing_service.modify_subscription(
        subscription_id=org.stripe_subscription_id,
        subscription_item_id=org.stripe_subscription_item_id,
        price_id=price_id,
        quantity=req.seat_count
    )
    
    logger.info(f"Successfully upgraded organization {org.id} to Business plan")
    
    return UpgradeToBusinessResponse(
        success=True,
        message=f"Successfully upgraded to Business plan with {req.seat_count} seats",
        new_plan="business",
        seat_count=req.seat_count
    )


@billing_router.post("/update-seats", response_model=UpdateSeatsResponse)
async def update_subscription_seats(
    req: UpdateSeatsRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Manually update subscription seat count
    
    This allows users to:
    - Add more seats before inviting members
    - Reduce seats (if no members would be affected)
    
    For Business plan only.
    Requires: Owner or Admin role
    """
    print(f"\n{'='*60}")
    print(f"🎫 Manual Seat Update Request")
    print(f"   User ID: {user_id}")
    print(f"   Organization ID: {req.organization_id}")
    print(f"   Requested Seats: {req.seat_count}")
    print(f"{'='*60}")
    
    logger.info(f"Manual seat update for organization {req.organization_id} to {req.seat_count} seats")
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    billing_service = BillingService(org_repo, supabase)
    
    # Authorization & validation using single-responsibility methods
    org = await billing_service.get_organization_or_404(req.organization_id)
    print(f"✅ Organization: {org.name}")
    
    await billing_service.verify_user_is_owner_or_admin(req.organization_id, user_id)
    print(f"✅ User authorized")
    
    billing_service.validate_plan_type(
        org, "business",
        "Seat updates are only available for Business plan"
    )
    billing_service.validate_subscription_exists(org)
    billing_service.validate_seat_count(org, req.seat_count)
    
    # Check if update is needed
    if req.seat_count == org.seat_count:
        print(f"ℹ️  Seat count unchanged: {req.seat_count}")
        return UpdateSeatsResponse(
            success=True,
            message="Seat count unchanged",
            old_seat_count=org.seat_count,
            new_seat_count=org.seat_count
        )
    
    old_seat_count = org.seat_count
    print(f"📝 Updating Stripe seats: {old_seat_count} → {req.seat_count}")
    
    # Update Stripe subscription quantity (validated to exist by validate_subscription_exists)
    assert org.stripe_subscription_id is not None
    assert org.stripe_subscription_item_id is not None
    billing_service.modify_subscription(
        subscription_id=org.stripe_subscription_id,
        subscription_item_id=org.stripe_subscription_item_id,
        quantity=req.seat_count
    )
    
    logger.info(f"Updated seats for organization {req.organization_id}: {old_seat_count} → {req.seat_count}")
    
    return UpdateSeatsResponse(
        success=True,
        message=f"Seats updated from {old_seat_count} to {req.seat_count}",
        old_seat_count=old_seat_count,
        new_seat_count=req.seat_count
    )


@billing_router.post("/purchase", response_model=PurchasePlanResponse)
async def purchase_plan(
    req: PurchasePlanRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Universal plan purchase endpoint - supports Pro and Business plans
    
    Purchases a plan for the user's existing organization (auto-created with user).
    
    This replaces the Next.js create-checkout-session and switch-to-team-billing routes
    """
    print(f"\n{'='*60}")
    print(f"🚀 Plan Purchase Request")
    print(f"   User ID: {user_id}")
    print(f"   Plan: {req.plan_id}")
    print(f"   Organization ID: {req.organization_id}")
    print(f"{'='*60}")
    
    logger.info(f"Processing {req.plan_id} plan purchase for user {user_id}")
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    billing_service = BillingService(org_repo, supabase)
    
    # Validate plan_id and get price
    price_id = billing_service.get_price_id(req.plan_id)
    
    # Authorization & validation using single-responsibility methods
    org = await billing_service.get_organization_or_404(req.organization_id)
    print(f"✅ Organization found: {org.name}")
    
    await billing_service.verify_user_is_owner(req.organization_id, user_id)
    print("✅ User verified as organization owner")
    
    billing_service.validate_no_active_subscription(org)
    print("✅ No active subscription found - proceeding with purchase")
    
    # Create or get Stripe customer
    customer_id = await billing_service.ensure_stripe_customer(org, user_id)
    
    # Determine quantity
    quantity = billing_service.calculate_quantity_for_plan(
        req.plan_id, 
        req.seat_count, 
        org
    )
    
    # Create Checkout Session
    print("📝 Creating Stripe Checkout Session...")
    print(f"   Price ID: {price_id}")
    print(f"   Quantity: {quantity}")
    
    session = billing_service.create_checkout_session(
        customer_id=customer_id,
        price_id=price_id,
        quantity=quantity,
        organization_id=org.id,
        plan_type=req.plan_id,
        user_id=user_id,
        return_url=f"{CLIENT_URL}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}"
    )
    
    print("✅ Checkout Session created")
    print(f"   Session ID: {session.id}")
    print(f"   Client Secret: {session.client_secret[:20]}...")
    print(f"{'='*60}\n")
    
    logger.info(f"Checkout session created for organization {org.id}: {session.id}")
    
    return PurchasePlanResponse(
        client_secret=session.client_secret,
        session_id=session.id,
        organization_id=org.id
    )


@billing_router.post("/portal-session", response_model=CreatePortalSessionResponse)
async def create_portal_session(
    req: CreatePortalSessionRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create Stripe Customer Portal session
    
    Allows customers to manage their subscription, payment methods, invoices, etc.
    This replaces the Next.js create-portal-session route.
    """
    print(f"\n{'='*60}")
    print(f"🔐 Customer Portal Session Request")
    print(f"   User ID: {user_id}")
    print(f"   Organization ID: {req.organization_id}")
    print(f"{'='*60}")
    
    logger.info(f"Creating portal session for organization {req.organization_id}")
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    billing_service = BillingService(org_repo, supabase)
    
    # Authorization & validation using single-responsibility methods
    org = await billing_service.get_organization_or_404(req.organization_id)
    print(f"✅ Organization: {org.name}")
    
    await billing_service.verify_user_is_owner_or_admin(req.organization_id, user_id)
    print(f"✅ User is authorized")
    
    billing_service.validate_customer_exists(org)
    
    # Determine return URL
    return_url = req.return_url if req.return_url else f"{CLIENT_URL}/user/subscription"
    
    print(f"📝 Creating portal session...")
    print(f"   Customer ID: {org.stripe_customer_id}")
    print(f"   Return URL: {return_url}")
    
    # Create portal session (validated to exist by validate_customer_exists)
    assert org.stripe_customer_id is not None
    portal_session = billing_service.create_portal_session(
        customer_id=org.stripe_customer_id,
        return_url=return_url
    )
    
    print(f"✅ Portal session created")
    print(f"   URL: {portal_session.url[:50]}...")
    print(f"{'='*60}\n")
    
    logger.info(f"Portal session created for organization {req.organization_id}")
    
    return CreatePortalSessionResponse(url=portal_session.url)


# Combined router that includes both billing and stripe routes
router = APIRouter()
router.include_router(billing_router)
router.include_router(stripe_router)
