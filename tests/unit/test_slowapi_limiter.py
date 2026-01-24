"""Tests for slowapi rate limiting."""
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from src.middleware.slowapi_limiter import setup_rate_limiting, create_limiter
from slowapi.errors import RateLimitExceeded
from unittest.mock import Mock, MagicMock


def test_create_limiter_with_redis():
    """Test limiter creation with Redis backend."""
    limiter = create_limiter("redis://localhost:6379")
    assert limiter is not None
    assert limiter.enabled == True


def test_create_limiter_without_redis():
    """Test limiter creation without Redis (in-memory)."""
    limiter = create_limiter(None)
    assert limiter is not None


def test_setup_rate_limiting():
    """Test setup_rate_limiting configures app correctly."""
    app = FastAPI()
    limiter = setup_rate_limiting(app, None)

    # Check limiter is attached to app state
    assert hasattr(app.state, "limiter")
    assert app.state.limiter == limiter

    # Check exception handler is registered
    assert RateLimitExceeded in app.exception_handlers


def test_limiter_enabled_by_default():
    """Test that limiter is enabled by default."""
    limiter = create_limiter(None)
    assert limiter.enabled == True


def test_limiter_has_default_limits():
    """Test that limiter has default limits configured."""
    limiter = create_limiter(None)
    # Slowapi stores limits in _default_limits
    assert hasattr(limiter, '_default_limits')
    assert len(limiter._default_limits) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
