"""Performance monitoring and tracking.

Q3 2026 Phase 4: Response time tracking and slow query detection.
"""
import logging
import time
from functools import wraps
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Import Prometheus metrics
try:
    from .prometheus import (
        http_request_duration,
        db_query_duration
    )
    METRICS_ENABLED = True
except ImportError:
    METRICS_ENABLED = False


class PerformanceTracker:
    """Track performance metrics for requests and queries."""

    def __init__(self):
        self.slow_query_threshold = 0.1  # 100ms
        self.slow_request_threshold = 1.0  # 1 second

    def track_request(self, func):
        """Decorator to track request performance.

        Usage:
            @perf_tracker.track_request
            async def my_endpoint():
                ...
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start

                # Record metric
                if METRICS_ENABLED:
                    http_request_duration.labels(
                        method=func.__name__,
                        endpoint=func.__name__
                    ).observe(duration)

                # Log slow requests
                if duration > self.slow_request_threshold:
                    logger.warning(
                        f"Slow request: {func.__name__} took {duration:.2f}s"
                    )

                return result
            except Exception as e:
                duration = time.time() - start
                logger.error(f"Request failed after {duration:.2f}s: {e}")
                raise

        return wrapper

    def track_query(self, operation: str):
        """Decorator to track database query performance.

        Usage:
            @perf_tracker.track_query("get_by_id")
            async def get_by_id(self, task_id: str):
                ...
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start = time.time()

                try:
                    result = await func(*args, **kwargs)
                    duration = time.time() - start

                    # Record metric
                    if METRICS_ENABLED:
                        db_query_duration.labels(operation=operation).observe(duration)

                    # Log slow queries
                    if duration > self.slow_query_threshold:
                        logger.warning(
                            f"Slow query: {operation} took {duration:.2f}s"
                        )

                    return result
                except Exception as e:
                    duration = time.time() - start
                    logger.error(f"Query failed after {duration:.2f}s: {e}")
                    raise

            return wrapper
        return decorator


# Global tracker
perf_tracker = PerformanceTracker()
