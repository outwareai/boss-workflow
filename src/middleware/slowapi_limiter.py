"""
Slowapi-based rate limiting middleware.

Q1 2026: Alternative rate limiting using slowapi library.
Can be toggled via USE_SLOWAPI_RATE_LIMITING config flag.
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
import logging

logger = logging.getLogger(__name__)


def get_request_identifier(request: Request) -> str:
    """
    Get unique identifier for rate limiting.

    Priority:
    1. API key from header (for authenticated requests)
    2. User ID from session (if SessionMiddleware is enabled)
    3. IP address (fallback)
    """
    # Check for API key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"api_key:{api_key}"

    # Check for user session (only if SessionMiddleware is installed)
    try:
        if "session" in request.scope:
            user_id = request.session.get("user_id")
            if user_id:
                return f"user:{user_id}"
    except (AttributeError, AssertionError):
        # SessionMiddleware not installed or session not available
        pass

    # Fallback to IP
    return get_remote_address(request)


def create_limiter(redis_url: str = None):
    """
    Create and configure slowapi Limiter.

    Args:
        redis_url: Redis connection URL for distributed rate limiting

    Returns:
        Configured Limiter instance
    """
    if redis_url:
        # Use Redis for distributed rate limiting
        limiter = Limiter(
            key_func=get_request_identifier,
            storage_uri=redis_url,
            default_limits=["20/minute"],  # Public default
            headers_enabled=True,
        )
        logger.info("Rate limiting configured with Redis backend")
    else:
        # Use in-memory storage (single instance only)
        limiter = Limiter(
            key_func=get_request_identifier,
            default_limits=["20/minute"],
            headers_enabled=True,
        )
        logger.warning("Rate limiting using in-memory storage (not distributed)")

    return limiter


def setup_rate_limiting(app, redis_url: str = None):
    """
    Setup slowapi rate limiting on FastAPI app.

    Args:
        app: FastAPI application instance
        redis_url: Redis connection URL
    """
    limiter = create_limiter(redis_url)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Set feature flag metric
    try:
        from ..monitoring import feature_flag_status
        feature_flag_status.labels(feature_name="slowapi_rate_limiting").set(1)
    except ImportError:
        logger.warning("Monitoring module not available for metrics")
    except Exception as e:
        logger.warning(f"Failed to set feature flag metric: {e}")

    logger.info("Slowapi rate limiting enabled")
    return limiter
