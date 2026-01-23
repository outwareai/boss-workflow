"""
Pydantic models for API endpoint input validation.

Part of Q1 2026 security audit - adds validation to prevent:
- SQL injection
- XSS attacks
- Resource exhaustion
- Invalid data types
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, EmailStr
from enum import Enum


# ============================================
# ENUMS
# ============================================

class DependencyType(str, Enum):
    """Valid dependency types between tasks."""
    DEPENDS_ON = "depends_on"
    BLOCKED_BY = "blocked_by"
    PREVENTS = "prevents"


class TaskStatusFilter(str, Enum):
    """Valid task statuses for filtering."""
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


# ============================================
# WEBHOOK VALIDATION
# ============================================

class TelegramMessage(BaseModel):
    """Telegram message structure (subset of fields)."""
    message_id: int
    text: Optional[str] = Field(None, max_length=4096)  # Telegram limit
    chat: dict  # Simplified - contains id, type, etc.


class TelegramUpdate(BaseModel):
    """Telegram webhook payload validation."""
    update_id: int = Field(..., gt=0)
    message: Optional[TelegramMessage] = None
    callback_query: Optional[dict] = None  # Simplified

    @field_validator("update_id")
    @classmethod
    def validate_update_id(cls, v):
        if v < 0:
            raise ValueError("update_id must be positive")
        return v


class DiscordWebhookPayload(BaseModel):
    """Discord webhook payload validation."""
    type: int = Field(..., ge=0, le=25)  # Discord interaction types 0-25
    id: Optional[str] = Field(None, pattern=r"^\d{17,19}$")  # Snowflake ID
    token: Optional[str] = Field(None, min_length=10, max_length=200)
    data: Optional[dict] = None


# ============================================
# TASK OPERATIONS
# ============================================

class SubtaskCreate(BaseModel):
    """Input validation for creating subtasks."""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        stripped = v.strip()
        if not stripped:
            raise ValueError("title cannot be empty after stripping whitespace")
        return stripped


class DependencyCreate(BaseModel):
    """Input validation for creating task dependencies."""
    depends_on: str = Field(..., pattern=r"^TASK-\d{8}-\d{3}$")
    type: DependencyType = Field(default=DependencyType.DEPENDS_ON)


class TaskFilter(BaseModel):
    """Input validation for task filtering/queries."""
    status: Optional[TaskStatusFilter] = None
    assignee: Optional[str] = Field(None, max_length=100)
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0, le=100000)


# ============================================
# ADMIN ENDPOINTS
# ============================================

class AdminAuthRequest(BaseModel):
    """Secure admin authentication (secret in body, not query params)."""
    secret: str = Field(..., min_length=1)


class MigrationRequest(AdminAuthRequest):
    """Migration execution request."""
    migration_file: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+\.sql$")


class TeamMemberCreate(BaseModel):
    """Validation for creating team members."""
    name: str = Field(..., min_length=1, max_length=100)
    role: Literal["Developer", "Admin", "Manager", "Marketing"] = Field(...)
    telegram_id: Optional[str] = Field(None, pattern=r"^\d{9,12}$")
    discord_id: Optional[str] = Field(None, pattern=r"^\d{17,19}$")
    email: Optional[EmailStr] = None
    is_active: bool = Field(default=True)


# ============================================
# USER PREFERENCES
# ============================================

class TeachingRequest(BaseModel):
    """Input validation for teaching user preferences."""
    text: str = Field(..., min_length=5, max_length=2000)

    @field_validator("text")
    @classmethod
    def validate_text(cls, v):
        stripped = v.strip()
        if len(stripped) < 5:
            raise ValueError("teaching text must be at least 5 characters after stripping")
        return stripped


# ============================================
# JOB TRIGGERS
# ============================================

class TriggerJobRequest(BaseModel):
    """Input validation for job trigger requests."""
    job_id: str = Field(..., pattern=r"^[a-z_]{3,50}$")
    force: bool = Field(default=False)


# ============================================
# PROJECT OPERATIONS
# ============================================

class ProjectCreate(BaseModel):
    """Input validation for creating projects."""
    name: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Validate and sanitize project name."""
        stripped = v.strip()
        if len(stripped) < 3:
            raise ValueError("name must be at least 3 characters after stripping")
        # XSS prevention
        if "<" in stripped or ">" in stripped:
            raise ValueError("name cannot contain HTML/script tags")
        return stripped

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        """Validate and sanitize description."""
        if v is None:
            return v
        stripped = v.strip()
        # XSS prevention
        if "<script" in stripped.lower() or "<iframe" in stripped.lower():
            raise ValueError("description cannot contain script/iframe tags")
        return stripped if stripped else None


# ============================================
# ONBOARDING (Enhanced)
# ============================================

class OnboardingDataEnhanced(BaseModel):
    """Enhanced onboarding data with stricter validation."""
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    role: Literal["Developer", "Admin", "Manager", "Marketing", "Intern"] = Field(...)
    discord_id: str = Field(..., pattern=r"^\d{17,19}$")
    telegram_id: Optional[str] = Field(None, pattern=r"^\d{9,12}$")
    timezone: str = Field(default="UTC", pattern=r"^[A-Za-z/_]+$")
    calendar_token: Optional[str] = Field(None, min_length=10)
    tasks_token: Optional[str] = Field(None, min_length=10)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        stripped = v.strip()
        if len(stripped) < 2:
            raise ValueError("name must be at least 2 characters")
        # Prevent script injection
        if "<" in stripped or ">" in stripped:
            raise ValueError("name cannot contain HTML/script tags")
        return stripped


# ============================================
# OAUTH CALLBACK
# ============================================

class OAuthCallback(BaseModel):
    """OAuth callback validation."""
    code: str = Field(..., min_length=10, max_length=500)
    state: str = Field(..., pattern=r"^[a-zA-Z0-9_-]{32,}$")
    error: Optional[str] = Field(None, max_length=200)

    @field_validator("error")
    @classmethod
    def validate_error(cls, v):
        if v and ("<" in v or ">" in v):
            raise ValueError("error cannot contain HTML tags (XSS prevention)")
        return v
