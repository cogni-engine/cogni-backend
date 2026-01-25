"""Billing service for subscription management operations"""
import logging
from typing import Optional
from dataclasses import dataclass
from enum import Enum
import stripe
from fastapi import HTTPException

from app.infra.supabase.repositories.organizations import OrganizationRepository
from app.models.organization import Organization, OrganizationUpdate

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """Organization user roles"""
    OWNER = 1
    ADMIN = 2
    MEMBER = 3


@dataclass
class OrganizationMembership:
    """User's membership in an organization"""
    organization_id: int
    user_id: str
    role_id: int
    status: str
    
    @property
    def is_owner(self) -> bool:
        return self.role_id == UserRole.OWNER.value
    
    @property
    def is_admin(self) -> bool:
        return self.role_id == UserRole.ADMIN.value
    
    @property
    def is_owner_or_admin(self) -> bool:
        return self.role_id in [UserRole.OWNER.value, UserRole.ADMIN.value]


class BillingService:
    """Service for billing and subscription management operations"""
    
    def __init__(self, org_repo: OrganizationRepository, supabase_client):
        self.org_repo = org_repo
        self.supabase = supabase_client
    
    # ============================================================================
    # AUTHORIZATION & VALIDATION
    # ============================================================================
    
    async def get_organization_or_404(self, organization_id: int) -> Organization:
        """
        Get organization by ID or raise 404
        
        Single responsibility: Organization retrieval with error handling
        """
        org = await self.org_repo.find_by_id(organization_id)
        if not org:
            logger.error(f"Organization not found: {organization_id}")
            raise HTTPException(status_code=404, detail="Organization not found")
        return org
    
    async def get_user_membership(
        self, 
        organization_id: int, 
        user_id: str
    ) -> OrganizationMembership:
        """
        Get user's membership in organization
        
        Single responsibility: Membership lookup
        
        Raises:
            HTTPException(403): User is not a member
        """
        result = self.supabase.table('organization_members') \
            .select('role_id, status') \
            .eq('organization_id', organization_id) \
            .eq('user_id', user_id) \
            .eq('status', 'active') \
            .single() \
            .execute()
        
        if not result.data:
            logger.warning(f"User {user_id} not found in organization {organization_id}")
            raise HTTPException(
                status_code=403,
                detail="You are not a member of this organization"
            )
        
        return OrganizationMembership(
            organization_id=organization_id,
            user_id=user_id,
            role_id=result.data.get('role_id'),
            status=result.data.get('status')
        )
    
    async def verify_user_is_owner(
        self, 
        organization_id: int, 
        user_id: str
    ) -> OrganizationMembership:
        """
        Verify user is the organization owner
        
        Single responsibility: Owner-only authorization
        
        Raises:
            HTTPException(403): User is not owner
        """
        membership = await self.get_user_membership(organization_id, user_id)
        
        if not membership.is_owner:
            logger.warning(f"User {user_id} is not owner of organization {organization_id}")
            raise HTTPException(
                status_code=403,
                detail="Only organization owners can perform this action"
            )
        
        return membership
    
    async def verify_user_is_owner_or_admin(
        self, 
        organization_id: int, 
        user_id: str
    ) -> OrganizationMembership:
        """
        Verify user is owner or admin
        
        Single responsibility: Owner/Admin authorization
        
        Raises:
            HTTPException(403): User is not owner or admin
        """
        membership = await self.get_user_membership(organization_id, user_id)
        
        if not membership.is_owner_or_admin:
            logger.warning(
                f"User {user_id} is not owner/admin of organization {organization_id} "
                f"(role_id={membership.role_id})"
            )
            raise HTTPException(
                status_code=403,
                detail="Only organization owners/admins can perform this action"
            )
        
        return membership
    
    def validate_subscription_exists(self, org: Organization) -> None:
        """
        Validate organization has an active subscription
        
        Single responsibility: Subscription existence validation
        
        Raises:
            HTTPException(400): No active subscription found
        """
        if not org.stripe_subscription_id or not org.stripe_subscription_item_id:
            logger.error(f"No active subscription for organization {org.id}")
            raise HTTPException(
                status_code=400,
                detail="No active subscription found"
            )
    
    def validate_plan_type(
        self, 
        org: Organization, 
        expected_plan: str,
        error_message: Optional[str] = None
    ) -> None:
        """
        Validate organization is on expected plan
        
        Single responsibility: Plan type validation
        
        Raises:
            HTTPException(400): Wrong plan type
        """
        if org.plan_type != expected_plan:
            message = error_message or f"Expected {expected_plan} plan, got {org.plan_type}"
            logger.error(f"Plan type mismatch for organization {org.id}: {message}")
            raise HTTPException(status_code=400, detail=message)
    
    def validate_no_active_subscription(self, org: Organization) -> None:
        """
        Validate organization has NO active subscription (for new purchases)
        
        Single responsibility: No-subscription validation
        
        Raises:
            HTTPException(400): Already has subscription
        """
        if org.plan_type in ["pro", "business"]:
            logger.error(f"Organization {org.id} already has {org.plan_type} subscription")
            raise HTTPException(
                status_code=400,
                detail=f"Organization already has an active {org.plan_type} subscription. "
                       f"Use the upgrade or portal endpoint to modify your subscription."
            )
    
    def validate_seat_count(
        self, 
        org: Organization, 
        requested_seats: int
    ) -> None:
        """
        Validate seat count is sufficient for active members
        
        Single responsibility: Seat count validation
        
        Raises:
            HTTPException(400): Seat count too low
        """
        if requested_seats < org.active_member_count:
            logger.error(
                f"Requested seats ({requested_seats}) < active members "
                f"({org.active_member_count}) for organization {org.id}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Seat count must be at least {org.active_member_count} "
                       f"(current member count)"
            )
    
    # ============================================================================
    # STRIPE OPERATIONS
    # ============================================================================
    
    async def ensure_stripe_customer(
        self, 
        org: Organization, 
        user_id: str
    ) -> str:
        """
        Ensure organization has a Stripe customer ID
        
        Single responsibility: Customer creation/retrieval
        
        Returns:
            str: Stripe customer ID
            
        Raises:
            HTTPException(500): Stripe error
        """
        if org.stripe_customer_id:
            return org.stripe_customer_id
        
        try:
            logger.info(f"Creating Stripe customer for organization {org.id}")
            customer = stripe.Customer.create(
                metadata={
                    "organization_id": str(org.id),
                    "user_id": user_id
                }
            )
            customer_id = customer.id
            
            # Update organization with customer ID
            await self.org_repo.update(
                org.id,
                OrganizationUpdate(stripe_customer_id=customer_id)
            )
            
            logger.info(f"Created Stripe customer {customer_id} for organization {org.id}")
            return customer_id
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create Stripe customer: {str(e)}"
            )
    
    def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        quantity: int,
        organization_id: int,
        plan_type: str,
        user_id: str,
        return_url: str
    ) -> stripe.checkout.Session:
        """
        Create Stripe Checkout Session
        
        Single responsibility: Checkout session creation
        
        Raises:
            HTTPException(500): Stripe error
        """
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
                return_url=return_url,
                metadata={
                    "organization_id": str(organization_id),
                    "plan_type": plan_type,
                    "user_id": user_id
                }
            )
            logger.info(f"Created checkout session {session.id} for organization {organization_id}")
            return session
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create checkout session: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create checkout session: {str(e)}"
            )
    
    def modify_subscription(
        self,
        subscription_id: str,
        subscription_item_id: str,
        price_id: Optional[str] = None,
        quantity: Optional[int] = None,
        proration_behavior: str = "create_prorations"
    ) -> stripe.Subscription:
        """
        Modify Stripe subscription
        
        Single responsibility: Subscription modification
        
        Args:
            subscription_id: Stripe subscription ID
            subscription_item_id: Stripe subscription item ID
            price_id: New price ID (optional - if changing plan)
            quantity: New quantity (optional - if changing seats)
            proration_behavior: How to handle proration
            
        Raises:
            HTTPException(500): Stripe error
        """
        try:
            item_updates = {"id": subscription_item_id}
            
            if price_id:
                item_updates["price"] = price_id  # type: ignore
            if quantity is not None:
                item_updates["quantity"] = quantity  # type: ignore
            
            subscription = stripe.Subscription.modify(
                subscription_id,
                items=[item_updates],
                proration_behavior=proration_behavior
            )
            
            logger.info(
                f"Modified subscription {subscription_id}: "
                f"price={price_id}, quantity={quantity}"
            )
            return subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to modify subscription: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to modify subscription: {str(e)}"
            )
    
    def create_portal_session(
        self,
        customer_id: str,
        return_url: str
    ) -> stripe.billing_portal.Session:
        """
        Create Stripe Customer Portal session
        
        Single responsibility: Portal session creation
        
        Raises:
            HTTPException(500): Stripe error
        """
        try:
            portal_session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url
            )
            logger.info(f"Created portal session for customer {customer_id}")
            return portal_session
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create portal session: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create portal session: {str(e)}"
            )
    
    # ============================================================================
    # BUSINESS LOGIC HELPERS
    # ============================================================================
    
    def get_price_id(self, plan_type: str) -> str:
        """
        Get Stripe price ID for plan type
        
        Single responsibility: Price ID mapping
        
        Raises:
            HTTPException(400): Invalid plan type
            HTTPException(500): Price ID not configured
        """
        from app.config import STRIPE_PRICE_ID_PRO, STRIPE_PRICE_ID_BUSINESS
        
        if plan_type == "pro":
            price_id = STRIPE_PRICE_ID_PRO
        elif plan_type == "business":
            price_id = STRIPE_PRICE_ID_BUSINESS
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid plan type: {plan_type}"
            )
        
        if not price_id:
            raise HTTPException(
                status_code=500,
                detail=f"Stripe price ID for {plan_type} plan is not configured"
            )
        
        return price_id
    
    def calculate_quantity_for_plan(
        self,
        plan_type: str,
        requested_seats: Optional[int],
        org: Organization
    ) -> int:
        """
        Calculate subscription quantity based on plan type
        
        Single responsibility: Quantity calculation logic
        
        Args:
            plan_type: "pro" or "business"
            requested_seats: User-requested seat count (for business)
            org: Organization object
            
        Returns:
            int: Quantity for subscription
        """
        if plan_type == "pro":
            return 1  # Pro is always 1 seat
        elif plan_type == "business":
            # Use requested seats or default to active member count
            return requested_seats if requested_seats else org.active_member_count
        else:
            return 1
    
    def validate_customer_exists(self, org: Organization) -> None:
        """
        Validate organization has a Stripe customer ID
        
        Single responsibility: Customer existence validation
        
        Raises:
            HTTPException(400): No Stripe customer found
        """
        if not org.stripe_customer_id:
            logger.error(f"No Stripe customer for organization {org.id}")
            raise HTTPException(
                status_code=400,
                detail="No Stripe customer found for this organization"
            )
