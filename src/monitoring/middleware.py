"""
Metrics collection middleware.

Q3 2026: Custom middleware for tracking HTTP requests and response times.
"""
import time
import logging
from fastapi import Request
from .prometheus import (
    http_requests_total,
    http_request_duration,
    errors_total,
    error_rate_current
)

logger = logging.getLogger(__name__)


async def metrics_middleware(request: Request, call_next):
    """
    Collect HTTP metrics for all requests.

    Tracks:
    - Request counts by method, endpoint, status code
    - Request duration by method, endpoint
    - Error rates and spike detection
    """
    start_time = time.time()

    try:
        # Process request
        response = await call_next(request)
    except Exception as e:
        # Record error metrics
        await _record_error_metrics(request, e)
        raise

    # Record metrics
    duration = time.time() - start_time

    # Normalize endpoint path (replace IDs with placeholders)
    path = request.url.path
    normalized_path = normalize_endpoint(path)

    http_requests_total.labels(
        method=request.method,
        endpoint=normalized_path,
        status=response.status_code
    ).inc()

    http_request_duration.labels(
        method=request.method,
        endpoint=normalized_path
    ).observe(duration)

    # Record error if status code indicates error (5xx or 4xx)
    if response.status_code >= 400:
        await _record_error_metrics(request, None, response.status_code)

    # Update current error rate gauge
    try:
        from .error_spike_detector import detector
        metrics = detector.get_current_metrics()
        error_rate_current.labels(time_window="5m").set(metrics["current_rate"])
    except Exception as e:
        logger.debug(f"Failed to update error rate gauge: {e}")

    return response


async def _record_error_metrics(request: Request, exception: Exception = None, status_code: int = None):
    """
    Record error in Prometheus metrics and spike detector.

    Args:
        request: FastAPI request object
        exception: Exception that occurred, if any
        status_code: HTTP status code, if applicable
    """
    try:
        # Determine error type and severity
        error_type = "http_error"
        severity = "unknown"

        if exception:
            error_type = type(exception).__name__
            severity = "critical"
        elif status_code:
            if 400 <= status_code < 500:
                error_type = "http_4xx"
                severity = "warning"
            elif 500 <= status_code < 600:
                error_type = "http_5xx"
                severity = "critical"

        # Record in Prometheus
        errors_total.labels(type=error_type, severity=severity).inc()

        # Record in error spike detector
        from .error_spike_detector import detector
        await detector.record_error()

    except Exception as e:
        logger.warning(f"Failed to record error metrics: {e}")


def normalize_endpoint(path: str) -> str:
    """
    Normalize endpoint paths to reduce cardinality.

    Examples:
    - /api/db/tasks/TASK-123 -> /api/db/tasks/{task_id}
    - /api/db/audit/TASK-456 -> /api/db/audit/{task_id}
    """
    parts = path.split('/')

    # Replace task IDs
    normalized = []
    for i, part in enumerate(parts):
        if part.startswith('TASK-'):
            normalized.append('{task_id}')
        elif part.isdigit() and len(part) > 3:  # Likely an ID
            normalized.append('{id}')
        else:
            normalized.append(part)

    return '/'.join(normalized)
