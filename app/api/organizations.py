"""Organizations API endpoints"""
import logging
import os
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import List, Optional
from enum import Enum

from app.config import supabase
from app.auth import get_current_user_id
from app.infra.supabase.repositories.organizations import OrganizationRepository
from app.models.organization import OrganizationUpdate

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


# ============================================
# Organization Member Management Models
# ============================================

class UpdateMemberRoleRequest(BaseModel):
    """Request model for updating a member's role"""
    model_config = ConfigDict(populate_by_name=True)
    
    organization_id: int = Field(..., alias="organizationId")
    member_id: int = Field(..., alias="memberId")  # organization_members.id
    role_id: int = Field(..., alias="roleId")


class UpdateMemberRoleResponse(BaseModel):
    """Response model for role update"""
    success: bool
    message: str
    member_id: int
    new_role_id: int
    new_role_name: Optional[str]


class DeleteMemberRequest(BaseModel):
    """Request model for deleting a member"""
    model_config = ConfigDict(populate_by_name=True)
    
    organization_id: int = Field(..., alias="organizationId")
    member_id: int = Field(..., alias="memberId")  # organization_members.id


class DeleteMemberResponse(BaseModel):
    """Response model for member deletion"""
    success: bool
    message: str


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
# Organization Member Management Endpoints
# ============================================

@router.put("/members/update-role", response_model=UpdateMemberRoleResponse)
async def update_member_role(
    req: UpdateMemberRoleRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Update a member's role in the organization
    
    Restrictions:
    - Only owners/admins can update roles
    - Cannot assign owner role (role_id=1) to members
    
    Requires: Owner or Admin role
    """
    print(f"\n{'='*60}")
    print(f"👤 Update Member Role")
    print(f"   User ID: {user_id}")
    print(f"   Organization ID: {req.organization_id}")
    print(f"   Member ID: {req.member_id}")
    print(f"   New Role ID: {req.role_id}")
    print(f"{'='*60}")
    
    org_repo = OrganizationRepository(supabase)
    
    # Get organization
    org = await org_repo.find_by_id(req.organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    print(f"✅ Organization: {org.name}")
    
    # Verify actioning user is owner/admin
    print("🔍 Verifying user authorization...")
    actioner_check = supabase.table('organization_members') \
        .select('role_id') \
        .eq('organization_id', req.organization_id) \
        .eq('user_id', user_id) \
        .eq('status', 'active') \
        .single() \
        .execute()
    
    if not actioner_check.data:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization"
        )
    
    actioner_role_id = actioner_check.data.get('role_id')
    if actioner_role_id not in [1, 2]:
        raise HTTPException(
            status_code=403,
            detail="Only organization owners/admins can update member roles"
        )
    
    print(f"✅ User authorized (role_id={actioner_role_id})")
    
    # Prevent assigning owner role
    if req.role_id == 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot assign owner role to members"
        )
    
    # Get target member
    member_response = supabase.table('organization_members') \
        .select('*') \
        .eq('id', req.member_id) \
        .eq('organization_id', req.organization_id) \
        .eq('status', 'active') \
        .single() \
        .execute()
    
    if not member_response.data:
        raise HTTPException(
            status_code=404,
            detail="Member not found"
        )
    
    member = member_response.data
    
    # Check if trying to update own role
    if member['user_id'] == user_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot update your own role"
        )
    
    # Update role
    try:
        supabase.table('organization_members') \
            .update({"role_id": req.role_id}) \
            .eq('id', req.member_id) \
            .execute()
        
        # Get new role name
        role_response = supabase.table('organization_member_roles') \
            .select('name') \
            .eq('id', req.role_id) \
            .single() \
            .execute()
        
        role_name = role_response.data['name'] if role_response.data else None
        
        print(f"✅ Role updated successfully")
        print(f"{'='*60}\n")
        
        return UpdateMemberRoleResponse(
            success=True,
            message=f"Member role updated to {role_name}",
            member_id=req.member_id,
            new_role_id=req.role_id,
            new_role_name=role_name
        )
        
    except Exception as e:
        print(f"❌ Error updating role: {e}")
        logger.error(f"Error updating member role: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update member role: {str(e)}"
        )


@router.delete("/members/delete", response_model=DeleteMemberResponse)
async def delete_member(
    req: DeleteMemberRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Remove a member from the organization
    
    Restrictions:
    - Only owners/admins can delete members
    - Cannot delete owners (role_id=1)
    - Updates active_member_count
    
    Requires: Owner or Admin role
    """
    print(f"\n{'='*60}")
    print(f"🗑️  Delete Member")
    print(f"   User ID: {user_id}")
    print(f"   Organization ID: {req.organization_id}")
    print(f"   Member ID: {req.member_id}")
    print(f"{'='*60}")
    
    org_repo = OrganizationRepository(supabase)
    
    # Get organization
    org = await org_repo.find_by_id(req.organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    print(f"✅ Organization: {org.name}")
    
    # Verify actioning user is owner/admin
    print("🔍 Verifying user authorization...")
    actioner_check = supabase.table('organization_members') \
        .select('role_id') \
        .eq('organization_id', req.organization_id) \
        .eq('user_id', user_id) \
        .eq('status', 'active') \
        .single() \
        .execute()
    
    if not actioner_check.data:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization"
        )
    
    actioner_role_id = actioner_check.data.get('role_id')
    if actioner_role_id not in [1, 2]:
        raise HTTPException(
            status_code=403,
            detail="Only organization owners/admins can delete members"
        )
    
    print(f"✅ User authorized (role_id={actioner_role_id})")
    
    # Get target member
    member_response = supabase.table('organization_members') \
        .select('*') \
        .eq('id', req.member_id) \
        .eq('organization_id', req.organization_id) \
        .eq('status', 'active') \
        .single() \
        .execute()
    
    if not member_response.data:
        raise HTTPException(
            status_code=404,
            detail="Member not found"
        )
    
    member = member_response.data
    
    # Cannot delete owners
    if member['role_id'] == 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete organization owners"
        )
    
    # Cannot delete yourself
    if member['user_id'] == user_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete yourself from the organization"
        )
    
    # Delete member (mark as inactive)
    try:
        supabase.table('organization_members') \
            .update({"status": "inactive"}) \
            .eq('id', req.member_id) \
            .execute()
        
        # Update active_member_count
        current_count = org.active_member_count or 0
        new_count = max(current_count - 1, 0)
        
        await org_repo.update(org.id, OrganizationUpdate(
            active_member_count=new_count
        ))
        
        print(f"✅ Member deleted successfully")
        print(f"   Updated active_member_count: {current_count} → {new_count}")
        print(f"{'='*60}\n")
        
        return DeleteMemberResponse(
            success=True,
            message="Member removed from organization"
        )
        
    except Exception as e:
        print(f"❌ Error deleting member: {e}")
        logger.error(f"Error deleting member: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete member: {str(e)}"
        )


# ============================================
# Organization Invitation Endpoints
# ============================================

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


@router.post("/invitations/create", response_model=OrganizationInvitationResponse)
async def create_organization_invitation(
    req: CreateOrganizationInvitationRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create an email invitation to join an organization
    
    Flow:
    1. Validate organization exists
    2. Verify user is owner/admin
    3. Verify organization is on Business plan (only Business plans support invitations)
    4. Check if invitee already a member
    5. Check for existing pending invitation
    6. Check available seats
    7. Generate invitation token
    8. Create invitation with 7-day expiry
    9. Return invitation link
    
    Requires: 
    - Owner or Admin role
    - Business plan subscription
    """
    print(f"\n{'='*60}")
    print(f"📨 Create Organization Invitation")
    print(f"   User ID: {user_id}")
    print(f"   Organization ID: {req.organization_id}")
    print(f"   Invitee Email: {req.invitee_email}")
    print(f"{'='*60}")
    
    org_repo = OrganizationRepository(supabase)
    
    # 1. Get organization
    org = await org_repo.find_by_id(req.organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    print(f"✅ Organization: {org.name} (Plan: {org.plan_type})")
    
    # 2. Verify user is a member and has owner/admin role
    print("🔍 Verifying user authorization...")
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
    
    # Check if user is owner/admin (role_id 1 or 2)
    role_id = member_check.data.get('role_id')
    if role_id not in [1, 2]:
        print(f"❌ User is not owner/admin (role_id={role_id})")
        raise HTTPException(
            status_code=403,
            detail="Only organization owners/admins can create invitations"
        )
    
    print(f"✅ User authorized (role_id={role_id})")
    
    # 3. Verify organization is on Business plan (only Business plans support invitations)
    if org.plan_type != "business":
        print(f"❌ Organization is not on Business plan: {org.plan_type}")
        raise HTTPException(
            status_code=400,
            detail=f"Organization invitations are only available for Business plans. Current plan: {org.plan_type}. Please upgrade to Business to invite team members."
        )
    
    print(f"✅ Business plan verified")
    
    # 4. Check if invitee email already exists as member
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
    
    # 5. Check for existing pending invitation (only recent ones matter)
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
    
    # 6. Check available seats
    if org.stripe_subscription_id:
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
        print(f"   Plan Type: {org.plan_type}")
        print(f"   Current Members: {current_member_count}")
        print(f"   Pending Invites: {pending_count}")
        print(f"   Projected Total: {projected_member_count}")
        print(f"   Current Seats: {current_seat_count}")
        
        if projected_member_count > current_seat_count:
            # Not enough seats available
            seats_needed = projected_member_count - current_seat_count
            print(f"❌ Not enough seats! Need {seats_needed} more seat(s)")
            raise HTTPException(
                status_code=400,
                detail=f"Not enough seats available. You need {seats_needed} more seat(s). Current seats: {current_seat_count}, Required: {projected_member_count}"
            )
        
        print(f"✅ Sufficient seats available")
    
    # 7. Generate invitation token and expiry
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    # 8. Create invitation
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
        
        # 9. Get role name if role_id provided
        role_name = None
        if req.role_id:
            role_response = supabase.table('organization_member_roles') \
                .select('name') \
                .eq('id', req.role_id) \
                .single() \
                .execute()
            role_name = role_response.data['name'] if role_response.data else None
        
        # 10. Get inviter name
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
    user_id: str = Depends(get_current_user_id)
):
    """
    Accept an organization invitation
    
    Flow:
    1. Validate token and check expiry
    2. Get current user (must be authenticated)
    3. Check if user is already a member
    4. Check if organization has available seats (Business plan)
    5. Add user to organization_members
    6. Update invitation status to 'accepted'
    7. Update organization.active_member_count
    8. Return success
    """
    print(f"\n{'='*60}")
    print(f"✅ Accept Organization Invitation")
    print(f"   User ID: {user_id}")
    print(f"   Token: {req.token}")
    print(f"{'='*60}")
    
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
    
    # 4. Check if organization has available seats (Business plan)
    if org.plan_type == "business" and org.stripe_subscription_id:
        current_member_count = org.active_member_count or 0
        current_seat_count = org.seat_count or 1
        
        print(f"📊 Seat Check Before Accepting:")
        print(f"   Current Members: {current_member_count}")
        print(f"   Current Seats: {current_seat_count}")
        
        if current_member_count >= current_seat_count:
            print(f"❌ No available seats!")
            raise HTTPException(
                status_code=400,
                detail=f"Organization has reached its seat limit ({current_seat_count} seats). Please contact your organization admin to add more seats."
            )
        
        print(f"✅ Seat available for new member")
    
    # 5. Add member
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
        
        # 6. Update invitation status
        supabase.table('organization_invitations') \
            .update({
                "status": "accepted",
                "accepted_at": datetime.utcnow().isoformat(),
                "invitee_id": user_id
            }) \
            .eq('id', invitation['id']) \
            .execute()
        
        print(f"✅ Invitation marked as accepted")
        
        # 7. Update active_member_count
        current_count = org.active_member_count or 0
        new_count = current_count + 1
        
        await org_repo.update(org.id, OrganizationUpdate(
            active_member_count=new_count
        ))
        
        print(f"✅ Updated active_member_count: {current_count} → {new_count}")
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
async def cancel_organization_invitation(
    invitation_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Cancel a pending invitation
    
    Requires: Owner or Admin role
    """
    
    # Get invitation
    invite_response = supabase.table('organization_invitations') \
        .select('*') \
        .eq('id', invitation_id) \
        .single() \
        .execute()
    
    if not invite_response.data:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    invitation = invite_response.data
    organization_id = invitation['organization_id']
    
    # Verify user is a member and has owner/admin role
    member_check = supabase.table('organization_members') \
        .select('role_id') \
        .eq('organization_id', organization_id) \
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
            detail="Only organization owners/admins can cancel invitations"
        )
    
    # Verify invitation is pending
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
