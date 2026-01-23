"""SQLAlchemy repository for AI Notifications"""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, func, select, cast, String, update, text

# SQLAlchemy ORM models
from app.db.models.ai_notification import (
    AINotification as AINotificationORM, 
    NotificationStatus,
    ReactionStatus
)
from app.db.models.task_result import TaskResult as TaskResultORM
from app.db.models.task import Task as TaskORM
from app.db.models.note import Note as NoteORM
from app.db.models.workspace_member import WorkspaceMember as WorkspaceMemberORM
from app.db.models.user_profile import UserProfile as UserProfileORM

# Pydantic domain models (feature-local)
from app.features.ai_notifications.domain import AINotification
from app.features.ai_notifications.schemas import ReactedAINotification, NoteInfo, UserInfo

logger = logging.getLogger(__name__)


class AINotificationRepository:
    """Repository for AI Notification operations using SQLAlchemy"""
    
    def __init__(self, db: AsyncSession):
        """
        Initialize the repository with a database session.
        
        Args:
            db: SQLAlchemy async database session
        """
        self.db = db
    
    async def get_past_due_notifications_for_user(
        self, 
        user_id: UUID | str,
        current_time: datetime | None = None
    ) -> List[AINotification]:
        """
        Get all past due notifications for a specific user that need action.
        
        Returns notifications where:
        - due_date is in the past
        - status is not "resolved"
        - reaction_status is "None" (not completed, postponed, or dismissed)
        
        Args:
            user_id: The UUID of the user (can be UUID object or string)
            current_time: The reference time to compare against (defaults to now)
            
        Returns:
            List of past AINotification domain models (Pydantic), 
            ordered by due_date (oldest first)
        """
        if current_time is None:
            current_time = datetime.now()
        
        # Convert string UUID to UUID object if needed
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        # Build query for past notifications with intelligent deduplication:
        # 1. Include ALL notifications that have a task_result_id
        # 2. For notifications WITHOUT task_result_id, only include the most recent per task
        # 3. Exclude resolved notifications or notifications with user reactions
        
        # Subquery: Get the max ID (most recent) for each task where task_result_id is NULL
        subquery = (
            select(
                AINotificationORM.task_id,
                func.max(AINotificationORM.id).label('max_id')
            )
            .where(
                and_(
                    AINotificationORM.user_id == user_id,
                    AINotificationORM.due_date < current_time,
                    AINotificationORM.task_result_id.is_(None),
                    cast(AINotificationORM.status, String) != "resolved",
                    cast(AINotificationORM.reaction_status, String) == "None"
                )
            )
            .group_by(AINotificationORM.task_id)
            .subquery()
        )
        
        # Main query with conditions
        stmt = (
            select(AINotificationORM)
            .outerjoin(TaskResultORM, AINotificationORM.task_result_id == TaskResultORM.id)
            .where(
                and_(
                    AINotificationORM.user_id == user_id,
                    AINotificationORM.due_date < current_time,
                    cast(AINotificationORM.status, String) != "resolved",
                    cast(AINotificationORM.reaction_status, String) == "None",
                    or_(
                        AINotificationORM.task_result_id.isnot(None),
                        and_(
                            AINotificationORM.task_id == subquery.c.task_id,
                            AINotificationORM.id == subquery.c.max_id
                        )
                    )
                )
            )
            .order_by(AINotificationORM.due_date.asc())
        )
        result = await self.db.execute(stmt)
        orm_notifications = result.scalars().all()
        
        # Convert to domain models
        domain_notifications = [
            self._to_domain_model(orm_notification)
            for orm_notification in orm_notifications
        ]
        
        return domain_notifications
    
    async def get_notification_by_id(
        self, 
        notification_id: int,
        user_id: UUID | str
    ) -> AINotification | None:
        """
        Get a specific notification by ID for a user.
        
        Args:
            notification_id: The notification ID
            user_id: The UUID of the user (for authorization)
            
        Returns:
            AINotification domain model or None if not found
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        stmt = (
            select(AINotificationORM)
            .where(
                and_(
                    AINotificationORM.id == notification_id,
                    AINotificationORM.user_id == user_id
                )
            )
        )
        result = await self.db.execute(stmt)
        orm_notification = result.scalar_one_or_none()
        
        if not orm_notification:
            return None
        
        return self._to_domain_model(orm_notification)
    
    async def complete_notification_and_resolve_previous(
        self,
        notification_id: int,
        user_id: UUID | str
    ) -> tuple[int, List[int]]:
        """
        Complete a notification and resolve all previous notifications from the same task.
        
        This method:
        1. Sets the target notification's reaction_status to "completed"
        2. Sets all notifications from the same task with due_date <= target's due_date status to "resolved"
        
        Args:
            notification_id: The ID of the notification being completed
            user_id: The UUID of the user (for authorization)
            
        Returns:
            Tuple of (completed_notification_id, list of resolved_notification_ids)
            
        Raises:
            ValueError: If notification not found or doesn't belong to user
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        # Get the target notification (with row-level lock for consistency)
        stmt = (
            select(AINotificationORM)
            .where(
                and_(
                    AINotificationORM.id == notification_id,
                    AINotificationORM.user_id == user_id
                )
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        target_notification = result.scalar_one_or_none()
        
        if not target_notification:
            raise ValueError(f"Notification {notification_id} not found or access denied")
        
        # Extract task_id and due_date for the query
        task_id = target_notification.task_id
        target_due_date = target_notification.due_date
        
        # Update the target notification's reaction_status to "completed"
        # Use update() with cast to handle PostgreSQL enum type
        stmt_update_target = (
            update(AINotificationORM)
            .where(AINotificationORM.id == notification_id)
            .values(reaction_status=text(f"'{ReactionStatus.COMPLETED.value}'::ai_notification_reaction_status"))
        )
        await self.db.execute(stmt_update_target)
        
        # Find all notifications from the same task with due_date <= target's due_date
        # excluding the target itself (it's already set to completed)
        stmt_previous = (
            select(AINotificationORM)
            .where(
                and_(
                    AINotificationORM.task_id == task_id,
                    AINotificationORM.user_id == user_id,
                    AINotificationORM.due_date <= target_due_date,
                    AINotificationORM.id != notification_id,
                    # Only update if not already resolved
                    cast(AINotificationORM.status, String) != "resolved"
                )
            )
        )
        result_previous = await self.db.execute(stmt_previous)
        previous_notifications = result_previous.scalars().all()
        
        # Update all previous notifications' status to "resolved"
        # Use update() with cast to handle PostgreSQL enum type
        resolved_ids: List[int] = [notification.id for notification in previous_notifications]  # type: ignore[list-item]
        if resolved_ids:
            stmt_update = (
                update(AINotificationORM)
                .where(AINotificationORM.id.in_(resolved_ids))
                .values(status=text(f"'{NotificationStatus.RESOLVED.value}'::notification_status"))
            )
            await self.db.execute(stmt_update)
        
        # Commit the transaction (I/O happens here)
        await self.db.commit()
        
        return (notification_id, resolved_ids)
    
    async def postpone_notification_and_resolve_previous(
        self,
        notification_id: int,
        user_id: UUID | str,
        reaction_text: str
    ) -> tuple[int, List[int]]:
        """
        Postpone a notification with user's reaction text and resolve all previous notifications from the same task.
        
        This method:
        1. Sets the target notification's reaction_status to "postponed"
        2. Stores the user's reaction_text
        3. Sets all notifications from the same task with due_date <= target's due_date status to "resolved"
        
        Args:
            notification_id: The ID of the notification being postponed
            user_id: The UUID of the user (for authorization)
            reaction_text: The user's text response/reason for postponement
            
        Returns:
            Tuple of (postponed_notification_id, list of resolved_notification_ids)
            
        Raises:
            ValueError: If notification not found or doesn't belong to user
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        # Get the target notification (with row-level lock for consistency)
        stmt = (
            select(AINotificationORM)
            .where(
                and_(
                    AINotificationORM.id == notification_id,
                    AINotificationORM.user_id == user_id
                )
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        target_notification = result.scalar_one_or_none()
        
        if not target_notification:
            raise ValueError(f"Notification {notification_id} not found or access denied")
        
        # Extract task_id and due_date for the query
        task_id = target_notification.task_id
        target_due_date = target_notification.due_date
        
        # Update the target notification's reaction_status to "postponed" and store reaction text
        # Use update() with cast to handle PostgreSQL enum type
        stmt_update_target = (
            update(AINotificationORM)
            .where(AINotificationORM.id == notification_id)
            .values(
                reaction_status=text(f"'{ReactionStatus.POSTPONED.value}'::ai_notification_reaction_status"),
                reaction_text=reaction_text
            )
        )
        await self.db.execute(stmt_update_target)
        
        # Find all notifications from the same task with due_date <= target's due_date
        # excluding the target itself (it's already set to postponed)
        stmt_previous = (
            select(AINotificationORM)
            .where(
                and_(
                    AINotificationORM.task_id == task_id,
                    AINotificationORM.user_id == user_id,
                    AINotificationORM.due_date <= target_due_date,
                    AINotificationORM.id != notification_id,
                    # Only update if not already resolved
                    cast(AINotificationORM.status, String) != "resolved"
                )
            )
        )
        result_previous = await self.db.execute(stmt_previous)
        previous_notifications = result_previous.scalars().all()
        
        # Update all previous notifications' status to "resolved"
        # Use update() with cast to handle PostgreSQL enum type
        resolved_ids: List[int] = [notification.id for notification in previous_notifications]  # type: ignore[list-item]
        if resolved_ids:
            stmt_update = (
                update(AINotificationORM)
                .where(AINotificationORM.id.in_(resolved_ids))
                .values(status=text(f"'{NotificationStatus.RESOLVED.value}'::notification_status"))
            )
            await self.db.execute(stmt_update)
        
        # Commit the transaction (I/O happens here)
        await self.db.commit()
        
        return (notification_id, resolved_ids)
    
    async def get_reacted_notifications_by_workspace(
        self,
        workspace_id: int,
        workspace_member_ids: Optional[List[int]] = None
    ) -> List[ReactedAINotification]:
        """
        Get all AI notifications that have been reacted on (reaction_status != 'None') for a workspace.
        
        Joins:
        - ai_notifications -> tasks -> notes (for note name and id)
        - ai_notifications -> workspace_member -> user_profiles (for user icon and name)
        
        Args:
            workspace_id: The workspace ID to filter by
            workspace_member_ids: Optional list of workspace_member_ids to filter by
            
        Returns:
            List of ReactedAINotification domain models with note and user information
        """
        try:
            stmt_members = select(WorkspaceMemberORM.id).where(
                WorkspaceMemberORM.workspace_id == workspace_id
            )
            
            if workspace_member_ids:
                stmt_members = stmt_members.where(
                    WorkspaceMemberORM.id.in_(workspace_member_ids)
                )
            
            result_members = await self.db.execute(stmt_members)
            workspace_member_ids_list = [row[0] for row in result_members.all()]
            
            if not workspace_member_ids_list:
                return []
            
            stmt_main = (
                select(AINotificationORM, TaskORM)
                .join(TaskORM, AINotificationORM.task_id == TaskORM.id)
                .where(
                    and_(
                        TaskORM.workspace_member_id.in_(workspace_member_ids_list),
                        cast(AINotificationORM.reaction_status, String) != "None"
                    )
                )
                .order_by(AINotificationORM.updated_at.desc())
            )
            result_main = await self.db.execute(stmt_main)
            results = result_main.all()
            
            if not results:
                return []

            note_ids = {
                getattr(task, 'source_note_id', None)
                for _, task in results
                if task and getattr(task, 'source_note_id', None) is not None
            }
            workspace_member_ids_to_fetch = {
                getattr(result, 'workspace_member_id', None)
                for result, _ in results
                if getattr(result, 'workspace_member_id', None) is not None
            }
            task_result_ids = {
                getattr(result, 'task_result_id', None)
                for result, _ in results
                if getattr(result, 'task_result_id', None) is not None
            }
            
            # Batch fetch notes - OPTIMIZED: Only select id and title to avoid loading large TEXT columns
            notes_dict = {}
            if note_ids:
                try:
                    # Only select the columns we actually need (id and title)
                    # This avoids loading large TEXT columns like ydoc_state and text
                    stmt_notes = select(NoteORM.id, NoteORM.title).where(NoteORM.id.in_(note_ids))
                    result_notes = await self.db.execute(stmt_notes)
                    notes_rows = result_notes.all()
                    # Build dict from rows (Row objects with id and title attributes)
                    notes_dict = {row.id: row for row in notes_rows}
                except Exception as e:
                    logger.error(f"Step 4 ERROR: {e}", exc_info=True)
                    raise
            # Batch fetch task results
            task_results_dict = {}
            if task_result_ids:
                stmt_task_results = select(TaskResultORM).where(TaskResultORM.id.in_(task_result_ids))
                result_task_results = await self.db.execute(stmt_task_results)
                task_results = result_task_results.scalars().all()
                task_results_dict = {getattr(tr, 'id', None): tr for tr in task_results if getattr(tr, 'id', None) is not None}
            
            # Batch fetch workspace members and their user profiles - OPTIMIZED with JOIN
            workspace_members_dict = {}
            user_profiles_dict = {}
            if workspace_member_ids_to_fetch:
                try:
                    # Single query with LEFT JOIN to get both workspace members and user profiles
                    # Only select the columns we need from UserProfile
                    stmt_wm_with_profiles = (
                        select(
                            WorkspaceMemberORM,
                            UserProfileORM.id,
                            UserProfileORM.name,
                            UserProfileORM.avatar_url
                        )
                        .outerjoin(
                            UserProfileORM,
                            WorkspaceMemberORM.user_id == UserProfileORM.id
                        )
                        .where(WorkspaceMemberORM.id.in_(workspace_member_ids_to_fetch))
                    )
                    result_wm_profiles = await self.db.execute(stmt_wm_with_profiles)
                    rows = result_wm_profiles.all()
                    
                    # Build both dictionaries in one pass
                    for row in rows:
                        wm = row[0]  # WorkspaceMemberORM object
                        workspace_members_dict[wm.id] = wm
                        
                        # Extract user profile info if available
                        profile_id = row[1]  # UserProfileORM.id
                        if profile_id:
                            # Create a simple object that mimics UserProfileORM for compatibility
                            class ProfileData:
                                def __init__(self, id, name, avatar_url):
                                    self.id = id
                                    self.name = name
                                    self.avatar_url = avatar_url
                            
                            user_profiles_dict[profile_id] = ProfileData(
                                id=profile_id,
                                name=row[2],  # name
                                avatar_url=row[3]  # avatar_url
                            )
                except Exception as e:
                    logger.error(f"Step 6 ERROR: {e}", exc_info=True)
                    raise

            domain_notifications = []
            for result, task in results:
                try:
                    # Get note info
                    note_info = None
                    if task:
                        source_note_id = getattr(task, 'source_note_id', None)
                        if source_note_id:
                            note_row = notes_dict.get(source_note_id)
                            if note_row:
                                # note_row is a Row object with id and title attributes
                                note_info = NoteInfo(
                                    id=int(note_row.id),
                                    title=note_row.title if note_row.title else None
                                )
                    
                    # Get user info
                    user_info = None
                    workspace_member_id = getattr(result, 'workspace_member_id', None)
                    if workspace_member_id:
                        workspace_member = workspace_members_dict.get(workspace_member_id)
                        if workspace_member:
                            user_id_value = getattr(workspace_member, 'user_id', None)
                            if user_id_value:
                                user_profile = user_profiles_dict.get(user_id_value)
                                if user_profile:
                                    user_id_str = str(getattr(user_profile, 'id', ''))
                                    user_name = getattr(user_profile, 'name', None)
                                    user_avatar = getattr(user_profile, 'avatar_url', None)
                                    user_info = UserInfo(
                                        id=user_id_str,
                                        name=user_name,
                                        avatar_url=user_avatar
                                    )
                    
                    # Get task result info
                    task_result_info = None
                    task_result_id = getattr(result, 'task_result_id', None)
                    if task_result_id:
                        task_result = task_results_dict.get(task_result_id)
                        if task_result:
                            from app.features.ai_notifications.domain import TaskResult
                            task_result_info = TaskResult(
                                id=getattr(task_result, 'id'),
                                task_id=getattr(task_result, 'task_id'),
                                result_title=getattr(task_result, 'result_title'),
                                result_text=getattr(task_result, 'result_text'),
                                executed_at=getattr(task_result, 'executed_at'),
                                created_at=getattr(task_result, 'created_at')
                            )
                    
                    domain_notification = ReactedAINotification(
                        id=result.id,
                        title=result.title,
                        ai_context=result.ai_context,
                        body=result.body,
                        due_date=result.due_date,
                        task_id=result.task_id,
                        user_id=str(result.user_id),
                        workspace_member_id=result.workspace_member_id,
                        status=result.status,
                        reaction_status=result.reaction_status,
                        reaction_text=result.reaction_text,
                        created_at=result.created_at,
                        updated_at=result.updated_at,
                        note=note_info,
                        user=user_info,
                        task_result=task_result_info
                    )
                    domain_notifications.append(domain_notification)
                except Exception as e:
                    logger.error(f"Error processing notification {result.id}: {e}", exc_info=True)
                    raise
            return domain_notifications
            
        except Exception as e:
            logger.error(
                f"Error in get_reacted_notifications_by_workspace: {e}",
                exc_info=True
            )
            raise
    
    async def is_user_workspace_member(
        self,
        workspace_id: int,
        user_id: UUID | str
    ) -> bool:
        """
        Check if a user is a member of a workspace.
        
        Args:
            workspace_id: The workspace ID to check
            user_id: The user ID to check (can be UUID object or string)
            
        Returns:
            True if user is a member, False otherwise
        """
        # Convert string UUID to UUID object if needed
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        stmt = select(WorkspaceMemberORM.id).where(
            and_(
                WorkspaceMemberORM.workspace_id == workspace_id,
                WorkspaceMemberORM.user_id == user_id
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None
    
    async def validate_workspace_member_ids(
        self,
        workspace_id: int,
        workspace_member_ids: List[int]
    ) -> None:
        """
        Validate that all provided workspace_member_ids belong to the specified workspace.
        
        Args:
            workspace_id: The workspace ID to validate against
            workspace_member_ids: List of workspace_member_ids to validate
            
        Raises:
            ValueError: If any workspace_member_id does not belong to the workspace
        """
        if not workspace_member_ids:
            return
        
        # Query all workspace member IDs that belong to this workspace
        stmt = select(WorkspaceMemberORM.id).where(
            WorkspaceMemberORM.workspace_id == workspace_id
        )
        result = await self.db.execute(stmt)
        valid_member_ids = {row[0] for row in result.all()}
        
        # Check if all provided IDs are valid
        invalid_ids = set(workspace_member_ids) - valid_member_ids
        if invalid_ids:
            raise ValueError(
                f"Invalid workspace_member_ids: {sorted(invalid_ids)}. "
                f"These IDs do not belong to workspace {workspace_id}"
            )
    
    def _to_domain_model(self, orm_notification: AINotificationORM) -> AINotification:
        """
        Convert SQLAlchemy ORM model to Pydantic domain model.
        
        Args:
            orm_notification: SQLAlchemy AINotification ORM object
            
        Returns:
            Pydantic AINotification domain model
        """
        return AINotification.model_validate(orm_notification)
