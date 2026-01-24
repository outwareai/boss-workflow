"""
Monitoring module for Prometheus metrics and Grafana dashboards.

Q3 2026: Production observability infrastructure.
"""
from .prometheus import (
    http_requests_total,
    http_request_duration,
    tasks_created_total,
    tasks_completed_total,
    tasks_by_status,
    ai_requests_total,
    ai_request_duration,
    db_queries_total,
    db_query_duration,
    db_pool_connections,
    cache_operations_total,
    discord_messages_sent,
    errors_total,
    update_db_pool_metrics,
    record_task_status_counts,
)

from .middleware import metrics_middleware

__all__ = [
    'http_requests_total',
    'http_request_duration',
    'tasks_created_total',
    'tasks_completed_total',
    'tasks_by_status',
    'ai_requests_total',
    'ai_request_duration',
    'db_queries_total',
    'db_query_duration',
    'db_pool_connections',
    'cache_operations_total',
    'discord_messages_sent',
    'errors_total',
    'update_db_pool_metrics',
    'record_task_status_counts',
    'metrics_middleware',
]
