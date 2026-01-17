"""
Repository for recurring tasks.

Handles CRUD operations and schedule management for recurring tasks.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import re

from ..connection import get_database
from ..models import RecurringTaskDB

logger = logging.getLogger(__name__)


class RecurrenceCalculator:
    """Calculate next run times for recurring patterns."""

    WEEKDAYS = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
        "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6
    }

    @classmethod
    def parse_pattern(cls, pattern: str) -> Dict[str, Any]:
        """Parse a recurrence pattern string."""
        pattern = pattern.lower().strip()

        if not pattern.startswith("every:"):
            pattern = f"every:{pattern}"

        value = pattern.replace("every:", "").strip()

        # Daily patterns
        if value == "day":
            return {"type": "daily", "interval": 1}
        if value == "weekday":
            return {"type": "weekday"}

        # Weekly patterns (day names)
        if value in cls.WEEKDAYS:
            return {"type": "weekly", "days": [cls.WEEKDAYS[value]]}

        # Multiple days: monday,wednesday,friday
        if "," in value:
            days = [cls.WEEKDAYS.get(d.strip()) for d in value.split(",")]
            days = [d for d in days if d is not None]
            if days:
                return {"type": "weekly", "days": sorted(days)}

        # Monthly patterns: 1st, 15th, last
        if value in ("1st", "first"):
            return {"type": "monthly", "day": 1}
        if value == "15th":
            return {"type": "monthly", "day": 15}
        if value == "last":
            return {"type": "monthly", "day": -1}

        # Interval patterns: 2weeks, 3days
        interval_match = re.match(r"(\d+)(weeks?|days?)", value)
        if interval_match:
            num = int(interval_match.group(1))
            unit = interval_match.group(2)
            if "week" in unit:
                return {"type": "interval", "days": num * 7}
            else:
                return {"type": "interval", "days": num}

        # Default to daily if unknown
        return {"type": "daily", "interval": 1}

    @classmethod
    def parse_time(cls, time_str: str) -> tuple:
        """Parse time string to (hour, minute)."""
        time_str = time_str.lower().strip()

        # Handle 12-hour format with am/pm
        am_pm_match = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", time_str)
        if am_pm_match:
            hour = int(am_pm_match.group(1))
            minute = int(am_pm_match.group(2) or 0)
            period = am_pm_match.group(3)

            if period == "pm" and hour < 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0

            return (hour, minute)

        # Handle 24-hour format: 09:00, 18:30
        if ":" in time_str:
            parts = time_str.split(":")
            return (int(parts[0]), int(parts[1]))

        # Just hour
        return (int(time_str), 0)

    @classmethod
    def calculate_next_run(cls, pattern: str, time_str: str, after: datetime = None) -> datetime:
        """Calculate the next run time after a given datetime."""
        if after is None:
            after = datetime.now()

        parsed = cls.parse_pattern(pattern)
        hour, minute = cls.parse_time(time_str)

        if parsed["type"] == "daily":
            # Next occurrence at this time
            next_run = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= after:
                next_run += timedelta(days=1)
            return next_run

        elif parsed["type"] == "weekday":
            next_run = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= after:
                next_run += timedelta(days=1)
            # Skip weekends
            while next_run.weekday() >= 5:
                next_run += timedelta(days=1)
            return next_run

        elif parsed["type"] == "weekly":
            target_days = parsed["days"]
            current_day = after.weekday()
            next_run = after.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # Find next matching day
            for i in range(8):  # Check next 7 days
                check_day = (current_day + i) % 7
                if check_day in target_days:
                    candidate = next_run + timedelta(days=i)
                    if candidate > after:
                        return candidate
                    elif i == 0 and candidate <= after:
                        continue

            # If nothing found, go to first target day next week
            days_ahead = target_days[0] - current_day
            if days_ahead <= 0:
                days_ahead += 7
            return next_run + timedelta(days=days_ahead)

        elif parsed["type"] == "monthly":
            day = parsed["day"]
            next_run = after.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if day == -1:  # Last day of month
                # Go to next month, then back one day
                if after.month == 12:
                    next_month = after.replace(year=after.year + 1, month=1, day=1)
                else:
                    next_month = after.replace(month=after.month + 1, day=1)
                next_run = next_month - timedelta(days=1)
                next_run = next_run.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= after:
                    # Go to last day of next month
                    if next_month.month == 12:
                        next_next = next_month.replace(year=next_month.year + 1, month=1, day=1)
                    else:
                        next_next = next_month.replace(month=next_month.month + 1, day=1)
                    next_run = next_next - timedelta(days=1)
                    next_run = next_run.replace(hour=hour, minute=minute, second=0, microsecond=0)
            else:
                try:
                    next_run = after.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    if next_run <= after:
                        if after.month == 12:
                            next_run = next_run.replace(year=after.year + 1, month=1)
                        else:
                            next_run = next_run.replace(month=after.month + 1)
                except ValueError:
                    # Day doesn't exist in this month, go to next
                    if after.month == 12:
                        next_run = after.replace(year=after.year + 1, month=1, day=day)
                    else:
                        next_run = after.replace(month=after.month + 1, day=day)

            return next_run

        elif parsed["type"] == "interval":
            days = parsed["days"]
            next_run = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= after:
                next_run += timedelta(days=days)
            return next_run

        # Default fallback
        return after + timedelta(days=1)

    @classmethod
    def is_valid_pattern(cls, pattern: str) -> bool:
        """Check if a pattern is valid."""
        try:
            parsed = cls.parse_pattern(pattern)
            return parsed.get("type") is not None
        except Exception:
            return False


class RecurringTaskRepository:
    """Repository for recurring task operations."""

    def __init__(self):
        self.db = get_database()

    async def create(self, data: Dict[str, Any]) -> Optional[RecurringTaskDB]:
        """Create a new recurring task."""
        from sqlalchemy import select, func

        async with self.db.session() as session:
            # Generate recurring_id
            today = datetime.now().strftime("%Y%m%d")
            result = await session.execute(
                select(func.count()).select_from(RecurringTaskDB).where(
                    RecurringTaskDB.recurring_id.like(f"REC-{today}%")
                )
            )
            count = result.scalar() or 0
            recurring_id = f"REC-{today}-{count + 1:03d}"

            # Calculate next run
            pattern = data.get("pattern", "every:day")
            time_str = data.get("time", "09:00")
            next_run = RecurrenceCalculator.calculate_next_run(pattern, time_str)

            recurring = RecurringTaskDB(
                recurring_id=recurring_id,
                title=data.get("title"),
                description=data.get("description"),
                assignee=data.get("assignee"),
                priority=data.get("priority", "medium"),
                task_type=data.get("task_type", "task"),
                estimated_effort=data.get("estimated_effort"),
                tags=data.get("tags"),
                pattern=pattern,
                time=time_str,
                timezone=data.get("timezone", "Asia/Bangkok"),
                is_active=True,
                next_run=next_run,
                created_by=data.get("created_by"),
            )

            session.add(recurring)
            await session.flush()

            logger.info(f"Created recurring task {recurring_id}")
            return recurring

    async def get_by_id(self, recurring_id: str) -> Optional[RecurringTaskDB]:
        """Get a recurring task by ID."""
        from sqlalchemy import select

        async with self.db.session() as session:
            result = await session.execute(
                select(RecurringTaskDB).where(RecurringTaskDB.recurring_id == recurring_id)
            )
            return result.scalar_one_or_none()

    async def get_active(self) -> List[RecurringTaskDB]:
        """Get all active recurring tasks."""
        from sqlalchemy import select

        async with self.db.session() as session:
            result = await session.execute(
                select(RecurringTaskDB).where(RecurringTaskDB.is_active == True).order_by(RecurringTaskDB.next_run)
            )
            return list(result.scalars().all())

    async def get_due_now(self) -> List[RecurringTaskDB]:
        """Get recurring tasks that are due to run."""
        from sqlalchemy import select

        now = datetime.now()

        async with self.db.session() as session:
            result = await session.execute(
                select(RecurringTaskDB).where(
                    RecurringTaskDB.is_active == True,
                    RecurringTaskDB.next_run <= now
                ).order_by(RecurringTaskDB.next_run)
            )
            return list(result.scalars().all())

    async def update_after_run(self, recurring_id: str) -> bool:
        """Update recurring task after it runs."""
        from sqlalchemy import select

        async with self.db.session() as session:
            result = await session.execute(
                select(RecurringTaskDB).where(RecurringTaskDB.recurring_id == recurring_id)
            )
            recurring = result.scalar_one_or_none()

            if not recurring:
                return False

            now = datetime.now()
            recurring.last_run = now
            recurring.instances_created += 1
            recurring.next_run = RecurrenceCalculator.calculate_next_run(
                recurring.pattern, recurring.time, now
            )

            await session.flush()
            logger.info(f"Updated recurring task {recurring_id}, next run: {recurring.next_run}")
            return True

    async def pause(self, recurring_id: str) -> bool:
        """Pause a recurring task."""
        from sqlalchemy import select

        async with self.db.session() as session:
            result = await session.execute(
                select(RecurringTaskDB).where(RecurringTaskDB.recurring_id == recurring_id)
            )
            recurring = result.scalar_one_or_none()

            if not recurring:
                return False

            recurring.is_active = False
            await session.flush()
            logger.info(f"Paused recurring task {recurring_id}")
            return True

    async def resume(self, recurring_id: str) -> bool:
        """Resume a paused recurring task."""
        from sqlalchemy import select

        async with self.db.session() as session:
            result = await session.execute(
                select(RecurringTaskDB).where(RecurringTaskDB.recurring_id == recurring_id)
            )
            recurring = result.scalar_one_or_none()

            if not recurring:
                return False

            recurring.is_active = True
            # Recalculate next run from now
            recurring.next_run = RecurrenceCalculator.calculate_next_run(
                recurring.pattern, recurring.time
            )
            await session.flush()
            logger.info(f"Resumed recurring task {recurring_id}")
            return True

    async def delete(self, recurring_id: str) -> bool:
        """Delete a recurring task."""
        from sqlalchemy import select, delete

        async with self.db.session() as session:
            result = await session.execute(
                select(RecurringTaskDB).where(RecurringTaskDB.recurring_id == recurring_id)
            )
            recurring = result.scalar_one_or_none()

            if not recurring:
                return False

            await session.delete(recurring)
            await session.flush()
            logger.info(f"Deleted recurring task {recurring_id}")
            return True

    async def get_all(self) -> List[RecurringTaskDB]:
        """Get all recurring tasks."""
        from sqlalchemy import select

        async with self.db.session() as session:
            result = await session.execute(
                select(RecurringTaskDB).order_by(RecurringTaskDB.created_at.desc())
            )
            return list(result.scalars().all())


# Singleton
_recurring_repo: Optional[RecurringTaskRepository] = None


def get_recurring_repository() -> RecurringTaskRepository:
    """Get the recurring task repository singleton."""
    global _recurring_repo
    if _recurring_repo is None:
        _recurring_repo = RecurringTaskRepository()
    return _recurring_repo
