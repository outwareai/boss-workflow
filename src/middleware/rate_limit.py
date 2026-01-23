"""
Rate limiting middleware for API protection.

Q1 2026 Security: Prevent DoS attacks and resource exhaustion.
Uses Redis for distributed rate limiting (fallback to in-memory if Redis unavailable).
"""

import time
import logging
from typing import Dict, Tuple
from collections import defaultdict, deque
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Token bucket rate limiting middleware.

    Limits:
    - General API: 100 requests/minute per IP
    - Admin endpoints: 5 requests/hour per IP
    - Webhook endpoints: 200 requests/minute (no IP limit - from Telegram/Discord)
    """

    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self.redis = redis_client
        self.in_memory_store: Dict[str, deque] = defaultdict(deque)
        self.cleanup_interval = 60  # Clean up old entries every 60 seconds
        self.last_cleanup = time.time()

    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting based on endpoint and IP."""

        # Determine rate limit based on path
        limits = self._get_limits(request.url.path)
        if not limits:
            # No rate limiting for this endpoint
            return await call_next(request)

        max_requests, window_seconds = limits

        # Get client identifier (IP address)
        client_ip = self._get_client_ip(request)

        # Check rate limit
        allowed, remaining, reset_time = await self._check_rate_limit(
            client_ip, request.url.path, max_requests, window_seconds
        )

        if not allowed:
            retry_after = int(reset_time - time.time())
            logger.warning(
                f"Rate limit exceeded for {client_ip} on {request.url.path}",
                extra={"ip": client_ip, "path": request.url.path, "retry_after": retry_after}
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                    "limit": max_requests,
                    "window": window_seconds,
                },
                headers={"Retry-After": str(retry_after)}
            )

        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(reset_time))

        return response

    def _get_limits(self, path: str) -> Tuple[int, int] | None:
        """
        Get rate limit for the given path.

        Returns: (max_requests, window_seconds) or None if no limit
        """
        # Admin endpoints: 5 requests/hour
        if path.startswith("/admin/"):
            return (5, 3600)

        # Webhook endpoints: 200 requests/minute (high volume expected)
        if path.startswith("/webhook/"):
            return (200, 60)

        # Database API endpoints: 50 requests/minute
        if path.startswith("/api/db/"):
            return (50, 60)

        # General API: 100 requests/minute
        if path.startswith("/api/"):
            return (100, 60)

        # Health check and root: no limit
        if path in ["/", "/health", "/docs", "/openapi.json"]:
            return None

        # Default: 100 requests/minute
        return (100, 60)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, checking proxy headers."""
        # Check X-Forwarded-For header (from reverse proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"

    async def _check_rate_limit(
        self, client_id: str, path: str, max_requests: int, window_seconds: int
    ) -> Tuple[bool, int, float]:
        """
        Check if request is within rate limit using token bucket algorithm.

        Returns: (allowed, remaining_requests, reset_timestamp)
        """
        key = f"ratelimit:{client_id}:{path}"
        now = time.time()

        if self.redis:
            try:
                return await self._check_redis(key, now, max_requests, window_seconds)
            except Exception as e:
                logger.warning(f"Redis rate limit check failed, using in-memory: {e}")

        # Fallback to in-memory
        return self._check_memory(key, now, max_requests, window_seconds)

    async def _check_redis(
        self, key: str, now: float, max_requests: int, window_seconds: int
    ) -> Tuple[bool, int, float]:
        """Redis-based rate limiting using sorted set."""
        # Remove old entries outside the window
        cutoff = now - window_seconds
        await self.redis.zremrangebyscore(key, 0, cutoff)

        # Count requests in current window
        count = await self.redis.zcard(key)

        if count >= max_requests:
            # Rate limit exceeded
            oldest = await self.redis.zrange(key, 0, 0, withscores=True)
            reset_time = oldest[0][1] + window_seconds if oldest else now + window_seconds
            return (False, 0, reset_time)

        # Add current request
        await self.redis.zadd(key, {str(now): now})
        await self.redis.expire(key, window_seconds)

        # Calculate reset time (when oldest request expires)
        oldest = await self.redis.zrange(key, 0, 0, withscores=True)
        reset_time = oldest[0][1] + window_seconds if oldest else now + window_seconds

        remaining = max_requests - (count + 1)
        return (True, remaining, reset_time)

    def _check_memory(
        self, key: str, now: float, max_requests: int, window_seconds: int
    ) -> Tuple[bool, int, float]:
        """In-memory rate limiting using deque."""
        # Periodic cleanup of old keys
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup_memory(now, window_seconds)
            self.last_cleanup = now

        # Get request timestamps for this key
        timestamps = self.in_memory_store[key]

        # Remove old entries outside the window
        cutoff = now - window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        if len(timestamps) >= max_requests:
            # Rate limit exceeded
            reset_time = timestamps[0] + window_seconds
            return (False, 0, reset_time)

        # Add current request
        timestamps.append(now)

        reset_time = timestamps[0] + window_seconds if timestamps else now + window_seconds
        remaining = max_requests - len(timestamps)
        return (True, remaining, reset_time)

    def _cleanup_memory(self, now: float, window_seconds: int):
        """Clean up old entries from in-memory store."""
        cutoff = now - window_seconds * 2  # Keep 2x window for safety
        keys_to_delete = []

        for key, timestamps in self.in_memory_store.items():
            # Remove old timestamps
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            # Delete key if empty
            if not timestamps:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self.in_memory_store[key]

        if keys_to_delete:
            logger.debug(f"Cleaned up {len(keys_to_delete)} empty rate limit keys")


def get_rate_limiter(redis_client=None) -> RateLimitMiddleware:
    """Factory function to create rate limiter instance."""
    return RateLimitMiddleware(None, redis_client=redis_client)
