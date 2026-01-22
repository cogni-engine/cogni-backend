"""Notification Service - Handles notification-triggered conversations"""
import logging

from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.repositories.notifications import AINotificationRepository
from app.infra.supabase.repositories.threads import ThreadRepository
from app.infra.supabase.repositories.ai_messages import AIMessageRepository
from app.models.notification import AINotificationUpdate, NotificationStatus
from app.services.llm.call_llm import LLMService
from app.services.cogno.conversation.conversation_service import conversation_stream
from .prompts.notification_prompt import build_daily_summary_prompt

logger = logging.getLogger(__name__)


async def handle_notification_click(notification_id: int, thread_id: int) -> None:
    """
    Handle notification click event.
    Generates AI conversation response and marks notification as resolved.
    
    Args:
        notification_id: Notification ID that was clicked
        thread_id: Thread ID to send message to
    """
    supabase_client = get_supabase_client()
    notification_repo = AINotificationRepository(supabase_client)
    
    try:
        # Get notification
        notification = await notification_repo.find_by_id(notification_id)
        if not notification:
            logger.error(f"Notification {notification_id} not found")
            return
        
        logger.info(f"Handling notification click: {notification_id} - {notification.title}")
        
        # Generate AI response using conversation stream
        async for chunk in conversation_stream(
            thread_id=thread_id,
            user_message=None,
            notification_triggered=True,
            notification_context=notification
        ):
            # Just consume the stream - conversation_stream will save the message
            pass
        
        # Mark AI notification as resolved
        update = AINotificationUpdate(status=NotificationStatus.RESOLVED)
        await notification_repo.update(notification_id, update)
        
        logger.info(f"Notification {notification_id} marked as resolved")
        
    except Exception as e:
        logger.error(f"Error handling notification click: {e}")
        raise


async def daily_notification_check(workspace_id: int) -> None:
    """
    Daily notification check (to be called at 10:00 AM JST).
    Checks if latest message is notification-triggered, and if not,
    summarizes pending notifications and generates AI message.
    
    Args:
        workspace_id: Workspace ID to check
    """
    supabase_client = get_supabase_client()
    thread_repo = ThreadRepository(supabase_client)
    ai_message_repo = AIMessageRepository(supabase_client)
    notification_repo = AINotificationRepository(supabase_client)
    
    try:
        logger.info(f"Starting daily notification check for workspace {workspace_id}")
        
        # Get latest thread in workspace
        recent_threads = await thread_repo.get_recent_threads(workspace_id, limit=1)
        if not recent_threads:
            logger.info(f"No threads found in workspace {workspace_id}")
            return
        
        latest_thread = recent_threads[0]
        logger.info(f"Latest thread: {latest_thread.id}")
        
        # Get latest message in thread
        recent_messages = await ai_message_repo.get_recent_messages(latest_thread.id, limit=1)
        if not recent_messages:
            logger.info(f"No messages in thread {latest_thread.id}")
            # No messages yet, proceed with notification check
        else:
            latest_message = recent_messages[0]
            # Check if latest message is notification-triggered
            if latest_message.meta and latest_message.meta.get("notification_trigger"):
                logger.info(f"Latest message is notification-triggered, skipping daily check")
                return
        
        # Get all sent/scheduled notifications for users in workspace
        # Note: We need to get all users in workspace first
        # For now, we'll get notifications by workspace-related approach
        # This is a simplification - you might need to adjust based on your data model
        
        # Get sent and scheduled notifications
        sent_notifications = await notification_repo.find_by_filters({"status": NotificationStatus.SENT})
        scheduled_notifications = await notification_repo.find_by_filters({"status": NotificationStatus.SCHEDULED})
        
        all_notifications = sent_notifications + scheduled_notifications
        
        if not all_notifications:
            logger.info("No pending notifications found")
            return
        
        logger.info("Found %d pending notifications", len(all_notifications))
        
        # Use LLM to summarize notifications into natural language
        summary_prompt = build_daily_summary_prompt(all_notifications)
        
        llm_service = LLMService(model="gpt-5-mini", temperature=0.7)
        messages = [{"role": "user", "content": summary_prompt}]
        
        # Get summary (non-streaming)
        response = await llm_service.invoke(messages)
        daily_summary = response.strip()
        
        logger.info(f"Generated daily summary: {daily_summary[:100]}...")
        
        # Generate conversation AI message with the summary context
        async for chunk in conversation_stream(
            thread_id=latest_thread.id,
            user_message=None,
            notification_triggered=True,
            daily_summary_context=daily_summary
        ):
            # Just consume the stream - conversation_stream will save the message
            pass
        
        logger.info(f"Daily notification check completed for workspace {workspace_id}")
        
    except Exception as e:
        logger.error(f"Error in daily notification check: {e}")
        raise

