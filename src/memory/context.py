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
    Falls back to in-memory storage when Redis isn't available.
    """

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self._memory_store: Dict[str, str] = {}  # Fallback in-memory storage
        self._connected = False
        self.default_ttl = settings.conversation_timeout_minutes * 60  # seconds

    async def connect(self):
        """Connect to Redis (optional - falls back to in-memory)."""
        if self._connected:
            return

        if settings.redis_url:
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

        self._connected = True

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            self.redis = None
        self._connected = False

    # =========== Storage helper methods ===========

    async def _store_get(self, key: str) -> Optional[str]:
        """Get value from Redis or memory."""
        if self.redis:
            return await self.redis.get(key)
        return self._memory_store.get(key)

    async def _store_set(self, key: str, value: str, ttl: int = None) -> bool:
        """Set value in Redis or memory."""
        try:
            if self.redis:
                if ttl:
                    await self.redis.setex(key, ttl, value)
                else:
                    await self.redis.set(key, value)
            else:
                self._memory_store[key] = value
            return True
        except Exception as e:
            logger.error(f"Error storing key {key}: {e}")
            return False

    async def _store_delete(self, key: str) -> bool:
        """Delete value from Redis or memory."""
        try:
            if self.redis:
                await self.redis.delete(key)
            else:
                self._memory_store.pop(key, None)
            return True
        except Exception as e:
            logger.error(f"Error deleting key {key}: {e}")
            return False

    async def _store_scan(self, pattern: str) -> List[str]:
        """Scan keys matching pattern."""
        if self.redis:
            keys = []
            cursor = 0
            while True:
                cursor, batch = await self.redis.scan(cursor=cursor, match=pattern, count=100)
                keys.extend(batch)
                if cursor == 0:
                    break
            return keys
        else:
            # Simple in-memory pattern matching
            import fnmatch
            return [k for k in self._memory_store.keys() if fnmatch.fnmatch(k, pattern)]

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
        data = await self._store_get(key)

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
        conversation_id = await self._store_get(active_key)

        if conversation_id:
            return await self.get_conversation(conversation_id, user_id)

        return None

    async def save_conversation(self, conversation: ConversationState) -> bool:
        """Save conversation state to storage."""
        await self.connect()

        try:
            key = conversation.to_redis_key()
            conversation.updated_at = datetime.now()

            # Extend TTL for active conversations
            ttl = self.default_ttl
            if conversation.stage in [ConversationStage.COMPLETED, ConversationStage.ABANDONED]:
                ttl = 3600  # Keep completed conversations for 1 hour for reference

            await self._store_set(
                key,
                json.dumps(conversation.model_dump(mode="json")),
                ttl
            )
            return True

        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            return False

    async def _set_active_conversation(self, user_id: str, conversation_id: str) -> bool:
        """Set the user's active conversation ID."""
        try:
            active_key = ConversationState.active_conversation_key(user_id)
            await self._store_set(active_key, conversation_id, self.default_ttl)
            return True
        except Exception as e:
            logger.error(f"Error setting active conversation: {e}")
            return False

    async def clear_active_conversation(self, user_id: str) -> bool:
        """Clear the user's active conversation."""
        try:
            active_key = ConversationState.active_conversation_key(user_id)
            await self._store_delete(active_key)
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
        keys = await self._store_scan("active_conversation:*")

        for key in keys:
            user_id = key.split(":")[-1]
            conv = await self.get_active_conversation(user_id)

            if conv and conv.last_activity_at < timeout_threshold:
                timed_out.append(conv)

        return timed_out

    async def get_conversations_to_auto_finalize(self) -> List[ConversationState]:
        """Get conversations that should be auto-finalized."""
        await self.connect()

        to_finalize = []
        finalize_threshold = datetime.now() - timedelta(hours=settings.auto_finalize_hours)

        # Scan for active conversation keys
        keys = await self._store_scan("active_conversation:*")

        for key in keys:
            user_id = key.split(":")[-1]
            conv = await self.get_active_conversation(user_id)

            if conv and conv.last_activity_at < finalize_threshold:
                if conv.stage not in [ConversationStage.COMPLETED, ConversationStage.ABANDONED]:
                    to_finalize.append(conv)

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
