"""
Rate Limiter Service - Protects against excessive requests.

Features:
- Configurable rate limits per user/endpoint
- Sliding window algorithm for accurate limiting
- Redis-backed for distributed environments
- Fallback to in-memory when Redis unavailable

v2.0.5: Initial implementation
"""

import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import defaultdict

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit."""
    requests: int       # Max requests in window
    window_seconds: int # Window size in seconds
    burst: int = 0      # Extra burst capacity (optional)


class RateLimiter:
    """
    Token bucket rate limiter with sliding window.

    Features:
    - Per-user rate limiting
    - Per-endpoint rate limiting
    - Global rate limiting
    - Burst capacity for short spikes
    """

    # Default rate limits
    DEFAULT_LIMITS = {
        "global": RateLimitConfig(requests=1000, window_seconds=60),  # 1000 req/min globally
        "user": RateLimitConfig(requests=60, window_seconds=60, burst=10),  # 60 req/min per user
        "ai_request": RateLimitConfig(requests=30, window_seconds=60),  # 30 AI calls/min per user
        "discord_post": RateLimitConfig(requests=20, window_seconds=60),  # 20 Discord posts/min
        "sheets_write": RateLimitConfig(requests=50, window_seconds=60),  # 50 Sheets writes/min
    }

    def __init__(self):
        # In-memory storage: {key: [(timestamp, count), ...]}
        self._requests: Dict[str, list] = defaultdict(list)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

        # Redis client (lazy loaded)
        self._redis = None
        self._redis_available = None

    def _get_redis(self):
        """Lazy load Redis client."""
        if self._redis is None and settings.redis_url:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(settings.redis_url, decode_responses=True)
                self._redis_available = True
            except Exception as e:
                logger.warning(f"Redis not available for rate limiting: {e}")
                self._redis_available = False
        return self._redis

    def _get_key(self, limit_type: str, identifier: str = "") -> str:
        """Generate a rate limit key."""
        if identifier:
            return f"ratelimit:{limit_type}:{identifier}"
        return f"ratelimit:{limit_type}"

    def _get_config(self, limit_type: str) -> RateLimitConfig:
        """Get rate limit configuration for a type."""
        return self.DEFAULT_LIMITS.get(limit_type, self.DEFAULT_LIMITS["user"])

    async def check_rate_limit(
        self,
        limit_type: str,
        identifier: str = "",
        consume: bool = True
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if a request is allowed under rate limits.

        Args:
            limit_type: Type of rate limit to check
            identifier: User/endpoint identifier
            consume: If True, consume a request token

        Returns:
            Tuple of (allowed: bool, info: dict)
            info contains: remaining, limit, reset_seconds
        """
        config = self._get_config(limit_type)
        key = self._get_key(limit_type, identifier)

        async with self._locks[key]:
            now = datetime.now()
            window_start = now - timedelta(seconds=config.window_seconds)

            # Clean old requests
            self._requests[key] = [
                (ts, count) for ts, count in self._requests[key]
                if ts > window_start
            ]

            # Count current requests
            current_count = sum(count for _, count in self._requests[key])
            total_limit = config.requests + config.burst

            # Check if allowed
            allowed = current_count < total_limit
            remaining = max(0, total_limit - current_count - (1 if consume and allowed else 0))

            # Calculate reset time
            if self._requests[key]:
                oldest = min(ts for ts, _ in self._requests[key])
                reset_seconds = max(0, config.window_seconds - (now - oldest).total_seconds())
            else:
                reset_seconds = config.window_seconds

            # Consume a token if allowed and requested
            if allowed and consume:
                self._requests[key].append((now, 1))

            info = {
                "allowed": allowed,
                "remaining": remaining,
                "limit": total_limit,
                "reset_seconds": round(reset_seconds),
                "limit_type": limit_type,
            }

            if not allowed:
                logger.warning(f"Rate limit exceeded for {limit_type}:{identifier}")

            return allowed, info

    async def is_allowed(
        self,
        limit_type: str,
        identifier: str = ""
    ) -> bool:
        """
        Quick check if a request is allowed.

        Consumes a token if allowed.
        """
        allowed, _ = await self.check_rate_limit(limit_type, identifier, consume=True)
        return allowed

    async def get_remaining(
        self,
        limit_type: str,
        identifier: str = ""
    ) -> int:
        """Get remaining requests in the current window."""
        _, info = await self.check_rate_limit(limit_type, identifier, consume=False)
        return info["remaining"]

    # ==================== CONVENIENCE METHODS ====================

    async def check_user_limit(self, user_id: str) -> Tuple[bool, Dict[str, Any]]:
        """Check rate limit for a specific user."""
        return await self.check_rate_limit("user", user_id)

    async def check_ai_limit(self, user_id: str) -> Tuple[bool, Dict[str, Any]]:
        """Check rate limit for AI requests for a user."""
        return await self.check_rate_limit("ai_request", user_id)

    async def check_discord_limit(self) -> Tuple[bool, Dict[str, Any]]:
        """Check global Discord posting rate limit."""
        return await self.check_rate_limit("discord_post", "global")

    async def check_sheets_limit(self) -> Tuple[bool, Dict[str, Any]]:
        """Check Google Sheets write rate limit."""
        return await self.check_rate_limit("sheets_write", "global")

    # ==================== ADMIN METHODS ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get current rate limiter statistics."""
        stats = {
            "active_keys": len(self._requests),
            "by_type": defaultdict(int),
            "total_tracked_requests": 0,
        }

        for key, requests in self._requests.items():
            limit_type = key.split(":")[1] if ":" in key else "unknown"
            count = sum(c for _, c in requests)
            stats["by_type"][limit_type] += count
            stats["total_tracked_requests"] += count

        return dict(stats)

    async def reset_limit(self, limit_type: str, identifier: str = "") -> None:
        """Reset rate limit for a specific key."""
        key = self._get_key(limit_type, identifier)
        async with self._locks[key]:
            self._requests[key] = []
        logger.info(f"Reset rate limit for {key}")

    async def reset_user(self, user_id: str) -> None:
        """Reset all rate limits for a user."""
        keys_to_reset = [
            k for k in self._requests.keys()
            if f":{user_id}" in k
        ]
        for key in keys_to_reset:
            async with self._locks[key]:
                self._requests[key] = []
        logger.info(f"Reset all rate limits for user {user_id}")


# Singleton
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


# ==================== DECORATOR ====================

def rate_limited(limit_type: str = "user", identifier_param: str = "user_id"):
    """
    Decorator for rate-limiting async functions.

    Args:
        limit_type: Type of rate limit to apply
        identifier_param: Name of the parameter to use as identifier

    Usage:
        @rate_limited("ai_request", "user_id")
        async def process_ai_request(user_id: str, message: str):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            limiter = get_rate_limiter()
            identifier = kwargs.get(identifier_param, "anonymous")

            allowed, info = await limiter.check_rate_limit(limit_type, str(identifier))

            if not allowed:
                raise RateLimitExceeded(
                    f"Rate limit exceeded for {limit_type}",
                    retry_after=info["reset_seconds"]
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after
