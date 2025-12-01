"""
Push Notification Service

Handles sending push notifications via Expo Push API
"""

import httpx
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from supabase import Client
from app.models.push_notification import (
    ExpoPushMessage,
    PushNotificationStatus,
)

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class PushNotificationService:
    """Service for sending push notifications via Expo"""

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client

    async def send_notification(self, notification_id: int) -> Dict[str, Any]:
        """
        Send push notification via Expo Push API

        Args:
            notification_id: ID of the notification to send

        Returns:
            Dictionary with send results
        """
        try:
            # Fetch the notification from database
            response = (
                self.supabase.table("push_notifications")
                .select("*")
                .eq("id", notification_id)
                .single()
                .execute()
            )

            if not response.data:
                raise ValueError("Notification not found")

            notification = response.data

            # Skip if already sent
            if notification.get("status") == PushNotificationStatus.SENT:
                return {
                    "message": "Already sent",
                    "notificationId": notification_id,
                    "success": True,
                    "sent": 0,
                    "failed": 0,
                    "tickets": [],
                }

            # Fetch push tokens for the user
            tokens_response = (
                self.supabase.table("push_tokens")
                .select("expo_push_token")
                .eq("user_id", notification["user_id"])
                .execute()
            )

            tokens = tokens_response.data

            if not tokens or len(tokens) == 0:
                # No tokens found - mark as failed
                await self._update_notification_status(
                    notification_id, PushNotificationStatus.FAILED, "No push tokens registered"
                )
                return {
                    "message": "No push tokens found",
                    "notificationId": notification_id,
                    "success": False,
                    "sent": 0,
                    "failed": 0,
                    "tickets": [],
                }

            # Get unread message count for the user
            unread_message_count = await self.get_unread_message_count(notification["user_id"])

            # Build Expo push messages
            messages = [
                {
                    "to": token["expo_push_token"],
                    "badge": unread_message_count,
                    "title": notification["title"],
                    "body": notification["body"],
                    "data": notification.get("data", {}),
                    "sound": "default",
                    "priority": "high",
                    "channelId": "default",
                }
                for token in tokens
            ]

            # Send to Expo Push API
            async with httpx.AsyncClient() as client:
                expo_response = await client.post(
                    EXPO_PUSH_URL,
                    json=messages,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip, deflate",
                    },
                    timeout=10.0,
                )

                if expo_response.status_code != 200:
                    error_detail = expo_response.text
                    await self._update_notification_status(
                        notification_id,
                        PushNotificationStatus.FAILED,
                        f"Expo API error: {error_detail}",
                    )
                    raise Exception(f"Failed to send push notification: {error_detail}")

                result = expo_response.json()
                tickets = result.get("data", [])

                # Check for errors in tickets
                errors = [t for t in tickets if t.get("status") == "error"]

                if errors:
                    # Handle invalid tokens
                    for i, error in enumerate(errors):
                        error_type = error.get("details", {}).get("error")
                        error_message = error.get("message", "")

                        if error_type == "DeviceNotRegistered" or "not registered" in error_message:
                            # Remove invalid token
                            if i < len(tokens):
                                invalid_token = tokens[i]["expo_push_token"]
                                self.supabase.table("push_tokens").delete().eq(
                                    "expo_push_token", invalid_token
                                ).execute()
                                logger.info(f"Removed invalid token: {invalid_token}")

                    # Mark as sent if at least some succeeded
                    if len(errors) < len(tickets):
                        await self._update_notification_status(
                            notification_id,
                            PushNotificationStatus.SENT,
                            f"Sent to {len(tickets) - len(errors)} devices, {len(errors)} failed",
                        )
                    else:
                        await self._update_notification_status(
                            notification_id, PushNotificationStatus.FAILED, "All devices failed"
                        )
                else:
                    # All succeeded
                    await self._update_notification_status(
                        notification_id, PushNotificationStatus.SENT, None
                    )

                return {
                    "success": True,
                    "notificationId": notification_id,
                    "sent": len(tickets) - len(errors),
                    "failed": len(errors),
                    "tickets": tickets,
                }

        except Exception as e:
            logger.error(f"Error sending push notification: {str(e)}")
            await self._update_notification_status(
                notification_id, PushNotificationStatus.FAILED, str(e)
            )
            raise

    async def _update_notification_status(
        self, notification_id: int, status: str, error_message: Optional[str] = None
    ):
        """Update notification status in database"""
        update_data = {
            "status": status,
            "sent_at": datetime.utcnow().isoformat(),
        }

        if error_message:
            update_data["error_message"] = error_message

        self.supabase.table("push_notifications").update(update_data).eq(
            "id", notification_id
        ).execute()

    async def get_unread_message_count(self, user_id: str) -> int:
        """
        Get unread message count for the user
        
        Calls the RPC function 'get_unread_workspace_message_count_excl_self'
        which returns a single bigint value (count of unread messages excluding self)
        """
        try:
            response = self.supabase.rpc(
                'get_unread_workspace_message_count_excl_self',
                {'p_user_id': user_id}
            ).execute()
            
            # The RPC function returns a single scalar bigint value
            if response.data is not None:
                return int(response.data)
            
            return 0
        except Exception as e:
            logger.error(f"Error getting unread message count for user {user_id}: {e}")
            return 0