"""
Discord integration for posting task updates and embeds.

Supports:
- Webhook-based posting for tasks and alerts
- Interactive buttons for submission review flow
- Bot-based reactions (optional)
"""

import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from enum import Enum
import aiohttp
import asyncio

from config import settings
from ..models.task import Task, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)


class ReviewAction(str, Enum):
    """Possible actions for submission review."""
    ACCEPT_SUGGESTIONS = "accept_suggestions"  # Apply AI suggestions
    SEND_ANYWAY = "send_anyway"                # Send to boss despite issues
    EDIT_MANUAL = "edit_manual"                # User will edit manually


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

    # ==================== SUBMISSION REVIEW FLOW ====================

    async def post_review_feedback(
        self,
        user_id: str,
        user_name: str,
        review_message: str,
        submission_id: str,
        has_suggestions: bool = True
    ) -> Optional[str]:
        """
        Post review feedback with interactive buttons.

        Buttons:
        - ✅ Apply Suggestions (if suggestions available)
        - 📤 Send Anyway
        - ✏️ Edit Manually
        """
        webhook_url = self._get_webhook_url("tasks")
        if not webhook_url:
            return None

        embed = {
            "title": f"📋 Submission Review - {user_name}",
            "description": review_message,
            "color": 0xF39C12,  # Orange for "needs attention"
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": f"Submission ID: {submission_id}"}
        }

        # Build button components
        # Note: Webhooks can't use buttons directly - we'll simulate with reactions
        # For full button support, need Discord bot token

        if settings.discord_bot_token:
            # Full button support with bot
            components = [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {
                            "type": 2,  # Button
                            "style": 3,  # Green (Success)
                            "label": "Apply Suggestions",
                            "custom_id": f"review_accept_{submission_id}",
                            "emoji": {"name": "✅"},
                            "disabled": not has_suggestions
                        },
                        {
                            "type": 2,
                            "style": 1,  # Blue (Primary)
                            "label": "Send to Boss Anyway",
                            "custom_id": f"review_send_{submission_id}",
                            "emoji": {"name": "📤"}
                        },
                        {
                            "type": 2,
                            "style": 2,  # Gray (Secondary)
                            "label": "Edit Manually",
                            "custom_id": f"review_edit_{submission_id}",
                            "emoji": {"name": "✏️"}
                        }
                    ]
                }
            ]
            return await self._post_with_bot(embed, components, user_id)
        else:
            # Webhook fallback - add reaction instructions
            embed["description"] += "\n\n**React to choose:**\n"
            if has_suggestions:
                embed["description"] += "✅ = Apply my suggestions\n"
            embed["description"] += "📤 = Send to boss anyway\n"
            embed["description"] += "✏️ = I'll edit it myself"

            return await self._post_with_reactions(
                embed=embed,
                reactions=["✅", "📤", "✏️"] if has_suggestions else ["📤", "✏️"],
                channel="tasks"
            )

    async def _post_with_bot(
        self,
        embed: Dict,
        components: List[Dict],
        target_user_id: str
    ) -> Optional[str]:
        """Post message with buttons using Discord bot."""
        if not settings.discord_bot_token:
            return None

        # This would use discord.py or direct API calls
        # For now, falling back to webhook
        logger.warning("Bot token configured but bot posting not fully implemented")
        return None

    async def _post_with_reactions(
        self,
        embed: Dict,
        reactions: List[str],
        channel: str
    ) -> Optional[str]:
        """Post message and add reactions for interaction."""
        webhook_url = self._get_webhook_url(channel)
        if not webhook_url:
            return None

        payload = {
            "embeds": [embed],
            "username": "Boss Workflow Bot"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{webhook_url}?wait=true",
                    json=payload
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        message_id = data.get("id")
                        logger.info(f"Posted review message: {message_id}")

                        # Note: Adding reactions to webhook messages requires bot token
                        # For full functionality, use Discord bot

                        return message_id
                    else:
                        error = await response.text()
                        logger.error(f"Discord post error: {error}")
                        return None

        except Exception as e:
            logger.error(f"Error posting with reactions: {e}")
            return None

    async def post_submission_approved(
        self,
        user_name: str,
        task_description: str,
        submission_id: str,
        applied_suggestions: bool = False
    ) -> bool:
        """Post notification that submission passed review."""
        message = f"**{user_name}** submitted: {task_description[:100]}\n\n"
        if applied_suggestions:
            message += "✨ AI suggestions were applied\n"
        message += "📤 Sent to boss for final approval"

        return await self.post_alert(
            title="Submission Ready for Review",
            message=message,
            alert_type="success"
        )

    async def post_submission_revised(
        self,
        user_name: str,
        changes_made: str,
        submission_id: str
    ) -> bool:
        """Post notification that user is revising their submission."""
        message = f"**{user_name}** is revising their submission.\n"
        message += f"Changes: {changes_made[:200]}"

        return await self.post_alert(
            title="Submission Being Revised",
            message=message,
            alert_type="info"
        )


# Pending review callbacks - stores what to do when user responds
_review_callbacks: Dict[str, Dict[str, Any]] = {}


def register_review_callback(
    submission_id: str,
    user_id: str,
    callback_data: Dict[str, Any]
) -> None:
    """Register a callback for when user responds to review."""
    _review_callbacks[submission_id] = {
        "user_id": user_id,
        "data": callback_data,
        "registered_at": datetime.now().isoformat()
    }


def get_review_callback(submission_id: str) -> Optional[Dict[str, Any]]:
    """Get the callback data for a submission."""
    return _review_callbacks.get(submission_id)


def clear_review_callback(submission_id: str) -> None:
    """Clear a review callback."""
    _review_callbacks.pop(submission_id, None)


# Singleton instance
discord_integration = DiscordIntegration()


def get_discord_integration() -> DiscordIntegration:
    """Get the Discord integration instance."""
    return discord_integration
