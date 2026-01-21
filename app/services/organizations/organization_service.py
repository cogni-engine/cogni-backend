"""Organization service for member and invitation management"""
import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import uuid
from fastapi import HTTPException

from app.infra.supabase.repositories.organizations import OrganizationRepository
from app.models.organization import Organization, OrganizationUpdate

logger = logging.getLogger(__name__)


class OrganizationService:
    """Service for organization member and invitation management operations"""
    
    def __init__(self, org_repo: OrganizationRepository, supabase_client):
        self.org_repo = org_repo
        self.supabase = supabase_client
    
    # ============================================================================
    # AUTHORIZATION & ACCESS CONTROL
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
    
    async def verify_user_is_owner_or_admin(
        self,
        organization_id: int,
        user_id: str
    ) -> Dict:
        """
        Verify user is owner or admin of organization
        
        Single responsibility: Owner/Admin authorization
        
        Returns:
            Member record
            
        Raises:
            HTTPException(403): User is not a member or not owner/admin
        """
        result = self.supabase.table('organization_members') \
            .select('*') \
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
        
        role_id = result.data.get('role_id')
        if role_id not in [1, 2]:  # owner or admin
            logger.warning(
                f"User {user_id} is not owner/admin of organization {organization_id} "
                f"(role_id={role_id})"
            )
            raise HTTPException(
                status_code=403,
                detail="Only organization owners/admins can perform this action"
            )
        
        return result.data
    
    # ============================================================================
    # MEMBER OPERATIONS
    # ============================================================================
    
    def get_organization_member(
        self,
        member_id: int,
        organization_id: int
    ) -> Dict:
        """
        Get a specific organization member by ID
        
        Single responsibility: Fetch member record
        
        Raises:
            HTTPException(404): Member not found
        """
        result = self.supabase.table('organization_members') \
            .select('*') \
            .eq('id', member_id) \
            .eq('organization_id', organization_id) \
            .eq('status', 'active') \
            .single() \
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Member not found"
            )
        
        return result.data
    
    def get_organization_members(
        self,
        organization_id: int
    ) -> List[Dict]:
        """
        Get all active members of an organization
        
        Single responsibility: Fetch all active members
        """
        result = self.supabase.table('organization_members') \
            .select('*') \
            .eq('organization_id', organization_id) \
            .eq('status', 'active') \
            .execute()
        
        return result.data or []
    
    def update_member_role(
        self,
        member_id: int,
        new_role_id: int
    ) -> None:
        """
        Update a member's role
        
        Single responsibility: Role update operation
        """
        self.supabase.table('organization_members') \
            .update({"role_id": new_role_id}) \
            .eq('id', member_id) \
            .execute()
        
        logger.info(f"Updated member {member_id} to role {new_role_id}")
    
    def deactivate_member(
        self,
        member_id: int
    ) -> None:
        """
        Mark a member as inactive (soft delete)
        
        Single responsibility: Member deactivation
        """
        self.supabase.table('organization_members') \
            .update({"status": "inactive"}) \
            .eq('id', member_id) \
            .execute()
        
        logger.info(f"Deactivated member {member_id}")
    
    async def increment_active_member_count(
        self,
        org: Organization
    ) -> Organization:
        """
        Increment organization's active member count by 1
        
        Single responsibility: Member count increment
        """
        current_count = org.active_member_count or 0
        new_count = current_count + 1
        
        updated_org = await self.org_repo.update(
            org.id,
            OrganizationUpdate(active_member_count=new_count)
        )
        
        logger.info(f"Incremented active_member_count for org {org.id}: {current_count} → {new_count}")
        return updated_org
    
    async def decrement_active_member_count(
        self,
        org: Organization
    ) -> Organization:
        """
        Decrement organization's active member count by 1
        
        Single responsibility: Member count decrement
        """
        current_count = org.active_member_count or 0
        new_count = max(current_count - 1, 0)
        
        updated_org = await self.org_repo.update(
            org.id,
            OrganizationUpdate(active_member_count=new_count)
        )
        
        logger.info(f"Decremented active_member_count for org {org.id}: {current_count} → {new_count}")
        return updated_org
    
    async def deactivate_non_owner_members(
        self,
        organization_id: int
    ) -> int:
        """
        Deactivate all members except the owner (role_id = 1)
        
        This is used when an organization is downgraded to the free plan (1 seat).
        Only the owner remains active.
        
        Single responsibility: Bulk member deactivation on downgrade
        
        Args:
            organization_id: Organization ID
            
        Returns:
            Number of members deactivated
        """
        print(f"   🚫 Deactivating all non-owner members for organization {organization_id}...")
        
        # Get all active non-owner members
        result = self.supabase.table('organization_members') \
            .select('id, user_id, role_id') \
            .eq('organization_id', organization_id) \
            .eq('status', 'active') \
            .neq('role_id', 1) \
            .execute()
        
        members_to_deactivate = result.data or []
        count = len(members_to_deactivate)
        
        if count == 0:
            print(f"   ℹ️  No non-owner members to deactivate")
            logger.info(f"No non-owner members to deactivate for organization {organization_id}")
            return 0
        
        print(f"   📋 Found {count} non-owner member(s) to deactivate:")
        for member in members_to_deactivate:
            print(f"      - Member ID: {member['id']}, User ID: {member['user_id']}, Role ID: {member['role_id']}")
        
        # Deactivate all non-owner members
        self.supabase.table('organization_members') \
            .update({"status": "inactive"}) \
            .eq('organization_id', organization_id) \
            .eq('status', 'active') \
            .neq('role_id', 1) \
            .execute()
        
        print(f"   ✅ Deactivated {count} non-owner member(s)")
        logger.info(f"Deactivated {count} non-owner members for organization {organization_id}")
        
        # Update active_member_count to 1 (only owner remains)
        org = await self.org_repo.find_by_id(organization_id)
        if org:
            await self.org_repo.update(
                organization_id,
                OrganizationUpdate(active_member_count=1)
            )
            print(f"   ✅ Updated active_member_count to 1")
            logger.info(f"Updated active_member_count to 1 for organization {organization_id}")
        
        return count
    
    # ============================================================================
    # DATA ENRICHMENT
    # ============================================================================
    
    async def get_user_profiles_map(
        self,
        user_ids: List[str]
    ) -> Dict[str, Dict]:
        """
        Get user profiles for multiple users
        
        Single responsibility: Batch profile fetching
        
        Returns:
            Dict mapping user_id -> profile data
        """
        if not user_ids:
            return {}
        
        result = self.supabase.table('user_profiles') \
            .select('*') \
            .in_('id', user_ids) \
            .execute()
        
        profiles = result.data or []
        return {p['id']: p for p in profiles}
    
    async def get_user_emails_map(
        self,
        user_ids: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Get user emails from auth.users
        
        Single responsibility: Batch email fetching
        
        Returns:
            Dict mapping user_id -> email
        """
        all_users = self.supabase.auth.admin.list_users()
        
        if user_ids:
            # Filter to only requested user IDs
            return {
                user.id: user.email 
                for user in all_users 
                if user.id in user_ids and user.email
            }
        else:
            # Return all
            return {
                user.id: user.email 
                for user in all_users 
                if user.email
            }
    
    async def get_roles_map(
        self,
        role_ids: List[int]
    ) -> Dict[int, Dict]:
        """
        Get role information for multiple role IDs
        
        Single responsibility: Batch role fetching
        
        Returns:
            Dict mapping role_id -> role data
        """
        if not role_ids:
            return {}
        
        result = self.supabase.table('organization_member_roles') \
            .select('*') \
            .in_('id', role_ids) \
            .execute()
        
        roles = result.data or []
        return {r['id']: r for r in roles}
    
    def get_role_by_id(self, role_id: int) -> Optional[Dict]:
        """
        Get a single role by ID
        
        Single responsibility: Single role lookup
        """
        result = self.supabase.table('organization_member_roles') \
            .select('*') \
            .eq('id', role_id) \
            .single() \
            .execute()
        
        return result.data if result.data else None
    
    async def enrich_members_with_user_data(
        self,
        members: List[Dict]
    ) -> List[Dict]:
        """
        Enrich member data with profiles, emails, and roles
        
        Single responsibility: Complete member data enrichment
        
        Combines member data with:
        - User profiles (name, avatar)
        - User emails (from auth.users)
        - Role names
        """
        if not members:
            return []
        
        # Get unique IDs
        user_ids = list(set([m['user_id'] for m in members]))
        role_ids = list(set([m['role_id'] for m in members if m.get('role_id')]))
        
        # Fetch all data in parallel
        profiles_map = await self.get_user_profiles_map(user_ids)
        emails_map = await self.get_user_emails_map(user_ids)
        roles_map = await self.get_roles_map(role_ids)
        
        # Enrich each member
        enriched = []
        for member in members:
            user_id = member['user_id']
            role_id = member.get('role_id')
            
            profile = profiles_map.get(user_id, {})
            email = emails_map.get(user_id, 'unknown@example.com')
            role = roles_map.get(role_id) if role_id else None
            
            enriched.append({
                **member,
                'email': email,
                'name': profile.get('name'),
                'avatar_url': profile.get('avatar_url'),
                'role_name': role['name'] if role else None
            })
        
        return enriched
    
    # ============================================================================
    # INVITATION OPERATIONS
    # ============================================================================
    
    def get_invitation_by_token(
        self,
        token: str,
        status: Optional[str] = None
    ) -> Dict:
        """
        Get invitation by token
        
        Single responsibility: Invitation lookup
        
        Raises:
            HTTPException(404): Invitation not found
        """
        query = self.supabase.table('organization_invitations') \
            .select('*') \
            .eq('token', token)
        
        if status:
            query = query.eq('status', status)
        
        result = query.single().execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Invitation not found or already used"
            )
        
        return result.data
    
    def get_invitation_by_id(self, invitation_id: str) -> Dict:
        """
        Get invitation by ID
        
        Single responsibility: Invitation lookup by ID
        
        Raises:
            HTTPException(404): Invitation not found
        """
        result = self.supabase.table('organization_invitations') \
            .select('*') \
            .eq('id', invitation_id) \
            .single() \
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Invitation not found"
            )
        
        return result.data
    
    def check_invitation_expiry(
        self,
        invitation: Dict
    ) -> bool:
        """
        Check if invitation has expired
        
        Single responsibility: Expiry validation
        
        Returns:
            True if expired, False otherwise
        """
        expires_at = datetime.fromisoformat(invitation['expires_at'].replace('Z', '+00:00'))
        now = datetime.now(expires_at.tzinfo)
        return now > expires_at
    
    def mark_invitation_expired(
        self,
        invitation_id: str
    ) -> None:
        """
        Mark invitation as expired
        
        Single responsibility: Status update to expired
        """
        self.supabase.table('organization_invitations') \
            .update({"status": "expired"}) \
            .eq('id', invitation_id) \
            .execute()
        
        logger.info(f"Marked invitation {invitation_id} as expired")
    
    def mark_invitation_accepted(
        self,
        invitation_id: str,
        user_id: str
    ) -> None:
        """
        Mark invitation as accepted
        
        Single responsibility: Status update to accepted
        """
        self.supabase.table('organization_invitations') \
            .update({
                "status": "accepted",
                "accepted_at": datetime.utcnow().isoformat(),
                "invitee_id": user_id
            }) \
            .eq('id', invitation_id) \
            .execute()
        
        logger.info(f"Marked invitation {invitation_id} as accepted by {user_id}")
    
    def mark_invitation_cancelled(
        self,
        invitation_id: str
    ) -> None:
        """
        Mark invitation as cancelled
        
        Single responsibility: Status update to cancelled
        """
        self.supabase.table('organization_invitations') \
            .update({"status": "cancelled"}) \
            .eq('id', invitation_id) \
            .execute()
        
        logger.info(f"Marked invitation {invitation_id} as cancelled")
    
    def create_invitation(
        self,
        organization_id: int,
        inviter_id: str,
        invitee_email: str,
        role_id: Optional[int] = None,
        expires_in_days: int = 7
    ) -> Dict:
        """
        Create a new organization invitation
        
        Single responsibility: Invitation creation
        
        Returns:
            Created invitation record
        """
        token = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        invitation_data = {
            "organization_id": organization_id,
            "inviter_id": inviter_id,
            "invitee_email": invitee_email.lower(),
            "invitee_id": None,
            "token": token,
            "role_id": role_id,
            "status": "pending",
            "expires_at": expires_at.isoformat(),
        }
        
        result = self.supabase.table('organization_invitations') \
            .insert(invitation_data) \
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to create invitation"
            )
        
        invitation = result.data[0]
        logger.info(f"Created invitation {invitation['id']} for {invitee_email}")
        
        return invitation
    
    def get_pending_invitations_count(
        self,
        organization_id: int
    ) -> int:
        """
        Count pending invitations for organization
        
        Single responsibility: Pending count query
        """
        result = self.supabase.table('organization_invitations') \
            .select('id', count='exact') \
            .eq('organization_id', organization_id) \
            .eq('status', 'pending') \
            .execute()
        
        return result.count or 0
    
    def get_all_invitations(
        self,
        organization_id: int
    ) -> List[Dict]:
        """
        Get all invitations for an organization
        
        Single responsibility: Fetch all invitations
        """
        result = self.supabase.table('organization_invitations') \
            .select('*') \
            .eq('organization_id', organization_id) \
            .order('created_at', desc=True) \
            .execute()
        
        return result.data or []
    
    def check_existing_pending_invitation(
        self,
        organization_id: int,
        invitee_email: str
    ) -> Optional[Dict]:
        """
        Check for existing valid pending invitation
        
        Single responsibility: Duplicate invitation check
        
        Returns:
            Pending invitation if exists and not expired, None otherwise
        """
        result = self.supabase.table('organization_invitations') \
            .select('*') \
            .eq('organization_id', organization_id) \
            .eq('invitee_email', invitee_email.lower()) \
            .eq('status', 'pending') \
            .execute()
        
        if not result.data:
            return None
        
        # Check if any pending invitation is still valid (not expired)
        now = datetime.utcnow()
        
        for invite in result.data:
            expires_at = datetime.fromisoformat(invite['expires_at'].replace('Z', '+00:00'))
            if expires_at > now.replace(tzinfo=expires_at.tzinfo):
                # Found a valid pending invitation
                return invite
        
        # All pending invitations are expired
        return None
    
    # ============================================================================
    # VALIDATION
    # ============================================================================
    
    def validate_member_is_not_owner(
        self,
        member: Dict
    ) -> None:
        """
        Validate member is not an owner
        
        Single responsibility: Owner protection validation
        
        Raises:
            HTTPException(400): Member is owner
        """
        if member.get('role_id') == 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot perform this action on organization owners"
            )
    
    def validate_not_self(
        self,
        member_user_id: str,
        current_user_id: str,
        action: str = "this action"
    ) -> None:
        """
        Validate user is not performing action on themselves
        
        Single responsibility: Self-action prevention
        
        Raises:
            HTTPException(400): User trying to act on self
        """
        if member_user_id == current_user_id:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot perform {action} on yourself"
            )
    
    def validate_role_assignable(
        self,
        role_id: int
    ) -> None:
        """
        Validate role can be assigned to members
        
        Single responsibility: Role assignment validation
        
        Raises:
            HTTPException(400): Cannot assign this role (e.g., owner)
        """
        if role_id == 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot assign owner role to members"
            )
    
    async def validate_user_not_member(
        self,
        organization_id: int,
        user_email: str
    ) -> None:
        """
        Validate user is not already a member
        
        Single responsibility: Duplicate member check
        
        Raises:
            HTTPException(400): User is already a member
        """
        # Get all active members
        members_result = self.supabase.table('organization_members') \
            .select('id, user_id') \
            .eq('organization_id', organization_id) \
            .eq('status', 'active') \
            .execute()
        
        if not members_result.data:
            return  # No members, email is not a member
        
        # Get user IDs
        user_ids = [m['user_id'] for m in members_result.data]
        
        # Fetch emails for these users
        emails_map = await self.get_user_emails_map(user_ids)
        member_emails = [email.lower() for email in emails_map.values()]
        
        # Check if invited email is already a member
        if user_email.lower() in member_emails:
            raise HTTPException(
                status_code=400,
                detail="User is already a member of this organization"
            )
    
    def validate_business_plan_for_invitations(
        self,
        org: Organization
    ) -> None:
        """
        Validate organization is on Business plan (required for invitations)
        
        Single responsibility: Plan type validation for invitations
        
        Raises:
            HTTPException(400): Not on Business plan
        """
        if org.plan_type != "business":
            raise HTTPException(
                status_code=400,
                detail=f"Organization invitations are only available for Business plans. "
                       f"Current plan: {org.plan_type}. "
                       f"Please upgrade to Business to invite team members."
            )
    
    def validate_seats_available_for_invitation(
        self,
        org: Organization,
        pending_invitations_count: Optional[int] = None
    ) -> None:
        """
        Validate organization has seats available for new invitation
        
        Single responsibility: Seat availability validation
        
        Args:
            org: Organization
            pending_invitations_count: Optional count of pending invitations
                                       (will query if not provided)
        
        Raises:
            HTTPException(400): Not enough seats
        """
        if not org.stripe_subscription_id:
            return  # No subscription, no seat limit
        
        current_member_count = org.active_member_count or 0
        
        # Get pending invitations count if not provided
        if pending_invitations_count is None:
            pending_invitations_count = self.get_pending_invitations_count(org.id)
        
        # Calculate projected member count
        projected_member_count = current_member_count + pending_invitations_count + 1
        current_seat_count = org.seat_count or 1
        
        logger.info(
            f"Seat check for org {org.id}: "
            f"current={current_member_count}, pending={pending_invitations_count}, "
            f"projected={projected_member_count}, seats={current_seat_count}"
        )
        
        if projected_member_count > current_seat_count:
            seats_needed = projected_member_count - current_seat_count
            raise HTTPException(
                status_code=400,
                detail=f"Not enough seats available. You need {seats_needed} more seat(s). "
                       f"Current seats: {current_seat_count}, Required: {projected_member_count}"
            )
    
    def validate_seats_available_for_acceptance(
        self,
        org: Organization
    ) -> None:
        """
        Validate organization has seats available for accepting invitation
        
        Single responsibility: Seat availability for acceptance
        
        Raises:
            HTTPException(400): No seats available
        """
        if org.plan_type != "business" or not org.stripe_subscription_id:
            return  # No seat limit for non-Business plans
        
        current_member_count = org.active_member_count or 0
        current_seat_count = org.seat_count or 1
        
        if current_member_count >= current_seat_count:
            raise HTTPException(
                status_code=400,
                detail=f"Organization has reached its seat limit ({current_seat_count} seats). "
                       f"Please contact your organization admin to add more seats."
            )
    
    def validate_invitation_status(
        self,
        invitation: Dict,
        expected_status: str
    ) -> None:
        """
        Validate invitation has expected status
        
        Single responsibility: Invitation status validation
        
        Raises:
            HTTPException(400): Wrong status
        """
        if invitation['status'] != expected_status:
            raise HTTPException(
                status_code=400,
                detail=f"Invitation must be {expected_status} to perform this action"
            )
    
    # ============================================================================
    # MEMBER ADDITION
    # ============================================================================
    
    async def add_member_to_organization(
        self,
        organization_id: int,
        user_id: str,
        role_id: Optional[int] = None
    ) -> Dict:
        """
        Add a user as a member of an organization
        
        Single responsibility: Member creation
        
        Args:
            organization_id: Organization ID
            user_id: User ID to add
            role_id: Role ID (defaults to 'member' role if None)
            
        Returns:
            Created member record
        """
        # Get role_id if not provided
        if role_id is None:
            role_id = self.get_default_member_role_id()
        
        member_data = {
            "organization_id": organization_id,
            "user_id": user_id,
            "role_id": role_id,
            "status": "active"
        }
        
        result = self.supabase.table('organization_members') \
            .insert(member_data) \
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to add member to organization"
            )
        
        member = result.data[0]
        logger.info(f"Added user {user_id} to organization {organization_id}")
        
        return member
    
    def check_user_is_member(
        self,
        organization_id: int,
        user_id: str
    ) -> bool:
        """
        Check if user is an active member of organization
        
        Single responsibility: Membership check
        
        Returns:
            True if user is active member, False otherwise
        """
        result = self.supabase.table('organization_members') \
            .select('id') \
            .eq('organization_id', organization_id) \
            .eq('user_id', user_id) \
            .eq('status', 'active') \
            .execute()
        
        return bool(result.data)
    
    # ============================================================================
    # HELPER METHODS
    # ============================================================================
    
    def get_default_member_role_id(self) -> int:
        """
        Get the default 'member' role ID
        
        Single responsibility: Default role lookup
        
        Returns:
            Role ID for 'member' role (fallback to 3)
        """
        try:
            result = self.supabase.table('organization_member_roles') \
                .select('id') \
                .eq('name', 'member') \
                .single() \
                .execute()
            
            if result.data:
                return result.data['id']
        except Exception as e:
            logger.warning(f"Failed to fetch default member role: {e}")
        
        # Fallback to 3
        return 3
    
    def generate_invitation_link(
        self,
        token: str,
        frontend_url: str
    ) -> str:
        """
        Generate invitation link URL
        
        Single responsibility: URL generation
        """
        return f"{frontend_url}/invite/org/{token}"
    
    async def get_inviter_name(self, user_id: str) -> Optional[str]:
        """
        Get user's name from profile
        
        Single responsibility: Inviter name lookup
        """
        try:
            result = self.supabase.table('user_profiles') \
                .select('name') \
                .eq('id', user_id) \
                .single() \
                .execute()
            
            if result.data:
                return result.data.get('name')
        except Exception:
            pass
        
        return None

