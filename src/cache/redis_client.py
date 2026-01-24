"""
Redis caching client.

Q3 2026: Performance optimization with Redis caching.
"""
import redis.asyncio as redis
import json
import logging
from typing import Any, Optional
from datetime import timedelta
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Global Redis client
_redis_client: Optional[redis.Redis] = None


async def get_redis() -> Optional[redis.Redis]:
    """
    Get or create Redis client.

    Returns None if Redis URL is not configured.
    """
    global _redis_client

    # Check if Redis is configured
    if not settings.redis_url:
        logger.warning("Redis URL not configured - caching disabled")
        return None

    if _redis_client is None:
        try:
            _redis_client = await redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            # Test connection
            await _redis_client.ping()
            logger.info("Redis client created and connected")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            _redis_client = None
            return None

    return _redis_client


async def close_redis():
    """Close Redis connection."""
    global _redis_client

    if _redis_client:
        try:
            await _redis_client.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis: {e}")
        finally:
            _redis_client = None


class CacheClient:
    """Redis caching client with helper methods."""

    def __init__(self):
        self.prefix = "boss-workflow:"

    async def get(self, key: str) -> Optional[Any]:
        """
        Get cached value.

        Args:
            key: Cache key (prefix will be added automatically)

        Returns:
            Cached value or None if not found/Redis unavailable
        """
        client = await get_redis()
        if not client:
            return None

        full_key = f"{self.prefix}{key}"

        try:
            value = await client.get(full_key)
            if value:
                return json.loads(value)
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode cached value for {key}: {e}")
            # Delete corrupted cache entry
            await self.delete(key)
            return None
        except Exception as e:
            logger.error(f"Cache get error for {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 300  # 5 minutes default
    ) -> bool:
        """
        Set cached value with TTL.

        Args:
            key: Cache key (prefix will be added automatically)
            value: Value to cache (must be JSON-serializable)
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        client = await get_redis()
        if not client:
            return False

        full_key = f"{self.prefix}{key}"

        try:
            serialized = json.dumps(value)
            await client.setex(
                full_key,
                ttl,
                serialized
            )
            return True
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize value for {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Cache set error for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete cached value.

        Args:
            key: Cache key (prefix will be added automatically)

        Returns:
            True if successful, False otherwise
        """
        client = await get_redis()
        if not client:
            return False

        full_key = f"{self.prefix}{key}"

        try:
            await client.delete(full_key)
            return True
        except Exception as e:
            logger.error(f"Cache delete error for {key}: {e}")
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching pattern.

        Args:
            pattern: Pattern to match (e.g., "tasks:*")

        Returns:
            Number of keys deleted
        """
        client = await get_redis()
        if not client:
            return 0

        full_pattern = f"{self.prefix}{pattern}"

        try:
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = await client.scan(
                    cursor,
                    match=full_pattern,
                    count=100
                )
                if keys:
                    await client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break

            logger.info(f"Invalidated {deleted} cache entries matching {pattern}")
            return deleted
        except Exception as e:
            logger.error(f"Cache invalidate error for pattern {pattern}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key (prefix will be added automatically)

        Returns:
            True if exists, False otherwise
        """
        client = await get_redis()
        if not client:
            return False

        full_key = f"{self.prefix}{key}"

        try:
            return await client.exists(full_key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for {key}: {e}")
            return False

    async def ttl(self, key: str) -> int:
        """
        Get remaining TTL for key.

        Args:
            key: Cache key (prefix will be added automatically)

        Returns:
            TTL in seconds, -1 if no TTL, -2 if not found
        """
        client = await get_redis()
        if not client:
            return -2

        full_key = f"{self.prefix}{key}"

        try:
            return await client.ttl(full_key)
        except Exception as e:
            logger.error(f"Cache TTL error for {key}: {e}")
            return -2

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment counter.

        Args:
            key: Cache key (prefix will be added automatically)
            amount: Amount to increment by

        Returns:
            New value or None on error
        """
        client = await get_redis()
        if not client:
            return None

        full_key = f"{self.prefix}{key}"

        try:
            return await client.incrby(full_key, amount)
        except Exception as e:
            logger.error(f"Cache increment error for {key}: {e}")
            return None


# Global cache instance
cache = CacheClient()
