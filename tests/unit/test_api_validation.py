"""
Tests for API input validation models (api_validation.py).

Q1 2026: Ensures all Pydantic validation rules work correctly.
"""

import pytest
from pydantic import ValidationError
from src.models.api_validation import (
    SubtaskCreate,
    DependencyCreate,
    DependencyType,
    TaskFilter,
    TaskStatusFilter,
    AdminAuthRequest,
    TeamMemberCreate,
    TeachingRequest,
    TriggerJobRequest,
    OnboardingDataEnhanced,
    OAuthCallback,
    TelegramUpdate,
    DiscordWebhookPayload,
    ProjectCreate,
)


class TestSubtaskCreate:
    """Test subtask creation validation."""

    def test_valid_subtask(self):
        """Test creating valid subtask."""
        subtask = SubtaskCreate(title="Fix bug", description="Fix login bug")
        assert subtask.title == "Fix bug"
        assert subtask.description == "Fix login bug"

    def test_title_too_short(self):
        """Test title cannot be empty after stripping."""
        with pytest.raises(ValidationError):
            SubtaskCreate(title="   ", description="Test")

    def test_title_too_long(self):
        """Test title max length validation."""
        with pytest.raises(ValidationError):
            SubtaskCreate(title="x" * 501, description="Test")

    def test_description_too_long(self):
        """Test description max length validation."""
        with pytest.raises(ValidationError):
            SubtaskCreate(title="Test", description="x" * 5001)

    def test_optional_description(self):
        """Test description is optional."""
        subtask = SubtaskCreate(title="Test")
        assert subtask.description is None


class TestDependencyCreate:
    """Test dependency creation validation."""

    def test_valid_dependency(self):
        """Test creating valid dependency."""
        dep = DependencyCreate(depends_on="TASK-20260123-001", type=DependencyType.DEPENDS_ON)
        assert dep.depends_on == "TASK-20260123-001"
        assert dep.type == DependencyType.DEPENDS_ON

    def test_invalid_task_id_format(self):
        """Test task ID format validation."""
        with pytest.raises(ValidationError):
            DependencyCreate(depends_on="invalid-id")

    def test_default_type(self):
        """Test default dependency type."""
        dep = DependencyCreate(depends_on="TASK-20260123-001")
        assert dep.type == DependencyType.DEPENDS_ON

    def test_enum_types(self):
        """Test all valid dependency types."""
        for dep_type in [DependencyType.DEPENDS_ON, DependencyType.BLOCKED_BY, DependencyType.PREVENTS]:
            dep = DependencyCreate(depends_on="TASK-20260123-001", type=dep_type)
            assert dep.type == dep_type


class TestTaskFilter:
    """Test task filtering validation."""

    def test_valid_filter(self):
        """Test creating valid task filter."""
        filter = TaskFilter(status=TaskStatusFilter.PENDING, assignee="John", limit=10, offset=0)
        assert filter.status == TaskStatusFilter.PENDING
        assert filter.assignee == "John"
        assert filter.limit == 10

    def test_limit_bounds(self):
        """Test limit min/max validation."""
        # Too small
        with pytest.raises(ValidationError):
            TaskFilter(limit=0)

        # Too large
        with pytest.raises(ValidationError):
            TaskFilter(limit=1001)

        # Valid
        TaskFilter(limit=1)
        TaskFilter(limit=1000)

    def test_offset_bounds(self):
        """Test offset validation."""
        # Negative offset
        with pytest.raises(ValidationError):
            TaskFilter(offset=-1)

        # Too large
        with pytest.raises(ValidationError):
            TaskFilter(offset=100001)

        # Valid
        TaskFilter(offset=0)
        TaskFilter(offset=100000)

    def test_default_values(self):
        """Test default filter values."""
        filter = TaskFilter()
        assert filter.status is None
        assert filter.assignee is None
        assert filter.limit == 50
        assert filter.offset == 0


class TestAdminAuthRequest:
    """Test admin authentication validation."""

    def test_valid_secret(self):
        """Test valid admin secret."""
        auth = AdminAuthRequest(secret="test_secret_123")
        assert auth.secret == "test_secret_123"

    def test_empty_secret(self):
        """Test empty secret is rejected."""
        with pytest.raises(ValidationError):
            AdminAuthRequest(secret="")


class TestTeamMemberCreate:
    """Test team member creation validation."""

    def test_valid_member(self):
        """Test creating valid team member."""
        member = TeamMemberCreate(
            name="John Doe",
            role="Developer",
            telegram_id="123456789",
            discord_id="987654321012345678",
            email="john@example.com",
        )
        assert member.name == "John Doe"
        assert member.role == "Developer"

    def test_invalid_role(self):
        """Test invalid role is rejected."""
        with pytest.raises(ValidationError):
            TeamMemberCreate(name="John", role="InvalidRole")

    def test_invalid_telegram_id(self):
        """Test telegram ID format validation."""
        with pytest.raises(ValidationError):
            TeamMemberCreate(name="John", role="Developer", telegram_id="abc123")

    def test_invalid_discord_id(self):
        """Test discord ID format validation."""
        with pytest.raises(ValidationError):
            TeamMemberCreate(name="John", role="Developer", discord_id="123")  # Too short

    def test_default_active(self):
        """Test default is_active value."""
        member = TeamMemberCreate(name="John", role="Developer")
        assert member.is_active is True


class TestTeachingRequest:
    """Test teaching request validation."""

    def test_valid_teaching(self):
        """Test valid teaching text."""
        req = TeachingRequest(text="I prefer using Python for backend")
        assert req.text == "I prefer using Python for backend"

    def test_too_short(self):
        """Test minimum length validation."""
        with pytest.raises(ValidationError):
            TeachingRequest(text="Hi")

    def test_too_long(self):
        """Test maximum length validation."""
        with pytest.raises(ValidationError):
            TeachingRequest(text="x" * 2001)

    def test_whitespace_stripping(self):
        """Test whitespace is stripped and validated."""
        with pytest.raises(ValidationError):
            TeachingRequest(text="     ")  # Only whitespace


class TestTriggerJobRequest:
    """Test job trigger request validation."""

    def test_valid_job_id(self):
        """Test valid job ID."""
        req = TriggerJobRequest(job_id="daily_standup")
        assert req.job_id == "daily_standup"

    def test_invalid_job_id(self):
        """Test invalid job ID format."""
        # Contains uppercase
        with pytest.raises(ValidationError):
            TriggerJobRequest(job_id="Daily_Standup")

        # Too short
        with pytest.raises(ValidationError):
            TriggerJobRequest(job_id="ab")

        # Special characters
        with pytest.raises(ValidationError):
            TriggerJobRequest(job_id="job-name-123")

    def test_default_force(self):
        """Test default force value."""
        req = TriggerJobRequest(job_id="test_job")
        assert req.force is False


class TestOnboardingDataEnhanced:
    """Test enhanced onboarding validation."""

    def test_valid_onboarding(self):
        """Test valid onboarding data."""
        data = OnboardingDataEnhanced(
            name="John Doe",
            email="john@example.com",
            role="Developer",
            discord_id="987654321012345678",
        )
        assert data.name == "John Doe"
        assert data.role == "Developer"

    def test_xss_prevention(self):
        """Test XSS prevention in name field."""
        with pytest.raises(ValidationError):
            OnboardingDataEnhanced(
                name="John<script>alert('xss')</script>",
                email="john@example.com",
                role="Developer",
                discord_id="987654321012345678",
            )

    def test_invalid_email(self):
        """Test email validation."""
        with pytest.raises(ValidationError):
            OnboardingDataEnhanced(
                name="John", email="invalid-email", role="Developer", discord_id="987654321012345678"
            )

    def test_name_too_short(self):
        """Test minimum name length."""
        with pytest.raises(ValidationError):
            OnboardingDataEnhanced(name="J", email="j@example.com", role="Developer", discord_id="987654321012345678")


class TestOAuthCallback:
    """Test OAuth callback validation."""

    def test_valid_callback(self):
        """Test valid OAuth callback."""
        callback = OAuthCallback(code="abc123def456", state="a" * 32)
        assert callback.code == "abc123def456"

    def test_code_too_short(self):
        """Test code minimum length."""
        with pytest.raises(ValidationError):
            OAuthCallback(code="short", state="a" * 32)

    def test_invalid_state_format(self):
        """Test state format validation."""
        with pytest.raises(ValidationError):
            OAuthCallback(code="abc123def456", state="invalid state!")

    def test_xss_prevention_in_error(self):
        """Test XSS prevention in error parameter."""
        with pytest.raises(ValidationError):
            OAuthCallback(code="abc123def456", state="a" * 32, error="<script>alert('xss')</script>")


class TestTelegramUpdate:
    """Test Telegram webhook validation."""

    def test_valid_update(self):
        """Test valid Telegram update."""
        update = TelegramUpdate(update_id=123456, message={"message_id": 1, "chat": {"id": 789}})
        assert update.update_id == 123456

    def test_negative_update_id(self):
        """Test negative update ID is rejected."""
        with pytest.raises(ValidationError):
            TelegramUpdate(update_id=-1)

    def test_zero_update_id(self):
        """Test zero update ID is rejected."""
        with pytest.raises(ValidationError):
            TelegramUpdate(update_id=0)


class TestDiscordWebhookPayload:
    """Test Discord webhook validation."""

    def test_valid_payload(self):
        """Test valid Discord webhook payload."""
        payload = DiscordWebhookPayload(type=1, id="123456789012345678", token="test_token_123")
        assert payload.type == 1

    def test_invalid_type_range(self):
        """Test type must be in valid range."""
        with pytest.raises(ValidationError):
            DiscordWebhookPayload(type=-1)

        with pytest.raises(ValidationError):
            DiscordWebhookPayload(type=26)

    def test_invalid_id_format(self):
        """Test Discord snowflake ID format."""
        with pytest.raises(ValidationError):
            DiscordWebhookPayload(type=1, id="123")  # Too short


class TestProjectCreate:
    """Test project creation validation."""

    def test_valid_project(self):
        """Test creating valid project."""
        project = ProjectCreate(name="New Project", description="A test project", color="#FF5733")
        assert project.name == "New Project"
        assert project.description == "A test project"
        assert project.color == "#FF5733"

    def test_name_too_short(self):
        """Test minimum name length."""
        with pytest.raises(ValidationError):
            ProjectCreate(name="AB")  # Only 2 chars

    def test_name_too_long(self):
        """Test maximum name length."""
        with pytest.raises(ValidationError):
            ProjectCreate(name="x" * 201)

    def test_name_whitespace_only(self):
        """Test name cannot be whitespace only."""
        with pytest.raises(ValidationError):
            ProjectCreate(name="   ")

    def test_xss_prevention_in_name(self):
        """Test XSS prevention in name field."""
        with pytest.raises(ValidationError):
            ProjectCreate(name="Project<script>alert('xss')</script>")

    def test_xss_prevention_in_description(self):
        """Test XSS prevention in description field."""
        with pytest.raises(ValidationError):
            ProjectCreate(name="Valid Project", description="Test <script>alert('xss')</script>")

        with pytest.raises(ValidationError):
            ProjectCreate(name="Valid Project", description="Test <iframe src='evil'></iframe>")

    def test_invalid_color_format(self):
        """Test color format validation."""
        # Invalid hex format
        with pytest.raises(ValidationError):
            ProjectCreate(name="Project", color="FF5733")  # Missing #

        with pytest.raises(ValidationError):
            ProjectCreate(name="Project", color="#FF57")  # Too short

        with pytest.raises(ValidationError):
            ProjectCreate(name="Project", color="#FF57339")  # Too long

        with pytest.raises(ValidationError):
            ProjectCreate(name="Project", color="#GGGGGG")  # Invalid hex chars

    def test_valid_color_formats(self):
        """Test various valid color formats."""
        ProjectCreate(name="Project", color="#FF5733")
        ProjectCreate(name="Project", color="#ffffff")
        ProjectCreate(name="Project", color="#000000")
        ProjectCreate(name="Project", color="#AbCdEf")

    def test_optional_fields(self):
        """Test optional description and color."""
        project = ProjectCreate(name="Minimal Project")
        assert project.description is None
        assert project.color is None

    def test_description_max_length(self):
        """Test description maximum length."""
        with pytest.raises(ValidationError):
            ProjectCreate(name="Project", description="x" * 2001)
