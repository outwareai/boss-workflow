"""
SQLAlchemy models for PostgreSQL database.

Schema includes:
- Tasks with full relationship support
- Projects for grouping tasks
- Subtasks for breaking down work
- Dependencies (blocked-by, depends-on)
- Audit logs for all changes
- Conversation history
- AI memory per user
- Team members
- Webhook events
"""

from datetime import datetime, date
from typing import Optional, List, Dict
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Boolean,
    DateTime,
    Date,
    Float,
    ForeignKey,
    Enum as SQLEnum,
    JSON,
    Index,
    UniqueConstraint,
    Table,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.sql import func
import enum


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# ==================== ENUMS ====================

class TaskPriorityEnum(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatusEnum(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    AWAITING_VALIDATION = "awaiting_validation"
    NEEDS_REVISION = "needs_revision"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    DELAYED = "delayed"
    UNDONE = "undone"
    ON_HOLD = "on_hold"
    WAITING = "waiting"
    NEEDS_INFO = "needs_info"
    OVERDUE = "overdue"


class DependencyTypeEnum(str, enum.Enum):
    BLOCKS = "blocks"           # This task blocks another
    BLOCKED_BY = "blocked_by"   # This task is blocked by another
    DEPENDS_ON = "depends_on"   # Must complete after another
    REQUIRED_BY = "required_by" # Another task needs this first


class AuditActionEnum(str, enum.Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    PRIORITY_CHANGED = "priority_changed"
    DEADLINE_CHANGED = "deadline_changed"
    NOTE_ADDED = "note_added"
    PROOF_SUBMITTED = "proof_submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    DELAYED = "delayed"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"
    SUBTASK_ADDED = "subtask_added"
    SUBTASK_COMPLETED = "subtask_completed"
    DEPENDENCY_ADDED = "dependency_added"
    DEPENDENCY_REMOVED = "dependency_removed"
    PROJECT_ASSIGNED = "project_assigned"
    SYNCED_TO_SHEETS = "synced_to_sheets"


class MessageRoleEnum(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AttendanceEventTypeEnum(str, enum.Enum):
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"
    BREAK_START = "break_start"
    BREAK_END = "break_end"
    # Boss-reported attendance events
    ABSENCE_REPORTED = "absence_reported"
    LATE_REPORTED = "late_reported"
    EARLY_DEPARTURE_REPORTED = "early_departure_reported"
    SICK_LEAVE_REPORTED = "sick_leave_reported"
    EXCUSED_ABSENCE_REPORTED = "excused_absence_reported"


# ==================== PROJECTS ====================

class ProjectDB(Base):
    """Projects for grouping related tasks."""
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, completed, archived
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # For UI

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    tasks: Mapped[List["TaskDB"]] = relationship("TaskDB", back_populates="project")

    __table_args__ = (
        Index("idx_projects_status", "status"),
        Index("idx_projects_name", "name"),
    )


# ==================== TASKS ====================

class TaskDB(Base):
    """Main task table with full metadata."""
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # TASK-YYYYMMDD-XXX

    # Core fields
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Classification
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    task_type: Mapped[str] = mapped_column(String(50), default="task")  # task, bug, feature, research

    # Assignment
    assignee: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    assignee_telegram_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    assignee_discord_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    assignee_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timing
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    original_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Effort and progress
    estimated_effort: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100

    # Metadata
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Comma-separated
    acceptance_criteria: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)  # List of criteria
    notes: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)  # List of notes

    # Delay tracking
    delay_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delayed_count: Mapped[int] = mapped_column(Integer, default=0)

    # Validation
    requires_validation: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_validation_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Origin
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    original_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Integration IDs
    discord_message_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sheets_row_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    calendar_event_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Project relationship
    project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True)
    project: Mapped[Optional["ProjectDB"]] = relationship("ProjectDB", back_populates="tasks")

    # Self-referential for parent task (for subtasks stored as tasks)
    parent_task_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=True)
    parent_task: Mapped[Optional["TaskDB"]] = relationship("TaskDB", remote_side=[id], backref="child_tasks")

    # Relationships
    subtasks: Mapped[List["SubtaskDB"]] = relationship("SubtaskDB", back_populates="task", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLogDB"]] = relationship("AuditLogDB", back_populates="task", cascade="all, delete-orphan")

    # Dependencies (tasks this one depends on)
    dependencies_out: Mapped[List["TaskDependencyDB"]] = relationship(
        "TaskDependencyDB",
        foreign_keys="TaskDependencyDB.task_id",
        back_populates="task",
        cascade="all, delete-orphan"
    )
    # Tasks that depend on this one
    dependencies_in: Mapped[List["TaskDependencyDB"]] = relationship(
        "TaskDependencyDB",
        foreign_keys="TaskDependencyDB.depends_on_id",
        back_populates="depends_on_task",
        cascade="all, delete-orphan"
    )

    # Sync tracking
    last_synced_to_sheets: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    needs_sheet_sync: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_priority", "priority"),
        Index("idx_tasks_assignee", "assignee"),
        Index("idx_tasks_deadline", "deadline"),
        Index("idx_tasks_project", "project_id"),
        Index("idx_tasks_created", "created_at"),
        Index("idx_tasks_needs_sync", "needs_sheet_sync"),
    )


# ==================== SUBTASKS ====================

class SubtaskDB(Base):
    """Subtasks for breaking down larger tasks."""
    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    order: Mapped[int] = mapped_column(Integer, default=0)  # For ordering subtasks

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationship
    task: Mapped["TaskDB"] = relationship("TaskDB", back_populates="subtasks")

    __table_args__ = (
        Index("idx_subtasks_task", "task_id"),
        Index("idx_subtasks_completed", "completed"),
    )


# ==================== TASK DEPENDENCIES ====================

class TaskDependencyDB(Base):
    """Task dependencies and blocked-by relationships."""
    __tablename__ = "task_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    depends_on_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)

    dependency_type: Mapped[str] = mapped_column(String(30), default="depends_on")
    # Types: blocks, blocked_by, depends_on, required_by

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    task: Mapped["TaskDB"] = relationship("TaskDB", foreign_keys=[task_id], back_populates="dependencies_out")
    depends_on_task: Mapped["TaskDB"] = relationship("TaskDB", foreign_keys=[depends_on_id], back_populates="dependencies_in")

    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_id", "dependency_type", name="uq_task_dependency"),
        Index("idx_deps_task", "task_id"),
        Index("idx_deps_depends_on", "depends_on_id"),
    )


# ==================== AUDIT LOGS ====================

class AuditLogDB(Base):
    """Audit trail for all task changes."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # What changed
    task_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=True)
    task_ref: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # TASK-XXX for reference
    entity_type: Mapped[str] = mapped_column(String(50), default="task")  # task, project, team_member, etc.
    entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # The change
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    field_changed: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Who and when
    changed_by: Mapped[str] = mapped_column(String(100), nullable=False)
    changed_by_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Telegram/Discord ID
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Context
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="telegram")  # telegram, discord, api, scheduler
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # Full snapshot (optional)
    snapshot: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Relationship
    task: Mapped[Optional["TaskDB"]] = relationship("TaskDB", back_populates="audit_logs")

    __table_args__ = (
        Index("idx_audit_task", "task_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_changed_by", "changed_by"),
        Index("idx_audit_entity", "entity_type", "entity_id"),
    )


# ==================== CONVERSATIONS ====================

class ConversationDB(Base):
    """Conversation sessions with full history."""
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    chat_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Conversation state
    stage: Mapped[str] = mapped_column(String(50), default="initial")
    intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Context data
    context: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    generated_spec: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Result
    task_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # If resulted in task
    outcome: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # completed, cancelled, timeout

    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Messages
    messages: Mapped[List["MessageDB"]] = relationship("MessageDB", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_conv_user", "user_id"),
        Index("idx_conv_created", "created_at"),
        Index("idx_conv_stage", "stage"),
    )


class MessageDB(Base):
    """Individual messages in a conversation."""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id"), nullable=False)

    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Metadata
    message_type: Mapped[str] = mapped_column(String(30), default="text")  # text, photo, voice, document
    file_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # AI processing
    intent_detected: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Integer, nullable=True)  # Stored as int (0-100)

    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationship
    conversation: Mapped["ConversationDB"] = relationship("ConversationDB", back_populates="messages")

    __table_args__ = (
        Index("idx_msg_conv", "conversation_id"),
        Index("idx_msg_timestamp", "timestamp"),
    )


# ==================== AI MEMORY ====================

class AIMemoryDB(Base):
    """Persistent AI context memory per user."""
    __tablename__ = "ai_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # User preferences (from /teach and learning)
    preferences: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Team knowledge
    team_knowledge: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Custom triggers (ASAP -> 4 hours, etc.)
    custom_triggers: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Learned patterns (what user usually does)
    learned_patterns: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Recent context for continuity
    recent_context: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Stats
    total_tasks_created: Mapped[int] = mapped_column(Integer, default=0)
    total_conversations: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_memory_user", "user_id"),
    )


# ==================== TEAM MEMBERS ====================

class TeamMemberDB(Base):
    """Team member registry."""
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Contact IDs
    telegram_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    discord_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    discord_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Role and skills
    role: Mapped[str] = mapped_column(String(100), default="developer")
    skills: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)  # List of skills
    default_task_types: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Stats
    tasks_assigned: Mapped[int] = mapped_column(Integer, default=0)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_team_name", "name"),
        Index("idx_team_telegram", "telegram_id"),
        Index("idx_team_discord", "discord_id"),
        Index("idx_team_active", "is_active"),
    )


# ==================== RECURRING TASKS ====================

class RecurringTaskDB(Base):
    """Templates for recurring tasks."""
    __tablename__ = "recurring_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recurring_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # REC-YYYYMMDD-XXX

    # Task template
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assignee: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    task_type: Mapped[str] = mapped_column(String(50), default="task")
    estimated_effort: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Schedule
    pattern: Mapped[str] = mapped_column(String(100), nullable=False)  # every:monday, every:day, etc.
    time: Mapped[str] = mapped_column(String(10), nullable=False)  # 09:00, 18:30
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Bangkok")

    # Control
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_run: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Stats
    instances_created: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_recurring_active", "is_active"),
        Index("idx_recurring_next_run", "next_run"),
    )


# ==================== TIME TRACKING ====================

class TimeEntryDB(Base):
    """Individual time tracking entries."""
    __tablename__ = "time_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # TIME-YYYYMMDD-XXX

    # Links
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Time data
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)

    # Entry type
    entry_type: Mapped[str] = mapped_column(String(20), default="timer")  # timer, manual
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    task: Mapped["TaskDB"] = relationship("TaskDB", backref="time_entries")

    __table_args__ = (
        Index("idx_time_task", "task_id"),
        Index("idx_time_user", "user_id"),
        Index("idx_time_running", "is_running"),
        Index("idx_time_started", "started_at"),
    )


class ActiveTimerDB(Base):
    """Track currently running timer per user (only one allowed)."""
    __tablename__ = "active_timers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    time_entry_id: Mapped[int] = mapped_column(Integer, ForeignKey("time_entries.id"), nullable=False)
    task_ref: Mapped[str] = mapped_column(String(50), nullable=False)  # TASK-XXX for quick reference
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationship
    time_entry: Mapped["TimeEntryDB"] = relationship("TimeEntryDB")

    __table_args__ = (
        Index("idx_active_user", "user_id"),
    )


# ==================== ATTENDANCE RECORDS ====================

class AttendanceRecordDB(Base):
    """Attendance records for time clock system."""
    __tablename__ = "attendance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # ATT-YYYYMMDD-XXX

    # User info
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)  # Discord user ID
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Event details
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)  # clock_in, clock_out, break_start, break_end
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # Local time
    event_time_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # UTC for calculations

    # Channel info
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(50), nullable=False)  # dev/admin

    # Late tracking
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    expected_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Sync tracking
    synced_to_sheets: Mapped[bool] = mapped_column(Boolean, default=False)

    # Boss-reported attendance fields
    is_boss_reported: Mapped[bool] = mapped_column(Boolean, default=False)
    reported_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reported_by_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    affected_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_attendance_user", "user_id"),
        Index("idx_attendance_type", "event_type"),
        Index("idx_attendance_time", "event_time"),
        Index("idx_attendance_channel", "channel_id"),
        Index("idx_attendance_synced", "synced_to_sheets"),
        Index("idx_attendance_date", "event_time"),  # For daily queries
        Index("idx_attendance_boss_reported", "is_boss_reported"),
    )


# ==================== WEBHOOK EVENTS ====================

class WebhookEventDB(Base):
    """Webhook event log for debugging and replay."""
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    source: Mapped[str] = mapped_column(String(30), nullable=False)  # telegram, discord
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Raw payload
    payload: Mapped[str] = mapped_column(JSON, nullable=False)

    # Processing status
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_webhook_source", "source"),
        Index("idx_webhook_processed", "processed"),
        Index("idx_webhook_received", "received_at"),
    )


# ==================== OAUTH TOKENS ====================

class OAuthTokenDB(Base):
    """
    Store OAuth tokens for user-level Google integrations.

    Used for:
    - Google Calendar (create events on user's personal calendar)
    - Google Tasks (create tasks in user's personal task list)
    """
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # User identification (by email since that's consistent across platforms)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=False)

    # Service type: 'calendar', 'tasks'
    service: Mapped[str] = mapped_column(String(50), nullable=False)

    # OAuth tokens (encrypted in production)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(50), default="Bearer")

    # Token expiry
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Metadata
    scopes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Space-separated scopes

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("email", "service", name="uq_oauth_email_service"),
        Index("idx_oauth_email", "email"),
        Index("idx_oauth_service", "service"),
    )


# ==================== STAFF TASK CONTEXT ====================

class StaffTaskContextDB(Base):
    """
    Per-task conversation context for Staff AI Assistant.

    Persists:
    - Conversation history between staff and AI
    - Task context and details
    - Escalation history
    - Submission attempts
    """
    __tablename__ = "staff_task_contexts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # TASK-YYYYMMDD-XXX

    # Task details snapshot (for quick access without DB lookup)
    task_details: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Staff info
    staff_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Discord user ID
    staff_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Discord linking
    channel_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    thread_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, closed

    # Submission tracking
    submission_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_submission: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    last_activity: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    messages: Mapped[List["StaffContextMessageDB"]] = relationship(
        "StaffContextMessageDB", back_populates="context", cascade="all, delete-orphan"
    )
    escalations: Mapped[List["StaffEscalationDB"]] = relationship(
        "StaffEscalationDB", back_populates="context", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_staff_ctx_task", "task_id"),
        Index("idx_staff_ctx_staff", "staff_id"),
        Index("idx_staff_ctx_channel", "channel_id"),
        Index("idx_staff_ctx_thread", "thread_id"),
        Index("idx_staff_ctx_status", "status"),
        Index("idx_staff_ctx_activity", "last_activity"),
    )


class StaffContextMessageDB(Base):
    """Individual messages in a staff-AI conversation."""
    __tablename__ = "staff_context_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    context_id: Mapped[int] = mapped_column(Integer, ForeignKey("staff_task_contexts.id"), nullable=False)

    role: Mapped[str] = mapped_column(String(20), nullable=False)  # staff, assistant, boss
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Message metadata (attachments, message_url, action)
    message_metadata: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationship
    context: Mapped["StaffTaskContextDB"] = relationship("StaffTaskContextDB", back_populates="messages")

    __table_args__ = (
        Index("idx_staff_msg_ctx", "context_id"),
        Index("idx_staff_msg_time", "timestamp"),
    )


class StaffEscalationDB(Base):
    """Escalation records from staff to boss."""
    __tablename__ = "staff_escalations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    context_id: Mapped[int] = mapped_column(Integer, ForeignKey("staff_task_contexts.id"), nullable=False)

    # Escalation details
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    staff_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Boss response tracking
    boss_responded: Mapped[bool] = mapped_column(Boolean, default=False)
    boss_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    boss_response_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Telegram message tracking for boss reply routing
    telegram_message_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationship
    context: Mapped["StaffTaskContextDB"] = relationship("StaffTaskContextDB", back_populates="escalations")

    __table_args__ = (
        Index("idx_staff_esc_ctx", "context_id"),
        Index("idx_staff_esc_responded", "boss_responded"),
        Index("idx_staff_esc_telegram", "telegram_message_id"),
    )


# ==================== DISCORD THREAD TASK LINKS ====================

class DiscordThreadTaskLinkDB(Base):
    """
    Links Discord threads to tasks for automatic task identification.

    When a task is posted to Discord and a thread is created,
    this table maps thread_id → task_id for seamless staff conversations.
    """
    __tablename__ = "discord_thread_task_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Discord info
    thread_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(100), nullable=False)
    message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Original task message

    # Task info
    task_id: Mapped[str] = mapped_column(String(50), nullable=False)  # TASK-YYYYMMDD-XXX

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index("idx_thread_link_thread", "thread_id"),
        Index("idx_thread_link_task", "task_id"),
        Index("idx_thread_link_channel", "channel_id"),
    )


# ==================== UNDO HISTORY ====================

class UndoHistoryDB(Base):
    """
    Undo/redo history for reversible actions.

    Supports multi-level undo/redo with full audit trail integration.
    Stores complete context needed to reverse any operation.
    """
    __tablename__ = "undo_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # User identification
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Action details
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)  # delete_task, change_status, etc.
    action_data: Mapped[Dict] = mapped_column(JSON, nullable=False)  # Original action params

    # Undo details
    undo_function: Mapped[str] = mapped_column(String(100), nullable=False)  # Function to call for undo
    undo_data: Mapped[Dict] = mapped_column(JSON, nullable=False)  # Data needed for undo

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Human-readable description
    extra_metadata: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)  # Additional context

    # Status tracking
    is_undone: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    undo_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_undo_history_user", "user_id"),
        Index("idx_undo_history_timestamp", "timestamp"),
        Index("idx_undo_history_user_time", "user_id", "timestamp"),
        Index("idx_undo_history_action_type", "action_type"),
    )


# ==================== PLANNING SYSTEM (v3.0) ====================

class PlanningStateEnum(str, enum.Enum):
    """Planning session states"""
    INITIATED = "initiated"
    GATHERING_INFO = "gathering_info"
    AI_ANALYZING = "ai_analyzing"
    REVIEWING_BREAKDOWN = "reviewing_breakdown"
    REFINING = "refining"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProjectComplexityEnum(str, enum.Enum):
    """Project complexity levels"""
    SIMPLE = "simple"              # 1-3 tasks, <8 hours
    MODERATE = "moderate"          # 4-7 tasks, 8-40 hours
    COMPLEX = "complex"            # 8-15 tasks, 40-160 hours
    VERY_COMPLEX = "very_complex"  # 16+ tasks, >160 hours


class PlanningSessionDB(Base):
    """Planning sessions with AI-powered task breakdown"""
    __tablename__ = "planning_sessions"

    # Primary identifiers
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("conversations.conversation_id"), nullable=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # Session metadata
    state: Mapped[str] = mapped_column(String(50), default="initiated", nullable=False)
    project_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    project_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_project_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    detection_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # AI analysis results
    complexity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    estimated_duration_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    suggested_team_members: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    applied_template_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Planning data
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    clarifying_questions: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    ai_breakdown: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    user_edits: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Finalization
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_project_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_task_ids: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    conversation: Mapped[Optional["ConversationDB"]] = relationship("ConversationDB", foreign_keys=[conversation_id])
    task_drafts: Mapped[List["TaskDraftDB"]] = relationship("TaskDraftDB", back_populates="planning_session", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_planning_user_state", "user_id", "state"),
        Index("idx_planning_created", "created_at"),
        Index("idx_planning_project", "detected_project_id"),
        Index("idx_planning_activity", "last_activity_at"),
    )


class TaskDraftDB(Base):
    """Task drafts within planning sessions"""
    __tablename__ = "task_drafts"

    # Primary identifiers
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(50), ForeignKey("planning_sessions.session_id"), nullable=False)

    # Task details
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    priority: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Assignment
    assigned_to: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    estimated_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Dependencies
    depends_on: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    blocking: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # AI metadata
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_modified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Order
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Finalization
    created_task_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("tasks.task_id"), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    planning_session: Mapped["PlanningSessionDB"] = relationship("PlanningSessionDB", back_populates="task_drafts")
    created_task: Mapped[Optional["TaskDB"]] = relationship("TaskDB", foreign_keys=[created_task_id])

    __table_args__ = (
        Index("idx_draft_session", "session_id"),
        Index("idx_draft_order", "session_id", "sequence_order"),
        Index("idx_draft_created_task", "created_task_id"),
    )


class ProjectMemoryDB(Base):
    """AI-extracted patterns and learnings from completed projects"""
    __tablename__ = "project_memory"

    # Primary identifier
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # Pattern extraction (AI-powered)
    common_challenges: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    success_patterns: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    team_insights: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    estimated_vs_actual: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    bottleneck_patterns: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    recommended_templates: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Learning metadata
    pattern_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    analysis_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_memory_project", "project_id"),
        Index("idx_memory_analyzed", "last_analyzed_at"),
        Index("idx_memory_confidence", "pattern_confidence"),
    )


class ProjectDecisionDB(Base):
    """Key decisions made during project planning and execution"""
    __tablename__ = "project_decisions"

    # Primary identifier
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(50), nullable=False)
    planning_session_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("planning_sessions.session_id"), nullable=True)

    # Decision details
    decision_type: Mapped[str] = mapped_column(String(50), nullable=False)
    decision_text: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alternatives_considered: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Context
    made_by: Mapped[str] = mapped_column(String(100), nullable=False)
    context: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Impact tracking
    impact_assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    decided_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    planning_session: Mapped[Optional["PlanningSessionDB"]] = relationship("PlanningSessionDB", foreign_keys=[planning_session_id])

    __table_args__ = (
        Index("idx_decision_project", "project_id"),
        Index("idx_decision_type", "decision_type"),
        Index("idx_decision_date", "decided_at"),
        Index("idx_decision_session", "planning_session_id"),
    )


class KeyDiscussionDB(Base):
    """Important discussions extracted and summarized by AI"""
    __tablename__ = "key_discussions"

    # Primary identifier
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discussion_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(50), nullable=False)
    planning_session_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("planning_sessions.session_id"), nullable=True)

    # Discussion content
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Messages
    message_ids: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    participant_ids: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # AI extraction
    extracted_decisions: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    extracted_action_items: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Importance
    importance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Timestamps
    occurred_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    summarized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    planning_session: Mapped[Optional["PlanningSessionDB"]] = relationship("PlanningSessionDB", foreign_keys=[planning_session_id])

    __table_args__ = (
        Index("idx_discussion_project", "project_id"),
        Index("idx_discussion_importance", "importance_score"),
        Index("idx_discussion_date", "occurred_at"),
        Index("idx_discussion_session", "planning_session_id"),
    )


class PlanningTemplateDB(Base):
    """Reusable planning templates for common project types"""
    __tablename__ = "planning_templates"

    # Primary identifier
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Template metadata
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Template structure
    task_template: Mapped[str] = mapped_column(JSON, nullable=False)
    clarifying_questions: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    team_suggestions: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    # Learning metadata
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_project_ids: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Versioning
    version: Mapped[str] = mapped_column(String(20), default="1.0", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_template_category", "category"),
        Index("idx_template_active", "active"),
        Index("idx_template_usage", "usage_count"),
        Index("idx_template_success", "success_rate"),
    )
