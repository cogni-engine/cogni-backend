"""Stripe webhook endpoint"""
import logging
import json
from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import Response
import stripe
from app.config import supabase, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
from app.infra.supabase.repositories.organizations import OrganizationRepository
from app.services.payment import PaymentService

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY

router = APIRouter(prefix="/api/stripe", tags=["stripe"])


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


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="stripe-signature")
):
    """
    Stripe webhook endpoint to handle subscription events
    
    Handles:
    - checkout.session.completed: Initial subscription confirmed
    - customer.subscription.updated: Plan change / seat change / cancellation scheduled / status change
    - customer.subscription.deleted: Cancellation completed
    - invoice.payment_succeeded: Renewal success
    - invoice.payment_failed: Payment failed
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
    
    # Initialize payment service
    org_repo = OrganizationRepository(supabase)
    payment_service = PaymentService(org_repo)
    
    try:
        # Delegate to payment service
        await payment_service.handle_webhook_event(event_type, event_data)
        
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

