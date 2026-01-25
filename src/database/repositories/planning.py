"""
Repository for planning sessions and task drafts.

Follows Phase 2 exception handling patterns:
- Raises DatabaseConstraintError on duplicates/FK violations
- Raises EntityNotFoundError when entity not found
- Raises DatabaseOperationError on general DB failures
- Uses selectinload to avoid N+1 queries
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_, desc, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from src.database.models import PlanningSessionDB, TaskDraftDB, PlanningStateEnum, ProjectComplexityEnum
from src.database.exceptions import (
    DatabaseConstraintError,
    EntityNotFoundError,
    DatabaseOperationError,
    ValidationError
)
import logging
import uuid

logger = logging.getLogger(__name__)


class PlanningRepository:
    """Repository for planning sessions with AI-powered features"""

    def __init__(self, session):
        self.session = session

    def _generate_session_id(self) -> str:
        """Generate unique planning session ID"""
        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"PLAN-{timestamp}-{unique_id}"

    async def create(
        self,
        user_id: str,
        raw_input: str,
        conversation_id: Optional[str] = None,
        **kwargs
    ) -> PlanningSessionDB:
        """
        Create new planning session

        Args:
            user_id: User creating the session
            raw_input: Original planning request
            conversation_id: Optional linked conversation
            **kwargs: Additional session data

        Returns:
            Created planning session

        Raises:
            DatabaseConstraintError: On duplicate session_id
            DatabaseOperationError: On general DB failure
        """
        try:
            session_id = self._generate_session_id()

            session_data = {
                "session_id": session_id,
                "user_id": user_id,
                "raw_input": raw_input,
                "conversation_id": conversation_id,
                "state": PlanningStateEnum.INITIATED.value,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_activity_at": datetime.utcnow(),
                **kwargs
            }

            planning_session = PlanningSessionDB(**session_data)
            self.session.add(planning_session)
            await self.session.commit()
            await self.session.refresh(planning_session)

            logger.info(f"Created planning session: {session_id} for user {user_id}")
            return planning_session

        except IntegrityError as e:
            await self.session.rollback()
            logger.error(f"Constraint violation creating planning session: {e}", exc_info=True)
            raise DatabaseConstraintError(f"Duplicate planning session or invalid reference: {e}")
        except Exception as e:
            await self.session.rollback()
            logger.error(f"CRITICAL: Failed to create planning session: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to create planning session: {e}")

    async def get_by_id(self, session_id: str, with_drafts: bool = False) -> Optional[PlanningSessionDB]:
        """
        Get planning session by ID

        Args:
            session_id: Planning session ID
            with_drafts: Load task drafts (prevents N+1)

        Returns:
            Planning session or None if not found
        """
        try:
            query = select(PlanningSessionDB).where(PlanningSessionDB.session_id == session_id)

            if with_drafts:
                query = query.options(selectinload(PlanningSessionDB.task_drafts))

            result = await self.session.execute(query)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Error fetching planning session {session_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch planning session: {e}")

    async def get_by_id_or_fail(self, session_id: str, with_drafts: bool = False) -> PlanningSessionDB:
        """
        Get planning session or raise EntityNotFoundError

        Raises:
            EntityNotFoundError: If session not found
        """
        session = await self.get_by_id(session_id, with_drafts=with_drafts)
        if not session:
            raise EntityNotFoundError(f"Planning session {session_id} not found")
        return session

    async def update_state(
        self,
        session_id: str,
        new_state: PlanningStateEnum,
        **kwargs
    ) -> PlanningSessionDB:
        """
        Update planning session state with additional data

        Raises:
            EntityNotFoundError: If session not found
        """
        try:
            session = await self.get_by_id_or_fail(session_id)

            session.state = new_state.value
            session.updated_at = datetime.utcnow()
            session.last_activity_at = datetime.utcnow()

            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)

            await self.session.commit()
            await self.session.refresh(session)

            logger.info(f"Updated planning session {session_id} to state {new_state.value}")
            return session

        except EntityNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update planning session {session_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to update planning session: {e}")

    async def save_ai_breakdown(
        self,
        session_id: str,
        breakdown: Dict[str, Any],
        complexity: ProjectComplexityEnum,
        estimated_duration: float
    ) -> PlanningSessionDB:
        """Save AI-generated task breakdown"""
        return await self.update_state(
            session_id,
            PlanningStateEnum.REVIEWING_BREAKDOWN,
            ai_breakdown=breakdown,
            complexity=complexity.value,
            estimated_duration_hours=estimated_duration
        )

    async def add_user_edit(
        self,
        session_id: str,
        edit_type: str,
        edit_data: Dict[str, Any]
    ) -> PlanningSessionDB:
        """
        Track user modifications to the plan

        Args:
            session_id: Planning session ID
            edit_type: Type of edit (modify_task, add_task, remove_task, reorder)
            edit_data: Edit details
        """
        try:
            session = await self.get_by_id_or_fail(session_id)

            edits = session.user_edits or []
            edits.append({
                "type": edit_type,
                "data": edit_data,
                "timestamp": datetime.utcnow().isoformat()
            })

            session.user_edits = edits
            session.updated_at = datetime.utcnow()

            await self.session.commit()
            await self.session.refresh(session)

            logger.info(f"Added edit to planning session {session_id}: {edit_type}")
            return session

        except EntityNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to add edit to planning session {session_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to add edit: {e}")

    async def finalize(
        self,
        session_id: str,
        created_project_id: str,
        created_task_ids: List[str]
    ) -> PlanningSessionDB:
        """Mark planning session as completed"""
        return await self.update_state(
            session_id,
            PlanningStateEnum.COMPLETED,
            finalized_at=datetime.utcnow(),
            created_project_id=created_project_id,
            created_task_ids=created_task_ids
        )

    async def get_active_for_user(self, user_id: str) -> Optional[PlanningSessionDB]:
        """
        Get active planning session for user (if any)

        Returns most recent active session
        """
        try:
            active_states = [
                PlanningStateEnum.INITIATED.value,
                PlanningStateEnum.GATHERING_INFO.value,
                PlanningStateEnum.AI_ANALYZING.value,
                PlanningStateEnum.REVIEWING_BREAKDOWN.value,
                PlanningStateEnum.REFINING.value,
                PlanningStateEnum.FINALIZING.value
            ]

            query = (
                select(PlanningSessionDB)
                .where(
                    and_(
                        PlanningSessionDB.user_id == user_id,
                        PlanningSessionDB.state.in_(active_states)
                    )
                )
                .options(selectinload(PlanningSessionDB.task_drafts))
                .order_by(desc(PlanningSessionDB.last_activity_at))
            )

            result = await self.session.execute(query)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Error fetching active session for user {user_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch active session: {e}")

    async def get_recent_completed(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[PlanningSessionDB]:
        """Get recent completed planning sessions for learning"""
        try:
            query = (
                select(PlanningSessionDB)
                .where(
                    and_(
                        PlanningSessionDB.user_id == user_id,
                        PlanningSessionDB.state == PlanningStateEnum.COMPLETED.value
                    )
                )
                .order_by(desc(PlanningSessionDB.finalized_at))
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error fetching completed sessions for user {user_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch completed sessions: {e}")

    async def cleanup_stale_sessions(self, hours: int = 24) -> int:
        """
        Cleanup planning sessions that have been inactive for too long

        Args:
            hours: Inactive hours threshold

        Returns:
            Number of sessions cleaned up
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            active_states = [
                PlanningStateEnum.INITIATED.value,
                PlanningStateEnum.GATHERING_INFO.value,
                PlanningStateEnum.AI_ANALYZING.value,
                PlanningStateEnum.REVIEWING_BREAKDOWN.value,
                PlanningStateEnum.REFINING.value
            ]

            query = select(PlanningSessionDB).where(
                and_(
                    PlanningSessionDB.state.in_(active_states),
                    PlanningSessionDB.last_activity_at < cutoff_time
                )
            )

            result = await self.session.execute(query)
            stale_sessions = result.scalars().all()

            count = 0
            for session in stale_sessions:
                session.state = PlanningStateEnum.CANCELLED.value
                session.updated_at = datetime.utcnow()
                count += 1

            await self.session.commit()

            if count > 0:
                logger.info(f"Cleaned up {count} stale planning sessions (>{hours}h inactive)")

            return count

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to cleanup stale sessions: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to cleanup stale sessions: {e}")


class TaskDraftRepository:
    """Repository for task drafts within planning sessions"""

    def __init__(self, session):
        self.session = session

    def _generate_draft_id(self) -> str:
        """Generate unique draft ID"""
        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"DRAFT-{timestamp}-{unique_id}"

    async def create(
        self,
        session_id: str,
        title: str,
        sequence_order: int,
        **kwargs
    ) -> TaskDraftDB:
        """
        Create task draft

        Raises:
            DatabaseConstraintError: On invalid session_id reference
        """
        try:
            draft_id = self._generate_draft_id()

            draft_data = {
                "draft_id": draft_id,
                "session_id": session_id,
                "title": title,
                "sequence_order": sequence_order,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                **kwargs
            }

            draft = TaskDraftDB(**draft_data)
            self.session.add(draft)
            await self.session.commit()
            await self.session.refresh(draft)

            logger.info(f"Created task draft: {draft_id} for session {session_id}")
            return draft

        except IntegrityError as e:
            await self.session.rollback()
            logger.error(f"Constraint violation creating draft: {e}", exc_info=True)
            raise DatabaseConstraintError(f"Invalid session_id or duplicate draft: {e}")
        except Exception as e:
            await self.session.rollback()
            logger.error(f"CRITICAL: Failed to create task draft: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to create task draft: {e}")

    async def bulk_create_from_ai(
        self,
        session_id: str,
        ai_tasks: List[Dict[str, Any]]
    ) -> List[TaskDraftDB]:
        """
        Create multiple drafts from AI breakdown

        Args:
            session_id: Planning session ID
            ai_tasks: List of task dicts from AI

        Returns:
            List of created drafts
        """
        drafts = []

        try:
            for idx, task in enumerate(ai_tasks):
                draft = await self.create(
                    session_id=session_id,
                    title=task["title"],
                    description=task.get("description"),
                    category=task.get("category"),
                    priority=task.get("priority"),
                    estimated_hours=task.get("estimated_hours"),
                    assigned_to=task.get("assigned_to"),
                    ai_generated=True,
                    ai_reasoning=task.get("reasoning"),
                    sequence_order=idx + 1,
                    depends_on=task.get("depends_on", []),
                    confidence=task.get("confidence")
                )
                drafts.append(draft)

            logger.info(f"Created {len(drafts)} task drafts for session {session_id}")
            return drafts

        except Exception as e:
            # Rollback handled by individual create() calls
            logger.error(f"Failed to bulk create drafts: {e}", exc_info=True)
            raise

    async def get_by_id(self, draft_id: str) -> Optional[TaskDraftDB]:
        """Get draft by ID"""
        try:
            query = select(TaskDraftDB).where(TaskDraftDB.draft_id == draft_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching draft {draft_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch draft: {e}")

    async def get_by_id_or_fail(self, draft_id: str) -> TaskDraftDB:
        """Get draft or raise EntityNotFoundError"""
        draft = await self.get_by_id(draft_id)
        if not draft:
            raise EntityNotFoundError(f"Task draft {draft_id} not found")
        return draft

    async def update(
        self,
        draft_id: str,
        updates: Dict[str, Any]
    ) -> TaskDraftDB:
        """
        Update draft and mark as user-modified

        Raises:
            EntityNotFoundError: If draft not found
        """
        try:
            draft = await self.get_by_id_or_fail(draft_id)

            for key, value in updates.items():
                if hasattr(draft, key):
                    setattr(draft, key, value)

            draft.user_modified = True
            draft.updated_at = datetime.utcnow()

            await self.session.commit()
            await self.session.refresh(draft)

            logger.info(f"Updated task draft {draft_id}")
            return draft

        except EntityNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update draft {draft_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to update draft: {e}")

    async def get_by_session(self, session_id: str) -> List[TaskDraftDB]:
        """Get all drafts for session, ordered by sequence"""
        try:
            query = (
                select(TaskDraftDB)
                .where(TaskDraftDB.session_id == session_id)
                .order_by(TaskDraftDB.sequence_order)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error fetching drafts for session {session_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch drafts: {e}")

    async def reorder(self, draft_ids_in_order: List[str]) -> List[TaskDraftDB]:
        """
        Reorder drafts by updating sequence_order

        Args:
            draft_ids_in_order: Draft IDs in desired order

        Returns:
            Reordered drafts
        """
        try:
            drafts = []

            for idx, draft_id in enumerate(draft_ids_in_order):
                draft = await self.get_by_id_or_fail(draft_id)
                draft.sequence_order = idx + 1
                draft.updated_at = datetime.utcnow()
                drafts.append(draft)

            await self.session.commit()

            for draft in drafts:
                await self.session.refresh(draft)

            logger.info(f"Reordered {len(drafts)} task drafts")
            return drafts

        except EntityNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to reorder drafts: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to reorder drafts: {e}")

    async def delete(self, draft_id: str) -> bool:
        """
        Delete a task draft

        Returns:
            True if deleted, False if not found

        Raises:
            DatabaseOperationError: On DB failure
        """
        try:
            draft = await self.get_by_id(draft_id)
            if not draft:
                return False

            await self.session.delete(draft)
            await self.session.commit()

            logger.info(f"Deleted task draft {draft_id}")
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete draft {draft_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to delete draft: {e}")


# Helper functions for getting repositories
def get_planning_repository(session) -> PlanningRepository:
    """Factory function for planning repository"""
    return PlanningRepository(session)


def get_task_draft_repository(session) -> TaskDraftRepository:
    """Factory function for task draft repository"""
    return TaskDraftRepository(session)
