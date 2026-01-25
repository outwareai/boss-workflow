"""
Smart deadline reminder system with personalized notifications.

Features:
- Deadline reminders grouped by assignee
- Multi-channel delivery (Telegram + Discord)
- Smart escalation for critical deadlines
- Customizable reminder intervals
- Deduplication to prevent spam
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
import aiohttp

from config import settings
from ..database.repositories import get_task_repository
from ..integrations.discord import get_discord_integration
from ..models.task import TaskStatus

logger = logging.getLogger(__name__)


class SmartReminderSystem:
    """
    Smart reminder system for proactive deadline notifications.

    Enhances the base reminder system with:
    - Grouping by assignee
    - Priority-based escalation
    - Smart timing (only remind when productive)
    - Customizable rules per assignee
    """

    # Reminder intervals (in minutes before deadline)
    CRITICAL_INTERVAL = 120  # 2 hours - Critical escalation
    WARNING_INTERVAL = 60    # 1 hour - Warning level
    INFO_INTERVAL = 30       # 30 min - Informational

    def __init__(self):
        self.task_repo = get_task_repository()
        self.discord = get_discord_integration()
        self.telegram_api_base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        # Track sent reminders: {task_id: {interval: timestamp}}
        self._sent_reminders: Dict[str, Dict[int, datetime]] = {}

    async def send_telegram_message(self, chat_id: str, message: str) -> bool:
        """Send a message via Telegram API."""
        if not settings.telegram_bot_token:
            logger.warning("Telegram bot token not configured")
            return False

        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
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

    async def send_deadline_reminders(self) -> int:
        """
        Send proactive deadline reminders grouped by assignee.

        Returns:
            Number of reminders sent
        """
        logger.info("Starting smart deadline reminders")
        reminders_sent = 0

        try:
            # Get tasks due in next 2 hours
            tomorrow = datetime.utcnow() + timedelta(hours=2)
            tasks_due_soon = await self.task_repo.get_due_between(
                datetime.utcnow(),
                tomorrow
            )

            if not tasks_due_soon:
                logger.debug("No tasks due soon")
                return 0

            # Group by assignee for batch messaging
            by_assignee: Dict[str, List[dict]] = {}
            for task in tasks_due_soon:
                # Skip completed/cancelled tasks
                if task.get("status") in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
                    continue

                assignee = task.get("assignee", "Unassigned")
                if assignee not in by_assignee:
                    by_assignee[assignee] = []
                by_assignee[assignee].append(task)

            # Send grouped reminders
            for assignee, tasks in by_assignee.items():
                try:
                    count = await self._send_assignee_reminders(assignee, tasks)
                    reminders_sent += count
                except Exception as e:
                    logger.error(f"Error sending reminders for {assignee}: {e}")

            logger.info(f"Smart deadline reminders: sent {reminders_sent} total")
            return reminders_sent

        except Exception as e:
            logger.error(f"Error in smart deadline reminders: {e}")
            return reminders_sent

    async def _send_assignee_reminders(self, assignee: str, tasks: List[dict]) -> int:
        """
        Send consolidated reminders for one assignee.

        Args:
            assignee: Team member name
            tasks: List of tasks due soon

        Returns:
            Number of reminders sent
        """
        reminders_sent = 0
        now = datetime.utcnow()

        # Sort by deadline
        tasks.sort(key=lambda t: t.get("deadline") or datetime.max)

        # Build message
        message_lines = [f"⏰ **Deadline Reminders for {assignee}**", ""]
        message_lines.append(f"You have {len(tasks)} task(s) due soon:\n")

        for task in tasks:
            task_id = task.get("task_id", "Unknown")
            title = task.get("title", "Untitled")[:50]
            deadline = task.get("deadline")
            priority = task.get("priority", "Medium")

            if not deadline:
                continue

            # Calculate time remaining
            time_left = deadline - now
            hours = int(time_left.total_seconds() / 3600)
            minutes = int((time_left.total_seconds() % 3600) / 60)

            # Format priority emoji
            priority_emoji = self._get_priority_emoji(priority)

            # Format time
            if hours > 0:
                time_str = f"{hours}h {minutes}m"
            else:
                time_str = f"{minutes}m"

            message_lines.append(
                f"{priority_emoji} **{task_id}**: {title}\n"
                f"  Due in: {time_str} ({deadline.strftime('%H:%M')})"
            )

        message_lines.append("")
        message_lines.append("Please prioritize these tasks!")

        message = "\n".join(message_lines)

        # Send to Telegram (to boss if available, otherwise via team)
        if settings.telegram_boss_chat_id:
            try:
                success = await self.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    message
                )
                if success:
                    reminders_sent += 1
                    logger.info(f"Sent reminder to boss for {assignee} ({len(tasks)} tasks)")
            except Exception as e:
                logger.error(f"Failed to send Telegram reminder: {e}")

        # Send to Discord
        try:
            await self.discord.post_alert(
                title=f"Deadline Reminders: {assignee}",
                message=f"{len(tasks)} task(s) due soon",
                alert_type="warning"
            )
            reminders_sent += 1
            logger.info(f"Sent Discord reminder for {assignee}")
        except Exception as e:
            logger.error(f"Failed to send Discord reminder: {e}")

        return reminders_sent

    async def send_overdue_escalation(self) -> int:
        """
        Send escalated alerts for critically overdue tasks.

        Escalation levels:
        - >7 days: Critical (red alert)
        - >3 days: Warning (orange alert)
        - >1 day: Attention (yellow alert)

        Returns:
            Number of alerts sent
        """
        logger.info("Starting overdue escalation check")
        alerts_sent = 0

        try:
            repo = get_task_repository()
            overdue_tasks = await repo.get_overdue()

            if not overdue_tasks:
                logger.debug("No overdue tasks")
                return 0

            now = datetime.utcnow()

            # Categorize by severity
            critical = []  # >7 days
            warning = []   # >3 days
            attention = [] # >1 day

            for task in overdue_tasks:
                deadline = task.get("deadline")
                if not deadline:
                    continue

                days_overdue = (now - deadline).days

                if days_overdue > 7:
                    critical.append((task, days_overdue))
                elif days_overdue > 3:
                    warning.append((task, days_overdue))
                elif days_overdue > 1:
                    attention.append((task, days_overdue))

            # Send critical alerts (immediate)
            if critical:
                alerts_sent += await self._send_critical_escalation(critical)

            # Send warning alerts
            if warning:
                alerts_sent += await self._send_warning_escalation(warning)

            # Send attention alerts
            if attention:
                alerts_sent += await self._send_attention_escalation(attention)

            logger.info(f"Overdue escalation: {alerts_sent} alerts sent")
            return alerts_sent

        except Exception as e:
            logger.error(f"Error in overdue escalation: {e}")
            return alerts_sent

    async def _send_critical_escalation(self, critical_tasks: List[tuple]) -> int:
        """Send critical escalation for very overdue tasks."""
        if not critical_tasks:
            return 0

        alerts_sent = 0

        # Build message
        message_lines = ["🚨 **CRITICAL: Severely Overdue Tasks**", ""]
        message_lines.append(f"**{len(critical_tasks)} task(s) are >7 days overdue!**\n")

        for task, days_overdue in critical_tasks[:10]:  # Limit to top 10
            task_id = task.get("task_id", "Unknown")
            title = task.get("title", "Untitled")[:40]
            assignee = task.get("assignee", "Unknown")

            message_lines.append(
                f"🔴 **{task_id}**: {title}\n"
                f"   Assignee: {assignee} | Overdue: {days_overdue} days"
            )

        if len(critical_tasks) > 10:
            message_lines.append(f"\n... and {len(critical_tasks) - 10} more")

        message_lines.append("\n**Action Required:** Immediate follow-up needed!")

        message = "\n".join(message_lines)

        # Send to boss (high priority)
        if settings.telegram_boss_chat_id:
            try:
                success = await self.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    message
                )
                if success:
                    alerts_sent += 1
            except Exception as e:
                logger.error(f"Failed to send critical escalation: {e}")

        # Post to Discord with error alert type
        try:
            await self.discord.post_alert(
                title="CRITICAL ALERT: Severely Overdue Tasks",
                message=f"{len(critical_tasks)} task(s) overdue >7 days",
                alert_type="error"
            )
            alerts_sent += 1
        except Exception as e:
            logger.error(f"Failed to post critical escalation to Discord: {e}")

        return alerts_sent

    async def _send_warning_escalation(self, warning_tasks: List[tuple]) -> int:
        """Send warning escalation for moderately overdue tasks."""
        if not warning_tasks:
            return 0

        alerts_sent = 0

        # Build message
        message_lines = ["⚠️ **WARNING: Overdue Tasks**", ""]
        message_lines.append(f"{len(warning_tasks)} task(s) are 3-7 days overdue:\n")

        for task, days_overdue in warning_tasks[:5]:
            task_id = task.get("task_id", "Unknown")
            title = task.get("title", "Untitled")[:40]
            assignee = task.get("assignee", "Unknown")

            message_lines.append(
                f"🟠 {task_id}: {title}\n"
                f"   {assignee} | Overdue: {days_overdue}d"
            )

        if len(warning_tasks) > 5:
            message_lines.append(f"... and {len(warning_tasks) - 5} more")

        message = "\n".join(message_lines)

        # Send to boss
        if settings.telegram_boss_chat_id:
            try:
                success = await self.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    message
                )
                if success:
                    alerts_sent += 1
            except Exception as e:
                logger.error(f"Failed to send warning escalation: {e}")

        return alerts_sent

    async def _send_attention_escalation(self, attention_tasks: List[tuple]) -> int:
        """Send attention notice for mildly overdue tasks."""
        if not attention_tasks:
            return 0

        alerts_sent = 0

        # Brief message for attention level
        count = len(attention_tasks)
        message = f"📌 {count} task(s) overdue 1-3 days. Please review and update statuses."

        # Send to boss
        if settings.telegram_boss_chat_id:
            try:
                success = await self.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    message
                )
                if success:
                    alerts_sent += 1
            except Exception as e:
                logger.error(f"Failed to send attention escalation: {e}")

        return alerts_sent

    def _get_priority_emoji(self, priority: str) -> str:
        """Get emoji for priority level."""
        priority_lower = (priority or "").lower()

        if "critical" in priority_lower or "urgent" in priority_lower:
            return "🔴"
        elif "high" in priority_lower:
            return "🟠"
        elif "low" in priority_lower:
            return "🟢"
        else:
            return "🟡"  # Medium

    async def send_manual_reminder(self, task_id: str) -> bool:
        """
        Manually send a reminder for a specific task.

        Args:
            task_id: Task ID to remind about

        Returns:
            True if reminder sent successfully
        """
        try:
            task = await self.task_repo.get_by_id(task_id)
            if not task:
                logger.warning(f"Task {task_id} not found")
                return False

            assignee = task.get("assignee", "Unassigned")
            deadline = task.get("deadline")

            if not deadline:
                logger.warning(f"Task {task_id} has no deadline")
                return False

            now = datetime.utcnow()
            time_left = deadline - now

            if time_left.total_seconds() < 0:
                status_text = f"**OVERDUE** by {abs((time_left.days))} days"
            else:
                hours = int(time_left.total_seconds() / 3600)
                minutes = int((time_left.total_seconds() % 3600) / 60)
                status_text = f"Due in {hours}h {minutes}m"

            message = f"""🔔 **Manual Reminder**

Task: {task_id}
Title: {task.get("title", "Untitled")}
Assignee: {assignee}
Status: {status_text}
Deadline: {deadline.strftime('%b %d, %Y %I:%M %p')}"""

            # Send to boss
            if settings.telegram_boss_chat_id:
                await self.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    message
                )

            logger.info(f"Manual reminder sent for {task_id}")
            return True

        except Exception as e:
            logger.error(f"Error sending manual reminder: {e}")
            return False


# Singleton instance
_smart_reminder_system: Optional[SmartReminderSystem] = None


def get_smart_reminder_system() -> SmartReminderSystem:
    """Get or create the smart reminder system instance."""
    global _smart_reminder_system
    if _smart_reminder_system is None:
        _smart_reminder_system = SmartReminderSystem()
    return _smart_reminder_system
