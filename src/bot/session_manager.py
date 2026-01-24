"""
Session Manager - Centralized session state management.

Manages all handler session states with Redis persistence and in-memory fallback.
Part of the handler refactoring initiative (Task #4, Phase 1).

Features:
- Redis backend for persistence across restarts
- In-memory fallback when Redis unavailable
- TTL-based automatic expiration
- Thread-safe with async locks
- Support for 7 session types from UnifiedHandler

Session Types:
1. validation_sessions - User validation flows (user_id -> data)
2. pending_validations - Task validation tracking (task_id -> data)
3. pending_reviews - Submission review sessions (user_id -> data)
4. pending_actions - Dangerous action confirmations (user_id -> data)
5. batch_tasks - Batch task creation sessions (user_id -> data)
6. spec_sessions - Spec generation sessions (user_id -> data)
7. recent_messages - Recent message context (user_id -> data)
8. active_handler - Active handler for multi-turn routing (user_id -> data)

v2.4: Initial implementation for handler refactoring
"""

import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from collections import defaultdict

from config import settings

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Centralized session state manager with Redis persistence.

    Replaces the 7 session dictionaries in UnifiedHandler with a unified,
    persistent, thread-safe session storage system.
    """

    # Default TTL for sessions (1 hour)
    DEFAULT_TTL = 3600

    # Session type prefixes for Redis keys
    SESSION_TYPES = {
        "validation": "session:validation",
        "pending_validation": "session:pending_validation",
        "review": "session:review",
        "action": "session:action",
        "batch": "session:batch",
        "spec": "session:spec",
        "message": "session:message",
        "active_handler": "session:active_handler",
    }

    def __init__(self, redis_client: Optional[Any] = None):
        """
        Initialize SessionManager.

        Args:
            redis_client: Optional Redis client for persistence
        """
        self.redis: Optional[Any] = redis_client
        self._memory_store: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._connected: bool = False

    async def connect(self):
        """Connect to Redis if available."""
        if self._connected:
            return

        if settings.redis_url and not self.redis:
            try:
                import redis.asyncio as redis
                self.redis = await redis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                # Test connection
                await self.redis.ping()
                logger.info("SessionManager connected to Redis")
            except Exception as e:
                logger.warning(f"Redis not available for sessions, using in-memory: {e}")
                self.redis = None

        self._connected = True

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            self.redis = None
        self._connected = False

    def _get_key(self, session_type: str, identifier: str) -> str:
        """
        Generate Redis key for a session.

        Args:
            session_type: Type of session (validation, review, etc.)
            identifier: Unique identifier (user_id or task_id)

        Returns:
            Redis key string
        """
        prefix = self.SESSION_TYPES.get(session_type, f"session:{session_type}")
        return f"{prefix}:{identifier}"

    async def _store_get(self, key: str) -> Optional[str]:
        """Get value from Redis or memory."""
        await self.connect()

        if self.redis:
            try:
                return await self.redis.get(key)
            except Exception as e:
                logger.error(f"Redis GET error for {key}: {e}")
                return None
        else:
            # Extract session type and identifier from key
            parts = key.split(":", 2)
            if len(parts) == 3:
                session_type = parts[1]
                identifier = parts[2]
                data = self._memory_store.get(session_type, {}).get(identifier)
                if data:
                    try:
                        # If data is already a string (shouldn't be, but handle it)
                        if isinstance(data, str):
                            # Validate it's valid JSON
                            json.loads(data)
                            return data
                        # Otherwise convert dict to JSON
                        return json.dumps(data)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.error(f"Invalid data in memory for {key}: {e}")
                        return None
                return None
            return None

    async def _store_set(self, key: str, value: str, ttl: Optional[int] = None):
        """Set value in Redis or memory with optional TTL."""
        await self.connect()

        if self.redis:
            try:
                if ttl:
                    await self.redis.setex(key, ttl, value)
                else:
                    await self.redis.set(key, value)
            except Exception as e:
                logger.error(f"Redis SET error for {key}: {e}")
        else:
            # Store in memory
            parts = key.split(":", 2)
            if len(parts) == 3:
                session_type = parts[1]
                identifier = parts[2]
                self._memory_store[session_type][identifier] = json.loads(value)

    async def _store_delete(self, key: str):
        """Delete value from Redis or memory."""
        await self.connect()

        if self.redis:
            try:
                await self.redis.delete(key)
            except Exception as e:
                logger.error(f"Redis DELETE error for {key}: {e}")
        else:
            parts = key.split(":", 2)
            if len(parts) == 3:
                session_type = parts[1]
                identifier = parts[2]
                self._memory_store.get(session_type, {}).pop(identifier, None)

    async def _store_keys(self, pattern: str) -> List[str]:
        """Get all keys matching pattern."""
        await self.connect()

        if self.redis:
            try:
                return await self.redis.keys(pattern)
            except Exception as e:
                logger.error(f"Redis KEYS error for {pattern}: {e}")
                return []
        else:
            # In-memory: match pattern
            parts = pattern.rstrip("*").split(":", 2)
            if len(parts) >= 2:
                session_type = parts[1]
                prefix = f"session:{session_type}"
                return [
                    f"{prefix}:{identifier}"
                    for identifier in self._memory_store.get(session_type, {}).keys()
                ]
            return []

    # ==================== VALIDATION SESSIONS ====================

    async def get_validation_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get validation session for a user.

        Args:
            user_id: User identifier

        Returns:
            Session data dict or None
        """
        key = self._get_key("validation", user_id)
        async with self._locks[key]:
            data = await self._store_get(key)
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding validation session {user_id}: {e}")
            return None

    async def set_validation_session(
        self,
        user_id: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set validation session for a user.

        Args:
            user_id: User identifier
            data: Session data
            ttl: Time-to-live in seconds (default: 1 hour)

        Returns:
            True if successful
        """
        key = self._get_key("validation", user_id)
        async with self._locks[key]:
            try:
                await self._store_set(key, json.dumps(data), ttl or self.DEFAULT_TTL)
                return True
            except Exception as e:
                logger.error(f"Error setting validation session {user_id}: {e}")
                return False

    async def clear_validation_session(self, user_id: str) -> bool:
        """
        Clear validation session for a user.

        Args:
            user_id: User identifier

        Returns:
            True if successful
        """
        key = self._get_key("validation", user_id)
        async with self._locks[key]:
            try:
                await self._store_delete(key)
                return True
            except Exception as e:
                logger.error(f"Error clearing validation session {user_id}: {e}")
                return False

    # ==================== PENDING VALIDATIONS ====================

    async def get_pending_validation(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get pending validation for a task.

        Args:
            task_id: Task identifier

        Returns:
            Validation data dict or None
        """
        key = self._get_key("pending_validation", task_id)
        async with self._locks[key]:
            data = await self._store_get(key)
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding pending validation {task_id}: {e}")
            return None

    async def add_pending_validation(
        self,
        task_id: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Add pending validation for a task.

        Args:
            task_id: Task identifier
            data: Validation data
            ttl: Time-to-live in seconds (default: 1 hour)

        Returns:
            True if successful
        """
        key = self._get_key("pending_validation", task_id)
        async with self._locks[key]:
            try:
                await self._store_set(key, json.dumps(data), ttl or self.DEFAULT_TTL)
                return True
            except Exception as e:
                logger.error(f"Error adding pending validation {task_id}: {e}")
                return False

    async def remove_pending_validation(self, task_id: str) -> bool:
        """
        Remove pending validation for a task.

        Args:
            task_id: Task identifier

        Returns:
            True if successful
        """
        key = self._get_key("pending_validation", task_id)
        async with self._locks[key]:
            try:
                await self._store_delete(key)
                return True
            except Exception as e:
                logger.error(f"Error removing pending validation {task_id}: {e}")
                return False

    async def list_pending_validations(self) -> List[Dict[str, Any]]:
        """
        List all pending validations.

        Returns:
            List of validation data dicts with task_id included
        """
        pattern = f"{self.SESSION_TYPES['pending_validation']}:*"
        keys = await self._store_keys(pattern)

        validations = []
        for key in keys:
            data = await self._store_get(key)
            if data:
                try:
                    validation = json.loads(data)
                    # Extract task_id from key
                    task_id = key.split(":", 2)[2]
                    validation["task_id"] = task_id
                    validations.append(validation)
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding validation from {key}: {e}")

        return validations

    # ==================== PENDING REVIEWS ====================

    async def get_pending_review(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get pending review session for a user."""
        key = self._get_key("review", user_id)
        async with self._locks[key]:
            data = await self._store_get(key)
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding review session {user_id}: {e}")
            return None

    async def set_pending_review(
        self,
        user_id: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Set pending review session for a user."""
        key = self._get_key("review", user_id)
        async with self._locks[key]:
            try:
                await self._store_set(key, json.dumps(data), ttl or self.DEFAULT_TTL)
                return True
            except Exception as e:
                logger.error(f"Error setting review session {user_id}: {e}")
                return False

    async def clear_pending_review(self, user_id: str) -> bool:
        """Clear pending review session for a user."""
        key = self._get_key("review", user_id)
        async with self._locks[key]:
            try:
                await self._store_delete(key)
                return True
            except Exception as e:
                logger.error(f"Error clearing review session {user_id}: {e}")
                return False

    # ==================== PENDING ACTIONS ====================

    async def get_pending_action(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get pending action for a user."""
        key = self._get_key("action", user_id)
        async with self._locks[key]:
            data = await self._store_get(key)
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding action session {user_id}: {e}")
            return None

    async def set_pending_action(
        self,
        user_id: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Set pending action for a user."""
        key = self._get_key("action", user_id)
        async with self._locks[key]:
            try:
                await self._store_set(key, json.dumps(data), ttl or self.DEFAULT_TTL)
                return True
            except Exception as e:
                logger.error(f"Error setting action session {user_id}: {e}")
                return False

    async def clear_pending_action(self, user_id: str) -> bool:
        """Clear pending action for a user."""
        key = self._get_key("action", user_id)
        async with self._locks[key]:
            try:
                await self._store_delete(key)
                return True
            except Exception as e:
                logger.error(f"Error clearing action session {user_id}: {e}")
                return False

    # ==================== BATCH TASKS ====================

    async def get_batch_task(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get batch task session for a user."""
        key = self._get_key("batch", user_id)
        async with self._locks[key]:
            data = await self._store_get(key)
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding batch session {user_id}: {e}")
            return None

    async def set_batch_task(
        self,
        user_id: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Set batch task session for a user."""
        key = self._get_key("batch", user_id)
        async with self._locks[key]:
            try:
                await self._store_set(key, json.dumps(data), ttl or self.DEFAULT_TTL)
                return True
            except Exception as e:
                logger.error(f"Error setting batch session {user_id}: {e}")
                return False

    async def clear_batch_task(self, user_id: str) -> bool:
        """Clear batch task session for a user."""
        key = self._get_key("batch", user_id)
        async with self._locks[key]:
            try:
                await self._store_delete(key)
                return True
            except Exception as e:
                logger.error(f"Error clearing batch session {user_id}: {e}")
                return False

    # ==================== SPEC SESSIONS ====================

    async def get_spec_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get spec generation session for a user."""
        key = self._get_key("spec", user_id)
        async with self._locks[key]:
            data = await self._store_get(key)
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding spec session {user_id}: {e}")
            return None

    async def set_spec_session(
        self,
        user_id: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Set spec generation session for a user."""
        key = self._get_key("spec", user_id)
        async with self._locks[key]:
            try:
                await self._store_set(key, json.dumps(data), ttl or self.DEFAULT_TTL)
                return True
            except Exception as e:
                logger.error(f"Error setting spec session {user_id}: {e}")
                return False

    async def clear_spec_session(self, user_id: str) -> bool:
        """Clear spec generation session for a user."""
        key = self._get_key("spec", user_id)
        async with self._locks[key]:
            try:
                await self._store_delete(key)
                return True
            except Exception as e:
                logger.error(f"Error clearing spec session {user_id}: {e}")
                return False

    # ==================== RECENT MESSAGES ====================

    async def get_recent_message(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get recent message context for a user."""
        key = self._get_key("message", user_id)
        async with self._locks[key]:
            data = await self._store_get(key)
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding message context {user_id}: {e}")
            return None

    async def set_recent_message(
        self,
        user_id: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set recent message context for a user.

        Note: Recent messages typically have shorter TTL (e.g., 300s = 5 minutes)
        """
        key = self._get_key("message", user_id)
        async with self._locks[key]:
            try:
                # Default to shorter TTL for message context
                message_ttl = ttl if ttl is not None else 300
                await self._store_set(key, json.dumps(data), message_ttl)
                return True
            except Exception as e:
                logger.error(f"Error setting message context {user_id}: {e}")
                return False

    async def clear_recent_message(self, user_id: str) -> bool:
        """Clear recent message context for a user."""
        key = self._get_key("message", user_id)
        async with self._locks[key]:
            try:
                await self._store_delete(key)
                return True
            except Exception as e:
                logger.error(f"Error clearing message context {user_id}: {e}")
                return False

    # ==================== ACTIVE HANDLER ====================

    async def get_active_handler_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get active handler session for a user."""
        key = self._get_key("active_handler", user_id)
        async with self._locks[key]:
            data = await self._store_get(key)
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding active handler session {user_id}: {e}")
            return None

    async def set_active_handler_session(
        self,
        user_id: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Set active handler session for a user."""
        key = self._get_key("active_handler", user_id)
        async with self._locks[key]:
            try:
                await self._store_set(key, json.dumps(data), ttl or self.DEFAULT_TTL)
                return True
            except Exception as e:
                logger.error(f"Error setting active handler session {user_id}: {e}")
                return False

    async def clear_active_handler_session(self, user_id: str) -> bool:
        """Clear active handler session for a user."""
        key = self._get_key("active_handler", user_id)
        async with self._locks[key]:
            try:
                await self._store_delete(key)
                return True
            except Exception as e:
                logger.error(f"Error clearing active handler session {user_id}: {e}")
                return False

    # ==================== CLEANUP & MAINTENANCE ====================

    async def cleanup_expired_sessions(self, ttl_seconds: int = DEFAULT_TTL) -> Dict[str, int]:
        """
        Clean up expired sessions from in-memory storage.

        Note: Redis automatically handles expiration via TTL.
        This method is only needed for in-memory fallback.

        Args:
            ttl_seconds: Session TTL to use for cleanup

        Returns:
            Dict with count of cleaned sessions per type
        """
        if self.redis:
            # Redis handles expiration automatically
            return {"note": "Redis handles expiration automatically"}

        cleaned = {}
        cutoff_time = datetime.now() - timedelta(seconds=ttl_seconds)

        for session_type, sessions in self._memory_store.items():
            count = 0
            expired_keys = []

            for identifier, data in sessions.items():
                # Check if session has timestamp and is expired
                if isinstance(data, dict):
                    created_at = data.get("created_at")
                    if created_at:
                        try:
                            # Parse timestamp
                            if isinstance(created_at, str):
                                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            elif isinstance(created_at, (int, float)):
                                created_at = datetime.fromtimestamp(created_at)

                            if created_at < cutoff_time:
                                expired_keys.append(identifier)
                                count += 1
                        except Exception as e:
                            logger.error(f"Error parsing timestamp for {session_type}:{identifier}: {e}")

            # Remove expired sessions
            for key in expired_keys:
                sessions.pop(key, None)

            if count > 0:
                cleaned[session_type] = count
                logger.info(f"Cleaned {count} expired {session_type} sessions")

        return cleaned

    async def get_session_stats(self) -> Dict[str, Any]:
        """
        Get statistics about current sessions.

        Returns:
            Dict with session counts per type
        """
        stats = {
            "storage": "redis" if self.redis else "memory",
            "by_type": {},
            "total": 0,
        }

        for session_type, prefix in self.SESSION_TYPES.items():
            pattern = f"{prefix}:*"
            keys = await self._store_keys(pattern)
            count = len(keys)
            stats["by_type"][session_type] = count
            stats["total"] += count

        return stats

    async def clear_all_sessions(self, session_type: Optional[str] = None) -> bool:
        """
        Clear all sessions, optionally filtered by type.

        WARNING: This removes all active sessions!

        Args:
            session_type: Optional session type to clear (e.g., "validation")
                         If None, clears ALL sessions

        Returns:
            True if successful
        """
        try:
            if session_type:
                # Clear specific type
                pattern = f"{self.SESSION_TYPES[session_type]}:*"
                keys = await self._store_keys(pattern)

                for key in keys:
                    await self._store_delete(key)

                logger.warning(f"Cleared all {session_type} sessions ({len(keys)} total)")
            else:
                # Clear all types
                if self.redis:
                    for prefix in self.SESSION_TYPES.values():
                        pattern = f"{prefix}:*"
                        keys = await self._store_keys(pattern)
                        for key in keys:
                            await self._store_delete(key)
                else:
                    self._memory_store.clear()

                logger.warning("Cleared ALL sessions")

            return True
        except Exception as e:
            logger.error(f"Error clearing sessions: {e}")
            return False


# Singleton instance
_session_manager: Optional[SessionManager] = None


def get_session_manager(redis_client: Optional[Any] = None) -> SessionManager:
    """
    Get the SessionManager singleton.

    Args:
        redis_client: Optional Redis client (only used on first call)

    Returns:
        SessionManager instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(redis_client=redis_client)
    return _session_manager


async def init_session_manager(redis_client: Optional[Any] = None) -> SessionManager:
    """
    Initialize and connect the SessionManager.

    Args:
        redis_client: Optional Redis client

    Returns:
        Connected SessionManager instance
    """
    manager = get_session_manager(redis_client)
    await manager.connect()
    return manager
