"""
Repository classes for database operations.

Each repository handles CRUD and complex queries for its entity type.

Q3 2026: Added cached repository variants for performance.
"""

from .tasks import TaskRepository, get_task_repository
from .tasks_cached import CachedTaskRepository, get_cached_task_repository
from .audit import AuditRepository, get_audit_repository
from .conversations import ConversationRepository, get_conversation_repository
from .ai_memory import AIMemoryRepository, get_ai_memory_repository
from .team import TeamRepository, get_team_repository
from .projects import ProjectRepository, get_project_repository
from .attendance import AttendanceRepository, get_attendance_repository
from .oauth import OAuthTokenRepository, get_oauth_repository
from .staff_context import StaffContextRepository, get_staff_context_repository
from .planning import PlanningRepository, TaskDraftRepository, get_planning_repository, get_task_draft_repository
from .memory import MemoryRepository, DecisionRepository, DiscussionRepository, get_memory_repository, get_decision_repository, get_discussion_repository
from .templates import TemplateRepository, get_template_repository

__all__ = [
    "TaskRepository",
    "get_task_repository",
    "CachedTaskRepository",
    "get_cached_task_repository",
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
    "AttendanceRepository",
    "get_attendance_repository",
    "OAuthTokenRepository",
    "get_oauth_repository",
    "StaffContextRepository",
    "get_staff_context_repository",
    "PlanningRepository",
    "get_planning_repository",
    "TaskDraftRepository",
    "get_task_draft_repository",
    "MemoryRepository",
    "get_memory_repository",
    "DecisionRepository",
    "get_decision_repository",
    "DiscussionRepository",
    "get_discussion_repository",
    "TemplateRepository",
    "get_template_repository",
]
