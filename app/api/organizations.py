"""Organizations API endpoints"""
import logging
import os
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import List, Optional
from enum import Enum

from app.config import supabase
from app.infra.supabase.repositories.organizations import OrganizationRepository
from app.models.organization import OrganizationUpdate
import stripe

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


class OrganizationMemberResponse(BaseModel):
    """Response model for organization member"""
    id: int
    user_id: str
    organization_id: int
    role_id: Optional[int]
    status: str
    created_at: str
    # User data
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    # Role data
    role_name: Optional[str] = None


class OrganizationMembersResponse(BaseModel):
    """Response model for organization members list"""
    organization_id: int
    organization_name: str
    total_members: int
    members: List[OrganizationMemberResponse]


# ============================================
# Organization Invitation Models
# ============================================

class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class CreateOrganizationInvitationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    organization_id: int = Field(..., alias="organizationId")
    invitee_email: EmailStr = Field(..., alias="inviteeEmail")
    role_id: Optional[int] = Field(None, alias="roleId")


class OrganizationInvitationResponse(BaseModel):
    id: str
    organization_id: int
    organization_name: str
    inviter_id: str
    inviter_name: Optional[str]
    invitee_email: str
    invitee_id: Optional[str]
    token: str
    role_id: Optional[int]
    role_name: Optional[str]
    status: InvitationStatus
    expires_at: str
    created_at: str
    accepted_at: Optional[str]
    invitation_link: str


class AcceptOrganizationInvitationRequest(BaseModel):
    token: str


class OrganizationInvitationsListResponse(BaseModel):
    organization_id: int
    total_pending: int
    invitations: List[OrganizationInvitationResponse]


@router.get("/{organization_id}/members", response_model=OrganizationMembersResponse)
async def get_organization_members(organization_id: int):
    """
    Get all members of an organization with their user profiles
    
    Returns:
    - Organization info
    - List of members with user data (email, name, avatar)
    - Role information
    """
    print(f"\n{'='*60}")
    print(f"📋 Get Organization Members")
    print(f"   Organization ID: {organization_id}")
    print(f"{'='*60}")
    
    logger.info(f"Fetching members for organization {organization_id}")
    
    # Initialize repository
    org_repo = OrganizationRepository(supabase)
    
    # Get organization
    org = await org_repo.find_by_id(organization_id)
    if not org:
        print(f"❌ Organization not found: {organization_id}")
        raise HTTPException(status_code=404, detail="Organization not found")
    
    print(f"✅ Organization: {org.name}")
    
    try:
        # Get organization members
        response = supabase.table('organization_members') \
            .select('*') \
            .eq('organization_id', organization_id) \
            .eq('status', 'active') \
            .execute()
        
        org_members = response.data or []
        print(f"   Found {len(org_members)} members")
        
        if not org_members:
            return OrganizationMembersResponse(
                organization_id=organization_id,
                organization_name=org.name,
                total_members=0,
                members=[]
            )
        
        # Get user IDs
        user_ids = [m['user_id'] for m in org_members]
        
        # Fetch profiles
        profiles_response = supabase.table('user_profiles') \
            .select('*') \
            .in_('id', user_ids) \
            .execute()
        
        profiles = profiles_response.data or []
        profiles_map = {p['id']: p for p in profiles}
        
        # Fetch user emails from auth.users (service role)
        users_response = supabase.auth.admin.list_users()
        users = users_response or []
        users_map = {u.id: u for u in users}
        
        # Fetch roles
        role_ids = [m['role_id'] for m in org_members if m.get('role_id')]
        roles_map = {}
        
        if role_ids:
            roles_response = supabase.table('organization_member_roles') \
                .select('*') \
                .in_('id', role_ids) \
                .execute()
            
            roles = roles_response.data or []
            roles_map = {r['id']: r for r in roles}
        
        # Combine data
        members_data = []
        for member in org_members:
            user_id = member['user_id']
            profile = profiles_map.get(user_id, {})
            user = users_map.get(user_id)
            role = roles_map.get(member.get('role_id')) if member.get('role_id') else None
            
            members_data.append(OrganizationMemberResponse(
                id=member['id'],
                user_id=user_id,
                organization_id=member['organization_id'],
                role_id=member.get('role_id'),
                status=member['status'],
                created_at=member['created_at'],
                email=user.email if user else 'unknown@example.com',
                name=profile.get('name'),
                avatar_url=profile.get('avatar_url'),
                role_name=role['name'] if role else None
            ))
        
        print(f"✅ Successfully retrieved {len(members_data)} members")
        print(f"{'='*60}\n")
        
        return OrganizationMembersResponse(
            organization_id=organization_id,
            organization_name=org.name,
            total_members=len(members_data),
            members=members_data
        )
        
    except Exception as e:
        print(f"❌ Error fetching members: {e}")
        logger.error(f"Error fetching members for organization {organization_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch members: {str(e)}"
        )


# ============================================
# Organization Invitation Endpoints
# ============================================

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def get_user_id_from_token(authorization: Optional[str]) -> Optional[str]:
    """Extract user ID from Supabase JWT token"""
    if not authorization or not authorization.startswith('Bearer '):
        return None
    
    try:
        token = authorization.replace('Bearer ', '')
        # Verify with Supabase
        user = supabase.auth.get_user(token)
        return user.user.id if user.user else None
    except Exception as e:
        logger.error(f"Error extracting user from token: {e}")
        return None


@router.post("/invitations/create", response_model=OrganizationInvitationResponse)
async def create_organization_invitation(
    req: CreateOrganizationInvitationRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Create an email invitation to join an organization
    
    Flow:
    1. Validate organization exists
    2. Check if invitee already a member
    3. Check for existing pending invitation
    4. Check seat count and auto-add if needed (Business plan)
    5. Create invitation with 7-day expiry
    6. Return invitation link
    """
    print(f"\n{'='*60}")
    print(f"📨 Create Organization Invitation")
    print(f"   Organization ID: {req.organization_id}")
    print(f"   Invitee Email: {req.invitee_email}")
    print(f"{'='*60}")
    
    # Get current user
    user_id = get_user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    org_repo = OrganizationRepository(supabase)
    
    # 1. Get organization
    org = await org_repo.find_by_id(req.organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    print(f"✅ Organization: {org.name} (Plan: {org.plan_type})")
    
    # 2. Check if invitee email already exists as member
    existing_member_response = supabase.table('organization_members') \
        .select('id, user_id') \
        .eq('organization_id', req.organization_id) \
        .eq('status', 'active') \
        .execute()
    
    if existing_member_response.data:
        # Get user emails to check (only for THIS organization's members)
        user_ids = [m['user_id'] for m in existing_member_response.data]
        
        # Fetch all users to get emails
        all_users_response = supabase.auth.admin.list_users()
        
        # Filter to only users who are members of this organization
        member_emails = []
        for user in all_users_response:
            if user.id in user_ids and user.email:
                member_emails.append(user.email.lower())
        
        # Check if invited email is already a member
        if req.invitee_email.lower() in member_emails:
            raise HTTPException(
                status_code=400, 
                detail="User is already a member of this organization"
            )
    
    # 3. Check for existing pending invitation (only recent ones matter)
    # Allow re-inviting users who previously left or had expired invitations
    existing_invite_response = supabase.table('organization_invitations') \
        .select('*') \
        .eq('organization_id', req.organization_id) \
        .eq('invitee_email', req.invitee_email.lower()) \
        .eq('status', 'pending') \
        .execute()
    
    if existing_invite_response.data:
        # Check if any pending invitation is still valid (not expired)
        now = datetime.utcnow()
        
        for invite in existing_invite_response.data:
            expires_at = datetime.fromisoformat(invite['expires_at'].replace('Z', '+00:00'))
            if expires_at > now.replace(tzinfo=expires_at.tzinfo):
                # There's a valid pending invitation
                raise HTTPException(
                    status_code=400,
                    detail="A pending invitation already exists for this email"
                )
        
        # All pending invitations are expired, we can create a new one
        # (They will be auto-marked as expired by the system)
    
    # 4. Check seat count and auto-add if needed (Business plan only)
    if org.plan_type == "BUSINESS" and org.stripe_subscription_id:
        current_member_count = org.active_member_count or 0
        
        # Count pending invitations
        pending_invitations_response = supabase.table('organization_invitations') \
            .select('id', count='exact') \
            .eq('organization_id', req.organization_id) \
            .eq('status', 'pending') \
            .execute()
        
        pending_count = pending_invitations_response.count or 0
        projected_member_count = current_member_count + pending_count + 1  # +1 for this new invite
        current_seat_count = org.seat_count or 1
        
        print(f"📊 Seat Check:")
        print(f"   Current Members: {current_member_count}")
        print(f"   Pending Invites: {pending_count}")
        print(f"   Projected Total: {projected_member_count}")
        print(f"   Current Seats: {current_seat_count}")
        
        if projected_member_count > current_seat_count:
            # Auto-add seats
            new_seat_count = projected_member_count
            print(f"⚠️  Projected count exceeds seats! Auto-adding seats to {new_seat_count}")
            
            try:
                # Update Stripe subscription
                updated_subscription = stripe.Subscription.modify(
                    org.stripe_subscription_id,
                    items=[{
                        "id": org.stripe_subscription_item_id,
                        "quantity": new_seat_count,
                    }],
                    proration_behavior="create_prorations",
                )
                
                print(f"✅ Stripe subscription updated to {new_seat_count} seats")
                
                # Update local DB (webhook will also update, but we do it here for immediate consistency)
                await org_repo.update(org.id, OrganizationUpdate(
                    seat_count=new_seat_count
                ))
                
                print(f"✅ Database updated with new seat count")
                
            except Exception as e:
                print(f"❌ Failed to add seats: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to add additional seats: {str(e)}"
                )
    
    # 5. Generate invitation token and expiry
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    # 6. Create invitation
    try:
        invitation_data = {
            "organization_id": req.organization_id,
            "inviter_id": user_id,
            "invitee_email": req.invitee_email.lower(),
            "invitee_id": None,
            "token": token,
            "role_id": req.role_id,
            "status": "pending",
            "expires_at": expires_at.isoformat(),
        }
        
        create_response = supabase.table('organization_invitations') \
            .insert(invitation_data) \
            .execute()
        
        if not create_response.data:
            raise HTTPException(status_code=500, detail="Failed to create invitation")
        
        invitation = create_response.data[0]
        
        print(f"✅ Invitation created: {invitation['id']}")
        print(f"   Token: {token}")
        print(f"   Expires: {expires_at}")
        
        # 7. Get role name if role_id provided
        role_name = None
        if req.role_id:
            role_response = supabase.table('organization_member_roles') \
                .select('name') \
                .eq('id', req.role_id) \
                .single() \
                .execute()
            role_name = role_response.data['name'] if role_response.data else None
        
        # 8. Get inviter name
        inviter_name = None
        try:
            profile_response = supabase.table('user_profiles') \
                .select('name') \
                .eq('id', user_id) \
                .single() \
                .execute()
            if profile_response.data:
                inviter_name = profile_response.data.get('name')
        except Exception:
            pass
        
        invitation_link = f"{FRONTEND_URL}/invite/org/{token}"
        
        print(f"🔗 Invitation Link: {invitation_link}")
        print(f"{'='*60}\n")
        
        return OrganizationInvitationResponse(
            id=invitation['id'],
            organization_id=org.id,
            organization_name=org.name,
            inviter_id=invitation['inviter_id'],
            inviter_name=inviter_name,
            invitee_email=invitation['invitee_email'],
            invitee_id=invitation.get('invitee_id'),
            token=token,
            role_id=req.role_id,
            role_name=role_name,
            status=invitation['status'],
            expires_at=invitation['expires_at'],
            created_at=invitation['created_at'],
            accepted_at=invitation.get('accepted_at'),
            invitation_link=invitation_link
        )
        
    except Exception as e:
        print(f"❌ Error creating invitation: {e}")
        logger.error(f"Error creating organization invitation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create invitation: {str(e)}"
        )


@router.post("/invitations/accept")
async def accept_organization_invitation(
    req: AcceptOrganizationInvitationRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Accept an organization invitation
    
    Flow:
    1. Validate token and check expiry
    2. Get current user (must be authenticated)
    3. Check if user is already a member
    4. Add user to organization_members
    5. Update invitation status to 'accepted'
    6. Update organization.active_member_count
    7. Sync seats with Stripe (if needed)
    8. Return success
    """
    print(f"\n{'='*60}")
    print(f"✅ Accept Organization Invitation")
    print(f"   Token: {req.token}")
    print(f"{'='*60}")
    
    # Get current user
    user_id = get_user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized - please log in")
    
    # 1. Get invitation
    invite_response = supabase.table('organization_invitations') \
        .select('*') \
        .eq('token', req.token) \
        .eq('status', 'pending') \
        .single() \
        .execute()
    
    if not invite_response.data:
        raise HTTPException(status_code=404, detail="Invitation not found or already used")
    
    invitation = invite_response.data
    
    # Check expiry
    expires_at = datetime.fromisoformat(invitation['expires_at'].replace('Z', '+00:00'))
    if datetime.now(expires_at.tzinfo) > expires_at:
        # Mark as expired
        supabase.table('organization_invitations') \
            .update({"status": "expired"}) \
            .eq('id', invitation['id']) \
            .execute()
        raise HTTPException(status_code=400, detail="Invitation has expired")
    
    # 2. Get organization
    org_repo = OrganizationRepository(supabase)
    org = await org_repo.find_by_id(invitation['organization_id'])
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    print(f"📋 Organization: {org.name}")
    print(f"   Invitee: {invitation['invitee_email']}")
    print(f"   User ID: {user_id}")
    
    # 3. Check if already a member
    existing_member = supabase.table('organization_members') \
        .select('id') \
        .eq('organization_id', org.id) \
        .eq('user_id', user_id) \
        .eq('status', 'active') \
        .execute()
    
    if existing_member.data:
        # Already a member - just mark invitation as accepted
        supabase.table('organization_invitations') \
            .update({
                "status": "accepted",
                "accepted_at": datetime.utcnow().isoformat(),
                "invitee_id": user_id
            }) \
            .eq('id', invitation['id']) \
            .execute()
        
        return {
            "success": True,
            "organization_id": org.id,
            "organization_name": org.name,
            "message": "You are already a member of this organization"
        }
    
    # 4. Add member
    try:
        # Default to 'member' role (id=3) if no role specified
        role_id = invitation.get('role_id')
        if role_id is None:
            # Fetch the 'member' role id
            member_role_response = supabase.table('organization_member_roles') \
                .select('id') \
                .eq('name', 'member') \
                .single() \
                .execute()
            
            if member_role_response.data:
                role_id = member_role_response.data['id']
            else:
                # Fallback to id=3 if query fails
                role_id = 3
        
        member_data = {
            "organization_id": org.id,
            "user_id": user_id,
            "role_id": role_id,
            "status": "active"
        }
        
        supabase.table('organization_members') \
            .insert(member_data) \
            .execute()
        
        print(f"✅ Added user as organization member")
        
        # 5. Update invitation status
        supabase.table('organization_invitations') \
            .update({
                "status": "accepted",
                "accepted_at": datetime.utcnow().isoformat(),
                "invitee_id": user_id
            }) \
            .eq('id', invitation['id']) \
            .execute()
        
        print(f"✅ Invitation marked as accepted")
        
        # 6. Update active_member_count
        current_count = org.active_member_count or 0
        new_count = current_count + 1
        
        await org_repo.update(org.id, OrganizationUpdate(
            active_member_count=new_count
        ))
        
        print(f"✅ Updated active_member_count: {current_count} → {new_count}")
        
        # 7. Sync seats if Business plan
        if org.plan_type == "BUSINESS" and org.stripe_subscription_id:
            try:
                from app.services.subscription_seat_manager import SubscriptionSeatManager
                
                seat_manager = SubscriptionSeatManager(supabase)
                await seat_manager.sync_seats_with_members(org.id)
                
                print(f"✅ Synced seats with Stripe")
            except Exception as e:
                logger.warning(f"Failed to sync seats: {e}")
        
        print(f"{'='*60}\n")
        
        return {
            "success": True,
            "organization_id": org.id,
            "organization_name": org.name,
            "message": "Successfully joined organization"
        }
        
    except Exception as e:
        print(f"❌ Error accepting invitation: {e}")
        logger.error(f"Error accepting organization invitation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to accept invitation: {str(e)}"
        )


@router.get("/{organization_id}/invitations", response_model=OrganizationInvitationsListResponse)
async def get_organization_invitations(organization_id: int):
    """Get all invitations for an organization"""
    
    org_repo = OrganizationRepository(supabase)
    org = await org_repo.find_by_id(organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Get all invitations
    invitations_response = supabase.table('organization_invitations') \
        .select('*') \
        .eq('organization_id', organization_id) \
        .order('created_at', desc=True) \
        .execute()
    
    invitations_data = invitations_response.data or []
    
    # Get role names
    role_ids = [inv.get('role_id') for inv in invitations_data if inv.get('role_id')]
    roles_map = {}
    if role_ids:
        roles_response = supabase.table('organization_member_roles') \
            .select('*') \
            .in_('id', role_ids) \
            .execute()
        roles_map = {r['id']: r['name'] for r in roles_response.data or []}
    
    # Get inviter names
    inviter_ids = list(set([inv['inviter_id'] for inv in invitations_data]))
    inviters_map = {}
    if inviter_ids:
        profiles_response = supabase.table('user_profiles') \
            .select('id, name') \
            .in_('id', inviter_ids) \
            .execute()
        inviters_map = {p['id']: p.get('name') for p in profiles_response.data or []}
    
    invitations = []
    pending_count = 0
    
    for inv in invitations_data:
        if inv['status'] == 'pending':
            pending_count += 1
        
        invitations.append(OrganizationInvitationResponse(
            id=inv['id'],
            organization_id=inv['organization_id'],
            organization_name=org.name,
            inviter_id=inv['inviter_id'],
            inviter_name=inviters_map.get(inv['inviter_id']),
            invitee_email=inv['invitee_email'],
            invitee_id=inv.get('invitee_id'),
            token=inv['token'],
            role_id=inv.get('role_id'),
            role_name=roles_map.get(inv.get('role_id')),
            status=inv['status'],
            expires_at=inv['expires_at'],
            created_at=inv['created_at'],
            accepted_at=inv.get('accepted_at'),
            invitation_link=f"{FRONTEND_URL}/invite/org/{inv['token']}"
        ))
    
    return OrganizationInvitationsListResponse(
        organization_id=organization_id,
        total_pending=pending_count,
        invitations=invitations
    )


@router.delete("/invitations/{invitation_id}")
async def cancel_organization_invitation(invitation_id: str):
    """Cancel a pending invitation"""
    
    # Get invitation
    invite_response = supabase.table('organization_invitations') \
        .select('*') \
        .eq('id', invitation_id) \
        .single() \
        .execute()
    
    if not invite_response.data:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    invitation = invite_response.data
    
    if invitation['status'] != 'pending':
        raise HTTPException(
            status_code=400,
            detail="Can only cancel pending invitations"
        )
    
    # Update status
    supabase.table('organization_invitations') \
        .update({"status": "cancelled"}) \
        .eq('id', invitation_id) \
        .execute()
    
    return {"success": True, "message": "Invitation cancelled"}
