"""Billing API endpoints for subscription management"""
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
import stripe

from app.config import (
    supabase,
    STRIPE_SECRET_KEY,
    CLIENT_URL,
)
from app.auth import get_current_user_id
from app.infra.supabase.repositories.organizations import OrganizationRepository
from app.services.payment import BillingService

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY

router = APIRouter(prefix="/api/billing", tags=["billing"])


class UpgradeToBusinessRequest(BaseModel):
    """Request model for Business plan upgrade"""
    model_config = ConfigDict(populate_by_name=True)
    
    organization_id: int = Field(..., alias="organizationId")
    seat_count: int = Field(..., alias="seatCount", ge=1)  # Required: user must specify seat count


class UpgradeToBusinessResponse(BaseModel):
    """Response model for Business plan upgrade"""
    success: bool
    message: str
    new_plan: str
    seat_count: int


class UpdateSeatsRequest(BaseModel):
    """Request model for manual seat update"""
    model_config = ConfigDict(populate_by_name=True)
    
    organization_id: int = Field(..., alias="organizationId")
    seat_count: int = Field(..., alias="seatCount", ge=1)


class UpdateSeatsResponse(BaseModel):
    """Response model for manual seat update"""
    success: bool
    message: str
    old_seat_count: int
    new_seat_count: int


@router.post("/upgrade-to-business", response_model=UpgradeToBusinessResponse)
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


@router.post("/update-seats", response_model=UpdateSeatsResponse)
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


# ============================================================================
# NEW UNIFIED ENDPOINTS - Replacing Next.js API routes
# ============================================================================

class PurchasePlanRequest(BaseModel):
    """Request model for universal plan purchase (Pro or Business)"""
    model_config = ConfigDict(populate_by_name=True)
    
    plan_id: str = Field(..., alias="planId")  # "pro" or "business"
    organization_id: int = Field(..., alias="organizationId")  # Required: user's organization
    seat_count: int | None = Field(None, alias="seatCount", ge=1)  # Optional: for business plan


class PurchasePlanResponse(BaseModel):
    """Response model for plan purchase"""
    client_secret: str
    session_id: str
    organization_id: int


class CreatePortalSessionRequest(BaseModel):
    """Request model for Stripe Customer Portal session"""
    model_config = ConfigDict(populate_by_name=True)
    
    organization_id: int = Field(..., alias="organizationId")
    return_url: str | None = Field(None, alias="returnUrl")


class CreatePortalSessionResponse(BaseModel):
    """Response model for portal session"""
    url: str


@router.post("/purchase", response_model=PurchasePlanResponse)
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


@router.post("/portal-session", response_model=CreatePortalSessionResponse)
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

