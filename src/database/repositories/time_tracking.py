"""
Repository for time tracking.

Handles timer start/stop, manual logging, and timesheet generation.
"""

import logging
import re
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from ..connection import get_database
from ..models import TimeEntryDB, ActiveTimerDB, TaskDB

logger = logging.getLogger(__name__)


def parse_duration(duration_str: str) -> int:
    """
    Parse duration string to minutes.

    Supports:
    - "2h30m" -> 150
    - "2.5h" -> 150
    - "90m" -> 90
    - "1d" -> 480 (8 hours)
    - "2h" -> 120
    """
    duration_str = duration_str.lower().strip()
    total_minutes = 0

    # Handle days
    day_match = re.search(r"(\d+(?:\.\d+)?)\s*d", duration_str)
    if day_match:
        days = float(day_match.group(1))
        total_minutes += int(days * 8 * 60)  # 8 hours per day

    # Handle hours
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*h", duration_str)
    if hour_match:
        hours = float(hour_match.group(1))
        total_minutes += int(hours * 60)

    # Handle minutes
    min_match = re.search(r"(\d+)\s*m(?:in)?", duration_str)
    if min_match:
        total_minutes += int(min_match.group(1))

    # If just a number, assume minutes
    if total_minutes == 0 and duration_str.isdigit():
        total_minutes = int(duration_str)

    return total_minutes


def format_duration(minutes: int) -> str:
    """Format minutes to readable string like '2h 30m'."""
    if minutes < 0:
        return "0m"

    hours = minutes // 60
    mins = minutes % 60

    if hours == 0:
        return f"{mins}m"
    elif mins == 0:
        return f"{hours}h"
    else:
        return f"{hours}h {mins}m"


class TimeTrackingRepository:
    """Repository for time tracking operations."""

    def __init__(self):
        self.db = get_database()

    async def start_timer(self, user_id: str, user_name: str, task_id: str) -> Optional[Dict[str, Any]]:
        """Start a timer for a task."""
        from sqlalchemy import select, func

        async with self.db.session() as session:
            # Check for existing active timer
            existing = await session.execute(
                select(ActiveTimerDB).where(ActiveTimerDB.user_id == user_id)
            )
            active = existing.scalar_one_or_none()

            if active:
                return {"error": "timer_running", "task_ref": active.task_ref}

            # Find the task
            task_result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == task_id)
            )
            task = task_result.scalar_one_or_none()

            if not task:
                return {"error": "task_not_found"}

            # Generate entry_id
            today = datetime.now().strftime("%Y%m%d")
            result = await session.execute(
                select(func.count()).select_from(TimeEntryDB).where(
                    TimeEntryDB.entry_id.like(f"TIME-{today}%")
                )
            )
            count = result.scalar() or 0
            entry_id = f"TIME-{today}-{count + 1:03d}"

            now = datetime.now()

            # Create time entry
            entry = TimeEntryDB(
                entry_id=entry_id,
                task_id=task.id,
                user_id=user_id,
                user_name=user_name,
                started_at=now,
                entry_type="timer",
                is_running=True,
            )
            session.add(entry)
            await session.flush()

            # Create active timer record
            active_timer = ActiveTimerDB(
                user_id=user_id,
                time_entry_id=entry.id,
                task_ref=task_id,
                started_at=now,
            )
            session.add(active_timer)
            await session.flush()

            logger.info(f"Started timer for {user_name} on {task_id}")
            return {
                "success": True,
                "entry_id": entry_id,
                "task_id": task_id,
                "task_title": task.title,
                "started_at": now,
            }

    async def stop_timer(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Stop the active timer for a user."""
        from sqlalchemy import select

        async with self.db.session() as session:
            # Find active timer
            result = await session.execute(
                select(ActiveTimerDB).where(ActiveTimerDB.user_id == user_id)
            )
            active = result.scalar_one_or_none()

            if not active:
                return None

            # Get the time entry
            entry_result = await session.execute(
                select(TimeEntryDB).where(TimeEntryDB.id == active.time_entry_id)
            )
            entry = entry_result.scalar_one_or_none()

            if not entry:
                await session.delete(active)
                return None

            # Calculate duration
            now = datetime.now()
            duration = int((now - entry.started_at).total_seconds() / 60)

            # Update entry
            entry.ended_at = now
            entry.duration_minutes = duration
            entry.is_running = False

            # Get task info
            task_result = await session.execute(
                select(TaskDB).where(TaskDB.id == entry.task_id)
            )
            task = task_result.scalar_one_or_none()

            # Calculate total time on task
            total_result = await session.execute(
                select(func.sum(TimeEntryDB.duration_minutes)).where(
                    TimeEntryDB.task_id == entry.task_id,
                    TimeEntryDB.is_running == False
                )
            )
            from sqlalchemy import func
            total_minutes = total_result.scalar() or 0

            # Delete active timer
            await session.delete(active)
            await session.flush()

            logger.info(f"Stopped timer for user {user_id}, duration: {duration}m")
            return {
                "success": True,
                "task_id": active.task_ref,
                "task_title": task.title if task else "Unknown",
                "duration_minutes": duration,
                "duration_formatted": format_duration(duration),
                "total_task_minutes": total_minutes,
                "total_formatted": format_duration(total_minutes),
            }

    async def get_active_timer(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get the active timer for a user."""
        from sqlalchemy import select

        async with self.db.session() as session:
            result = await session.execute(
                select(ActiveTimerDB).where(ActiveTimerDB.user_id == user_id)
            )
            active = result.scalar_one_or_none()

            if not active:
                return None

            # Calculate current duration
            now = datetime.now()
            duration = int((now - active.started_at).total_seconds() / 60)

            return {
                "task_ref": active.task_ref,
                "started_at": active.started_at,
                "duration_minutes": duration,
                "duration_formatted": format_duration(duration),
            }

    async def log_manual(
        self,
        user_id: str,
        user_name: str,
        task_id: str,
        duration_str: str,
        description: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Log time manually for a task."""
        from sqlalchemy import select, func

        minutes = parse_duration(duration_str)
        if minutes <= 0:
            return {"error": "invalid_duration"}

        async with self.db.session() as session:
            # Find the task
            task_result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == task_id)
            )
            task = task_result.scalar_one_or_none()

            if not task:
                return {"error": "task_not_found"}

            # Generate entry_id
            today = datetime.now().strftime("%Y%m%d")
            result = await session.execute(
                select(func.count()).select_from(TimeEntryDB).where(
                    TimeEntryDB.entry_id.like(f"TIME-{today}%")
                )
            )
            count = result.scalar() or 0
            entry_id = f"TIME-{today}-{count + 1:03d}"

            now = datetime.now()

            # Create time entry
            entry = TimeEntryDB(
                entry_id=entry_id,
                task_id=task.id,
                user_id=user_id,
                user_name=user_name,
                started_at=now,
                ended_at=now,
                duration_minutes=minutes,
                entry_type="manual",
                description=description,
                is_running=False,
            )
            session.add(entry)
            await session.flush()

            # Get total time on task
            total_result = await session.execute(
                select(func.sum(TimeEntryDB.duration_minutes)).where(
                    TimeEntryDB.task_id == task.id,
                    TimeEntryDB.is_running == False
                )
            )
            total_minutes = total_result.scalar() or 0

            logger.info(f"Logged {minutes}m for {user_name} on {task_id}")
            return {
                "success": True,
                "entry_id": entry_id,
                "task_id": task_id,
                "task_title": task.title,
                "duration_minutes": minutes,
                "duration_formatted": format_duration(minutes),
                "total_task_minutes": total_minutes,
                "total_formatted": format_duration(total_minutes),
            }

    async def get_task_time(self, task_id: str) -> Dict[str, Any]:
        """Get total time spent on a task."""
        from sqlalchemy import select, func

        async with self.db.session() as session:
            # Find the task
            task_result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == task_id)
            )
            task = task_result.scalar_one_or_none()

            if not task:
                return {"error": "task_not_found"}

            # Get entries
            entries_result = await session.execute(
                select(TimeEntryDB).where(
                    TimeEntryDB.task_id == task.id
                ).order_by(TimeEntryDB.started_at.desc())
            )
            entries = list(entries_result.scalars().all())

            # Calculate totals
            total_minutes = sum(e.duration_minutes for e in entries if not e.is_running)

            # Check for running timer
            running = next((e for e in entries if e.is_running), None)
            if running:
                running_duration = int((datetime.now() - running.started_at).total_seconds() / 60)
            else:
                running_duration = 0

            return {
                "task_id": task_id,
                "task_title": task.title,
                "total_minutes": total_minutes,
                "total_formatted": format_duration(total_minutes),
                "entry_count": len(entries),
                "is_running": running is not None,
                "running_duration": running_duration,
                "entries": [
                    {
                        "entry_id": e.entry_id,
                        "user_name": e.user_name,
                        "duration": format_duration(e.duration_minutes),
                        "type": e.entry_type,
                        "date": e.started_at.strftime("%Y-%m-%d %H:%M"),
                    }
                    for e in entries[:10]  # Last 10 entries
                ],
            }

    async def get_user_timesheet(
        self,
        user_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """Get timesheet for a user within a date range."""
        from sqlalchemy import select, func

        async with self.db.session() as session:
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.max.time())

            # Get entries
            result = await session.execute(
                select(TimeEntryDB).where(
                    TimeEntryDB.user_id == user_id,
                    TimeEntryDB.started_at >= start_dt,
                    TimeEntryDB.started_at <= end_dt,
                    TimeEntryDB.is_running == False
                ).order_by(TimeEntryDB.started_at)
            )
            entries = list(result.scalars().all())

            # Group by task
            tasks: Dict[int, Dict] = {}
            for entry in entries:
                if entry.task_id not in tasks:
                    # Get task info
                    task_result = await session.execute(
                        select(TaskDB).where(TaskDB.id == entry.task_id)
                    )
                    task = task_result.scalar_one_or_none()
                    tasks[entry.task_id] = {
                        "task_id": task.task_id if task else "Unknown",
                        "title": task.title if task else "Unknown",
                        "total_minutes": 0,
                        "entries": [],
                    }

                tasks[entry.task_id]["total_minutes"] += entry.duration_minutes
                tasks[entry.task_id]["entries"].append(entry)

            # Calculate total
            total_minutes = sum(t["total_minutes"] for t in tasks.values())

            return {
                "user_id": user_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_minutes": total_minutes,
                "total_formatted": format_duration(total_minutes),
                "tasks": [
                    {
                        "task_id": t["task_id"],
                        "title": t["title"],
                        "duration": format_duration(t["total_minutes"]),
                        "minutes": t["total_minutes"],
                    }
                    for t in sorted(tasks.values(), key=lambda x: x["total_minutes"], reverse=True)
                ],
            }

    async def get_team_timesheet(
        self,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """Get timesheet for the entire team."""
        from sqlalchemy import select, func

        async with self.db.session() as session:
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.max.time())

            # Get all entries
            result = await session.execute(
                select(TimeEntryDB).where(
                    TimeEntryDB.started_at >= start_dt,
                    TimeEntryDB.started_at <= end_dt,
                    TimeEntryDB.is_running == False
                ).order_by(TimeEntryDB.user_name, TimeEntryDB.started_at)
            )
            entries = list(result.scalars().all())

            # Group by user
            users: Dict[str, Dict] = {}
            for entry in entries:
                if entry.user_id not in users:
                    users[entry.user_id] = {
                        "user_id": entry.user_id,
                        "user_name": entry.user_name,
                        "total_minutes": 0,
                        "tasks": {},
                    }

                users[entry.user_id]["total_minutes"] += entry.duration_minutes

                # Track per task
                task_id = entry.task_id
                if task_id not in users[entry.user_id]["tasks"]:
                    task_result = await session.execute(
                        select(TaskDB).where(TaskDB.id == task_id)
                    )
                    task = task_result.scalar_one_or_none()
                    users[entry.user_id]["tasks"][task_id] = {
                        "task_id": task.task_id if task else "Unknown",
                        "title": task.title if task else "Unknown",
                        "minutes": 0,
                    }
                users[entry.user_id]["tasks"][task_id]["minutes"] += entry.duration_minutes

            # Calculate team total
            team_total = sum(u["total_minutes"] for u in users.values())

            return {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "team_total_minutes": team_total,
                "team_total_formatted": format_duration(team_total),
                "members": [
                    {
                        "user_name": u["user_name"],
                        "total_minutes": u["total_minutes"],
                        "total_formatted": format_duration(u["total_minutes"]),
                        "tasks": [
                            {
                                "task_id": t["task_id"],
                                "title": t["title"],
                                "duration": format_duration(t["minutes"]),
                            }
                            for t in sorted(u["tasks"].values(), key=lambda x: x["minutes"], reverse=True)
                        ],
                    }
                    for u in sorted(users.values(), key=lambda x: x["total_minutes"], reverse=True)
                ],
            }

    async def get_idle_timers(self, hours: int = 4) -> List[Dict[str, Any]]:
        """Get timers that have been running for too long."""
        from sqlalchemy import select

        threshold = datetime.now() - timedelta(hours=hours)

        async with self.db.session() as session:
            result = await session.execute(
                select(ActiveTimerDB).where(ActiveTimerDB.started_at < threshold)
            )
            timers = list(result.scalars().all())

            return [
                {
                    "user_id": t.user_id,
                    "task_ref": t.task_ref,
                    "started_at": t.started_at,
                    "duration_minutes": int((datetime.now() - t.started_at).total_seconds() / 60),
                }
                for t in timers
            ]


# Singleton
_time_tracking_repo: Optional[TimeTrackingRepository] = None


def get_time_tracking_repository() -> TimeTrackingRepository:
    """Get the time tracking repository singleton."""
    global _time_tracking_repo
    if _time_tracking_repo is None:
        _time_tracking_repo = TimeTrackingRepository()
    return _time_tracking_repo
