"""
Prometheus metrics for monitoring.

Q3 2026: Production hardening with observability.
"""
from prometheus_client import Counter, Histogram, Gauge, Info
import logging

logger = logging.getLogger(__name__)

# HTTP Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

# Task Metrics
tasks_created_total = Counter(
    'tasks_created_total',
    'Total tasks created',
    ['assignee', 'priority']
)

tasks_completed_total = Counter(
    'tasks_completed_total',
    'Total tasks completed',
    ['assignee']
)

tasks_by_status = Gauge(
    'tasks_by_status',
    'Current tasks by status',
    ['status']
)

# AI Metrics
ai_requests_total = Counter(
    'ai_requests_total',
    'Total AI API requests',
    ['operation', 'status']
)

ai_request_duration = Histogram(
    'ai_request_duration_seconds',
    'AI request duration',
    ['operation']
)

# Database Metrics
db_queries_total = Counter(
    'db_queries_total',
    'Total database queries',
    ['operation']
)

db_query_duration = Histogram(
    'db_query_duration_seconds',
    'Database query duration',
    ['operation']
)

db_pool_connections = Gauge(
    'db_pool_connections',
    'Database pool connections',
    ['state']  # checked_in, checked_out, overflow
)

# Cache Metrics
cache_operations_total = Counter(
    'cache_operations_total',
    'Total cache operations',
    ['operation', 'result']  # get/set, hit/miss
)

# Discord Metrics
discord_messages_sent = Counter(
    'discord_messages_sent_total',
    'Total Discord messages sent',
    ['channel', 'status']
)

# Error Metrics
errors_total = Counter(
    'errors_total',
    'Total errors',
    ['type', 'severity']
)

error_rate_current = Gauge(
    'error_rate_current',
    'Current error rate (errors per minute)',
    ['time_window']
)

# Rate Limiting Metrics (Q1 2026 - Slowapi production rollout)
rate_limit_violations_total = Counter(
    'rate_limit_violations_total',
    'Total rate limit violations by endpoint and limiter',
    ['endpoint', 'limiter', 'client_type']
)

rate_limit_near_limit = Gauge(
    'rate_limit_near_limit',
    'Number of clients approaching rate limit (80% of limit)',
    ['endpoint']
)

redis_connection_errors = Counter(
    'redis_connection_errors_total',
    'Total Redis connection errors for slowapi backend',
    ['operation']
)

redis_operation_duration_seconds = Histogram(
    'redis_operation_duration_seconds',
    'Redis operation duration in seconds',
    ['operation'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1)
)

# Feature Flag Metrics (Q1 2026)
feature_flag_status = Gauge(
    'feature_flag_status',
    'Current feature flag status (0=disabled, 1=enabled)',
    ['feature_name']
)

# System Info
app_info = Info('app', 'Application information')
app_info.info({
    'name': 'boss-workflow',
    'version': '2.5.0'
})


def update_db_pool_metrics(pool):
    """Update database pool connection metrics."""
    try:
        db_pool_connections.labels(state='checked_in').set(pool.checkedin())
        db_pool_connections.labels(state='checked_out').set(pool.checkedout())
        db_pool_connections.labels(state='overflow').set(pool.overflow())
    except Exception as e:
        logger.warning(f"Failed to update DB pool metrics: {e}")


def record_task_status_counts(status_counts: dict):
    """Update task status gauge from a dict of status counts."""
    for status, count in status_counts.items():
        tasks_by_status.labels(status=status).set(count)
