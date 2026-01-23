"""
Tests for rate limiting middleware (rate_limit.py).

Q1 2026: Ensures rate limiting works correctly.
"""

import pytest
import time
from unittest.mock import Mock, AsyncMock
from fastapi import Request
from src.middleware.rate_limit import RateLimitMiddleware


class TestRateLimitMiddleware:
    """Test rate limiting middleware."""

    def test_get_limits_admin(self):
        """Test admin endpoint limits."""
        middleware = RateLimitMiddleware(None)
        limits = middleware._get_limits("/admin/seed-test-team")
        assert limits == (5, 3600)  # 5 req/hour

    def test_get_limits_webhook(self):
        """Test webhook endpoint limits."""
        middleware = RateLimitMiddleware(None)
        limits = middleware._get_limits("/webhook/telegram")
        assert limits == (200, 60)  # 200 req/min

    def test_get_limits_db_api(self):
        """Test database API limits."""
        middleware = RateLimitMiddleware(None)
        limits = middleware._get_limits("/api/db/tasks")
        assert limits == (50, 60)  # 50 req/min

    def test_get_limits_general_api(self):
        """Test general API limits."""
        middleware = RateLimitMiddleware(None)
        limits = middleware._get_limits("/api/preferences/123/teach")
        assert limits == (100, 60)  # 100 req/min

    def test_get_limits_health_check(self):
        """Test health check has no limit."""
        middleware = RateLimitMiddleware(None)
        limits = middleware._get_limits("/health")
        assert limits is None

    def test_get_client_ip_forwarded(self):
        """Test extracting IP from X-Forwarded-For header."""
        middleware = RateLimitMiddleware(None)
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
        request.client = Mock(host="127.0.0.1")

        ip = middleware._get_client_ip(request)
        assert ip == "192.168.1.1"

    def test_get_client_ip_real_ip(self):
        """Test extracting IP from X-Real-IP header."""
        middleware = RateLimitMiddleware(None)
        request = Mock(spec=Request)
        request.headers = {"X-Real-IP": "192.168.1.100"}
        request.client = Mock(host="127.0.0.1")

        ip = middleware._get_client_ip(request)
        assert ip == "192.168.1.100"

    def test_get_client_ip_direct(self):
        """Test extracting direct client IP."""
        middleware = RateLimitMiddleware(None)
        request = Mock(spec=Request)
        request.headers = {}
        request.client = Mock(host="192.168.1.200")

        ip = middleware._get_client_ip(request)
        assert ip == "192.168.1.200"

    def test_check_memory_within_limit(self):
        """Test in-memory rate limiting within limit."""
        middleware = RateLimitMiddleware(None)
        now = time.time()

        allowed, remaining, reset = middleware._check_memory("test_key", now, 10, 60)

        assert allowed is True
        assert remaining == 9
        assert reset > now

    def test_check_memory_exceeds_limit(self):
        """Test in-memory rate limiting exceeds limit."""
        middleware = RateLimitMiddleware(None)
        now = time.time()

        # Fill up to limit
        for _ in range(10):
            middleware._check_memory("test_key_2", now, 10, 60)

        # 11th request should be denied
        allowed, remaining, reset = middleware._check_memory("test_key_2", now, 10, 60)

        assert allowed is False
        assert remaining == 0

    def test_check_memory_window_expiry(self):
        """Test requests outside window are removed."""
        middleware = RateLimitMiddleware(None)
        now = time.time()
        window = 60

        # Add requests in the past
        old_time = now - window - 1
        middleware._check_memory("test_key_3", old_time, 10, window)

        # Current request should be allowed (old one expired)
        allowed, remaining, reset = middleware._check_memory("test_key_3", now, 10, window)

        assert allowed is True
        assert remaining == 9  # Only current request counts

    def test_cleanup_memory(self):
        """Test cleanup of old entries."""
        middleware = RateLimitMiddleware(None)
        now = time.time()
        window = 60

        # Add old entries
        old_time = now - window * 3
        middleware._check_memory("old_key_1", old_time, 10, window)
        middleware._check_memory("old_key_2", old_time, 10, window)

        assert len(middleware.in_memory_store) == 2

        # Cleanup
        middleware._cleanup_memory(now, window)

        # Old empty keys should be removed
        assert len(middleware.in_memory_store) == 0
