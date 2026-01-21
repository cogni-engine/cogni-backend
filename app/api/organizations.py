"""Organizations API endpoints"""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import List, Optional
from enum import Enum

from app.config import supabase
from app.auth import get_current_user_id
from app.infra.supabase.repositories.organizations import OrganizationRepository
from app.services.organizations import OrganizationService

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
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    org_service = OrganizationService(org_repo, supabase)
    
    # Get organization
    org = await org_service.get_organization_or_404(organization_id)
    print(f"✅ Organization: {org.name}")
    
    # Get all active members
    org_members = org_service.get_organization_members(organization_id)
    print(f"   Found {len(org_members)} members")
    
    if not org_members:
        return OrganizationMembersResponse(
            organization_id=organization_id,
            organization_name=org.name,
            total_members=0,
            members=[]
        )
    
    # Enrich members with user data (profiles, emails, roles)
    enriched_members = await org_service.enrich_members_with_user_data(org_members)
    
    # Convert to response models
    members_data = [
        OrganizationMemberResponse(
            id=m['id'],
            user_id=m['user_id'],
            organization_id=m['organization_id'],
            role_id=m.get('role_id'),
            status=m['status'],
            created_at=m['created_at'],
            email=m['email'],
            name=m.get('name'),
            avatar_url=m.get('avatar_url'),
            role_name=m.get('role_name')
        )
        for m in enriched_members
    ]
    
    print(f"✅ Successfully retrieved {len(members_data)} members")
    print(f"{'='*60}\n")
    
    return OrganizationMembersResponse(
        organization_id=organization_id,
        organization_name=org.name,
        total_members=len(members_data),
        members=members_data
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
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    org_service = OrganizationService(org_repo, supabase)
    
    # Authorization & validation
    org = await org_service.get_organization_or_404(req.organization_id)
    print(f"✅ Organization: {org.name}")
    
    await org_service.verify_user_is_owner_or_admin(req.organization_id, user_id)
    print(f"✅ User authorized")
    
    org_service.validate_role_assignable(req.role_id)
    
    member = org_service.get_organization_member(req.member_id, req.organization_id)
    org_service.validate_not_self(member['user_id'], user_id, "update your own role")
    
    # Update role
    org_service.update_member_role(req.member_id, req.role_id)
    
    # Get new role name
    role = org_service.get_role_by_id(req.role_id)
    role_name = role['name'] if role else None
    
    print(f"✅ Role updated successfully")
    print(f"{'='*60}\n")
    
    return UpdateMemberRoleResponse(
        success=True,
        message=f"Member role updated to {role_name}",
        member_id=req.member_id,
        new_role_id=req.role_id,
        new_role_name=role_name
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
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    org_service = OrganizationService(org_repo, supabase)
    
    # Authorization & validation
    org = await org_service.get_organization_or_404(req.organization_id)
    print(f"✅ Organization: {org.name}")
    
    await org_service.verify_user_is_owner_or_admin(req.organization_id, user_id)
    print(f"✅ User authorized")
    
    member = org_service.get_organization_member(req.member_id, req.organization_id)
    org_service.validate_member_is_not_owner(member)
    org_service.validate_not_self(member['user_id'], user_id, "delete yourself from the organization")
    
    # Delete member
    org_service.deactivate_member(req.member_id)
    
    # Update active_member_count
    await org_service.decrement_active_member_count(org)
    
    print(f"✅ Member deleted successfully")
    print(f"{'='*60}\n")
    
    return DeleteMemberResponse(
        success=True,
        message="Member removed from organization"
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
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    org_service = OrganizationService(org_repo, supabase)
    
    # 1. Get organization
    org = await org_service.get_organization_or_404(req.organization_id)
    print(f"✅ Organization: {org.name} (Plan: {org.plan_type})")
    
    # 2. Verify user is owner/admin
    await org_service.verify_user_is_owner_or_admin(req.organization_id, user_id)
    print(f"✅ User authorized")
    
    # 3. Verify organization is on Business plan
    org_service.validate_business_plan_for_invitations(org)
    print(f"✅ Business plan verified")
    
    # 4. Check if invitee email already exists as member
    await org_service.validate_user_not_member(req.organization_id, req.invitee_email)
    
    # 5. Check for existing pending invitation
    existing_invite = org_service.check_existing_pending_invitation(
        req.organization_id,
        req.invitee_email
    )
    if existing_invite:
        raise HTTPException(
            status_code=400,
            detail="A pending invitation already exists for this email"
        )
    
    # 6. Check available seats
    pending_count = org_service.get_pending_invitations_count(req.organization_id)
    org_service.validate_seats_available_for_invitation(org, pending_count)
    print(f"✅ Sufficient seats available")
    
    # 7-8. Create invitation
    invitation = org_service.create_invitation(
        organization_id=req.organization_id,
        inviter_id=user_id,
        invitee_email=req.invitee_email,
        role_id=req.role_id,
        expires_in_days=7
    )
    
    print(f"✅ Invitation created: {invitation['id']}")
    
    # 9. Get role name if role_id provided
    role_name = None
    if req.role_id:
        role = org_service.get_role_by_id(req.role_id)
        role_name = role['name'] if role else None
    
    # 10. Get inviter name
    inviter_name = await org_service.get_inviter_name(user_id)
    
    invitation_link = org_service.generate_invitation_link(invitation['token'], FRONTEND_URL)
    
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
        token=invitation['token'],
        role_id=req.role_id,
        role_name=role_name,
        status=invitation['status'],
        expires_at=invitation['expires_at'],
        created_at=invitation['created_at'],
        accepted_at=invitation.get('accepted_at'),
        invitation_link=invitation_link
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
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    org_service = OrganizationService(org_repo, supabase)
    
    # 1. Get invitation and check expiry
    invitation = org_service.get_invitation_by_token(req.token, status="pending")
    
    if org_service.check_invitation_expiry(invitation):
        org_service.mark_invitation_expired(invitation['id'])
        raise HTTPException(status_code=400, detail="Invitation has expired")
    
    # 2. Get organization
    org = await org_service.get_organization_or_404(invitation['organization_id'])
    print(f"📋 Organization: {org.name}")
    print(f"   Invitee: {invitation['invitee_email']}")
    
    # 3. Check if already a member
    if org_service.check_user_is_member(org.id, user_id):
        # Already a member - just mark invitation as accepted
        org_service.mark_invitation_accepted(invitation['id'], user_id)
        
        return {
            "success": True,
            "organization_id": org.id,
            "organization_name": org.name,
            "message": "You are already a member of this organization"
        }
    
    # 4. Check if organization has available seats (Business plan)
    org_service.validate_seats_available_for_acceptance(org)
    print(f"✅ Seat available for new member")
    
    # 5. Add member
    await org_service.add_member_to_organization(
        organization_id=org.id,
        user_id=user_id,
        role_id=invitation.get('role_id')
    )
    print(f"✅ Added user as organization member")
    
    # 6. Update invitation status
    org_service.mark_invitation_accepted(invitation['id'], user_id)
    print(f"✅ Invitation marked as accepted")
    
    # 7. Update active_member_count
    await org_service.increment_active_member_count(org)
    print(f"✅ Updated active_member_count")
    print(f"{'='*60}\n")
    
    return {
        "success": True,
        "organization_id": org.id,
        "organization_name": org.name,
        "message": "Successfully joined organization"
    }


@router.get("/{organization_id}/invitations", response_model=OrganizationInvitationsListResponse)
async def get_organization_invitations(organization_id: int):
    """Get all invitations for an organization"""
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    org_service = OrganizationService(org_repo, supabase)
    
    # Get organization
    org = await org_service.get_organization_or_404(organization_id)
    
    # Get all invitations
    invitations_data = org_service.get_all_invitations(organization_id)
    
    # Get role names (filter out None values)
    role_ids = [inv['role_id'] for inv in invitations_data if inv.get('role_id') is not None]
    roles_map = await org_service.get_roles_map(role_ids)
    roles_names_map = {rid: r['name'] for rid, r in roles_map.items()}
    
    # Get inviter names
    inviter_ids = list(set([inv['inviter_id'] for inv in invitations_data]))
    inviters_map = {}
    for inviter_id in inviter_ids:
        name = await org_service.get_inviter_name(inviter_id)
        if name:
            inviters_map[inviter_id] = name
    
    # Build response
    invitations = []
    pending_count = 0
    
    for inv in invitations_data:
        if inv['status'] == 'pending':
            pending_count += 1
        
        # Get role name for this invitation
        inv_role_id = inv.get('role_id')
        role_name = roles_names_map.get(inv_role_id) if inv_role_id else None
        
        invitations.append(OrganizationInvitationResponse(
            id=inv['id'],
            organization_id=inv['organization_id'],
            organization_name=org.name,
            inviter_id=inv['inviter_id'],
            inviter_name=inviters_map.get(inv['inviter_id']),
            invitee_email=inv['invitee_email'],
            invitee_id=inv.get('invitee_id'),
            token=inv['token'],
            role_id=inv_role_id,
            role_name=role_name,
            status=InvitationStatus(inv['status']),  # type: ignore
            expires_at=inv['expires_at'],
            created_at=inv['created_at'],
            accepted_at=inv.get('accepted_at'),
            invitation_link=org_service.generate_invitation_link(inv['token'], FRONTEND_URL)
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
    
    # Initialize services
    org_repo = OrganizationRepository(supabase)
    org_service = OrganizationService(org_repo, supabase)
    
    # Get invitation
    invitation = org_service.get_invitation_by_id(invitation_id)
    organization_id = invitation['organization_id']
    
    # Verify user is owner/admin
    await org_service.verify_user_is_owner_or_admin(organization_id, user_id)
    
    # Verify invitation is pending
    org_service.validate_invitation_status(invitation, "pending")
    
    # Cancel invitation
    org_service.mark_invitation_cancelled(invitation_id)
    
    return {"success": True, "message": "Invitation cancelled"}
