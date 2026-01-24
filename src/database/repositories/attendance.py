"""
Attendance repository for time clock system.

Handles CRUD operations for attendance records:
- Clock in/out events
- Break start/end events
- Daily and weekly summaries
- Late tracking
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta

from sqlalchemy import select, update, func, and_, or_, cast, Date
from sqlalchemy.exc import IntegrityError

from ..connection import get_database
from ..models import AttendanceRecordDB, AttendanceEventTypeEnum
from ..exceptions import DatabaseConstraintError, DatabaseOperationError, EntityNotFoundError

logger = logging.getLogger(__name__)


class AttendanceRepository:
    """Repository for attendance operations."""

    def __init__(self):
        self.db = get_database()
        self._counter = 0  # For generating record IDs

    def _generate_record_id(self) -> str:
        """Generate a unique record ID: ATT-YYYYMMDD-XXX."""
        today = datetime.now().strftime("%Y%m%d")
        self._counter += 1
        return f"ATT-{today}-{self._counter:03d}"

    async def record_event(
        self,
        user_id: str,
        user_name: str,
        event_type: str,
        channel_id: str,
        channel_name: str,
        event_time: datetime,
        event_time_utc: datetime,
        is_late: bool = False,
        late_minutes: int = 0,
        expected_time: Optional[datetime] = None,
    ) -> Optional[AttendanceRecordDB]:
        """Record a new attendance event."""
        async with self.db.session() as session:
            try:
                record = AttendanceRecordDB(
                    record_id=self._generate_record_id(),
                    user_id=user_id,
                    user_name=user_name,
                    event_type=event_type,
                    event_time=event_time,
                    event_time_utc=event_time_utc,
                    channel_id=channel_id,
                    channel_name=channel_name,
                    is_late=is_late,
                    late_minutes=late_minutes,
                    expected_time=expected_time,
                    synced_to_sheets=False,
                )
                session.add(record)
                await session.flush()

                logger.info(f"Recorded attendance: {user_name} {event_type} at {event_time}")
                return record

            except IntegrityError as e:
                logger.error(f"Duplicate attendance record: {e}", exc_info=True)
                raise DatabaseConstraintError(f"Duplicate attendance record for {user_name} at {event_time}") from e
            except Exception as e:
                logger.error(f"Error recording attendance: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to record attendance for {user_name}") from e

    async def record_boss_reported_event(
        self,
        user_id: str,
        user_name: str,
        event_type: str,
        event_time: datetime,
        event_time_utc: datetime,
        is_boss_reported: bool = True,
        reported_by: Optional[str] = None,
        reported_by_id: Optional[str] = None,
        reason: Optional[str] = None,
        affected_date: Optional[date] = None,
        duration_minutes: Optional[int] = None,
    ) -> Optional[AttendanceRecordDB]:
        """
        Record a boss-reported attendance event.

        Unlike regular events, these:
        - Don't have a channel_id/channel_name (reported via Telegram)
        - Have is_boss_reported=True
        - Have reported_by and reported_by_id set
        - May have a reason and affected_date different from event_time
        """
        async with self.db.session() as session:
            try:
                record = AttendanceRecordDB(
                    record_id=self._generate_record_id(),
                    user_id=user_id or "unknown",
                    user_name=user_name,
                    event_type=event_type,
                    event_time=event_time,
                    event_time_utc=event_time_utc,
                    channel_id="telegram-boss",
                    channel_name="boss-report",
                    is_late=event_type == "late_reported",
                    late_minutes=duration_minutes or 0,
                    expected_time=None,
                    synced_to_sheets=False,
                    is_boss_reported=is_boss_reported,
                    reported_by=reported_by,
                    reported_by_id=reported_by_id,
                    reason=reason,
                    affected_date=affected_date,
                    duration_minutes=duration_minutes,
                    notification_sent=False,
                )
                session.add(record)
                await session.flush()

                logger.info(f"Recorded boss-reported attendance: {user_name} {event_type} for {affected_date}")
                return record

            except IntegrityError as e:
                logger.error(f"Duplicate boss-reported attendance: {e}", exc_info=True)
                raise DatabaseConstraintError(f"Duplicate boss-reported attendance for {user_name} on {affected_date}") from e
            except Exception as e:
                logger.error(f"Error recording boss-reported attendance: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to record boss-reported attendance for {user_name}") from e

    async def get_user_events_for_date(
        self,
        user_id: str,
        target_date: date,
    ) -> List[AttendanceRecordDB]:
        """Get all events for a user on a specific date."""
        async with self.db.session() as session:
            try:
                start_of_day = datetime.combine(target_date, datetime.min.time())
                end_of_day = datetime.combine(target_date, datetime.max.time())

                result = await session.execute(
                    select(AttendanceRecordDB)
                    .where(
                        and_(
                            AttendanceRecordDB.user_id == user_id,
                            AttendanceRecordDB.event_time >= start_of_day,
                            AttendanceRecordDB.event_time <= end_of_day,
                        )
                    )
                    .order_by(AttendanceRecordDB.event_time)
                )
                return list(result.scalars().all())
            except Exception as e:
                logger.error(f"Error fetching events for user {user_id} on {target_date}: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to fetch events for {user_id}") from e

    async def get_user_last_event(
        self,
        user_id: str,
        event_types: Optional[List[str]] = None,
    ) -> Optional[AttendanceRecordDB]:
        """Get the user's most recent event (optionally filtered by type)."""
        async with self.db.session() as session:
            query = select(AttendanceRecordDB).where(
                AttendanceRecordDB.user_id == user_id
            )

            if event_types:
                query = query.where(AttendanceRecordDB.event_type.in_(event_types))

            query = query.order_by(AttendanceRecordDB.event_time.desc()).limit(1)

            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_user_last_event_today(
        self,
        user_id: str,
        event_types: Optional[List[str]] = None,
    ) -> Optional[AttendanceRecordDB]:
        """Get the user's most recent event today (optionally filtered by type)."""
        async with self.db.session() as session:
            today = date.today()
            start_of_day = datetime.combine(today, datetime.min.time())
            end_of_day = datetime.combine(today, datetime.max.time())

            query = select(AttendanceRecordDB).where(
                and_(
                    AttendanceRecordDB.user_id == user_id,
                    AttendanceRecordDB.event_time >= start_of_day,
                    AttendanceRecordDB.event_time <= end_of_day,
                )
            )

            if event_types:
                query = query.where(AttendanceRecordDB.event_type.in_(event_types))

            query = query.order_by(AttendanceRecordDB.event_time.desc()).limit(1)

            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_user_clock_in_today(self, user_id: str) -> Optional[AttendanceRecordDB]:
        """Check if user has clocked in today."""
        return await self.get_user_last_event_today(
            user_id,
            event_types=[AttendanceEventTypeEnum.CLOCK_IN.value]
        )

    async def get_user_break_status(self, user_id: str) -> Optional[str]:
        """
        Check user's current break status.
        Returns: "on_break" if on break, "not_on_break" if returned, None if never took break today
        """
        today_events = await self.get_user_events_for_date(user_id, date.today())

        # Find last break event
        last_break_event = None
        for event in reversed(today_events):
            if event.event_type in [AttendanceEventTypeEnum.BREAK_START.value,
                                     AttendanceEventTypeEnum.BREAK_END.value]:
                last_break_event = event
                break

        if not last_break_event:
            return None  # No break taken today

        if last_break_event.event_type == AttendanceEventTypeEnum.BREAK_START.value:
            return "on_break"
        else:
            return "not_on_break"

    async def get_weekly_summary(
        self,
        user_id: str,
        week_start: date,
    ) -> Dict[str, Any]:
        """Get weekly attendance summary for a user."""
        async with self.db.session() as session:
            try:
                week_end = week_start + timedelta(days=6)
                start_dt = datetime.combine(week_start, datetime.min.time())
                end_dt = datetime.combine(week_end, datetime.max.time())

                result = await session.execute(
                    select(AttendanceRecordDB)
                    .where(
                        and_(
                            AttendanceRecordDB.user_id == user_id,
                            AttendanceRecordDB.event_time >= start_dt,
                            AttendanceRecordDB.event_time <= end_dt,
                        )
                    )
                    .order_by(AttendanceRecordDB.event_time)
                )
                events = list(result.scalars().all())
            except Exception as e:
                logger.error(f"Error fetching weekly summary for {user_id}: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to fetch weekly summary for {user_id}") from e

            # Calculate stats
            days_worked = set()
            total_work_minutes = 0
            total_break_minutes = 0
            late_days = 0
            total_late_minutes = 0
            clock_ins = []
            clock_outs = []

            current_clock_in = None
            current_break_start = None

            for event in events:
                event_date = event.event_time.date()

                if event.event_type == AttendanceEventTypeEnum.CLOCK_IN.value:
                    days_worked.add(event_date)
                    current_clock_in = event
                    clock_ins.append(event.event_time)
                    if event.is_late:
                        late_days += 1
                        total_late_minutes += event.late_minutes

                elif event.event_type == AttendanceEventTypeEnum.CLOCK_OUT.value:
                    if current_clock_in:
                        work_duration = (event.event_time - current_clock_in.event_time).total_seconds() / 60
                        total_work_minutes += work_duration
                    clock_outs.append(event.event_time)
                    current_clock_in = None

                elif event.event_type == AttendanceEventTypeEnum.BREAK_START.value:
                    current_break_start = event

                elif event.event_type == AttendanceEventTypeEnum.BREAK_END.value:
                    if current_break_start:
                        break_duration = (event.event_time - current_break_start.event_time).total_seconds() / 60
                        total_break_minutes += break_duration
                        total_work_minutes -= break_duration  # Subtract break from work time
                    current_break_start = None

            # Calculate averages
            avg_start = None
            avg_end = None
            if clock_ins:
                avg_start_minutes = sum(
                    ci.hour * 60 + ci.minute for ci in clock_ins
                ) / len(clock_ins)
                avg_start = f"{int(avg_start_minutes // 60):02d}:{int(avg_start_minutes % 60):02d}"
            if clock_outs:
                avg_end_minutes = sum(
                    co.hour * 60 + co.minute for co in clock_outs
                ) / len(clock_outs)
                avg_end = f"{int(avg_end_minutes // 60):02d}:{int(avg_end_minutes % 60):02d}"

            return {
                "user_id": user_id,
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "days_worked": len(days_worked),
                "total_hours": round(total_work_minutes / 60, 2),
                "avg_start": avg_start,
                "avg_end": avg_end,
                "late_days": late_days,
                "total_late_minutes": total_late_minutes,
                "total_break_minutes": round(total_break_minutes, 0),
            }

    async def get_team_weekly_summary(
        self,
        week_start: date,
    ) -> List[Dict[str, Any]]:
        """Get weekly attendance summary for all users."""
        async with self.db.session() as session:
            try:
                week_end = week_start + timedelta(days=6)
                start_dt = datetime.combine(week_start, datetime.min.time())
                end_dt = datetime.combine(week_end, datetime.max.time())

                # Get unique users who have records in this week
                result = await session.execute(
                    select(AttendanceRecordDB.user_id, AttendanceRecordDB.user_name)
                    .where(
                        and_(
                            AttendanceRecordDB.event_time >= start_dt,
                            AttendanceRecordDB.event_time <= end_dt,
                        )
                    )
                    .distinct()
                )
                users = result.all()

                summaries = []
                for user_id, user_name in users:
                    summary = await self.get_weekly_summary(user_id, week_start)
                    summary["user_name"] = user_name
                    summaries.append(summary)

                return summaries
            except Exception as e:
                logger.error(f"Error fetching team weekly summary: {e}", exc_info=True)
                raise DatabaseOperationError("Failed to fetch team weekly summary") from e

    async def get_unsynced_records(self, limit: int = 100) -> List[AttendanceRecordDB]:
        """Get records that haven't been synced to Sheets."""
        async with self.db.session() as session:
            try:
                result = await session.execute(
                    select(AttendanceRecordDB)
                    .where(AttendanceRecordDB.synced_to_sheets == False)
                    .order_by(AttendanceRecordDB.event_time)
                    .limit(limit)
                )
                return list(result.scalars().all())
            except Exception as e:
                logger.error(f"Error fetching unsynced records: {e}", exc_info=True)
                raise DatabaseOperationError("Failed to fetch unsynced attendance records") from e

    async def mark_synced(self, record_ids: List[int]) -> int:
        """Mark records as synced to Sheets."""
        if not record_ids:
            return 0

        async with self.db.session() as session:
            try:
                result = await session.execute(
                    update(AttendanceRecordDB)
                    .where(AttendanceRecordDB.id.in_(record_ids))
                    .values(synced_to_sheets=True)
                )

                if result.rowcount == 0:
                    logger.warning(f"No records updated when marking as synced: {record_ids}")
                    raise EntityNotFoundError(f"No attendance records found with IDs: {record_ids}")

                logger.info(f"Marked {result.rowcount} attendance records as synced")
                return result.rowcount
            except EntityNotFoundError:
                raise
            except Exception as e:
                logger.error(f"Error marking records as synced: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to mark attendance records as synced") from e

    async def get_daily_report(self, target_date: date) -> Dict[str, Any]:
        """Get daily attendance report."""
        async with self.db.session() as session:
            try:
                start_dt = datetime.combine(target_date, datetime.min.time())
                end_dt = datetime.combine(target_date, datetime.max.time())

                result = await session.execute(
                    select(AttendanceRecordDB)
                    .where(
                        and_(
                            AttendanceRecordDB.event_time >= start_dt,
                            AttendanceRecordDB.event_time <= end_dt,
                        )
                    )
                    .order_by(AttendanceRecordDB.event_time)
                )
                events = list(result.scalars().all())
            except Exception as e:
                logger.error(f"Error fetching daily report for {target_date}: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to fetch daily report for {target_date}") from e

            # Group by user
            by_user = {}
            for event in events:
                if event.user_id not in by_user:
                    by_user[event.user_id] = {
                        "user_name": event.user_name,
                        "events": [],
                    }
                by_user[event.user_id]["events"].append({
                    "type": event.event_type,
                    "time": event.event_time.strftime("%H:%M"),
                    "is_late": event.is_late,
                    "late_minutes": event.late_minutes,
                })

            return {
                "date": target_date.isoformat(),
                "total_events": len(events),
                "unique_users": len(by_user),
                "late_count": sum(1 for e in events if e.is_late),
                "by_user": by_user,
            }

    async def to_dict(self, record: AttendanceRecordDB) -> Dict[str, Any]:
        """Convert attendance record to dictionary."""
        return {
            "id": record.id,
            "record_id": record.record_id,
            "user_id": record.user_id,
            "user_name": record.user_name,
            "event_type": record.event_type,
            "event_time": record.event_time.isoformat(),
            "event_time_utc": record.event_time_utc.isoformat(),
            "channel_id": record.channel_id,
            "channel_name": record.channel_name,
            "is_late": record.is_late,
            "late_minutes": record.late_minutes,
            "expected_time": record.expected_time.isoformat() if record.expected_time else None,
            "synced_to_sheets": record.synced_to_sheets,
            "created_at": record.created_at.isoformat(),
        }


# Singleton
_attendance_repository: Optional[AttendanceRepository] = None


def get_attendance_repository() -> AttendanceRepository:
    """Get the attendance repository singleton."""
    global _attendance_repository
    if _attendance_repository is None:
        _attendance_repository = AttendanceRepository()
    return _attendance_repository
