"""
Discord integration for posting task updates and embeds.

Supports both webhook-based posting and bot-based reactions (optional).
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import aiohttp

from config import settings
from ..models.task import Task, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)


class DiscordIntegration:
    """
    Handles Discord webhook and bot integration.

    Primary use: Post rich task embeds to Discord channels.
    Optional: Track reactions for status updates.
    """

    def __init__(self):
        self.tasks_webhook = settings.discord_tasks_channel_webhook
        self.standup_webhook = settings.discord_standup_channel_webhook
        self.default_webhook = settings.discord_webhook_url

    async def post_task(self, task: Task, channel: str = "tasks") -> Optional[str]:
        """
        Post a task to Discord as a rich embed.

        Args:
            task: The task to post
            channel: Which channel to post to ("tasks", "standup")

        Returns:
            Discord message ID if successful, None otherwise
        """
        webhook_url = self._get_webhook_url(channel)
        if not webhook_url:
            logger.warning(f"No webhook configured for channel: {channel}")
            return None

        embed = task.to_discord_embed_dict()

        payload = {
            "embeds": [embed],
            "username": "Boss Workflow Bot",
        }

        try:
            async with aiohttp.ClientSession() as session:
                # Use ?wait=true to get the message ID back
                async with session.post(
                    f"{webhook_url}?wait=true",
                    json=payload
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        message_id = data.get("id")
                        logger.info(f"Posted task {task.id} to Discord: {message_id}")
                        return message_id
                    else:
                        error = await response.text()
                        logger.error(f"Discord webhook error: {response.status} - {error}")
                        return None

        except Exception as e:
            logger.error(f"Error posting to Discord: {e}")
            return None

    async def update_task_embed(
        self,
        task: Task,
        message_id: str,
        channel: str = "tasks"
    ) -> bool:
        """
        Update an existing task embed in Discord.

        Note: Webhooks can edit their own messages using the message ID.
        """
        webhook_url = self._get_webhook_url(channel)
        if not webhook_url or not message_id:
            return False

        embed = task.to_discord_embed_dict()

        payload = {
            "embeds": [embed]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(
                    f"{webhook_url}/messages/{message_id}",
                    json=payload
                ) as response:
                    if response.status == 200:
                        logger.info(f"Updated task {task.id} in Discord")
                        return True
                    else:
                        error = await response.text()
                        logger.error(f"Discord update error: {response.status} - {error}")
                        return False

        except Exception as e:
            logger.error(f"Error updating Discord message: {e}")
            return False

    async def post_standup(self, summary: str) -> bool:
        """Post daily standup summary to Discord."""
        webhook_url = self._get_webhook_url("standup")
        if not webhook_url:
            webhook_url = self._get_webhook_url("tasks")

        if not webhook_url:
            logger.warning("No webhook configured for standup")
            return False

        embed = {
            "title": "☀️ Daily Standup",
            "description": summary,
            "color": 0x3498DB,  # Blue
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": "Boss Workflow Automation"}
        }

        payload = {
            "embeds": [embed],
            "username": "Boss Workflow Bot"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    return response.status == 200 or response.status == 204

        except Exception as e:
            logger.error(f"Error posting standup: {e}")
            return False

    async def post_weekly_summary(self, summary: str) -> bool:
        """Post weekly summary report to Discord."""
        webhook_url = self._get_webhook_url("standup")
        if not webhook_url:
            webhook_url = self._get_webhook_url("tasks")

        if not webhook_url:
            return False

        embed = {
            "title": "📊 Weekly Summary Report",
            "description": summary,
            "color": 0x9B59B6,  # Purple
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": "Boss Workflow Automation"}
        }

        payload = {
            "embeds": [embed],
            "username": "Boss Workflow Bot"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    return response.status == 200 or response.status == 204

        except Exception as e:
            logger.error(f"Error posting weekly summary: {e}")
            return False

    async def post_alert(
        self,
        title: str,
        message: str,
        alert_type: str = "warning",
        task: Optional[Task] = None
    ) -> bool:
        """
        Post an alert message to Discord.

        Args:
            title: Alert title
            message: Alert message
            alert_type: "warning", "error", "info", "success"
            task: Optional task to include details for
        """
        webhook_url = self._get_webhook_url("tasks")
        if not webhook_url:
            return False

        color_map = {
            "warning": 0xF39C12,   # Orange
            "error": 0xE74C3C,     # Red
            "info": 0x3498DB,      # Blue
            "success": 0x2ECC71,   # Green
        }

        emoji_map = {
            "warning": "⚠️",
            "error": "🚨",
            "info": "ℹ️",
            "success": "✅",
        }

        embed = {
            "title": f"{emoji_map.get(alert_type, 'ℹ️')} {title}",
            "description": message,
            "color": color_map.get(alert_type, 0x95A5A6),
            "timestamp": datetime.now().isoformat()
        }

        if task:
            embed["fields"] = [
                {"name": "Task ID", "value": task.id, "inline": True},
                {"name": "Assignee", "value": task.assignee or "Unassigned", "inline": True},
            ]

        payload = {
            "embeds": [embed],
            "username": "Boss Workflow Bot"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    return response.status == 200 or response.status == 204

        except Exception as e:
            logger.error(f"Error posting alert: {e}")
            return False

    async def post_status_change(
        self,
        task: Task,
        old_status: TaskStatus,
        new_status: TaskStatus,
        changed_by: str,
        reason: Optional[str] = None
    ) -> bool:
        """Post a status change notification."""
        status_emoji = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.IN_PROGRESS: "🔨",
            TaskStatus.IN_REVIEW: "🔍",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.CANCELLED: "❌",
            TaskStatus.BLOCKED: "🚫",
            TaskStatus.DELAYED: "⏰",
            TaskStatus.UNDONE: "↩️",
            TaskStatus.ON_HOLD: "⏸️",
            TaskStatus.WAITING: "⏳",
            TaskStatus.NEEDS_INFO: "❓",
            TaskStatus.OVERDUE: "🚨",
        }

        old_emoji = status_emoji.get(old_status, "")
        new_emoji = status_emoji.get(new_status, "")

        message = f"**{task.title}** ({task.id})\n"
        message += f"{old_emoji} {old_status.value} → {new_emoji} {new_status.value}\n"
        message += f"Changed by: {changed_by}"

        if reason:
            message += f"\nReason: {reason}"

        return await self.post_alert(
            title="Status Update",
            message=message,
            alert_type="info",
            task=task
        )

    async def post_note_added(self, task: Task, note_content: str, author: str) -> bool:
        """Post notification when a note is added to a task."""
        message = f"New note on **{task.title}** ({task.id})\n"
        message += f"By: {author}\n"
        message += f"```{note_content[:500]}```"

        return await self.post_alert(
            title="Note Added",
            message=message,
            alert_type="info"
        )

    def _get_webhook_url(self, channel: str) -> Optional[str]:
        """Get the webhook URL for a given channel."""
        if channel == "tasks":
            return self.tasks_webhook or self.default_webhook
        elif channel == "standup":
            return self.standup_webhook or self.default_webhook
        return self.default_webhook


# Singleton instance
discord_integration = DiscordIntegration()


def get_discord_integration() -> DiscordIntegration:
    """Get the Discord integration instance."""
    return discord_integration
