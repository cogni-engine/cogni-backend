from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import logging

from app.infra.supabase.client import get_supabase_client
from app.middleware.auth import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Delete a user account by:
    1. Banning the user via Supabase Admin Auth
    2. Setting deleted_at timestamp on user_profile
    """
    # Verify the user is deleting their own account
    if current_user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own account"
        )
    
    try:
        supabase = get_supabase_client()
        
        # Ban the user using Supabase Admin Auth
        # The service role key allows admin operations
        # Ban duration of 876000h (100 years) effectively makes it permanent
        try:
            # Use admin auth to ban the user via Supabase Admin REST API
            import httpx
            import os
            
            supabase_url = os.getenv("SUPABASE_URL")
            service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            
            if supabase_url and service_role_key:
                # Use Supabase Admin REST API to ban user
                ban_url = f"{supabase_url}/auth/v1/admin/users/{user_id}"
                headers = {
                    "apikey": service_role_key,
                    "Authorization": f"Bearer {service_role_key}",
                    "Content-Type": "application/json"
                }
                ban_payload = {
                    "ban_duration": "876000h"  # 100 years (effectively permanent)
                }
                
                with httpx.Client() as client:
                    ban_response = client.put(ban_url, json=ban_payload, headers=headers, timeout=10.0)
                    if ban_response.status_code not in [200, 204]:
                        logger.warning(
                            f"Could not ban user via admin API: {ban_response.status_code} - {ban_response.text}"
                        )
            else:
                logger.warning("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set, skipping ban")
        except Exception as e:
            # If admin auth fails, log but continue with deleted_at update
            logger.warning(f"Could not ban user via admin auth: {e}")
            # Continue with deleted_at update even if ban fails
        
        # Update user_profile to set deleted_at timestamp
        # Use datetime.now(timezone.utc) instead of deprecated datetime.utcnow()
        # Supabase will handle the datetime conversion automatically
        now = datetime.now(timezone.utc)
        update_response = supabase.table("user_profiles").update({
            "deleted_at": now.isoformat()
        }).eq("id", user_id).execute()
        
        # Check if update was successful
        # Supabase returns empty list if no rows matched, or list with updated row(s) if successful
        if not update_response.data or len(update_response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="User profile not found or could not be updated"
            )
        
        # Verify that deleted_at was actually set
        updated_profile = update_response.data[0]
        if not updated_profile.get("deleted_at"):
            logger.error(f"Failed to set deleted_at for user {user_id}")
            raise HTTPException(
                status_code=500,
                detail="Failed to set deleted_at timestamp"
            )
        
        return {
            "message": "User account deleted successfully",
            "deleted_at": updated_profile["deleted_at"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete user account: {str(e)}"
        )

