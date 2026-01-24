"""
Conversation repository for chat history storage.

Stores:
- Full conversation sessions
- Individual messages
- Context and state
- Outcomes (task created, cancelled, etc.)
"""

import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import select, update, func, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from ..connection import get_database
from ..models import ConversationDB, MessageDB
from ..exceptions import DatabaseConstraintError, DatabaseOperationError, EntityNotFoundError

logger = logging.getLogger(__name__)


class ConversationRepository:
    """Repository for conversation operations."""

    def __init__(self):
        self.db = get_database()

    # ==================== CONVERSATIONS ====================

    async def create(
        self,
        user_id: str,
        user_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> ConversationDB:
        """Create a new conversation.

        Raises:
            DatabaseConstraintError: If conversation_id already exists
            DatabaseOperationError: If database operation fails
        """
        async with self.db.session() as session:
            try:
                conv_id = f"CONV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

                conversation = ConversationDB(
                    conversation_id=conv_id,
                    user_id=user_id,
                    user_name=user_name,
                    chat_id=chat_id,
                    intent=intent,
                    stage="initial",
                )
                session.add(conversation)
                await session.flush()

                logger.info(f"Created conversation {conv_id} for user {user_id}")
                return conversation

            except IntegrityError as e:
                logger.error(f"Constraint violation creating conversation: {e}", exc_info=True)
                raise DatabaseConstraintError(
                    f"Conversation {conv_id} already exists or constraint violation"
                ) from e
            except Exception as e:
                logger.error(f"Error creating conversation: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to create conversation: {e}") from e

    async def get_by_id(self, conversation_id: str) -> Optional[ConversationDB]:
        """Get conversation by ID."""
        async with self.db.session() as session:
            result = await session.execute(
                select(ConversationDB)
                .options(selectinload(ConversationDB.messages))
                .where(ConversationDB.conversation_id == conversation_id)
            )
            return result.scalar_one_or_none()

    async def get_active_for_user(self, user_id: str) -> Optional[ConversationDB]:
        """Get active (non-completed) conversation for a user."""
        async with self.db.session() as session:
            result = await session.execute(
                select(ConversationDB)
                .options(selectinload(ConversationDB.messages))
                .where(
                    and_(
                        ConversationDB.user_id == user_id,
                        ConversationDB.outcome.is_(None),
                    )
                )
                .order_by(ConversationDB.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def update_stage(
        self,
        conversation_id: str,
        stage: str,
        context: Optional[Dict] = None,
        generated_spec: Optional[Dict] = None,
    ) -> ConversationDB:
        """Update conversation stage and context.

        Raises:
            EntityNotFoundError: If conversation not found
            DatabaseOperationError: If update fails
        """
        async with self.db.session() as session:
            try:
                updates = {
                    "stage": stage,
                    "updated_at": datetime.now(),
                }
                if context is not None:
                    updates["context"] = context
                if generated_spec is not None:
                    updates["generated_spec"] = generated_spec

                result = await session.execute(
                    update(ConversationDB)
                    .where(ConversationDB.conversation_id == conversation_id)
                    .values(**updates)
                )

                if result.rowcount == 0:
                    raise EntityNotFoundError(f"Conversation {conversation_id} not found")

                result = await session.execute(
                    select(ConversationDB)
                    .where(ConversationDB.conversation_id == conversation_id)
                )
                conversation = result.scalar_one_or_none()

                if not conversation:
                    raise EntityNotFoundError(f"Conversation {conversation_id} not found after update")

                return conversation

            except EntityNotFoundError:
                raise
            except Exception as e:
                logger.error(f"Error updating conversation stage: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to update conversation stage: {e}") from e

    async def complete(
        self,
        conversation_id: str,
        outcome: str,
        task_id: Optional[str] = None,
    ) -> ConversationDB:
        """Mark conversation as completed.

        Raises:
            EntityNotFoundError: If conversation not found
            DatabaseOperationError: If update fails
        """
        async with self.db.session() as session:
            try:
                result = await session.execute(
                    update(ConversationDB)
                    .where(ConversationDB.conversation_id == conversation_id)
                    .values(
                        outcome=outcome,
                        task_id=task_id,
                        completed_at=datetime.now(),
                        stage="completed",
                    )
                )

                if result.rowcount == 0:
                    raise EntityNotFoundError(f"Conversation {conversation_id} not found")

                result = await session.execute(
                    select(ConversationDB)
                    .where(ConversationDB.conversation_id == conversation_id)
                )
                conversation = result.scalar_one_or_none()

                if not conversation:
                    raise EntityNotFoundError(f"Conversation {conversation_id} not found after completion")

                return conversation

            except EntityNotFoundError:
                raise
            except Exception as e:
                logger.error(f"Error completing conversation: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to complete conversation: {e}") from e

    async def clear_user_conversations(self, user_id: str) -> int:
        """Clear all active conversations for a user (mark as cancelled).

        Raises:
            DatabaseOperationError: If operation fails
        """
        async with self.db.session() as session:
            try:
                result = await session.execute(
                    update(ConversationDB)
                    .where(
                        and_(
                            ConversationDB.user_id == user_id,
                            ConversationDB.outcome.is_(None),
                        )
                    )
                    .values(
                        outcome="cancelled",
                        completed_at=datetime.now(),
                    )
                )
                return result.rowcount

            except Exception as e:
                logger.error(f"Error clearing user conversations: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to clear conversations for user {user_id}: {e}") from e

    # ==================== MESSAGES ====================

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        message_type: str = "text",
        file_id: Optional[str] = None,
        intent_detected: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> MessageDB:
        """Add a message to a conversation.

        Raises:
            EntityNotFoundError: If conversation not found
            DatabaseOperationError: If operation fails
        """
        async with self.db.session() as session:
            try:
                # Get conversation
                conv_result = await session.execute(
                    select(ConversationDB)
                    .where(ConversationDB.conversation_id == conversation_id)
                )
                conversation = conv_result.scalar_one_or_none()

                if not conversation:
                    raise EntityNotFoundError(f"Conversation {conversation_id} not found")

                message = MessageDB(
                    conversation_id=conversation.id,
                    role=role,
                    content=content,
                    message_type=message_type,
                    file_id=file_id,
                    intent_detected=intent_detected,
                    confidence=int(confidence * 100) if confidence else None,
                )
                session.add(message)
                await session.flush()

                # Update conversation timestamp
                conversation.updated_at = datetime.now()

                return message

            except EntityNotFoundError:
                raise
            except Exception as e:
                logger.error(f"Error adding message to conversation: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to add message to conversation {conversation_id}: {e}") from e

    async def get_messages(self, conversation_id: str) -> List[MessageDB]:
        """Get all messages in a conversation."""
        async with self.db.session() as session:
            conv_result = await session.execute(
                select(ConversationDB)
                .where(ConversationDB.conversation_id == conversation_id)
            )
            conversation = conv_result.scalar_one_or_none()

            if not conversation:
                return []

            result = await session.execute(
                select(MessageDB)
                .where(MessageDB.conversation_id == conversation.id)
                .order_by(MessageDB.timestamp.asc())
            )
            return list(result.scalars().all())

    # ==================== QUERY METHODS ====================

    async def get_user_history(
        self,
        user_id: str,
        limit: int = 20
    ) -> List[ConversationDB]:
        """Get recent conversations for a user."""
        async with self.db.session() as session:
            result = await session.execute(
                select(ConversationDB)
                .options(selectinload(ConversationDB.messages))
                .where(ConversationDB.user_id == user_id)
                .order_by(ConversationDB.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_recent(self, limit: int = 50) -> List[ConversationDB]:
        """Get recent conversations."""
        async with self.db.session() as session:
            result = await session.execute(
                select(ConversationDB)
                .order_by(ConversationDB.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_stale_conversations(
        self,
        timeout_minutes: int = 30
    ) -> List[ConversationDB]:
        """Get conversations that have timed out."""
        cutoff = datetime.now() - timedelta(minutes=timeout_minutes)

        async with self.db.session() as session:
            result = await session.execute(
                select(ConversationDB)
                .where(
                    and_(
                        ConversationDB.updated_at < cutoff,
                        ConversationDB.outcome.is_(None),
                    )
                )
            )
            return list(result.scalars().all())

    async def cleanup_stale(self, timeout_minutes: int = 30) -> int:
        """Mark stale conversations as timed out.

        Raises:
            DatabaseOperationError: If cleanup fails
        """
        cutoff = datetime.now() - timedelta(minutes=timeout_minutes)

        async with self.db.session() as session:
            try:
                result = await session.execute(
                    update(ConversationDB)
                    .where(
                        and_(
                            ConversationDB.updated_at < cutoff,
                            ConversationDB.outcome.is_(None),
                        )
                    )
                    .values(
                        outcome="timeout",
                        completed_at=datetime.now(),
                    )
                )
                count = result.rowcount
                if count > 0:
                    logger.info(f"Cleaned up {count} stale conversations")
                return count

            except Exception as e:
                logger.error(f"Error cleaning up stale conversations: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to cleanup stale conversations: {e}") from e

    async def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get conversation statistics."""
        since = datetime.now() - timedelta(days=days)

        async with self.db.session() as session:
            # Total conversations
            total = await session.execute(
                select(func.count(ConversationDB.id))
                .where(ConversationDB.created_at >= since)
            )
            total_count = total.scalar() or 0

            # By outcome
            outcomes = await session.execute(
                select(ConversationDB.outcome, func.count(ConversationDB.id))
                .where(ConversationDB.created_at >= since)
                .group_by(ConversationDB.outcome)
            )
            outcome_counts = {row[0] or "active": row[1] for row in outcomes}

            # Tasks created
            tasks_created = await session.execute(
                select(func.count(ConversationDB.id))
                .where(
                    and_(
                        ConversationDB.created_at >= since,
                        ConversationDB.task_id.isnot(None),
                    )
                )
            )
            tasks_count = tasks_created.scalar() or 0

            # Average messages per conversation
            avg_messages = await session.execute(
                select(func.avg(
                    select(func.count(MessageDB.id))
                    .where(MessageDB.conversation_id == ConversationDB.id)
                    .correlate(ConversationDB)
                    .scalar_subquery()
                ))
                .where(ConversationDB.created_at >= since)
            )

            return {
                "total_conversations": total_count,
                "by_outcome": outcome_counts,
                "tasks_created": tasks_count,
                "conversion_rate": (tasks_count / total_count * 100) if total_count > 0 else 0,
                "period_days": days,
            }


# Singleton
_conversation_repository: Optional[ConversationRepository] = None


def get_conversation_repository() -> ConversationRepository:
    """Get the conversation repository singleton."""
    global _conversation_repository
    if _conversation_repository is None:
        _conversation_repository = ConversationRepository()
    return _conversation_repository
