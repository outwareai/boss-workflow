"""
Attendance service for time clock system.

Handles business logic for:
- Processing clock in/out/break events
- Late detection based on timezone
- Team member working hours
"""

import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, date, time, timedelta
import pytz

from config import settings
from ..database.repositories.attendance import get_attendance_repository, AttendanceRepository
from ..database.models import AttendanceEventTypeEnum
from ..integrations.sheets import get_sheets_integration, SHEET_TEAM

logger = logging.getLogger(__name__)

# Event type to display name mapping
EVENT_DISPLAY_NAMES = {
    "clock_in": "in",
    "clock_out": "out",
    "break_start": "break in",
    "break_end": "break out",
}


class AttendanceService:
    """Service for attendance operations."""

    def __init__(self):
        self.repo: AttendanceRepository = get_attendance_repository()
        self.sheets = get_sheets_integration()
        self._team_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=15)

    async def _sync_to_sheets(
        self,
        record_id: str,
        user_name: str,
        event_type: str,
        event_time: datetime,
        channel_name: str,
        is_late: bool = False,
        late_minutes: int = 0,
    ) -> bool:
        """
        Sync an attendance event to Google Sheets.

        Args:
            record_id: The database record ID
            user_name: Staff member name
            event_type: clock_in, clock_out, break_start, break_end
            event_time: Local event time
            channel_name: Channel name (dev/admin)
            is_late: Whether the clock-in was late
            late_minutes: Minutes late

        Returns:
            True if synced successfully
        """
        try:
            # Determine late status display
            if event_type == "clock_in":
                late_display = "Yes" if is_late else "No"
            else:
                late_display = "-"

            # Get event display name
            event_display = EVENT_DISPLAY_NAMES.get(event_type, event_type)

            # Build record dict for sheets
            record_dict = {
                "record_id": record_id,
                "date": event_time.strftime("%Y-%m-%d"),
                "time": event_time.strftime("%H:%M"),
                "name": user_name,
                "event": event_display,
                "late": late_display,
                "late_min": late_minutes if is_late else 0,
                "channel": channel_name.replace("attendance-", ""),  # dev or admin
            }

            success = await self.sheets.add_attendance_log(record_dict)
            if success:
                logger.info(f"Synced attendance to Sheets: {record_id}")
            else:
                logger.warning(f"Failed to sync attendance to Sheets: {record_id}")
            return success

        except Exception as e:
            logger.error(f"Error syncing attendance to Sheets: {e}")
            return False

    async def _refresh_team_cache(self) -> None:
        """Refresh the team member cache from Sheets."""
        now = datetime.now()
        if self._cache_time and (now - self._cache_time) < self._cache_ttl:
            return  # Cache is still fresh

        try:
            team_members = await self.sheets.get_all_team_members()
            self._team_cache = {}

            for member in team_members:
                discord_id = str(member.get("Discord ID", ""))
                if discord_id:
                    # Parse grace period (minutes)
                    grace_str = str(member.get("Grace Period", ""))
                    try:
                        grace_period = int(grace_str) if grace_str else settings.default_grace_period_minutes
                    except ValueError:
                        grace_period = settings.default_grace_period_minutes

                    # Parse max break (minutes)
                    max_break_str = str(member.get("Max Break", ""))
                    try:
                        max_break = int(max_break_str) if max_break_str else 60
                    except ValueError:
                        max_break = 60

                    # Parse hours per day
                    hours_day_str = str(member.get("Hours/Day", ""))
                    try:
                        hours_per_day = int(hours_day_str) if hours_day_str else 8
                    except ValueError:
                        hours_per_day = 8

                    self._team_cache[discord_id] = {
                        "name": member.get("Name", ""),
                        "timezone": member.get("Timezone", settings.timezone),
                        "work_start": member.get("Work Start", f"{settings.default_work_start_hour:02d}:00"),
                        "work_end": member.get("Work End", f"{settings.default_work_end_hour:02d}:00"),
                        "role": member.get("Role", ""),
                        "grace_period": grace_period,
                        "max_break": max_break,
                        "hours_per_day": hours_per_day,
                    }

            self._cache_time = now
            logger.debug(f"Team cache refreshed: {len(self._team_cache)} members")

        except Exception as e:
            logger.error(f"Error refreshing team cache: {e}")

    async def get_team_member_info(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Get team member info from cache or Sheets."""
        await self._refresh_team_cache()
        return self._team_cache.get(discord_id)

    def calculate_late_status(
        self,
        clock_in_time_utc: datetime,
        user_timezone: str,
        work_start_time: str,
        grace_period_minutes: int = None,
    ) -> Tuple[bool, int, Optional[datetime]]:
        """
        Calculate if a clock-in is late.

        Args:
            clock_in_time_utc: The clock-in time in UTC
            user_timezone: The user's timezone (e.g., "Asia/Bangkok", "Asia/Kolkata")
            work_start_time: Expected start time in HH:MM format (local time)
            grace_period_minutes: Grace period in minutes (default from settings)

        Returns:
            Tuple of (is_late, late_minutes, expected_time_utc)

        Example:
            Staff: Mayank (India, UTC+5:30)
            Thailand work start: 9:00 AM ICT (UTC+7)

            If Thailand expects 9:00 AM:
            - 9:00 AM ICT = 7:30 AM IST (Mayank's local time)

            For a member working from India:
            - If work_start is "09:00" (Thailand time), they need to be online at 9:00 ICT
            - 9:00 ICT = 02:00 UTC
            - If they clock in at 9:30 ICT = 02:30 UTC, they are 30 min late
        """
        if grace_period_minutes is None:
            grace_period_minutes = settings.default_grace_period_minutes

        try:
            # Parse work start time
            work_hour, work_minute = map(int, work_start_time.split(":"))

            # Get the reference timezone (Thailand time - where work hours are defined)
            reference_tz = pytz.timezone(settings.timezone)  # Thailand

            # Get today in reference timezone
            now_reference = datetime.now(reference_tz)
            today_reference = now_reference.date()

            # Create expected start time in reference timezone
            expected_start_local = reference_tz.localize(
                datetime.combine(today_reference, time(work_hour, work_minute))
            )

            # Convert to UTC for comparison
            expected_start_utc = expected_start_local.astimezone(pytz.UTC)

            # Add grace period
            expected_with_grace_utc = expected_start_utc + timedelta(minutes=grace_period_minutes)

            # Compare (clock_in_time_utc should already be timezone-aware)
            if clock_in_time_utc.tzinfo is None:
                clock_in_time_utc = pytz.UTC.localize(clock_in_time_utc)

            is_late = clock_in_time_utc > expected_with_grace_utc
            late_minutes = 0

            if is_late:
                delta = clock_in_time_utc - expected_start_utc
                late_minutes = int(delta.total_seconds() / 60)

            return (is_late, late_minutes, expected_start_utc.replace(tzinfo=None))

        except Exception as e:
            logger.error(f"Error calculating late status: {e}")
            return (False, 0, None)

    async def process_clock_in(
        self,
        user_id: str,
        user_name: str,
        channel_id: str,
        channel_name: str,
    ) -> Dict[str, Any]:
        """
        Process a clock-in event.

        Returns:
            Dict with: success, emoji, is_late, late_minutes, message
        """
        now_utc = datetime.now(pytz.UTC)
        now_local = now_utc.astimezone(pytz.timezone(settings.timezone))

        # Check if already clocked in today
        existing = await self.repo.get_user_clock_in_today(user_id)
        if existing:
            return {
                "success": False,
                "emoji": "⚠️",
                "is_late": False,
                "late_minutes": 0,
                "message": "Already clocked in today",
            }

        # Get team member info for late detection
        member_info = await self.get_team_member_info(user_id)

        # Calculate late status
        is_late = False
        late_minutes = 0
        expected_time = None

        if member_info:
            work_start = member_info.get("work_start", f"{settings.default_work_start_hour:02d}:00")
            user_tz = member_info.get("timezone", settings.timezone)
            grace_period = member_info.get("grace_period", settings.default_grace_period_minutes)

            is_late, late_minutes, expected_time = self.calculate_late_status(
                clock_in_time_utc=now_utc,
                user_timezone=user_tz,
                work_start_time=work_start,
                grace_period_minutes=grace_period,
            )
        else:
            # Use default settings for unknown users
            is_late, late_minutes, expected_time = self.calculate_late_status(
                clock_in_time_utc=now_utc,
                user_timezone=settings.timezone,
                work_start_time=f"{settings.default_work_start_hour:02d}:00",
            )

        # Record the event
        record = await self.repo.record_event(
            user_id=user_id,
            user_name=user_name,
            event_type=AttendanceEventTypeEnum.CLOCK_IN.value,
            channel_id=channel_id,
            channel_name=channel_name,
            event_time=now_local.replace(tzinfo=None),
            event_time_utc=now_utc.replace(tzinfo=None),
            is_late=is_late,
            late_minutes=late_minutes,
            expected_time=expected_time,
        )

        if record:
            # Sync to Google Sheets
            await self._sync_to_sheets(
                record_id=record.record_id,
                user_name=user_name,
                event_type="clock_in",
                event_time=now_local.replace(tzinfo=None),
                channel_name=channel_name,
                is_late=is_late,
                late_minutes=late_minutes,
            )

            return {
                "success": True,
                "emoji": "✅",
                "is_late": is_late,
                "late_minutes": late_minutes,
                "message": f"Clocked in at {now_local.strftime('%H:%M')}",
                "record_id": record.record_id,
            }
        else:
            return {
                "success": False,
                "emoji": "❌",
                "is_late": False,
                "late_minutes": 0,
                "message": "Failed to record clock-in",
            }

    async def process_clock_out(
        self,
        user_id: str,
        user_name: str,
        channel_id: str,
        channel_name: str,
    ) -> Dict[str, Any]:
        """
        Process a clock-out event.

        Returns:
            Dict with: success, emoji, message, work_hours, pending_tasks_reminder
        """
        now_utc = datetime.now(pytz.UTC)
        now_local = now_utc.astimezone(pytz.timezone(settings.timezone))

        # Check if clocked in today
        clock_in = await self.repo.get_user_clock_in_today(user_id)
        if not clock_in:
            return {
                "success": False,
                "emoji": "⚠️",
                "message": "Haven't clocked in today",
                "work_hours": 0,
            }

        # Check if on break - end break first if needed
        break_status = await self.repo.get_user_break_status(user_id)
        if break_status == "on_break":
            # Auto-end break before clock out
            await self.repo.record_event(
                user_id=user_id,
                user_name=user_name,
                event_type=AttendanceEventTypeEnum.BREAK_END.value,
                channel_id=channel_id,
                channel_name=channel_name,
                event_time=now_local.replace(tzinfo=None),
                event_time_utc=now_utc.replace(tzinfo=None),
            )
            logger.info(f"Auto-ended break for {user_name} before clock out")

        # Record the clock out
        record = await self.repo.record_event(
            user_id=user_id,
            user_name=user_name,
            event_type=AttendanceEventTypeEnum.CLOCK_OUT.value,
            channel_id=channel_id,
            channel_name=channel_name,
            event_time=now_local.replace(tzinfo=None),
            event_time_utc=now_utc.replace(tzinfo=None),
        )

        # Calculate work hours
        work_hours = 0
        if clock_in:
            clock_in_utc = pytz.UTC.localize(clock_in.event_time_utc)
            work_duration = now_utc - clock_in_utc
            work_hours = round(work_duration.total_seconds() / 3600, 2)

        # Get pending tasks for this user (clock-out reminder)
        pending_tasks_reminder = await self._get_pending_tasks_reminder(user_name)

        if record:
            # Sync to Google Sheets
            await self._sync_to_sheets(
                record_id=record.record_id,
                user_name=user_name,
                event_type="clock_out",
                event_time=now_local.replace(tzinfo=None),
                channel_name=channel_name,
            )

            base_message = f"Clocked out at {now_local.strftime('%H:%M')}. Total: {work_hours}h"

            return {
                "success": True,
                "emoji": "👋",
                "message": base_message,
                "work_hours": work_hours,
                "record_id": record.record_id,
                "pending_tasks_reminder": pending_tasks_reminder,
            }
        else:
            return {
                "success": False,
                "emoji": "❌",
                "message": "Failed to record clock-out",
                "work_hours": 0,
            }

    async def _get_pending_tasks_reminder(self, user_name: str) -> Optional[str]:
        """
        Get a reminder of pending/in-progress tasks for the user.

        Called at clock-out time to remind staff what's still on their plate.
        """
        try:
            # Get tasks assigned to this user that are still active
            pending_tasks = []
            in_progress_tasks = []

            all_tasks = await self.sheets.get_daily_tasks()

            for task in all_tasks:
                assignee = task.get("Assignee", "").lower()
                status = task.get("Status", "").lower()
                task_id = task.get("Task ID", "")
                title = task.get("Title", "")[:40]  # Truncate for readability

                if user_name.lower() in assignee:
                    if status in ["pending", "needs_info"]:
                        pending_tasks.append((task_id, title))
                    elif status in ["in_progress", "in_review"]:
                        in_progress_tasks.append((task_id, title))

            # Build reminder if there are tasks
            if not pending_tasks and not in_progress_tasks:
                return None  # No reminder needed

            reminder_lines = ["📋 **Tasks Reminder Before You Go:**"]

            if in_progress_tasks:
                reminder_lines.append(f"\n🚧 **In Progress ({len(in_progress_tasks)}):**")
                for task_id, title in in_progress_tasks[:5]:  # Limit to 5
                    reminder_lines.append(f"  • {task_id}: {title}")
                if len(in_progress_tasks) > 5:
                    reminder_lines.append(f"  _...and {len(in_progress_tasks) - 5} more_")

            if pending_tasks:
                reminder_lines.append(f"\n⏳ **Pending ({len(pending_tasks)}):**")
                for task_id, title in pending_tasks[:5]:  # Limit to 5
                    reminder_lines.append(f"  • {task_id}: {title}")
                if len(pending_tasks) > 5:
                    reminder_lines.append(f"  _...and {len(pending_tasks) - 5} more_")

            if in_progress_tasks:
                reminder_lines.append("\n_Don't forget to update your task status before tomorrow!_")

            return "\n".join(reminder_lines)

        except Exception as e:
            logger.error(f"Error getting pending tasks reminder: {e}")
            return None

    async def process_break_toggle(
        self,
        user_id: str,
        user_name: str,
        channel_id: str,
        channel_name: str,
    ) -> Dict[str, Any]:
        """
        Process a break toggle event.

        Returns:
            Dict with: success, emoji, is_starting_break, message
        """
        now_utc = datetime.now(pytz.UTC)
        now_local = now_utc.astimezone(pytz.timezone(settings.timezone))

        # Check if clocked in today
        clock_in = await self.repo.get_user_clock_in_today(user_id)
        if not clock_in:
            return {
                "success": False,
                "emoji": "⚠️",
                "is_starting_break": False,
                "message": "Clock in first before taking a break",
            }

        # Check current break status
        break_status = await self.repo.get_user_break_status(user_id)

        if break_status == "on_break":
            # End break
            event_type = AttendanceEventTypeEnum.BREAK_END.value
            emoji = "💪"
            is_starting = False
            message = f"Break ended at {now_local.strftime('%H:%M')}"
        else:
            # Start break
            event_type = AttendanceEventTypeEnum.BREAK_START.value
            emoji = "☕"
            is_starting = True
            message = f"Break started at {now_local.strftime('%H:%M')}"

        # Record the event
        record = await self.repo.record_event(
            user_id=user_id,
            user_name=user_name,
            event_type=event_type,
            channel_id=channel_id,
            channel_name=channel_name,
            event_time=now_local.replace(tzinfo=None),
            event_time_utc=now_utc.replace(tzinfo=None),
        )

        if record:
            # Sync to Google Sheets
            await self._sync_to_sheets(
                record_id=record.record_id,
                user_name=user_name,
                event_type=event_type,
                event_time=now_local.replace(tzinfo=None),
                channel_name=channel_name,
            )

            return {
                "success": True,
                "emoji": emoji,
                "is_starting_break": is_starting,
                "message": message,
                "record_id": record.record_id,
            }
        else:
            return {
                "success": False,
                "emoji": "❌",
                "is_starting_break": False,
                "message": "Failed to record break",
            }

    async def process_event(
        self,
        user_id: str,
        user_name: str,
        event_type: str,
        channel_id: str,
        channel_name: str,
    ) -> Dict[str, Any]:
        """
        Process any attendance event.

        Args:
            event_type: "in", "out", or "break"

        Returns:
            Dict with result details
        """
        if event_type == "in":
            return await self.process_clock_in(user_id, user_name, channel_id, channel_name)
        elif event_type == "out":
            return await self.process_clock_out(user_id, user_name, channel_id, channel_name)
        elif event_type == "break":
            return await self.process_break_toggle(user_id, user_name, channel_id, channel_name)
        else:
            return {
                "success": False,
                "emoji": "❌",
                "message": f"Unknown event type: {event_type}",
            }

    async def record_boss_reported_attendance(
        self,
        affected_person: str,
        status_type: str,
        affected_date: str,
        reason: Optional[str],
        duration_minutes: Optional[int],
        reported_by: str,
        reported_by_id: str,
    ) -> Dict[str, Any]:
        """
        Record an attendance event reported by the boss.

        Args:
            affected_person: Name of the team member
            status_type: Type of attendance event (absence_reported, late_reported, etc.)
            affected_date: Date of the event (YYYY-MM-DD)
            reason: Optional reason/context
            duration_minutes: For late arrivals, minutes late
            reported_by: Name of the boss reporting
            reported_by_id: Boss's user ID

        Returns:
            Dict with success status, record_id, and notification status
        """
        from datetime import datetime

        try:
            # Parse the affected date
            try:
                affected_dt = datetime.strptime(affected_date, "%Y-%m-%d").date()
            except ValueError:
                affected_dt = date.today()

            # Look up team member by name to get Discord ID
            team_member = await self._find_team_member_by_name(affected_person)

            user_id = team_member.get("discord_id", "") if team_member else ""
            user_name = affected_person

            now_utc = datetime.now(pytz.UTC)
            now_local = now_utc.astimezone(pytz.timezone(settings.timezone))

            # Record the event in the database
            record = await self.repo.record_boss_reported_event(
                user_id=user_id,
                user_name=user_name,
                event_type=status_type,
                event_time=now_local.replace(tzinfo=None),
                event_time_utc=now_utc.replace(tzinfo=None),
                is_boss_reported=True,
                reported_by=reported_by,
                reported_by_id=reported_by_id,
                reason=reason,
                affected_date=affected_dt,
                duration_minutes=duration_minutes,
            )

            if not record:
                return {
                    "success": False,
                    "error": "Failed to create attendance record",
                }

            # Sync to Google Sheets with [BR] prefix
            await self._sync_boss_reported_to_sheets(
                record_id=record.record_id,
                user_name=user_name,
                status_type=status_type,
                affected_date=affected_dt,
                reason=reason,
                duration_minutes=duration_minutes,
                reported_by=reported_by,
            )

            # Send Discord notification to the affected team member
            notification_status = ""
            if user_id:
                notification_status = await self._send_attendance_notification(
                    user_id=user_id,
                    user_name=user_name,
                    status_type=status_type,
                    affected_date=affected_dt,
                    reason=reason,
                    team_member=team_member,
                )

            # Get emoji based on status type
            emoji = self._get_status_emoji(status_type)

            return {
                "success": True,
                "record_id": record.record_id,
                "emoji": emoji,
                "notification_status": notification_status,
            }

        except Exception as e:
            logger.error(f"Error recording boss-reported attendance: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _find_team_member_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a team member by name (case-insensitive partial match)."""
        await self._refresh_team_cache()

        name_lower = name.lower()

        # First try exact match in cache values
        for discord_id, member in self._team_cache.items():
            member_name = member.get("name", "").lower()
            if member_name == name_lower:
                return {"discord_id": discord_id, **member}

        # Then try partial match
        for discord_id, member in self._team_cache.items():
            member_name = member.get("name", "").lower()
            if name_lower in member_name or member_name in name_lower:
                return {"discord_id": discord_id, **member}

        # Try fetching from sheets directly
        try:
            team_members = await self.sheets.get_all_team_members()
            for member in team_members:
                member_name = str(member.get("Name", "")).lower()
                if name_lower in member_name or member_name in name_lower:
                    return {
                        "discord_id": str(member.get("Discord ID", "")),
                        "name": member.get("Name", ""),
                        "role": member.get("Role", ""),
                        "email": member.get("Email", ""),
                    }
        except Exception as e:
            logger.error(f"Error fetching team members: {e}")

        return None

    async def _sync_boss_reported_to_sheets(
        self,
        record_id: str,
        user_name: str,
        status_type: str,
        affected_date: date,
        reason: Optional[str],
        duration_minutes: Optional[int],
        reported_by: str,
    ) -> bool:
        """Sync a boss-reported attendance event to Google Sheets."""
        try:
            # Get display name for the status
            status_display = {
                "absence_reported": "[BR] Absent",
                "late_reported": f"[BR] Late ({duration_minutes}min)" if duration_minutes else "[BR] Late",
                "early_departure_reported": "[BR] Left Early",
                "sick_leave_reported": "[BR] Sick Leave",
                "excused_absence_reported": "[BR] Excused",
            }.get(status_type, f"[BR] {status_type}")

            # Build record dict for sheets
            record_dict = {
                "record_id": record_id,
                "date": affected_date.strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M"),
                "name": user_name,
                "event": status_display,
                "late": "Yes" if status_type == "late_reported" else "-",
                "late_min": duration_minutes if duration_minutes else 0,
                "channel": "boss",
                "notes": f"Reported by {reported_by}: {reason}" if reason else f"Reported by {reported_by}",
            }

            success = await self.sheets.add_attendance_log(record_dict)
            if success:
                logger.info(f"Synced boss-reported attendance to Sheets: {record_id}")
            else:
                logger.warning(f"Failed to sync boss-reported attendance to Sheets: {record_id}")
            return success

        except Exception as e:
            logger.error(f"Error syncing boss-reported attendance to Sheets: {e}")
            return False

    async def _send_attendance_notification(
        self,
        user_id: str,
        user_name: str,
        status_type: str,
        affected_date: date,
        reason: Optional[str],
        team_member: Optional[Dict[str, Any]],
    ) -> str:
        """Send Discord notification to the affected team member."""
        try:
            from ..integrations.discord import get_discord_integration

            discord = get_discord_integration()

            # Get status display
            status_display = {
                "absence_reported": "Absent",
                "late_reported": "Late",
                "early_departure_reported": "Left Early",
                "sick_leave_reported": "Sick Leave",
                "excused_absence_reported": "Excused Absence",
            }.get(status_type, status_type.replace("_", " ").title())

            # Build notification embed
            embed = {
                "title": "📋 Attendance Report",
                "description": f"The boss has recorded the following for <@{user_id}>:",
                "color": 0xFF9800,  # Orange
                "fields": [
                    {"name": "Status", "value": status_display, "inline": True},
                    {"name": "Date", "value": affected_date.strftime("%Y-%m-%d"), "inline": True},
                ],
                "footer": {"text": "Boss Workflow Attendance System"},
            }

            if reason:
                embed["fields"].append({"name": "Reason", "value": reason, "inline": False})

            # Determine which channel to post to based on role
            role = team_member.get("role", "").lower() if team_member else "dev"
            channel_type = "admin" if role in ["admin", "marketing"] else "dev"

            # Send via Discord webhook
            success = await discord.send_attendance_notification(
                embed=embed,
                channel_type=channel_type,
                mention_user_id=user_id,
            )

            if success:
                return "Notification sent to team member."
            else:
                return "Note: Could not send Discord notification."

        except Exception as e:
            logger.error(f"Error sending attendance notification: {e}")
            return "Note: Could not send Discord notification."

    def _get_status_emoji(self, status_type: str) -> str:
        """Get emoji for attendance status type."""
        emoji_map = {
            "absence_reported": "🚫",
            "late_reported": "⏰",
            "early_departure_reported": "🚪",
            "sick_leave_reported": "🤒",
            "excused_absence_reported": "✅",
        }
        return emoji_map.get(status_type, "📋")

    async def get_user_daily_summary(self, user_id: str) -> Dict[str, Any]:
        """Get a user's attendance summary for today."""
        today = date.today()
        events = await self.repo.get_user_events_for_date(user_id, today)

        if not events:
            return {
                "has_data": False,
                "message": "No attendance records for today",
            }

        clock_in = None
        clock_out = None
        break_start = None
        total_break_minutes = 0

        for event in events:
            if event.event_type == AttendanceEventTypeEnum.CLOCK_IN.value:
                clock_in = event
            elif event.event_type == AttendanceEventTypeEnum.CLOCK_OUT.value:
                clock_out = event
            elif event.event_type == AttendanceEventTypeEnum.BREAK_START.value:
                break_start = event
            elif event.event_type == AttendanceEventTypeEnum.BREAK_END.value:
                if break_start:
                    delta = event.event_time - break_start.event_time
                    total_break_minutes += delta.total_seconds() / 60
                    break_start = None

        work_hours = 0
        if clock_in and clock_out:
            delta = clock_out.event_time - clock_in.event_time
            work_hours = (delta.total_seconds() / 60 - total_break_minutes) / 60

        return {
            "has_data": True,
            "clock_in": clock_in.event_time.strftime("%H:%M") if clock_in else None,
            "clock_out": clock_out.event_time.strftime("%H:%M") if clock_out else None,
            "is_late": clock_in.is_late if clock_in else False,
            "late_minutes": clock_in.late_minutes if clock_in else 0,
            "break_minutes": round(total_break_minutes),
            "work_hours": round(work_hours, 2),
            "is_on_break": break_start is not None,
        }


# Singleton
_attendance_service: Optional[AttendanceService] = None


def get_attendance_service() -> AttendanceService:
    """Get the attendance service singleton."""
    global _attendance_service
    if _attendance_service is None:
        _attendance_service = AttendanceService()
    return _attendance_service
