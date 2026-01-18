"""
Task validation utilities.

Validates task data before database save to catch errors early
and provide clear feedback.
"""

import re
import logging
from typing import Optional, List, Tuple
from datetime import datetime
from dataclasses import dataclass

from .datetime_utils import get_local_now
from .team_utils import validate_discord_id

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]

    @classmethod
    def success(cls, warnings: Optional[List[str]] = None) -> "ValidationResult":
        """Create a successful validation result."""
        return cls(is_valid=True, errors=[], warnings=warnings or [])

    @classmethod
    def failure(cls, errors: List[str], warnings: Optional[List[str]] = None) -> "ValidationResult":
        """Create a failed validation result."""
        return cls(is_valid=False, errors=errors, warnings=warnings or [])


def validate_email(email: str) -> bool:
    """
    Validate email format.

    Args:
        email: Email address to validate

    Returns:
        True if valid email format
    """
    if not email:
        return False

    # Basic email regex - not exhaustive but catches most issues
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_task_id(task_id: str) -> bool:
    """
    Validate task ID format.

    Expected format: TASK-YYYYMMDD-XXX

    Args:
        task_id: Task ID to validate

    Returns:
        True if valid task ID format
    """
    if not task_id:
        return False

    # Pattern: TASK-20260118-ABC
    pattern = r'^TASK-\d{8}-[A-Z0-9]{3}$'
    return bool(re.match(pattern, task_id))


def validate_priority(priority: str) -> bool:
    """
    Validate priority value.

    Args:
        priority: Priority string

    Returns:
        True if valid priority
    """
    valid_priorities = {"low", "medium", "high", "urgent"}
    return priority.lower() in valid_priorities if priority else False


def validate_status(status: str) -> bool:
    """
    Validate status value.

    Args:
        status: Status string

    Returns:
        True if valid status
    """
    valid_statuses = {
        "pending", "in_progress", "in_review", "awaiting_validation",
        "needs_revision", "completed", "cancelled", "blocked",
        "delayed", "undone", "on_hold", "waiting", "needs_info", "overdue"
    }
    return status.lower() in valid_statuses if status else False


def validate_task_data(
    title: str,
    description: Optional[str] = None,
    assignee: Optional[str] = None,
    assignee_discord_id: Optional[str] = None,
    assignee_email: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    deadline: Optional[datetime] = None,
    task_id: Optional[str] = None,
) -> ValidationResult:
    """
    Validate task data before save.

    Checks all fields for validity and returns detailed errors/warnings.

    Args:
        title: Task title (required)
        description: Task description
        assignee: Assignee name
        assignee_discord_id: Discord user ID
        assignee_email: Email address
        priority: Priority level
        status: Task status
        deadline: Task deadline
        task_id: Task ID (if updating existing)

    Returns:
        ValidationResult with errors and warnings
    """
    errors = []
    warnings = []

    # Required field: title
    if not title or not title.strip():
        errors.append("Task title is required")
    elif len(title) > 500:
        errors.append("Task title exceeds 500 characters")
    elif len(title) < 3:
        warnings.append("Task title is very short - consider adding more detail")

    # Description length check
    if description and len(description) > 10000:
        errors.append("Task description exceeds 10000 characters")

    # Validate task ID format if provided
    if task_id and not validate_task_id(task_id):
        warnings.append(f"Task ID '{task_id}' doesn't match expected format TASK-YYYYMMDD-XXX")

    # Validate priority if provided
    if priority and not validate_priority(priority):
        errors.append(f"Invalid priority '{priority}'. Valid: low, medium, high, urgent")

    # Validate status if provided
    if status and not validate_status(status):
        errors.append(f"Invalid status '{status}'")

    # Validate Discord ID format if provided
    if assignee_discord_id:
        # Should be a numeric ID
        if not validate_discord_id(assignee_discord_id):
            warnings.append(f"Discord ID '{assignee_discord_id}' may not be a valid user ID (expected 17-19 digits)")

    # Validate email format if provided
    if assignee_email and not validate_email(assignee_email):
        warnings.append(f"Email '{assignee_email}' may not be valid")

    # Validate deadline
    if deadline:
        now = get_local_now()
        if deadline < now:
            warnings.append("Deadline is in the past")

    # Assignee without contact info
    if assignee and not any([assignee_discord_id, assignee_email]):
        warnings.append(f"Assignee '{assignee}' has no contact info (Discord ID or email)")

    if errors:
        return ValidationResult.failure(errors, warnings)
    return ValidationResult.success(warnings)


def validate_status_transition(
    from_status: str,
    to_status: str
) -> Tuple[bool, Optional[str]]:
    """
    Validate that a status transition is allowed.

    Some transitions don't make sense (e.g., cancelled -> in_progress).

    Args:
        from_status: Current status
        to_status: Target status

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Define invalid transitions
    invalid_transitions = {
        "completed": {"pending"},  # Can't go back to pending from completed
        "cancelled": {"pending", "in_progress"},  # Cancelled tasks need explicit reopen
    }

    # Define transitions that require confirmation (warnings)
    warn_transitions = {
        "completed": {"in_progress", "in_review"},  # Reopening completed tasks
        "cancelled": {"completed"},  # Marking cancelled as completed
    }

    from_status = from_status.lower()
    to_status = to_status.lower()

    # Check for invalid transitions
    if from_status in invalid_transitions:
        if to_status in invalid_transitions[from_status]:
            return False, f"Cannot transition from '{from_status}' to '{to_status}'"

    # Check for warning transitions
    if from_status in warn_transitions:
        if to_status in warn_transitions[from_status]:
            return True, f"Warning: Transitioning from '{from_status}' to '{to_status}' may need review"

    return True, None
