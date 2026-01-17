"""
Repository classes for database operations.

Each repository handles CRUD and complex queries for its entity type.
"""

from .tasks import TaskRepository, get_task_repository
from .audit import AuditRepository, get_audit_repository
from .conversations import ConversationRepository, get_conversation_repository
from .ai_memory import AIMemoryRepository, get_ai_memory_repository
from .team import TeamRepository, get_team_repository
from .projects import ProjectRepository, get_project_repository

__all__ = [
    "TaskRepository",
    "get_task_repository",
    "AuditRepository",
    "get_audit_repository",
    "ConversationRepository",
    "get_conversation_repository",
    "AIMemoryRepository",
    "get_ai_memory_repository",
    "TeamRepository",
    "get_team_repository",
    "ProjectRepository",
    "get_project_repository",
]
