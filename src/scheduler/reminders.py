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
    - Deadline reminders X hours before due
    - Overdue alerts every Y hours
    - Telegram notifications to boss and assignees
    - Discord alerts
    """

    def __init__(self):
        self.sheets = get_sheets_integration()
        self.discord = get_discord_integration()
        self.calendar = get_calendar_integration()
        self.telegram_api_base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    async def send_telegram_message(self, chat_id: str, message: str) -> bool:
        """Send a message via Telegram API."""
        if not settings.telegram_bot_token:
            logger.warning("Telegram bot token not configured")
            return False

        try:
            async with aiohttp.ClientSession() as session:
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

        Returns the number of reminders sent.
        """
        reminders_sent = 0
        hours_before = settings.deadline_reminder_hours_before

        try:
            # Get tasks from sheets
            all_tasks = await self.sheets.get_daily_tasks()

            now = datetime.now()
            reminder_threshold = now + timedelta(hours=hours_before)

            for task in all_tasks:
                deadline_str = task.get('Deadline', '')
                status = task.get('Status', '')

                # Skip if no deadline or already completed/cancelled
                if not deadline_str or status in ['completed', 'cancelled']:
                    continue

                try:
                    deadline = datetime.fromisoformat(deadline_str)
                except ValueError:
                    continue

                # Check if within reminder window
                if now < deadline <= reminder_threshold:
                    await self._send_deadline_reminder(task, deadline)
                    reminders_sent += 1

            logger.info(f"Sent {reminders_sent} deadline reminders")
            return reminders_sent

        except Exception as e:
            logger.error(f"Error checking deadline reminders: {e}")
            return reminders_sent

    async def _send_deadline_reminder(self, task: Dict[str, Any], deadline: datetime) -> None:
        """Send a deadline reminder for a specific task."""
        task_id = task.get('Task ID', 'Unknown')
        title = task.get('Title', 'Untitled')
        assignee = task.get('Assignee', 'Unassigned')

        time_remaining = deadline - datetime.now()
        hours = int(time_remaining.total_seconds() // 3600)
        minutes = int((time_remaining.total_seconds() % 3600) // 60)

        message = f"""⏰ **Deadline Reminder**

**{task_id}**: {title}
**Assignee:** {assignee}
**Deadline:** {deadline.strftime('%b %d, %Y %I:%M %p')}
**Time Remaining:** {hours}h {minutes}m

This task is due soon!"""

        # Send to boss
        if settings.telegram_boss_chat_id:
            await self.send_telegram_message(settings.telegram_boss_chat_id, message)

        # Post to Discord
        await self.discord.post_alert(
            title="Deadline Reminder",
            message=f"**{task_id}**: {title}\nDue in {hours}h {minutes}m",
            alert_type="warning"
        )

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
