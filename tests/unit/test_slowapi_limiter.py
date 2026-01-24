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


def test_rate_limit_exception_handler():
    """Test custom exception handler for rate limit exceeded."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    setup_rate_limiting(app, None)

    # Verify handler is registered
    assert RateLimitExceeded in app.exception_handlers


def test_metrics_initialization():
    """Test that Prometheus metrics are initialized for rate limiting."""
    try:
        from src.monitoring import (
            rate_limit_violations_total,
            rate_limit_near_limit,
            redis_connection_errors,
            redis_operation_duration_seconds,
            feature_flag_status
        )
        # If imports succeed, metrics are available
        assert rate_limit_violations_total is not None
        assert rate_limit_near_limit is not None
        assert redis_connection_errors is not None
        assert redis_operation_duration_seconds is not None
        assert feature_flag_status is not None
    except ImportError:
        pytest.skip("Monitoring module not available")


def test_feature_flag_metric():
    """Test that slowapi feature flag metric can be set."""
    try:
        from src.monitoring import feature_flag_status

        # This should not raise an exception
        feature_flag_status.labels(feature_name="slowapi_rate_limiting").set(1)
        feature_flag_status.labels(feature_name="slowapi_rate_limiting").set(0)
    except ImportError:
        pytest.skip("Monitoring module not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
