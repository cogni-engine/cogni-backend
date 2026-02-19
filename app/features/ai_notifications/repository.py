"""SQLAlchemy repository for AI Notifications"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, func, select, cast, String, update, text

# SQLAlchemy ORM models
from app.db.models.ai_notification import (
    AINotification as AINotificationORM,
    NotificationStatus,
)
from app.db.models.task import Task as TaskORM
from app.db.models.note import Note as NoteORM
from app.db.models.workspace_member import WorkspaceMember as WorkspaceMemberORM
from app.db.models.user_profile import UserProfile as UserProfileORM

# Pydantic domain models (feature-local)
from app.features.ai_notifications.domain import AINotification, NoteInfo as DomainNoteInfo
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
        - reaction_text is NULL (not yet reacted)

        Args:
            user_id: The UUID of the user (can be UUID object or string)
            current_time: The reference time to compare against (defaults to now)

        Returns:
            List of past AINotification domain models (Pydantic),
            ordered by due_date (oldest first)
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # Convert string UUID to UUID object if needed
        if isinstance(user_id, str):
            user_id = UUID(user_id)

        # user_idからworkspace_member_idsを取得してフィルタリング
        stmt_wm = select(WorkspaceMemberORM.id).where(WorkspaceMemberORM.user_id == user_id)
        result_wm = await self.db.execute(stmt_wm)
        wm_ids = [row[0] for row in result_wm.all()]
        if not wm_ids:
            return []

        # Fetch all past due notifications (no deduplication in SQL)
        stmt = (
            select(AINotificationORM)
            .where(
                and_(
                    AINotificationORM.workspace_member_id.in_(wm_ids),
                    AINotificationORM.due_date < current_time,
                    cast(AINotificationORM.status, String) != "resolved",
                    AINotificationORM.reaction_text.is_(None)
                )
            )
            .order_by(AINotificationORM.due_date.asc())
        )
        result = await self.db.execute(stmt)
        all_notifications = result.scalars().all()

        # Deduplicate: keep only the most recent notification per task (highest ID)
        notifications_by_task: dict[int, AINotificationORM] = {}
        for n in all_notifications:
            existing = notifications_by_task.get(n.task_id)
            if existing is None or n.id > existing.id:
                notifications_by_task[n.task_id] = n

        notifications = list(notifications_by_task.values())
        notifications.sort(key=lambda x: x.due_date)

        if not notifications:
            return []

        # Collect task IDs for batch fetching
        task_ids = set()
        for orm_notification in notifications:
            task_ids.add(orm_notification.task_id)

        # Batch fetch tasks
        tasks_dict = {}
        if task_ids:
            stmt_tasks = select(TaskORM).where(TaskORM.id.in_(task_ids))
            result_tasks = await self.db.execute(stmt_tasks)
            tasks = result_tasks.scalars().all()
            tasks_dict = {t.id: t for t in tasks}

        # Collect note_ids from tasks (source_type='note' means source_id is a note ID)
        note_ids = {
            t.source_id for t in tasks_dict.values()
            if t.source_type == 'note' and t.source_id is not None
        }

        # Batch fetch notes - OPTIMIZED: Only select id and title
        notes_dict = {}
        if note_ids:
            stmt_notes = select(NoteORM.id, NoteORM.title).where(NoteORM.id.in_(note_ids))
            result_notes = await self.db.execute(stmt_notes)
            notes_rows = result_notes.all()
            notes_dict = {row.id: row for row in notes_rows}

        # Convert to domain models with note info
        domain_notifications = []
        for orm_notification in notifications:
            # Get task for this notification
            task = tasks_dict.get(orm_notification.task_id)

            # Get note info if task has source_type='note'
            note_info = None
            if task and task.source_type == 'note' and task.source_id:
                note_row = notes_dict.get(task.source_id)
                if note_row:
                    note_info = DomainNoteInfo(
                        id=int(note_row.id),
                        title=note_row.title if note_row.title else None
                    )

            domain_notification = self._to_domain_model_with_note(orm_notification, note_info)
            domain_notifications.append(domain_notification)

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
        
        # user_idからworkspace_member_idsを取得して認可チェック
        stmt_wm = select(WorkspaceMemberORM.id).where(WorkspaceMemberORM.user_id == user_id)
        result_wm = await self.db.execute(stmt_wm)
        wm_ids = [row[0] for row in result_wm.all()]

        stmt = (
            select(AINotificationORM)
            .where(
                and_(
                    AINotificationORM.id == notification_id,
                    AINotificationORM.workspace_member_id.in_(wm_ids) if wm_ids else False
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
        Complete a notification and resolve previous notifications from the same task.

        This method:
        1. Sets the target notification's reaction_text to "completed" and status to "resolved"
        2. Resolves all previous notifications from the same task with due_date <= target's due_date

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

        # user_idからworkspace_member_idsを取得して認可チェック
        stmt_wm = select(WorkspaceMemberORM.id).where(WorkspaceMemberORM.user_id == user_id)
        result_wm = await self.db.execute(stmt_wm)
        wm_ids = [row[0] for row in result_wm.all()]

        # Get the target notification (with row-level lock for consistency)
        stmt = (
            select(AINotificationORM)
            .where(
                and_(
                    AINotificationORM.id == notification_id,
                    AINotificationORM.workspace_member_id.in_(wm_ids) if wm_ids else False
                )
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        target_notification = result.scalar_one_or_none()

        if not target_notification:
            raise ValueError(f"Notification {notification_id} not found or access denied")

        task_id = target_notification.task_id
        target_due_date = target_notification.due_date
        target_wm_id = target_notification.workspace_member_id

        # Update the target notification's reaction_text and status to "resolved"
        stmt_update_target = (
            update(AINotificationORM)
            .where(AINotificationORM.id == notification_id)
            .values(
                reaction_text="completed",
                status=text(f"'{NotificationStatus.RESOLVED.value}'::notification_status")
            )
        )
        await self.db.execute(stmt_update_target)

        # Resolve all previous notifications from the same task & same workspace_member
        # with due_date <= target's due_date, excluding the target itself
        stmt_previous = (
            select(AINotificationORM)
            .where(
                and_(
                    AINotificationORM.task_id == task_id,
                    AINotificationORM.workspace_member_id == target_wm_id,
                    AINotificationORM.due_date <= target_due_date,
                    AINotificationORM.id != notification_id,
                    cast(AINotificationORM.status, String) != "resolved"
                )
            )
        )
        result_previous = await self.db.execute(stmt_previous)
        previous_notifications = result_previous.scalars().all()

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
        1. Stores the user's reaction_text and sets status to "resolved"
        2. Sets all notifications from the same task with due_date <= target's due_date status to "resolved"
        
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
        
        # user_idからworkspace_member_idsを取得して認可チェック
        stmt_wm = select(WorkspaceMemberORM.id).where(WorkspaceMemberORM.user_id == user_id)
        result_wm = await self.db.execute(stmt_wm)
        wm_ids = [row[0] for row in result_wm.all()]

        # Get the target notification (with row-level lock for consistency)
        stmt = (
            select(AINotificationORM)
            .where(
                and_(
                    AINotificationORM.id == notification_id,
                    AINotificationORM.workspace_member_id.in_(wm_ids) if wm_ids else False
                )
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        target_notification = result.scalar_one_or_none()

        if not target_notification:
            raise ValueError(f"Notification {notification_id} not found or access denied")

        # Extract task_id, due_date, workspace_member_id for the query
        task_id = target_notification.task_id
        target_due_date = target_notification.due_date
        target_wm_id = target_notification.workspace_member_id

        # Update the target notification's reaction_text and status to "resolved"
        stmt_update_target = (
            update(AINotificationORM)
            .where(AINotificationORM.id == notification_id)
            .values(
                reaction_text=reaction_text,
                status=text(f"'{NotificationStatus.RESOLVED.value}'::notification_status")
            )
        )
        await self.db.execute(stmt_update_target)

        # Find all notifications from the same task & same workspace_member
        # with due_date <= target's due_date, excluding the target itself
        stmt_previous = (
            select(AINotificationORM)
            .where(
                and_(
                    AINotificationORM.task_id == task_id,
                    AINotificationORM.workspace_member_id == target_wm_id,
                    AINotificationORM.due_date <= target_due_date,
                    AINotificationORM.id != notification_id,
                    cast(AINotificationORM.status, String) != "resolved"
                )
            )
        )
        result_previous = await self.db.execute(stmt_previous)
        previous_notifications = result_previous.scalars().all()

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
        Get all AI notifications that have been reacted on (reaction_text IS NOT NULL) for a workspace.
        
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
            # workspace_idで直接フィルタリング（ai_notifications.workspace_id使用）
            conditions = [
                AINotificationORM.workspace_id == workspace_id,
                AINotificationORM.reaction_text.isnot(None)
            ]
            if workspace_member_ids:
                conditions.append(AINotificationORM.workspace_member_id.in_(workspace_member_ids))

            stmt_main = (
                select(AINotificationORM, TaskORM)
                .join(TaskORM, AINotificationORM.task_id == TaskORM.id)
                .where(and_(*conditions))
                .order_by(AINotificationORM.updated_at.desc())
            )
            result_main = await self.db.execute(stmt_main)
            results = result_main.all()
            
            if not results:
                return []

            note_ids = {
                task.source_id
                for _, task in results
                if task and task.source_type == 'note' and task.source_id is not None
            }
            workspace_member_ids_to_fetch = {
                getattr(result, 'workspace_member_id', None)
                for result, _ in results
                if getattr(result, 'workspace_member_id', None) is not None
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
                        source_note_id = task.source_id if task.source_type == 'note' else None
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
                    
                    domain_notification = ReactedAINotification(
                        id=result.id,
                        title=result.title,
                        body=result.body,
                        due_date=result.due_date,
                        task_id=result.task_id,
                        workspace_id=result.workspace_id,
                        workspace_member_id=result.workspace_member_id,
                        status=result.status,
                        reaction_text=result.reaction_text,
                        reaction_choices=result.reaction_choices,
                        created_at=result.created_at,
                        updated_at=result.updated_at,
                        note=note_info,
                        user=user_info
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

    def _to_domain_model_with_note(
        self,
        orm_notification: AINotificationORM,
        note_info: Optional[DomainNoteInfo] = None
    ) -> AINotification:
        """
        Convert SQLAlchemy ORM model to Pydantic domain model with note info.

        Args:
            orm_notification: SQLAlchemy AINotification ORM object
            note_info: Optional NoteInfo domain model

        Returns:
            Pydantic AINotification domain model with note field populated
        """
        # First convert to domain model
        domain_notification = AINotification.model_validate(orm_notification)
        # Then add note info
        domain_notification.note = note_info
        return domain_notification
