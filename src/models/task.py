"""Task data model for the workflow system."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
import uuid


class TaskPriority(str, Enum):
    """Task priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(str, Enum):
    """Task status states with expanded expressions."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    AWAITING_VALIDATION = "awaiting_validation"  # Submitted for boss review
    NEEDS_REVISION = "needs_revision"            # Rejected, needs changes
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    DELAYED = "delayed"           # Task has been postponed
    UNDONE = "undone"             # Was completed but needs rework
    ON_HOLD = "on_hold"           # Paused intentionally
    WAITING = "waiting"           # Waiting for external dependency
    NEEDS_INFO = "needs_info"     # Blocked pending information
    OVERDUE = "overdue"           # Past deadline, not completed


class AcceptanceCriteria(BaseModel):
    """Individual acceptance criterion for a task."""
    description: str
    completed: bool = False


class TaskNote(BaseModel):
    """A note attached to a task."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str
    author: str
    created_at: datetime = Field(default_factory=datetime.now)
    note_type: str = "general"  # general, update, blocker, question, resolution
    is_pinned: bool = False


class StatusChange(BaseModel):
    """Track status changes for history."""
    from_status: TaskStatus
    to_status: TaskStatus
    changed_at: datetime = Field(default_factory=datetime.now)
    changed_by: str
    reason: Optional[str] = None


class Task(BaseModel):
    """Task model representing a work item."""

    # Identification
    id: str = Field(default_factory=lambda: f"TASK-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:3].upper()}")

    # Core fields
    title: str
    description: str
    assignee: Optional[str] = None

    # Classification
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    task_type: str = "task"  # task, bug, feature, research

    # Timing
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    deadline: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Details
    acceptance_criteria: List[AcceptanceCriteria] = Field(default_factory=list)
    estimated_effort: Optional[str] = None  # e.g., "2 hours", "1 day"
    tags: List[str] = Field(default_factory=list)

    # Notes system
    notes: List[TaskNote] = Field(default_factory=list)
    status_history: List[StatusChange] = Field(default_factory=list)

    # Delay tracking
    original_deadline: Optional[datetime] = None  # Store original if delayed
    delay_reason: Optional[str] = None
    delayed_count: int = 0

    # Metadata
    created_by: str = ""
    original_message: str = ""
    conversation_id: Optional[str] = None

    # Integration IDs
    discord_message_id: Optional[str] = None
    discord_thread_id: Optional[str] = None  # For forum threads
    sheets_row_id: Optional[int] = None
    google_calendar_event_id: Optional[str] = None  # For calendar integration
    spec_sheet_url: Optional[str] = None  # URL to detailed spec document

    # Validation tracking
    requires_validation: bool = True  # Whether task needs boss approval
    validation_attempts: int = 0
    last_validation_status: Optional[str] = None  # "approved", "rejected", "pending"
    validation_id: Optional[str] = None  # Links to TaskValidation record

    # Assignee info for notifications
    assignee_telegram_id: Optional[str] = None
    assignee_discord_id: Optional[str] = None  # Discord user ID or username for mentions
    assignee_email: Optional[str] = None  # Email for Google Calendar/Sheets

    def generate_task_id(self) -> str:
        """Generate a sequential task ID for the day."""
        date_part = datetime.now().strftime('%Y%m%d')
        # In practice, this would query the DB for the next sequence number
        return f"TASK-{date_part}-{str(uuid.uuid4())[:3].upper()}"

    def to_discord_embed_dict(self) -> dict:
        """Convert task to Discord embed format."""
        priority_emoji = {
            TaskPriority.LOW: "🟢",
            TaskPriority.MEDIUM: "🟡",
            TaskPriority.HIGH: "🟠",
            TaskPriority.URGENT: "🔴",
        }

        status_emoji = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.IN_PROGRESS: "🔨",
            TaskStatus.IN_REVIEW: "🔍",
            TaskStatus.AWAITING_VALIDATION: "📋",
            TaskStatus.NEEDS_REVISION: "🔄",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.CANCELLED: "❌",
            TaskStatus.BLOCKED: "🚫",
            TaskStatus.DELAYED: "⏰",
            TaskStatus.UNDONE: "↩️",
            TaskStatus.ON_HOLD: "⏸️",
            TaskStatus.WAITING: "⏳",
            TaskStatus.NEEDS_INFO: "❓",
            TaskStatus.OVERDUE: "🚨",
        }

        # Format assignee with Discord mention if available
        if self.assignee_discord_id:
            # Use @username format for Discord
            assignee_display = f"@{self.assignee_discord_id}" if not self.assignee_discord_id.startswith('@') else self.assignee_discord_id
            if self.assignee:
                assignee_display = f"{self.assignee} ({assignee_display})"
        else:
            assignee_display = self.assignee or "Unassigned"

        fields = [
            {"name": "Assignee", "value": assignee_display, "inline": True},
            {"name": "Priority", "value": f"{priority_emoji[self.priority]} {self.priority.value.upper()}", "inline": True},
            {"name": "Status", "value": f"{status_emoji[self.status]} {self.status.value.replace('_', ' ').title()}", "inline": True},
        ]

        if self.deadline:
            fields.append({
                "name": "Deadline",
                "value": self.deadline.strftime("%b %d, %Y %I:%M %p"),
                "inline": True
            })

        if self.estimated_effort:
            fields.append({
                "name": "Estimated Effort",
                "value": self.estimated_effort,
                "inline": True
            })

        if self.acceptance_criteria:
            criteria_text = "\n".join([
                f"{'☑' if c.completed else '☐'} {c.description}"
                for c in self.acceptance_criteria
            ])
            fields.append({
                "name": "Acceptance Criteria",
                "value": criteria_text[:1024],  # Discord field limit
                "inline": False
            })

        # Show pinned notes
        pinned_notes = [n for n in self.notes if n.is_pinned]
        if pinned_notes:
            notes_text = "\n".join([f"📌 {n.content[:100]}" for n in pinned_notes[:3]])
            fields.append({
                "name": "Pinned Notes",
                "value": notes_text[:1024],
                "inline": False
            })

        # Show delay info if delayed
        if self.status == TaskStatus.DELAYED and self.delay_reason:
            fields.append({
                "name": "Delay Reason",
                "value": self.delay_reason[:256],
                "inline": False
            })

        # Color based on priority
        color_map = {
            TaskPriority.LOW: 0x2ECC71,      # Green
            TaskPriority.MEDIUM: 0xF1C40F,   # Yellow
            TaskPriority.HIGH: 0xE67E22,     # Orange
            TaskPriority.URGENT: 0xE74C3C,   # Red
        }

        return {
            "title": f"🎯 {self.id}",
            "description": f"**{self.title}**\n\n{self.description}",
            "color": color_map[self.priority],
            "fields": fields,
            "footer": {
                "text": f"Created: {self.created_at.strftime('%Y-%m-%d %H:%M')}"
            },
            "timestamp": self.created_at.isoformat()
        }

    def to_sheets_row(self) -> List:
        """Convert task to Google Sheets row format."""
        return [
            self.id,
            self.title,
            self.description,
            self.assignee or "",
            self.priority.value,
            self.status.value,
            self.task_type,
            self.deadline.isoformat() if self.deadline else "",
            self.created_at.isoformat(),
            self.updated_at.isoformat(),
            self.estimated_effort or "",
            ", ".join([c.description for c in self.acceptance_criteria]),
            ", ".join(self.tags),
            self.created_by,
        ]

    @classmethod
    def sheets_headers(cls) -> List[str]:
        """Get headers for Google Sheets."""
        return [
            "Task ID",
            "Title",
            "Description",
            "Assignee",
            "Priority",
            "Status",
            "Type",
            "Deadline",
            "Created At",
            "Updated At",
            "Estimated Effort",
            "Acceptance Criteria",
            "Tags",
            "Created By",
            "Notes Count",
            "Delay Count",
            "Calendar Event ID",
        ]

    def add_note(self, content: str, author: str, note_type: str = "general", pinned: bool = False) -> TaskNote:
        """Add a note to the task."""
        note = TaskNote(
            content=content,
            author=author,
            note_type=note_type,
            is_pinned=pinned
        )
        self.notes.append(note)
        self.updated_at = datetime.now()
        return note

    def change_status(self, new_status: TaskStatus, changed_by: str, reason: Optional[str] = None) -> None:
        """Change task status with history tracking."""
        old_status = self.status

        # Track status change
        change = StatusChange(
            from_status=old_status,
            to_status=new_status,
            changed_by=changed_by,
            reason=reason
        )
        self.status_history.append(change)

        # Handle special status transitions
        if new_status == TaskStatus.DELAYED:
            if self.deadline and not self.original_deadline:
                self.original_deadline = self.deadline
            self.delayed_count += 1
            self.delay_reason = reason

        elif new_status == TaskStatus.UNDONE:
            # Was completed but needs rework
            if self.completed_at:
                self.add_note(
                    f"Reopened from completed status. Reason: {reason or 'Not specified'}",
                    changed_by,
                    "update"
                )
            self.completed_at = None

        elif new_status == TaskStatus.IN_PROGRESS and not self.started_at:
            self.started_at = datetime.now()

        elif new_status == TaskStatus.COMPLETED:
            self.completed_at = datetime.now()

        self.status = new_status
        self.updated_at = datetime.now()

    def delay_task(self, new_deadline: datetime, reason: str, changed_by: str) -> None:
        """Delay a task with a new deadline and reason."""
        if not self.original_deadline and self.deadline:
            self.original_deadline = self.deadline

        self.deadline = new_deadline
        self.change_status(TaskStatus.DELAYED, changed_by, reason)

    def get_notes_summary(self) -> str:
        """Get a summary of task notes."""
        if not self.notes:
            return "No notes"

        lines = []
        for note in sorted(self.notes, key=lambda n: n.created_at, reverse=True)[:5]:
            pin = "📌 " if note.is_pinned else ""
            lines.append(f"{pin}[{note.note_type}] {note.content[:50]}... - {note.author}")

        return "\n".join(lines)

    def to_sheets_row(self) -> List:
        """Convert task to Google Sheets row format."""
        return [
            self.id,
            self.title,
            self.description,
            self.assignee or "",
            self.priority.value,
            self.status.value,
            self.task_type,
            self.deadline.isoformat() if self.deadline else "",
            self.created_at.isoformat(),
            self.updated_at.isoformat(),
            self.estimated_effort or "",
            ", ".join([c.description for c in self.acceptance_criteria]),
            ", ".join(self.tags),
            self.created_by,
            str(len(self.notes)),
            str(self.delayed_count),
            self.google_calendar_event_id or "",
        ]
