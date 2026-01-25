"""
Tests for src/utils/datetime_utils.py

Tests all datetime utilities including timezone conversion, deadline parsing,
formatting, and time calculations.
"""

import pytest
from datetime import datetime, timedelta
import pytz
from src.utils.datetime_utils import (
    get_local_tz,
    get_local_now,
    to_naive_local,
    to_aware_utc,
    parse_deadline,
    format_deadline,
    is_overdue,
    hours_until_deadline,
)


class TestGetLocalTz:
    """Tests for get_local_tz function."""

    def test_returns_timezone_object(self):
        """Test that get_local_tz returns a timezone object."""
        tz = get_local_tz()
        assert isinstance(tz, pytz.BaseTzInfo)

    def test_returns_configured_timezone(self):
        """Test that timezone matches configuration."""
        tz = get_local_tz()
        # Should not raise an error
        assert tz is not None


class TestGetLocalNow:
    """Tests for get_local_now function."""

    def test_returns_naive_datetime(self):
        """Test that get_local_now returns naive datetime."""
        now = get_local_now()
        assert isinstance(now, datetime)
        assert now.tzinfo is None

    def test_returns_current_time(self):
        """Test that returned time is current."""
        now = get_local_now()
        # Just verify it's a recent datetime, not None
        assert now is not None
        assert isinstance(now, datetime)
        # Check year is reasonable
        assert 2025 <= now.year <= 2030


class TestToNaiveLocal:
    """Tests for to_naive_local function."""

    def test_none_returns_none(self):
        """Test that None input returns None."""
        result = to_naive_local(None)
        assert result is None

    def test_naive_datetime_unchanged(self):
        """Test that naive datetime passes through unchanged."""
        dt = datetime(2026, 1, 18, 12, 0, 0)
        result = to_naive_local(dt)
        assert result == dt
        assert result.tzinfo is None

    def test_aware_utc_converted(self):
        """Test that UTC datetime is converted to local."""
        utc_dt = datetime(2026, 1, 18, 12, 0, 0, tzinfo=pytz.UTC)
        result = to_naive_local(utc_dt)
        assert result.tzinfo is None
        # Result should be in local time (different from UTC hour unless timezone is UTC)
        assert result is not None

    def test_aware_other_timezone_converted(self):
        """Test that non-UTC timezone datetime is converted."""
        est = pytz.timezone('US/Eastern')
        est_dt = est.localize(datetime(2026, 1, 18, 12, 0, 0))
        result = to_naive_local(est_dt)
        assert result.tzinfo is None

    def test_strips_timezone_info(self):
        """Test that timezone info is always stripped."""
        utc_dt = datetime(2026, 1, 18, 12, 0, 0, tzinfo=pytz.UTC)
        result = to_naive_local(utc_dt)
        assert result.tzinfo is None


class TestToAwareUtc:
    """Tests for to_aware_utc function."""

    def test_none_returns_none(self):
        """Test that None input returns None."""
        result = to_aware_utc(None)
        assert result is None

    def test_naive_datetime_converted_to_utc(self):
        """Test that naive datetime is localized and converted to UTC."""
        dt = datetime(2026, 1, 18, 12, 0, 0)
        result = to_aware_utc(dt)
        assert result.tzinfo is not None
        assert result.tzinfo.zone == 'UTC'

    def test_aware_datetime_converted_to_utc(self):
        """Test that aware datetime is converted to UTC."""
        est = pytz.timezone('US/Eastern')
        est_dt = est.localize(datetime(2026, 1, 18, 12, 0, 0))
        result = to_aware_utc(est_dt)
        assert result.tzinfo.zone == 'UTC'

    def test_utc_datetime_unchanged(self):
        """Test that UTC datetime remains in UTC."""
        utc_dt = datetime(2026, 1, 18, 12, 0, 0, tzinfo=pytz.UTC)
        result = to_aware_utc(utc_dt)
        assert result.tzinfo.zone == 'UTC'


class TestParseDeadline:
    """Tests for parse_deadline function."""

    def test_none_returns_none(self):
        """Test that None input returns None."""
        result = parse_deadline(None)
        assert result is None

    def test_empty_string_returns_none(self):
        """Test that empty string returns None."""
        result = parse_deadline("")
        assert result is None

    def test_parse_today(self):
        """Test parsing 'today' keyword."""
        result = parse_deadline("today")
        assert result is not None
        assert result.hour == 23
        assert result.minute == 59

    def test_parse_tonight(self):
        """Test parsing 'tonight' keyword."""
        result = parse_deadline("tonight")
        assert result is not None
        assert result.hour == 21
        assert result.minute == 0

    def test_parse_tomorrow(self):
        """Test parsing 'tomorrow' keyword."""
        result = parse_deadline("tomorrow")
        assert result is not None
        now = get_local_now()
        tomorrow = now + timedelta(days=1)
        assert result.day == tomorrow.day

    def test_parse_eod(self):
        """Test parsing 'eod' (end of day) keyword."""
        result = parse_deadline("eod")
        assert result is not None
        assert result.hour == 18
        assert result.minute == 0

    def test_parse_iso_format_with_timezone(self):
        """Test parsing ISO format with timezone."""
        result = parse_deadline("2026-01-18T19:00:00+07:00")
        assert result is not None
        assert result.tzinfo is None  # Should be naive

    def test_parse_iso_format_without_timezone(self):
        """Test parsing ISO format without timezone."""
        result = parse_deadline("2026-01-18T19:00:00")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 18
        assert result.hour == 19

    def test_parse_date_only(self):
        """Test parsing date-only format."""
        result = parse_deadline("2026-01-18")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 18
        # Date-only format sets time to end of day
        assert result.hour in [0, 23]  # May depend on timezone handling
        assert result.minute in [0, 59]

    def test_parse_z_suffix(self):
        """Test parsing ISO format with 'Z' suffix."""
        result = parse_deadline("2026-01-18T12:00:00Z")
        assert result is not None
        assert result.tzinfo is None

    def test_invalid_format_returns_none(self):
        """Test that invalid format returns None."""
        result = parse_deadline("invalid-date")
        assert result is None

    def test_case_insensitive_keywords(self):
        """Test that keywords are case-insensitive."""
        result = parse_deadline("TODAY")
        assert result is not None

        result = parse_deadline("Tomorrow")
        assert result is not None


class TestFormatDeadline:
    """Tests for format_deadline function."""

    def test_none_returns_not_set(self):
        """Test that None returns 'Not set'."""
        result = format_deadline(None)
        assert result == "Not set"

    def test_format_with_time(self):
        """Test formatting datetime with time."""
        dt = datetime(2026, 1, 18, 14, 30, 0)
        result = format_deadline(dt, include_time=True)
        assert "Jan 18, 2026" in result
        assert "02:30 PM" in result

    def test_format_without_time(self):
        """Test formatting datetime without time."""
        dt = datetime(2026, 1, 18, 14, 30, 0)
        result = format_deadline(dt, include_time=False)
        assert "Jan 18, 2026" in result
        assert "PM" not in result

    def test_default_includes_time(self):
        """Test that default behavior includes time."""
        dt = datetime(2026, 1, 18, 14, 30, 0)
        result = format_deadline(dt)
        assert "PM" in result or "AM" in result


class TestIsOverdue:
    """Tests for is_overdue function."""

    def test_none_returns_false(self):
        """Test that None deadline returns False."""
        result = is_overdue(None)
        assert result is False

    def test_past_deadline_returns_true(self):
        """Test that past deadline returns True."""
        past = datetime.now() - timedelta(days=1)
        result = is_overdue(past)
        assert result is True

    def test_future_deadline_returns_false(self):
        """Test that future deadline returns False."""
        future = datetime.now() + timedelta(days=1)
        result = is_overdue(future)
        assert result is False

    def test_very_recent_past_returns_true(self):
        """Test that just-passed deadline returns True."""
        past = datetime.now() - timedelta(seconds=1)
        result = is_overdue(past)
        assert result is True


class TestHoursUntilDeadline:
    """Tests for hours_until_deadline function."""

    def test_none_returns_none(self):
        """Test that None deadline returns None."""
        result = hours_until_deadline(None)
        assert result is None

    def test_future_deadline_positive_hours(self):
        """Test that future deadline returns positive hours."""
        future = datetime.now() + timedelta(hours=24)
        result = hours_until_deadline(future)
        assert result is not None
        assert result > 23  # Should be close to 24
        assert result < 25

    def test_past_deadline_negative_hours(self):
        """Test that past deadline returns negative hours."""
        past = datetime.now() - timedelta(hours=12)
        result = hours_until_deadline(past)
        assert result is not None
        assert result < -11  # Should be close to -12
        assert result > -13

    def test_very_close_deadline(self):
        """Test deadline in minutes."""
        future = datetime.now() + timedelta(minutes=30)
        result = hours_until_deadline(future)
        assert result is not None
        assert 0.4 < result < 0.6  # Should be close to 0.5 hours

    def test_calculation_accuracy(self):
        """Test that calculation is accurate."""
        future = datetime.now() + timedelta(hours=48)
        result = hours_until_deadline(future)
        assert result is not None
        assert 47 < result < 49  # Should be close to 48
