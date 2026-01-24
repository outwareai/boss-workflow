"""
Metrics collection middleware.

Q3 2026: Custom middleware for tracking HTTP requests and response times.
"""
import time
import logging
from fastapi import Request
from .prometheus import (
    http_requests_total,
    http_request_duration
)

logger = logging.getLogger(__name__)


async def metrics_middleware(request: Request, call_next):
    """
    Collect HTTP metrics for all requests.

    Tracks:
    - Request counts by method, endpoint, status code
    - Request duration by method, endpoint
    """
    start_time = time.time()

    # Process request
    response = await call_next(request)

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

    return response


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
