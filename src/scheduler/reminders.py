"""
Reminder service for deadline and overdue task notifications.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import aiohttp

from config import settings
from ..integrations.sheets import get_sheets_integration
from ..integrations.discord import get_discord_integration
from ..integrations.calendar import get_calendar_integration
from ..models.task import TaskStatus

logger = logging.getLogger(__name__)


class ReminderService:
    """
    Service for sending deadline reminders and overdue alerts.

    Features:
    - Deadline reminders at specific intervals (2h, 1h, 30m before due)
    - Deduplication to prevent spam
    - Overdue alerts every Y hours
    - Telegram notifications to boss
    - Discord alerts
    """

    # Reminder intervals: remind at these times before deadline (in minutes)
    REMINDER_INTERVALS = [120, 60, 30]  # 2h, 1h, 30m before

    def __init__(self):
        self.sheets = get_sheets_integration()
        self.discord = get_discord_integration()
        self.calendar = get_calendar_integration()
        self.telegram_api_base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        # Track reminded tasks: {task_id: {interval: timestamp}}
        self._reminded_tasks: Dict[str, Dict[int, datetime]] = {}

    async def send_telegram_message(self, chat_id: str, message: str) -> bool:
        """Send a message via Telegram API."""
        if not settings.telegram_bot_token:
            logger.warning("Telegram bot token not configured")
            return False

        try:
            timeout = aiohttp.ClientTimeout(total=30.0)  # 30 second timeout for Telegram API
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.telegram_api_base}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": "Markdown"
                    }
                ) as response:
                    return response.status == 200

        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False

    async def check_and_send_deadline_reminders(self) -> int:
        """
        Check for upcoming deadlines and send reminders.

        Only sends ONE reminder per task per interval (2h, 1h, 30m).
        Prevents spam by tracking which tasks have been reminded.

        Returns the number of reminders sent.
        """
        reminders_sent = 0

        try:
            # Get tasks from sheets
            all_tasks = await self.sheets.get_daily_tasks()
            now = datetime.now()

            # Clean up old tracking data (tasks past deadline)
            self._cleanup_old_reminders(now)

            for task in all_tasks:
                deadline_str = task.get('Deadline', '')
                status = task.get('Status', '').lower()

                # Skip if no deadline or already completed/cancelled
                if not deadline_str or status in ['completed', 'cancelled', 'archived']:
                    continue

                try:
                    # Handle various deadline formats
                    if 'T' in deadline_str:
                        deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
                        if deadline.tzinfo:
                            deadline = deadline.replace(tzinfo=None)
                    else:
                        deadline = datetime.fromisoformat(deadline_str)
                except (ValueError, TypeError):
                    continue

                # Skip if deadline has passed (overdue handler will deal with it)
                if deadline <= now:
                    continue

                # Get task ID (try multiple column names)
                task_id = (
                    task.get('Task ID') or
                    task.get('TaskID') or
                    task.get('task_id') or
                    task.get('ID') or
                    None
                )

                # Skip tasks without proper ID
                if not task_id or task_id == 'Unknown':
                    continue

                # Check if we should send a reminder at any interval
                minutes_until_deadline = (deadline - now).total_seconds() / 60

                for interval in self.REMINDER_INTERVALS:
                    # Check if we're within this interval window (± 15 minutes)
                    if interval - 15 <= minutes_until_deadline <= interval + 15:
                        # Check if we already reminded for this interval
                        if self._should_remind(task_id, interval):
                            await self._send_deadline_reminder(task, deadline, interval)
                            self._mark_reminded(task_id, interval)
                            reminders_sent += 1
                            break  # Only one reminder per task per check

            logger.info(f"Sent {reminders_sent} deadline reminders")
            return reminders_sent

        except Exception as e:
            logger.error(f"Error checking deadline reminders: {e}")
            return reminders_sent

    def _should_remind(self, task_id: str, interval: int) -> bool:
        """Check if we should send a reminder for this task at this interval."""
        if task_id not in self._reminded_tasks:
            return True
        return interval not in self._reminded_tasks[task_id]

    def _mark_reminded(self, task_id: str, interval: int) -> None:
        """Mark that we've sent a reminder for this task at this interval."""
        if task_id not in self._reminded_tasks:
            self._reminded_tasks[task_id] = {}
        self._reminded_tasks[task_id][interval] = datetime.now()

    def _cleanup_old_reminders(self, now: datetime) -> None:
        """Remove tracking for tasks that are past their deadline or very old."""
        # Keep tracking data for 24 hours max
        cutoff = now - timedelta(hours=24)
        to_remove = []

        for task_id, intervals in self._reminded_tasks.items():
            # Remove if all reminders are old
            if all(ts < cutoff for ts in intervals.values()):
                to_remove.append(task_id)

        for task_id in to_remove:
            del self._reminded_tasks[task_id]

    async def _send_deadline_reminder(self, task: Dict[str, Any], deadline: datetime, interval: int) -> None:
        """Send a deadline reminder for a specific task."""
        # Get task ID (try multiple column names)
        task_id = (
            task.get('Task ID') or
            task.get('TaskID') or
            task.get('task_id') or
            task.get('ID') or
            'Unknown'
        )
        title = task.get('Title', 'Untitled')
        assignee = task.get('Assignee', 'Unassigned')

        time_remaining = deadline - datetime.now()
        total_minutes = int(time_remaining.total_seconds() // 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60

        # Format time remaining nicely
        if hours > 0:
            time_str = f"{hours}h {minutes}m"
        else:
            time_str = f"{minutes} minutes"

        message = f"""⏰ **Deadline Reminder**

**{task_id}**: {title}
**Assignee:** {assignee}
**Deadline:** {deadline.strftime('%b %d, %Y %I:%M %p')}
**Time Remaining:** {time_str}

This task is due soon!"""

        # Send to boss only
        if settings.telegram_boss_chat_id:
            await self.send_telegram_message(settings.telegram_boss_chat_id, message)

        # Don't spam Discord with every reminder - only post at 1h mark
        if interval == 60:
            await self.discord.post_alert(
                title="Deadline Approaching",
                message=f"**{task_id}**: {title}\nAssignee: {assignee}\nDue in ~1 hour",
                alert_type="warning"
            )

        logger.info(f"Sent {interval}m reminder for {task_id} to boss")

    async def check_and_send_overdue_alerts(self) -> int:
        """
        Check for overdue tasks and send alerts.

        Returns the number of alerts sent.
        """
        alerts_sent = 0

        try:
            overdue_tasks = await self.sheets.get_overdue_tasks()

            if not overdue_tasks:
                return 0

            # Build summary message
            summary_lines = ["🚨 **Overdue Tasks Alert**", ""]

            for task in overdue_tasks:
                task_id = task.get('Task ID', 'Unknown')
                title = task.get('Title', 'Untitled')
                assignee = task.get('Assignee', 'Unassigned')
                deadline_str = task.get('Deadline', '')

                try:
                    deadline = datetime.fromisoformat(deadline_str)
                    overdue_by = datetime.now() - deadline
                    overdue_hours = int(overdue_by.total_seconds() // 3600)
                    overdue_text = f"{overdue_hours}h overdue"
                except ValueError:
                    overdue_text = "Overdue"

                summary_lines.append(f"• **{task_id}**: {title[:40]}")
                summary_lines.append(f"  Assignee: {assignee} | {overdue_text}")
                summary_lines.append("")

            summary_lines.append(f"**Total:** {len(overdue_tasks)} overdue task(s)")

            message = "\n".join(summary_lines)

            # Send to boss
            if settings.telegram_boss_chat_id:
                await self.send_telegram_message(settings.telegram_boss_chat_id, message)
                alerts_sent += 1

            # Post to Discord
            await self.discord.post_alert(
                title="Overdue Tasks",
                message=f"{len(overdue_tasks)} task(s) are overdue!",
                alert_type="error"
            )

            logger.info(f"Sent overdue alert for {len(overdue_tasks)} tasks")
            return alerts_sent

        except Exception as e:
            logger.error(f"Error checking overdue tasks: {e}")
            return alerts_sent

    async def send_eod_reminder(self) -> bool:
        """Send end-of-day reminder for pending tasks."""
        try:
            # Get today's tasks
            daily_tasks = await self.sheets.get_daily_tasks()

            # Filter pending tasks
            pending = [t for t in daily_tasks if t.get('Status') in ['pending', 'in_progress']]

            if not pending:
                message = "✅ **End of Day Summary**\n\nAll tasks for today are complete! Great job!"
            else:
                message_lines = ["📋 **End of Day Reminder**", ""]
                message_lines.append(f"You have {len(pending)} task(s) still pending:", "")

                for task in pending[:10]:  # Limit to 10
                    task_id = task.get('Task ID', '')
                    title = task.get('Title', '')[:40]
                    status = task.get('Status', 'pending')
                    message_lines.append(f"• [{status.upper()}] {task_id}: {title}")

                if len(pending) > 10:
                    message_lines.append(f"... and {len(pending) - 10} more")

                message_lines.append("")
                message_lines.append("Don't forget to update task statuses!")

                message = "\n".join(message_lines)

            # Send to boss
            if settings.telegram_boss_chat_id:
                await self.send_telegram_message(settings.telegram_boss_chat_id, message)

            return True

        except Exception as e:
            logger.error(f"Error sending EOD reminder: {e}")
            return False

    async def send_conversation_timeout_reminder(
        self,
        user_id: str,
        conversation_id: str
    ) -> bool:
        """Send reminder about timed-out conversation."""
        message = """⏰ **Conversation Timeout**

Your task creation conversation has been inactive for 30 minutes.

Options:
• `/resume` - Continue where you left off
• Send a new message to start fresh

The conversation will auto-finalize in 1.5 hours if not resumed."""

        return await self.send_telegram_message(user_id, message)

    async def send_auto_finalize_notification(
        self,
        user_id: str,
        task_id: str,
        task_title: str
    ) -> bool:
        """Notify user that their task was auto-finalized."""
        message = f"""✅ **Task Auto-Created**

Your pending task has been automatically created with default values:

**{task_id}**: {task_title}

The task has been posted to Discord and added to Google Sheets.

If you need to make changes, use:
• `/note {task_id} [your note]` to add notes
• `/delay {task_id} [deadline] [reason]` to change deadline"""

        return await self.send_telegram_message(user_id, message)


# Singleton instance
reminder_service = ReminderService()


def get_reminder_service() -> ReminderService:
    """Get the reminder service instance."""
    return reminder_service
