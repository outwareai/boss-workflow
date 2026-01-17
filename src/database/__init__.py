"""
PostgreSQL Database Module for Boss Workflow.

Handles:
- Task storage with relationships (subtasks, dependencies, blocked-by, projects)
- Conversation history
- Audit logs
- AI context memory
- Team member data

Syncs with Google Sheets for boss visibility.
"""

from .connection import (
    get_database,
    Database,
    init_database,
    close_database,
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
