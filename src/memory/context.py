"""
Conversation context management.

Handles storage and retrieval of conversation state in Redis.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import redis.asyncio as redis

from config import settings
from ..models.conversation import ConversationState, ConversationStage

logger = logging.getLogger(__name__)


class ConversationContext:
    """
    Manages conversation state for multi-turn task creation.

    Stores conversation state in Redis with expiration.
    """

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.default_ttl = settings.conversation_timeout_minutes * 60  # seconds

    async def connect(self):
        """Connect to Redis (optional - falls back to in-memory)."""
        if not self.redis and settings.redis_url:
            try:
                self.redis = await redis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                # Test connection
                await self.redis.ping()
                logger.info("Connected to Redis for conversation context")
            except Exception as e:
                logger.warning(f"Redis not available for context, using in-memory: {e}")
                self.redis = None
                self._memory_store = {}  # Fallback in-memory storage

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            self.redis = None

    async def create_conversation(
        self,
        user_id: str,
        chat_id: str,
        original_message: str,
        is_urgent: bool = False
    ) -> ConversationState:
        """
        Create a new conversation state.

        Also sets this as the user's active conversation.
        """
        await self.connect()

        # Check for existing active conversation
        existing = await self.get_active_conversation(user_id)
        if existing and existing.stage not in [
            ConversationStage.COMPLETED,
            ConversationStage.ABANDONED
        ]:
            # Mark existing as abandoned
            existing.stage = ConversationStage.ABANDONED
            await self.save_conversation(existing)

        # Create new conversation
        conversation = ConversationState(
            user_id=user_id,
            chat_id=chat_id,
            original_message=original_message,
            is_urgent=is_urgent
        )

        # Add the original message to history
        conversation.add_user_message(original_message)

        # Save and set as active
        await self.save_conversation(conversation)
        await self._set_active_conversation(user_id, conversation.conversation_id)

        logger.info(f"Created conversation {conversation.conversation_id} for user {user_id}")
        return conversation

    async def get_conversation(self, conversation_id: str, user_id: str) -> Optional[ConversationState]:
        """Get a conversation by ID."""
        await self.connect()

        key = f"conversation:{user_id}:{conversation_id}"
        data = await self.redis.get(key)

        if data:
            try:
                return ConversationState(**json.loads(data))
            except Exception as e:
                logger.error(f"Error loading conversation {conversation_id}: {e}")

        return None

    async def get_active_conversation(self, user_id: str) -> Optional[ConversationState]:
        """Get the user's current active conversation."""
        await self.connect()

        active_key = ConversationState.active_conversation_key(user_id)
        conversation_id = await self.redis.get(active_key)

        if conversation_id:
            return await self.get_conversation(conversation_id, user_id)

        return None

    async def save_conversation(self, conversation: ConversationState) -> bool:
        """Save conversation state to Redis."""
        await self.connect()

        try:
            key = conversation.to_redis_key()
            conversation.updated_at = datetime.now()

            # Extend TTL for active conversations
            ttl = self.default_ttl
            if conversation.stage in [ConversationStage.COMPLETED, ConversationStage.ABANDONED]:
                ttl = 3600  # Keep completed conversations for 1 hour for reference

            await self.redis.setex(
                key,
                ttl,
                json.dumps(conversation.model_dump(mode="json"))
            )
            return True

        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            return False

    async def _set_active_conversation(self, user_id: str, conversation_id: str) -> bool:
        """Set the user's active conversation ID."""
        try:
            active_key = ConversationState.active_conversation_key(user_id)
            await self.redis.setex(
                active_key,
                self.default_ttl,
                conversation_id
            )
            return True
        except Exception as e:
            logger.error(f"Error setting active conversation: {e}")
            return False

    async def clear_active_conversation(self, user_id: str) -> bool:
        """Clear the user's active conversation."""
        try:
            active_key = ConversationState.active_conversation_key(user_id)
            await self.redis.delete(active_key)
            return True
        except Exception as e:
            logger.error(f"Error clearing active conversation: {e}")
            return False

    async def update_stage(
        self,
        conversation: ConversationState,
        new_stage: ConversationStage
    ) -> bool:
        """Update conversation stage."""
        conversation.stage = new_stage
        conversation.updated_at = datetime.now()

        if new_stage == ConversationStage.COMPLETED:
            conversation.completed_at = datetime.now()
            await self.clear_active_conversation(conversation.user_id)

        return await self.save_conversation(conversation)

    async def get_timed_out_conversations(self) -> List[ConversationState]:
        """Get all conversations that have timed out."""
        await self.connect()

        timed_out = []
        timeout_threshold = datetime.now() - timedelta(minutes=settings.conversation_timeout_minutes)

        # Scan for active conversation keys
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor=cursor,
                match="active_conversation:*",
                count=100
            )

            for key in keys:
                user_id = key.split(":")[-1]
                conv = await self.get_active_conversation(user_id)

                if conv and conv.last_activity_at < timeout_threshold:
                    timed_out.append(conv)

            if cursor == 0:
                break

        return timed_out

    async def get_conversations_to_auto_finalize(self) -> List[ConversationState]:
        """Get conversations that should be auto-finalized."""
        await self.connect()

        to_finalize = []
        finalize_threshold = datetime.now() - timedelta(hours=settings.auto_finalize_hours)

        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor=cursor,
                match="active_conversation:*",
                count=100
            )

            for key in keys:
                user_id = key.split(":")[-1]
                conv = await self.get_active_conversation(user_id)

                if conv and conv.last_activity_at < finalize_threshold:
                    if conv.stage not in [ConversationStage.COMPLETED, ConversationStage.ABANDONED]:
                        to_finalize.append(conv)

            if cursor == 0:
                break

        return to_finalize

    async def add_message_to_conversation(
        self,
        conversation: ConversationState,
        content: str,
        role: str = "user",
        message_id: Optional[str] = None
    ) -> bool:
        """Add a message to conversation history."""
        if role == "user":
            conversation.add_user_message(content, message_id)
        else:
            conversation.add_assistant_message(content)

        conversation.last_activity_at = datetime.now()
        return await self.save_conversation(conversation)


# Singleton instance
conversation_context = ConversationContext()


def get_conversation_context() -> ConversationContext:
    """Get the conversation context instance."""
    return conversation_context
