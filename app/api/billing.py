"""Billing API endpoints for subscription management"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import stripe

from app.config import (
    supabase,
    STRIPE_SECRET_KEY,
    STRIPE_PRICE_ID_PRO,
    CLIENT_URL,
)
from app.infra.supabase.repositories.organizations import OrganizationRepository
from app.models.organization import OrganizationUpdate

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY

router = APIRouter(prefix="/api/billing", tags=["billing"])


class PurchaseProRequest(BaseModel):
    """Request model for Pro plan purchase"""
    organization_id: int


class PurchaseProResponse(BaseModel):
    """Response model for Pro plan purchase"""
    client_secret: str
    session_id: str


@router.post("/pro/purchase", response_model=PurchaseProResponse)
async def purchase_pro_subscription(req: PurchaseProRequest):
    """
    Create a Stripe Checkout Session for Pro plan purchase
    
    Steps:
    1. Get organization by ID
    2. Create Stripe customer if not exists
    3. Create Stripe Checkout Session (embedded UI mode)
    4. Return client_secret for Embedded Checkout
    
    The actual subscription update happens via webhook (customer.subscription.updated)
    """
    print(f"\n{'='*60}")
    print(f"🚀 Pro Plan Purchase Request")
    print(f"   Organization ID: {req.organization_id}")
    print(f"{'='*60}")
    
    logger.info(f"Processing Pro plan purchase for organization {req.organization_id}")
    
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
    print(f"   Stripe customer ID: {org.stripe_customer_id or 'Not set'}")
    
    # Create Stripe customer if not exists
    customer_id = org.stripe_customer_id
    if not customer_id:
        print(f"📝 Creating new Stripe customer...")
        try:
            customer = stripe.Customer.create(
                metadata={
                    "organization_id": str(org.id),
                }
            )
            customer_id = customer.id
            print(f"✅ Stripe customer created: {customer_id}")
            
            # Update organization with customer ID
            await org_repo.update(
                org.id,
                OrganizationUpdate(stripe_customer_id=customer_id)
            )
            print(f"✅ Organization updated with customer ID")
            
        except stripe.error.StripeError as e:
            print(f"❌ Stripe customer creation failed: {e}")
            logger.error(f"Stripe customer creation failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create Stripe customer: {str(e)}"
            )
    
    # Create Checkout Session
    print(f"📝 Creating Stripe Checkout Session...")
    print(f"   Mode: subscription")
    print(f"   UI Mode: embedded")
    print(f"   Price ID: {STRIPE_PRICE_ID_PRO}")
    print(f"   Quantity: 1")
    
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            ui_mode="embedded",
            customer=customer_id,
            line_items=[
                {
                    "price": STRIPE_PRICE_ID_PRO,
                    "quantity": 1,
                }
            ],
            # For embedded checkout, we use return_url with session_id placeholder
            return_url=f"{CLIENT_URL}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
            metadata={
                "organization_id": str(org.id),
                "plan_type": "pro",
            }
        )
        
        print(f"✅ Checkout Session created")
        print(f"   Session ID: {session.id}")
        print(f"   Client Secret: {session.client_secret[:20]}...")
        print(f"{'='*60}\n")
        
        logger.info(f"Checkout session created for organization {org.id}: {session.id}")
        
        return PurchaseProResponse(
            client_secret=session.client_secret,
            session_id=session.id
        )
        
    except stripe.error.StripeError as e:
        print(f"❌ Stripe session creation failed: {e}")
        logger.error(f"Stripe session creation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create checkout session: {str(e)}"
        )
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error in purchase_pro_subscription: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

