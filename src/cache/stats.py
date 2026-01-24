"""
Cache statistics tracking.

Q3 2026: Performance optimization with Redis caching.
"""
import logging
from typing import Dict, Optional
from .redis_client import get_redis

logger = logging.getLogger(__name__)


class CacheStats:
    """Track cache hit/miss rates and Redis statistics."""

    def __init__(self):
        self.hits = 0
        self.misses = 0

    def record_hit(self):
        """Record a cache hit."""
        self.hits += 1

    def record_miss(self):
        """Record a cache miss."""
        self.misses += 1

    def get_rate(self) -> float:
        """
        Get cache hit rate.

        Returns:
            Hit rate as a float between 0.0 and 1.0
        """
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def get_total(self) -> int:
        """Get total cache operations."""
        return self.hits + self.misses

    def get_summary(self) -> Dict[str, any]:
        """
        Get statistics summary.

        Returns:
            Dictionary with hits, misses, total, and hit rate
        """
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total": self.get_total(),
            "hit_rate": self.get_rate(),
            "hit_rate_percent": f"{self.get_rate() * 100:.2f}%"
        }

    def reset(self):
        """Reset statistics counters."""
        self.hits = 0
        self.misses = 0
        logger.info("Cache statistics reset")

    async def get_redis_stats(self) -> Optional[Dict[str, any]]:
        """
        Get Redis server statistics.

        Returns:
            Dictionary with Redis server stats or None if unavailable
        """
        client = await get_redis()
        if not client:
            return None

        try:
            info = await client.info()

            # Extract useful stats
            return {
                # Server info
                "redis_version": info.get("redis_version"),
                "uptime_in_seconds": info.get("uptime_in_seconds"),

                # Clients
                "connected_clients": info.get("connected_clients"),
                "blocked_clients": info.get("blocked_clients"),

                # Memory
                "used_memory": info.get("used_memory"),
                "used_memory_human": info.get("used_memory_human"),
                "used_memory_peak": info.get("used_memory_peak"),
                "used_memory_peak_human": info.get("used_memory_peak_human"),
                "maxmemory": info.get("maxmemory"),
                "maxmemory_human": info.get("maxmemory_human"),

                # Stats
                "total_commands_processed": info.get("total_commands_processed"),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),

                # Keyspace
                "db0": info.get("db0"),  # Keys in database 0

                # Persistence
                "loading": info.get("loading"),
                "rdb_last_save_time": info.get("rdb_last_save_time"),

                # Replication
                "role": info.get("role"),
                "connected_slaves": info.get("connected_slaves"),
            }
        except Exception as e:
            logger.error(f"Failed to get Redis stats: {e}")
            return None

    async def get_redis_hit_rate(self) -> Optional[float]:
        """
        Get Redis server-side hit rate.

        Returns:
            Hit rate from Redis INFO stats or None if unavailable
        """
        client = await get_redis()
        if not client:
            return None

        try:
            info = await client.info()
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses

            return hits / total if total > 0 else 0.0
        except Exception as e:
            logger.error(f"Failed to get Redis hit rate: {e}")
            return None

    async def get_full_stats(self) -> Dict[str, any]:
        """
        Get combined application and Redis statistics.

        Returns:
            Dictionary with all available statistics
        """
        app_stats = self.get_summary()
        redis_stats = await self.get_redis_stats()
        redis_hit_rate = await self.get_redis_hit_rate()

        return {
            "application": app_stats,
            "redis": redis_stats,
            "redis_hit_rate": redis_hit_rate,
            "redis_hit_rate_percent": f"{redis_hit_rate * 100:.2f}%" if redis_hit_rate is not None else None,
            "redis_available": redis_stats is not None
        }


# Global stats instance
stats = CacheStats()
