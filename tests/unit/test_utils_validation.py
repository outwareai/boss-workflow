"""
Tests for src/utils/validation.py

Tests all validation functions including email, task ID, priority, status,
task data validation, and status transitions.
"""

import pytest
from datetime import datetime, timedelta
from src.utils.validation import (
    ValidationResult,
    validate_email,
    validate_task_id,
    validate_priority,
    validate_status,
    validate_task_data,
    validate_status_transition,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_success_creates_valid_result(self):
        """Test creating a successful validation result."""
        result = ValidationResult.success()
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_success_with_warnings(self):
        """Test successful result can include warnings."""
        result = ValidationResult.success(warnings=["This is a warning"])
        assert result.is_valid is True
        assert result.errors == []
        assert len(result.warnings) == 1

    def test_failure_creates_invalid_result(self):
        """Test creating a failed validation result."""
        result = ValidationResult.failure(errors=["Error 1", "Error 2"])
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert result.warnings == []

    def test_failure_with_warnings(self):
        """Test failure can include both errors and warnings."""
        result = ValidationResult.failure(
            errors=["Fatal error"],
            warnings=["Also a warning"]
        )
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert len(result.warnings) == 1


class TestValidateEmail:
    """Tests for email validation."""

    def test_valid_email_basic(self):
        """Test basic valid email addresses."""
        assert validate_email("user@example.com") is True
        assert validate_email("test.user@example.com") is True
        assert validate_email("user+tag@example.co.uk") is True

    def test_valid_email_complex(self):
        """Test complex but valid email formats."""
        assert validate_email("user123@sub.example.com") is True
        assert validate_email("first.last@company.org") is True
        assert validate_email("admin_user@example-site.com") is True

    def test_invalid_email_format(self):
        """Test invalid email formats."""
        assert validate_email("not-an-email") is False
        assert validate_email("@example.com") is False
        assert validate_email("user@") is False
        assert validate_email("user.example.com") is False

    def test_empty_email(self):
        """Test empty email returns False."""
        assert validate_email("") is False
        assert validate_email(None) is False


class TestValidateTaskId:
    """Tests for task ID validation."""

    def test_valid_task_id(self):
        """Test valid task ID format."""
        assert validate_task_id("TASK-20260118-ABC") is True
        assert validate_task_id("TASK-20260101-XYZ") is True
        assert validate_task_id("TASK-20251231-123") is True

    def test_invalid_task_id_format(self):
        """Test various invalid task ID formats."""
        assert validate_task_id("TASK-2026-ABC") is False  # Wrong date format
        assert validate_task_id("TASK-20260118-ABCD") is False  # Too many chars
        assert validate_task_id("TASK-20260118-AB") is False  # Too few chars
        assert validate_task_id("task-20260118-ABC") is False  # Lowercase
        assert validate_task_id("PROJ-20260118-ABC") is False  # Wrong prefix

    def test_empty_task_id(self):
        """Test empty task ID returns False."""
        assert validate_task_id("") is False
        assert validate_task_id(None) is False


class TestValidatePriority:
    """Tests for priority validation."""

    def test_valid_priorities(self):
        """Test all valid priority values."""
        assert validate_priority("low") is True
        assert validate_priority("medium") is True
        assert validate_priority("high") is True
        assert validate_priority("urgent") is True

    def test_case_insensitive_priority(self):
        """Test priority validation is case-insensitive."""
        assert validate_priority("LOW") is True
        assert validate_priority("Medium") is True
        assert validate_priority("HIGH") is True
        assert validate_priority("URGENT") is True

    def test_invalid_priority(self):
        """Test invalid priority values."""
        assert validate_priority("critical") is False
        assert validate_priority("normal") is False
        assert validate_priority("") is False
        assert validate_priority(None) is False


class TestValidateStatus:
    """Tests for status validation."""

    def test_valid_statuses(self):
        """Test all valid status values."""
        valid_statuses = [
            "pending", "in_progress", "in_review", "awaiting_validation",
            "needs_revision", "completed", "cancelled", "blocked",
            "delayed", "undone", "on_hold", "waiting", "needs_info", "overdue"
        ]
        for status in valid_statuses:
            assert validate_status(status) is True, f"Status '{status}' should be valid"

    def test_case_insensitive_status(self):
        """Test status validation is case-insensitive."""
        assert validate_status("PENDING") is True
        assert validate_status("In_Progress") is True
        assert validate_status("COMPLETED") is True

    def test_invalid_status(self):
        """Test invalid status values."""
        assert validate_status("unknown") is False
        assert validate_status("done") is False
        assert validate_status("") is False
        assert validate_status(None) is False


class TestValidateTaskData:
    """Tests for full task data validation."""

    def test_valid_minimal_task(self):
        """Test validation with only required fields."""
        result = validate_task_data(title="Valid task title")
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_empty_title_fails(self):
        """Test that empty title fails validation."""
        result = validate_task_data(title="")
        assert result.is_valid is False
        assert "required" in result.errors[0].lower()

    def test_whitespace_only_title_fails(self):
        """Test that whitespace-only title fails."""
        result = validate_task_data(title="   ")
        assert result.is_valid is False
        assert "required" in result.errors[0].lower()

    def test_title_too_long_fails(self):
        """Test that title exceeding 500 chars fails."""
        result = validate_task_data(title="x" * 501)
        assert result.is_valid is False
        assert "500 characters" in result.errors[0]

    def test_short_title_warning(self):
        """Test that very short title generates warning."""
        result = validate_task_data(title="ab")
        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert "short" in result.warnings[0].lower()

    def test_description_too_long_fails(self):
        """Test that description exceeding 10000 chars fails."""
        result = validate_task_data(
            title="Valid title",
            description="x" * 10001
        )
        assert result.is_valid is False
        assert "10000 characters" in result.errors[0]

    def test_invalid_task_id_format_warns(self):
        """Test that invalid task ID format generates warning."""
        result = validate_task_data(
            title="Valid title",
            task_id="INVALID-ID"
        )
        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert "TASK-YYYYMMDD-XXX" in result.warnings[0]

    def test_invalid_priority_fails(self):
        """Test that invalid priority fails validation."""
        result = validate_task_data(
            title="Valid title",
            priority="critical"
        )
        assert result.is_valid is False
        assert "priority" in result.errors[0].lower()

    def test_invalid_status_fails(self):
        """Test that invalid status fails validation."""
        result = validate_task_data(
            title="Valid title",
            status="done"
        )
        assert result.is_valid is False
        assert "status" in result.errors[0].lower()

    def test_invalid_email_warns(self):
        """Test that invalid email generates warning."""
        result = validate_task_data(
            title="Valid title",
            assignee_email="not-an-email"
        )
        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert "email" in result.warnings[0].lower()

    def test_past_deadline_warns(self):
        """Test that past deadline generates warning."""
        past_date = datetime.now() - timedelta(days=1)
        result = validate_task_data(
            title="Valid title",
            deadline=past_date
        )
        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert "past" in result.warnings[0].lower()

    def test_assignee_without_contact_warns(self):
        """Test that assignee without contact info generates warning."""
        result = validate_task_data(
            title="Valid title",
            assignee="John Doe"
        )
        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert "contact info" in result.warnings[0].lower()

    def test_valid_full_task_data(self):
        """Test validation with all valid fields."""
        future_date = datetime.now() + timedelta(days=7)
        result = validate_task_data(
            title="Complete task title",
            description="Detailed description of the task",
            assignee="John Doe",
            assignee_discord_id="123456789012345678",
            assignee_email="john@example.com",
            priority="high",
            status="in_progress",
            deadline=future_date,
            task_id="TASK-20260118-ABC"
        )
        assert result.is_valid is True
        assert len(result.errors) == 0


class TestValidateStatusTransition:
    """Tests for status transition validation."""

    def test_normal_transitions_allowed(self):
        """Test that normal status transitions are allowed."""
        is_valid, msg = validate_status_transition("pending", "in_progress")
        assert is_valid is True
        assert msg is None

        is_valid, msg = validate_status_transition("in_progress", "in_review")
        assert is_valid is True
        assert msg is None

        is_valid, msg = validate_status_transition("in_review", "completed")
        assert is_valid is True
        assert msg is None

    def test_completed_to_pending_invalid(self):
        """Test that completed -> pending is not allowed."""
        is_valid, msg = validate_status_transition("completed", "pending")
        assert is_valid is False
        assert "Cannot transition" in msg

    def test_cancelled_to_pending_invalid(self):
        """Test that cancelled -> pending is not allowed."""
        is_valid, msg = validate_status_transition("cancelled", "pending")
        assert is_valid is False
        assert "Cannot transition" in msg

    def test_cancelled_to_in_progress_invalid(self):
        """Test that cancelled -> in_progress is not allowed."""
        is_valid, msg = validate_status_transition("cancelled", "in_progress")
        assert is_valid is False
        assert "Cannot transition" in msg

    def test_completed_to_in_progress_warns(self):
        """Test that completed -> in_progress generates warning."""
        is_valid, msg = validate_status_transition("completed", "in_progress")
        assert is_valid is True
        assert msg is not None
        assert "Warning" in msg

    def test_completed_to_in_review_warns(self):
        """Test that completed -> in_review generates warning."""
        is_valid, msg = validate_status_transition("completed", "in_review")
        assert is_valid is True
        assert msg is not None
        assert "Warning" in msg

    def test_cancelled_to_completed_warns(self):
        """Test that cancelled -> completed generates warning."""
        is_valid, msg = validate_status_transition("cancelled", "completed")
        assert is_valid is True
        assert msg is not None
        assert "Warning" in msg

    def test_case_insensitive_transitions(self):
        """Test that transition validation is case-insensitive."""
        is_valid, msg = validate_status_transition("PENDING", "IN_PROGRESS")
        assert is_valid is True
        assert msg is None

        is_valid, msg = validate_status_transition("Completed", "Pending")
        assert is_valid is False
