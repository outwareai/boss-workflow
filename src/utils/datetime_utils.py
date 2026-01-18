"""
Centralized datetime and timezone utilities.

All datetime handling should use these functions to ensure consistency
between timezone-aware and timezone-naive datetimes across the application.
"""

from datetime import datetime, timedelta
from typing import Optional
import pytz

from config import settings


def get_local_tz() -> pytz.BaseTzInfo:
    """Get the configured local timezone."""
    return pytz.timezone(settings.timezone)


def get_local_now() -> datetime:
    """Get current time in local timezone (naive)."""
    local_tz = get_local_tz()
    return datetime.now(local_tz).replace(tzinfo=None)


def to_naive_local(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert any datetime to naive local time for database storage.

    PostgreSQL TIMESTAMP WITHOUT TIME ZONE expects naive datetimes.
    This converts timezone-aware datetimes to local time and strips tzinfo.

    Args:
        dt: Datetime to convert (can be aware or naive)

    Returns:
        Naive datetime in local timezone, or None if input is None
    """
    if dt is None:
        return None

    if dt.tzinfo is not None:
        # Convert to local timezone first
        local_tz = get_local_tz()
        local_dt = dt.astimezone(local_tz)
        # Strip timezone info for naive storage
        return local_dt.replace(tzinfo=None)

    # Already naive, assume it's in local time
    return dt


def to_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert naive datetime to timezone-aware UTC.

    Useful for API responses and external services that expect aware datetimes.

    Args:
        dt: Naive datetime (assumed to be in local time)

    Returns:
        Timezone-aware datetime in UTC
    """
    if dt is None:
        return None

    if dt.tzinfo is not None:
        # Already aware, convert to UTC
        return dt.astimezone(pytz.UTC)

    # Naive - assume local time, localize then convert to UTC
    local_tz = get_local_tz()
    local_dt = local_tz.localize(dt)
    return local_dt.astimezone(pytz.UTC)


def parse_deadline(deadline_str: str) -> Optional[datetime]:
    """
    Parse a deadline string into a naive local datetime.

    Handles various formats:
    - ISO format with timezone: "2026-01-18T19:00:00+07:00"
    - ISO format without timezone: "2026-01-18T19:00:00"
    - Date only: "2026-01-18"
    - Relative: "today", "tomorrow", "tonight"

    Args:
        deadline_str: String representation of deadline

    Returns:
        Naive datetime in local timezone, or None if parsing fails
    """
    if not deadline_str:
        return None

    deadline_str = deadline_str.strip().lower()
    now = get_local_now()

    # Handle relative dates
    if deadline_str == "today":
        return now.replace(hour=23, minute=59, second=0, microsecond=0)
    elif deadline_str == "tonight":
        return now.replace(hour=21, minute=0, second=0, microsecond=0)
    elif deadline_str == "tomorrow":
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=23, minute=59, second=0, microsecond=0)
    elif deadline_str == "eod":
        return now.replace(hour=18, minute=0, second=0, microsecond=0)

    # Try ISO format parsing
    try:
        # Handle 'Z' suffix (UTC)
        if deadline_str.endswith('z'):
            deadline_str = deadline_str[:-1] + '+00:00'

        dt = datetime.fromisoformat(deadline_str)
        return to_naive_local(dt)
    except ValueError:
        pass

    # Try date-only format
    try:
        dt = datetime.strptime(deadline_str, "%Y-%m-%d")
        return dt.replace(hour=23, minute=59, second=0, microsecond=0)
    except ValueError:
        pass

    return None


def format_deadline(dt: Optional[datetime], include_time: bool = True) -> str:
    """
    Format a deadline for display.

    Args:
        dt: Datetime to format
        include_time: Whether to include time component

    Returns:
        Formatted string or "Not set" if None
    """
    if dt is None:
        return "Not set"

    if include_time:
        return dt.strftime("%b %d, %Y %I:%M %p")
    return dt.strftime("%b %d, %Y")


def is_overdue(deadline: Optional[datetime]) -> bool:
    """
    Check if a deadline has passed.

    Args:
        deadline: Naive datetime in local time

    Returns:
        True if deadline has passed
    """
    if deadline is None:
        return False

    now = get_local_now()
    return deadline < now


def hours_until_deadline(deadline: Optional[datetime]) -> Optional[float]:
    """
    Get hours remaining until deadline.

    Args:
        deadline: Naive datetime in local time

    Returns:
        Hours until deadline (negative if overdue), or None
    """
    if deadline is None:
        return None

    now = get_local_now()
    delta = deadline - now
    return delta.total_seconds() / 3600
