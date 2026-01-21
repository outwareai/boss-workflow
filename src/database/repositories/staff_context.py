"""
Staff Task Context Repository.

Handles persistence for:
- Staff-AI conversation contexts per task
- Conversation messages
- Escalation records
- Discord thread-task links
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..connection import get_database
from ..models import (
    StaffTaskContextDB,
    StaffContextMessageDB,
    StaffEscalationDB,
    DiscordThreadTaskLinkDB,
)

logger = logging.getLogger(__name__)


class StaffContextRepository:
    """Repository for staff task context operations."""

    def __init__(self):
        self.db = get_database()

    # ==================== CONTEXT CRUD ====================

    async def create_context(
        self,
        task_id: str,
        task_details: Dict[str, Any] = None,
        staff_id: str = None,
        staff_name: str = None,
        channel_id: str = None,
        thread_id: str = None,
    ) -> Optional[StaffTaskContextDB]:
        """Create a new staff task context."""
        async with self.db.session() as session:
            try:
                context = StaffTaskContextDB(
                    task_id=task_id,
                    task_details=task_details,
                    staff_id=staff_id,
                    staff_name=staff_name,
                    channel_id=channel_id,
                    thread_id=thread_id,
                    status="active",
                )
                session.add(context)
                await session.flush()
                logger.info(f"Created staff context for task {task_id}")
                return context
            except Exception as e:
                logger.error(f"Error creating staff context: {e}")
                return None

    async def get_context(self, task_id: str) -> Optional[StaffTaskContextDB]:
        """Get context by task_id with messages and escalations."""
        async with self.db.session() as session:
            result = await session.execute(
                select(StaffTaskContextDB)
                .options(
                    selectinload(StaffTaskContextDB.messages),
                    selectinload(StaffTaskContextDB.escalations),
                )
                .where(StaffTaskContextDB.task_id == task_id)
            )
            return result.scalar_one_or_none()

    async def get_context_by_channel(self, channel_id: str) -> Optional[StaffTaskContextDB]:
        """Get active context by Discord channel ID."""
        async with self.db.session() as session:
            result = await session.execute(
                select(StaffTaskContextDB)
                .where(
                    and_(
                        StaffTaskContextDB.channel_id == channel_id,
                        StaffTaskContextDB.status == "active"
                    )
                )
            )
            return result.scalar_one_or_none()

    async def get_context_by_thread(self, thread_id: str) -> Optional[StaffTaskContextDB]:
        """Get active context by Discord thread ID."""
        async with self.db.session() as session:
            result = await session.execute(
                select(StaffTaskContextDB)
                .where(
                    and_(
                        StaffTaskContextDB.thread_id == thread_id,
                        StaffTaskContextDB.status == "active"
                    )
                )
            )
            return result.scalar_one_or_none()

    async def get_context_by_staff(self, staff_id: str) -> Optional[StaffTaskContextDB]:
        """Get most recently active context for a staff member."""
        async with self.db.session() as session:
            result = await session.execute(
                select(StaffTaskContextDB)
                .where(
                    and_(
                        StaffTaskContextDB.staff_id == staff_id,
                        StaffTaskContextDB.status == "active"
                    )
                )
                .order_by(StaffTaskContextDB.last_activity.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def update_context(
        self,
        task_id: str,
        updates: Dict[str, Any]
    ) -> Optional[StaffTaskContextDB]:
        """Update a context."""
        async with self.db.session() as session:
            updates["last_activity"] = datetime.now()
            await session.execute(
                update(StaffTaskContextDB)
                .where(StaffTaskContextDB.task_id == task_id)
                .values(**updates)
            )
            return await self.get_context(task_id)

    async def close_context(self, task_id: str) -> bool:
        """Close a context (task completed/cancelled)."""
        async with self.db.session() as session:
            try:
                await session.execute(
                    update(StaffTaskContextDB)
                    .where(StaffTaskContextDB.task_id == task_id)
                    .values(status="closed", closed_at=datetime.now())
                )
                logger.info(f"Closed staff context for task {task_id}")
                return True
            except Exception as e:
                logger.error(f"Error closing context: {e}")
                return False

    async def get_all_active_contexts(self) -> List[StaffTaskContextDB]:
        """Get all active contexts."""
        async with self.db.session() as session:
            result = await session.execute(
                select(StaffTaskContextDB)
                .where(StaffTaskContextDB.status == "active")
            )
            return list(result.scalars().all())

    async def cleanup_old_contexts(self, hours: int = 72) -> int:
        """Close contexts older than specified hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        async with self.db.session() as session:
            try:
                result = await session.execute(
                    update(StaffTaskContextDB)
                    .where(
                        and_(
                            StaffTaskContextDB.status == "active",
                            StaffTaskContextDB.last_activity < cutoff
                        )
                    )
                    .values(status="closed", closed_at=datetime.now())
                )
                count = result.rowcount
                if count:
                    logger.info(f"Cleaned up {count} old staff contexts")
                return count
            except Exception as e:
                logger.error(f"Error cleaning up contexts: {e}")
                return 0

    # ==================== MESSAGES ====================

    async def add_message(
        self,
        task_id: str,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> Optional[StaffContextMessageDB]:
        """Add a message to the conversation history."""
        async with self.db.session() as session:
            try:
                # Get context
                result = await session.execute(
                    select(StaffTaskContextDB)
                    .where(StaffTaskContextDB.task_id == task_id)
                )
                context = result.scalar_one_or_none()
                if not context:
                    logger.warning(f"No context found for task {task_id}")
                    return None

                message = StaffContextMessageDB(
                    context_id=context.id,
                    role=role,
                    content=content,
                    metadata=metadata,
                )
                session.add(message)

                # Update last activity
                await session.execute(
                    update(StaffTaskContextDB)
                    .where(StaffTaskContextDB.id == context.id)
                    .values(last_activity=datetime.now())
                )

                await session.flush()
                return message

            except Exception as e:
                logger.error(f"Error adding message: {e}")
                return None

    async def get_conversation_history(
        self,
        task_id: str,
        limit: int = 10
    ) -> List[Dict[str, str]]:
        """Get recent conversation history for a task."""
        async with self.db.session() as session:
            # Get context first
            result = await session.execute(
                select(StaffTaskContextDB)
                .where(StaffTaskContextDB.task_id == task_id)
            )
            context = result.scalar_one_or_none()
            if not context:
                return []

            # Get messages
            result = await session.execute(
                select(StaffContextMessageDB)
                .where(StaffContextMessageDB.context_id == context.id)
                .order_by(StaffContextMessageDB.timestamp.desc())
                .limit(limit)
            )
            messages = list(result.scalars().all())
            messages.reverse()  # Oldest first

            return [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "metadata": msg.metadata or {}
                }
                for msg in messages
            ]

    # ==================== ESCALATIONS ====================

    async def record_escalation(
        self,
        task_id: str,
        reason: str,
        staff_message: str = None,
        message_url: str = None,
        telegram_message_id: str = None
    ) -> Optional[StaffEscalationDB]:
        """Record an escalation to boss."""
        async with self.db.session() as session:
            try:
                # Get context
                result = await session.execute(
                    select(StaffTaskContextDB)
                    .where(StaffTaskContextDB.task_id == task_id)
                )
                context = result.scalar_one_or_none()
                if not context:
                    logger.warning(f"No context found for task {task_id}")
                    return None

                escalation = StaffEscalationDB(
                    context_id=context.id,
                    reason=reason,
                    staff_message=staff_message,
                    message_url=message_url,
                    telegram_message_id=telegram_message_id,
                )
                session.add(escalation)
                await session.flush()

                logger.info(f"Recorded escalation for task {task_id}")
                return escalation

            except Exception as e:
                logger.error(f"Error recording escalation: {e}")
                return None

    async def get_pending_escalation_by_telegram(
        self,
        telegram_message_id: str
    ) -> Optional[StaffEscalationDB]:
        """Get escalation by Telegram message ID (for boss reply routing)."""
        async with self.db.session() as session:
            result = await session.execute(
                select(StaffEscalationDB)
                .options(selectinload(StaffEscalationDB.context))
                .where(
                    and_(
                        StaffEscalationDB.telegram_message_id == telegram_message_id,
                        StaffEscalationDB.boss_responded == False
                    )
                )
            )
            return result.scalar_one_or_none()

    async def get_latest_pending_escalation(
        self,
        task_id: str
    ) -> Optional[StaffEscalationDB]:
        """Get the most recent unanswered escalation for a task."""
        async with self.db.session() as session:
            # Get context first
            result = await session.execute(
                select(StaffTaskContextDB)
                .where(StaffTaskContextDB.task_id == task_id)
            )
            context = result.scalar_one_or_none()
            if not context:
                return None

            result = await session.execute(
                select(StaffEscalationDB)
                .where(
                    and_(
                        StaffEscalationDB.context_id == context.id,
                        StaffEscalationDB.boss_responded == False
                    )
                )
                .order_by(StaffEscalationDB.timestamp.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def mark_escalation_responded(
        self,
        escalation_id: int,
        boss_response: str
    ) -> bool:
        """Mark an escalation as responded to."""
        async with self.db.session() as session:
            try:
                await session.execute(
                    update(StaffEscalationDB)
                    .where(StaffEscalationDB.id == escalation_id)
                    .values(
                        boss_responded=True,
                        boss_response=boss_response,
                        boss_response_time=datetime.now()
                    )
                )
                logger.info(f"Marked escalation {escalation_id} as responded")
                return True
            except Exception as e:
                logger.error(f"Error marking escalation responded: {e}")
                return False

    # ==================== SUBMISSIONS ====================

    async def record_submission(
        self,
        task_id: str,
        validation_result: Dict[str, Any]
    ) -> bool:
        """Record a submission attempt."""
        async with self.db.session() as session:
            try:
                # Get context
                result = await session.execute(
                    select(StaffTaskContextDB)
                    .where(StaffTaskContextDB.task_id == task_id)
                )
                context = result.scalar_one_or_none()
                if not context:
                    return False

                await session.execute(
                    update(StaffTaskContextDB)
                    .where(StaffTaskContextDB.id == context.id)
                    .values(
                        submission_attempts=context.submission_attempts + 1,
                        last_submission={
                            "timestamp": datetime.now().isoformat(),
                            "result": validation_result
                        },
                        last_activity=datetime.now()
                    )
                )
                return True
            except Exception as e:
                logger.error(f"Error recording submission: {e}")
                return False

    # ==================== THREAD LINKS ====================

    async def link_thread_to_task(
        self,
        thread_id: str,
        task_id: str,
        channel_id: str,
        message_id: str = None,
        created_by: str = None
    ) -> Optional[DiscordThreadTaskLinkDB]:
        """Create a link between a Discord thread and a task."""
        async with self.db.session() as session:
            try:
                # Check if link already exists
                result = await session.execute(
                    select(DiscordThreadTaskLinkDB)
                    .where(DiscordThreadTaskLinkDB.thread_id == thread_id)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    # Update the task_id if it changed
                    await session.execute(
                        update(DiscordThreadTaskLinkDB)
                        .where(DiscordThreadTaskLinkDB.thread_id == thread_id)
                        .values(task_id=task_id)
                    )
                    logger.info(f"Updated thread link: {thread_id} → {task_id}")
                    return existing

                link = DiscordThreadTaskLinkDB(
                    thread_id=thread_id,
                    channel_id=channel_id,
                    message_id=message_id,
                    task_id=task_id,
                    created_by=created_by,
                )
                session.add(link)
                await session.flush()

                logger.info(f"Created thread link: {thread_id} → {task_id}")
                return link

            except Exception as e:
                logger.error(f"Error creating thread link: {e}")
                return None

    async def get_task_by_thread(self, thread_id: str) -> Optional[str]:
        """Get task_id from a Discord thread ID."""
        async with self.db.session() as session:
            result = await session.execute(
                select(DiscordThreadTaskLinkDB)
                .where(DiscordThreadTaskLinkDB.thread_id == thread_id)
            )
            link = result.scalar_one_or_none()
            return link.task_id if link else None

    async def get_thread_by_task(self, task_id: str) -> Optional[str]:
        """Get thread_id from a task_id."""
        async with self.db.session() as session:
            result = await session.execute(
                select(DiscordThreadTaskLinkDB)
                .where(DiscordThreadTaskLinkDB.task_id == task_id)
            )
            link = result.scalar_one_or_none()
            return link.thread_id if link else None


# Singleton
_staff_context_repository = None


def get_staff_context_repository() -> StaffContextRepository:
    global _staff_context_repository
    if _staff_context_repository is None:
        _staff_context_repository = StaffContextRepository()
    return _staff_context_repository
