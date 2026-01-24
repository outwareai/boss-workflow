"""
Redis caching layer for Boss Workflow.

Q3 2026: Performance optimization with Redis caching.

Provides:
- Redis client with connection pooling
- Cache decorators for easy use
- Statistics tracking
- Cache invalidation utilities
"""

from .redis_client import get_redis, close_redis, cache, CacheClient
from .decorators import cached
from .stats import stats, CacheStats

__all__ = [
    "get_redis",
    "close_redis",
    "cache",
    "CacheClient",
    "cached",
    "stats",
    "CacheStats",
]
