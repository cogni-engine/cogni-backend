"""Billing API endpoints for subscription management"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
import stripe

from app.config import (
    supabase,
    STRIPE_SECRET_KEY,
    STRIPE_PRICE_ID_PRO,
    STRIPE_PRICE_ID_BUSINESS,
    CLIENT_URL,
)
from app.auth import get_current_user_id
from app.infra.supabase.repositories.organizations import OrganizationRepository
from app.models.organization import OrganizationUpdate
from app.services.subscription_seat_manager import SubscriptionSeatManager

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY

router = APIRouter(prefix="/api/billing", tags=["billing"])


class UpgradeToBusinessRequest(BaseModel):
    """Request model for Business plan upgrade"""
    model_config = ConfigDict(populate_by_name=True)
    
    organization_id: int = Field(..., alias="organizationId")
    seat_count: int | None = Field(None, alias="seatCount", ge=1)  # Optional: user-specified seat count


class UpgradeToBusinessResponse(BaseModel):
    """Response model for Business plan upgrade"""
    success: bool
    message: str
    new_plan: str
    seat_count: int


class SyncSeatsRequest(BaseModel):
    """Request model for seat synchronization"""
    model_config = ConfigDict(populate_by_name=True)
    
    organization_id: int = Field(..., alias="organizationId")


class SyncSeatsResponse(BaseModel):
    """Response model for seat synchronization"""
    success: bool
    message: str
    old_seat_count: int
    new_seat_count: int
    updated: bool


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
async def upgrade_to_business(req: UpgradeToBusinessRequest):
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
    """
    print(f"\n{'='*60}")
    print(f"🚀 Business Plan Upgrade Request")
    print(f"   Organization ID: {req.organization_id}")
    print(f"{'='*60}")
    
    logger.info(f"Processing Business upgrade for organization {req.organization_id}")
    
    # Initialize repository
    org_repo = OrganizationRepository(supabase)
    
    # Get organization
    org = await org_repo.find_by_id(req.organization_id)
    if not org:
        print(f"❌ Organization not found: {req.organization_id}")
        logger.error(f"Organization not found: {req.organization_id}")
        raise HTTPException(status_code=404, detail="Organization not found")
    
    print(f"✅ Organization found: {org.name}")
    print(f"   Current plan: {org.plan_type}")
    print(f"   Active members: {org.active_member_count}")
    print(f"   Current seat count: {org.seat_count}")
    
    # Validate current plan
    if org.plan_type != "pro":
        print(f"❌ Organization is not on Pro plan: {org.plan_type}")
        raise HTTPException(
            status_code=400,
            detail=f"Can only upgrade from Pro plan. Current plan: {org.plan_type}"
        )
    
    # Validate has subscription
    if not org.stripe_subscription_id or not org.stripe_subscription_item_id:
        print(f"❌ No active subscription found")
        raise HTTPException(
            status_code=400,
            detail="No active Pro subscription found"
        )
    
    # Calculate seat count for Business plan
    # Use user-specified seat count if provided, otherwise use active_member_count
    if req.seat_count is not None:
        # User specified seat count
        seat_count = req.seat_count
        # Validate: seat count must be >= active members
        if seat_count < org.active_member_count:
            print(f"❌ Requested seats ({seat_count}) < active members ({org.active_member_count})")
            raise HTTPException(
                status_code=400,
                detail=f"Seat count must be at least {org.active_member_count} (current member count)"
            )
    else:
        # Auto-calculate from active members
        seat_count = max(org.active_member_count, 1)
    
    print(f"📝 Upgrading to Business plan...")
    print(f"   Subscription ID: {org.stripe_subscription_id}")
    print(f"   Subscription Item ID: {org.stripe_subscription_item_id}")
    print(f"   New seat count: {seat_count}")
    print(f"   Business Price ID: {STRIPE_PRICE_ID_BUSINESS}")
    
    try:
        # Update Stripe subscription
        # This single API call does:
        # 1. Changes price from PRO to BUSINESS
        # 2. Updates quantity to active_member_count
        # 3. Automatically calculates proration
        updated_subscription = stripe.Subscription.modify(
            org.stripe_subscription_id,
            items=[
                {
                    "id": org.stripe_subscription_item_id,
                    "price": STRIPE_PRICE_ID_BUSINESS,
                    "quantity": seat_count,
                }
            ],
            proration_behavior="create_prorations",  # Create proration invoice
        )
        
        print(f"✅ Stripe subscription updated successfully")
        print(f"   New status: {updated_subscription['status']}")
        print(f"   New item ID: {updated_subscription['items']['data'][0]['id']}")
        print(f"   Quantity: {updated_subscription['items']['data'][0]['quantity']}")
        print(f"   ⏳ Webhook will update DB to Business plan")
        print(f"{'='*60}\n")
        
        logger.info(f"Successfully upgraded organization {org.id} to Business plan")
        
        return UpgradeToBusinessResponse(
            success=True,
            message=f"Successfully upgraded to Business plan with {seat_count} seats",
            new_plan="business",
            seat_count=seat_count
        )
        
    except stripe.error.StripeError as e:
        print(f"❌ Stripe upgrade failed: {e}")
        logger.error(f"Stripe upgrade failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upgrade subscription: {str(e)}"
        )
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error in upgrade_to_business: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.post("/sync-seats", response_model=SyncSeatsResponse)
async def sync_subscription_seats(req: SyncSeatsRequest):
    """
    Sync Stripe subscription seats with organization member count
    
    This endpoint should be called after:
    - Adding a member to the organization
    - Activating a member
    
    Only increases seats (never decreases automatically)
    
    For Business plan only.
    """
    print(f"\n{'='*60}")
    print(f"🔄 Seat Sync Request")
    print(f"   Organization ID: {req.organization_id}")
    print(f"{'='*60}")
    
    logger.info(f"Syncing seats for organization {req.organization_id}")
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    seat_manager = SubscriptionSeatManager(org_repo)
    
    # Get organization
    org = await org_repo.find_by_id(req.organization_id)
    if not org:
        print(f"❌ Organization not found: {req.organization_id}")
        raise HTTPException(status_code=404, detail="Organization not found")
    
    old_seat_count = org.seat_count
    
    # Sync seats
    updated = await seat_manager.sync_seats_with_members(req.organization_id)
    
    if updated:
        # Refresh organization to get updated seat count
        org = await org_repo.find_by_id(req.organization_id)
        new_seat_count = org.seat_count if org else old_seat_count
        
        return SyncSeatsResponse(
            success=True,
            message=f"Seats updated from {old_seat_count} to {new_seat_count}",
            old_seat_count=old_seat_count,
            new_seat_count=new_seat_count,
            updated=True
        )
    else:
        return SyncSeatsResponse(
            success=True,
            message="No seat update needed",
            old_seat_count=old_seat_count,
            new_seat_count=old_seat_count,
            updated=False
        )


@router.post("/update-seats", response_model=UpdateSeatsResponse)
async def update_subscription_seats(req: UpdateSeatsRequest):
    """
    Manually update subscription seat count
    
    This allows users to:
    - Add more seats before inviting members
    - Reduce seats (if no members would be affected)
    
    For Business plan only.
    """
    print(f"\n{'='*60}")
    print(f"🎫 Manual Seat Update Request")
    print(f"   Organization ID: {req.organization_id}")
    print(f"   Requested Seats: {req.seat_count}")
    print(f"{'='*60}")
    
    logger.info(f"Manual seat update for organization {req.organization_id} to {req.seat_count} seats")
    
    # Initialize repository
    org_repo = OrganizationRepository(supabase)
    
    # Get organization
    org = await org_repo.find_by_id(req.organization_id)
    if not org:
        print(f"❌ Organization not found: {req.organization_id}")
        raise HTTPException(status_code=404, detail="Organization not found")
    
    print(f"✅ Organization: {org.name}")
    print(f"   Plan: {org.plan_type}")
    print(f"   Active members: {org.active_member_count}")
    print(f"   Current seats: {org.seat_count}")
    
    # Only for Business plan
    if org.plan_type != "business":
        print(f"❌ Not a Business plan: {org.plan_type}")
        raise HTTPException(
            status_code=400,
            detail="Seat updates are only available for Business plan"
        )
    
    # Validate has subscription
    if not org.stripe_subscription_id or not org.stripe_subscription_item_id:
        print(f"❌ No active subscription found")
        raise HTTPException(
            status_code=400,
            detail="No active subscription found"
        )
    
    # Validate: seat count must be >= active members
    if req.seat_count < org.active_member_count:
        print(f"❌ Requested seats ({req.seat_count}) < active members ({org.active_member_count})")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reduce seats below active member count ({org.active_member_count})"
        )
    
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
    
    try:
        # Update Stripe subscription quantity
        updated_subscription = stripe.Subscription.modify(
            org.stripe_subscription_id,
            items=[
                {
                    "id": org.stripe_subscription_item_id,
                    "quantity": req.seat_count,
                }
            ],
            proration_behavior="create_prorations",  # Pro-rate the change
        )
        
        print(f"✅ Stripe subscription updated")
        print(f"   New quantity: {updated_subscription['items']['data'][0]['quantity']}")
        print(f"   Status: {updated_subscription['status']}")
        print(f"   ⏳ Webhook will update DB seat_count")
        print(f"{'='*60}\n")
        
        logger.info(f"Updated seats for organization {req.organization_id}: {old_seat_count} → {req.seat_count}")
        
        return UpdateSeatsResponse(
            success=True,
            message=f"Seats updated from {old_seat_count} to {req.seat_count}",
            old_seat_count=old_seat_count,
            new_seat_count=req.seat_count
        )
        
    except stripe.error.StripeError as e:
        print(f"❌ Stripe update failed: {e}")
        logger.error(f"Failed to update Stripe seats for organization {req.organization_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update seats: {str(e)}"
        )
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error updating seats for organization {req.organization_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
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
    
    # Validate plan_id
    if req.plan_id not in ["pro", "business"]:
        raise HTTPException(status_code=400, detail=f"Invalid plan_id: {req.plan_id}")
    
    # Get price ID
    price_id = STRIPE_PRICE_ID_PRO if req.plan_id == "pro" else STRIPE_PRICE_ID_BUSINESS
    if not price_id:
        raise HTTPException(
            status_code=500,
            detail=f"Stripe price ID for {req.plan_id} plan is not configured"
        )
    
    # Initialize repository
    org_repo = OrganizationRepository(supabase)
    
    # Get organization
    org = await org_repo.find_by_id(req.organization_id)
    if not org:
        print(f"❌ Organization not found: {req.organization_id}")
        raise HTTPException(status_code=404, detail="Organization not found")
    
    print(f"✅ Organization found: {org.name}")
    
    # Verify user is the owner of the organization
    print("🔍 Verifying user is organization owner...")
    member_check = supabase.table('organization_members') \
        .select('role_id') \
        .eq('organization_id', req.organization_id) \
        .eq('user_id', user_id) \
        .eq('status', 'active') \
        .single() \
        .execute()
    
    if not member_check.data:
        print(f"❌ User is not a member of organization {req.organization_id}")
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization"
        )
    
    role_id = member_check.data.get('role_id')
    if role_id != 1:  # Must be owner (role_id=1)
        print(f"❌ User is not owner (role_id={role_id})")
        raise HTTPException(
            status_code=403,
            detail="Only organization owners can purchase plans"
        )
    
    print("✅ User verified as organization owner")
    
    # Check if organization already has an active subscription
    print("🔍 Checking for existing subscription...")
    print(f"   Current plan: {org.plan_type}")
    
    if org.plan_type in ["pro", "business"]:
        print(f"❌ Organization already has {org.plan_type} plan")
        raise HTTPException(
            status_code=400,
            detail=f"Organization already has an active {org.plan_type} subscription. Use the upgrade or portal endpoint to modify your subscription."
        )
    
    print("✅ No active subscription found - proceeding with purchase")
    
    # Create or get Stripe customer
    customer_id = org.stripe_customer_id
    if not customer_id:
        print("📝 Creating Stripe customer...")
        try:
            customer = stripe.Customer.create(
                metadata={
                    "organization_id": str(org.id),
                    "user_id": user_id
                }
            )
            customer_id = customer.id
            print(f"✅ Stripe customer created: {customer_id}")
            
            # Update organization with customer ID
            await org_repo.update(
                org.id,
                OrganizationUpdate(stripe_customer_id=customer_id)
            )
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe customer creation failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create Stripe customer: {str(e)}"
            )
    
    # Determine quantity
    quantity = req.seat_count if req.seat_count else 1
    
    # Create Checkout Session
    print("📝 Creating Stripe Checkout Session...")
    print(f"   Price ID: {price_id}")
    print(f"   Quantity: {quantity}")
    
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            ui_mode="embedded",
            customer=customer_id,
            line_items=[
                {
                    "price": price_id,
                    "quantity": quantity,
                }
            ],
            return_url=f"{CLIENT_URL}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
            metadata={
                "organization_id": str(org.id),
                "plan_type": req.plan_id,
                "user_id": user_id
            }
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
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe session creation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create checkout session: {str(e)}"
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
    
    # Initialize repository
    org_repo = OrganizationRepository(supabase)
    
    # Get organization
    org = await org_repo.find_by_id(req.organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    print(f"✅ Organization: {org.name}")
    
    # Verify user is a member of the organization
    member_check = supabase.table('organization_members') \
        .select('role_id') \
        .eq('organization_id', req.organization_id) \
        .eq('user_id', user_id) \
        .eq('status', 'active') \
        .single() \
        .execute()
    
    if not member_check.data:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization"
        )
    
    # Check if user is owner/admin (role_id 1 or 2)
    role_id = member_check.data.get('role_id')
    if role_id not in [1, 2]:
        raise HTTPException(
            status_code=403,
            detail="Only organization owners/admins can access the customer portal"
        )
    
    print(f"✅ User is authorized (role_id={role_id})")
    
    # Check if organization has a Stripe customer ID
    if not org.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe customer found for this organization"
        )
    
    # Determine return URL
    return_url = req.return_url if req.return_url else f"{CLIENT_URL}/user/subscription"
    
    print(f"📝 Creating portal session...")
    print(f"   Customer ID: {org.stripe_customer_id}")
    print(f"   Return URL: {return_url}")
    
    try:
        # Create portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=org.stripe_customer_id,
            return_url=return_url
        )
        
        print(f"✅ Portal session created")
        print(f"   URL: {portal_session.url[:50]}...")
        print(f"{'='*60}\n")
        
        logger.info(f"Portal session created for organization {req.organization_id}")
        
        return CreatePortalSessionResponse(url=portal_session.url)
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe portal session creation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create portal session: {str(e)}"
        )

