"""
PostgreSQL Database Module for Boss Workflow.

Handles:
- Task storage with relationships (subtasks, dependencies, blocked-by, projects)
- Conversation history
- Audit logs
- AI context memory
- Team member data

Syncs with Google Sheets for boss visibility.

Q3 2026: Enhanced with connection pooling and health monitoring.
"""

from .connection import (
    get_database,
    Database,
    init_database,
    close_database,
    get_pool_status,
    check_pool_health,
    get_session,
)
from .health import (
    check_connection_leaks,
    get_detailed_health_report,
)
from .models import (
    Base,
    TaskDB,
    ProjectDB,
    SubtaskDB,
    TaskDependencyDB,
    AuditLogDB,
    ConversationDB,
    MessageDB,
    AIMemoryDB,
    TeamMemberDB,
    WebhookEventDB,
)

__all__ = [
    "get_database",
    "Database",
    "init_database",
    "close_database",
    "get_pool_status",
    "check_pool_health",
    "get_session",
    "check_connection_leaks",
    "get_detailed_health_report",
    "Base",
    "TaskDB",
    "ProjectDB",
    "SubtaskDB",
    "TaskDependencyDB",
    "AuditLogDB",
    "ConversationDB",
    "MessageDB",
    "AIMemoryDB",
    "TeamMemberDB",
    "WebhookEventDB",
]
