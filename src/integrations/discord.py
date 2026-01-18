"""
Discord integration for posting task updates and embeds.

Supports:
- Webhook-based posting for tasks and alerts
- Interactive buttons for submission review flow
- Bot-based reactions (optional)
"""

import logging
from typing import Dict, Any, Optional, List, Callable, Tuple
from datetime import datetime
from enum import Enum
import aiohttp
import asyncio

from config import settings
from ..models.task import Task, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)


def _register_message_task_mapping(message_id: str, task_id: str):
    """Register a Discord message ID -> task ID mapping for reaction tracking."""
    try:
        from .discord_bot import get_discord_bot
        bot = get_discord_bot()
        if bot:
            bot.register_message_task(int(message_id), task_id)
            logger.debug(f"Registered Discord message {message_id} -> task {task_id}")
    except Exception as e:
        logger.debug(f"Could not register message-task mapping: {e}")


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
    Supports role-based channel routing for tasks.
    """

    # Reaction guide for status updates
    REACTION_GUIDE = "React: ✅ Done | 🚧 In Progress | 🚫 Blocked | ⏸️ On Hold | 🔄 In Review"
    REACTION_HELP = "React to update status: ✅=Done 🚧=Working 🚫=Blocked ⏸️=Paused 🔄=Review"

    # Role to webhook mapping keywords
    ROLE_KEYWORDS = {
        "dev": ["developer", "dev", "backend", "frontend", "engineer", "programmer", "software"],
        "admin": ["admin", "administrator", "manager", "lead", "director", "executive"],
        "marketing": ["marketing", "content", "social", "growth", "seo", "ads"],
        "design": ["design", "designer", "ui", "ux", "graphic", "creative", "artist"],
    }

    def __init__(self):
        self.tasks_webhook = settings.discord_tasks_channel_webhook
        self.standup_webhook = settings.discord_standup_channel_webhook
        self.specs_webhook = settings.discord_specs_channel_webhook
        self.default_webhook = settings.discord_webhook_url

        # Role-based webhooks
        self.role_webhooks = {
            "dev": settings.discord_dev_tasks_webhook,
            "admin": settings.discord_admin_tasks_webhook,
            "marketing": settings.discord_marketing_tasks_webhook,
            "design": settings.discord_design_tasks_webhook,
        }

    def _get_role_category(self, role: str) -> Optional[str]:
        """
        Determine which webhook category a role belongs to.

        Args:
            role: The team member's role (e.g., "Developer", "Marketing Lead")

        Returns:
            Category key ("dev", "admin", "marketing", "design") or None
        """
        if not role:
            return None

        role_lower = role.lower()

        for category, keywords in self.ROLE_KEYWORDS.items():
            if any(keyword in role_lower for keyword in keywords):
                return category

        return None

    def _get_webhook_for_role(self, role: str) -> Optional[str]:
        """
        Get the appropriate webhook URL for a given role.

        Args:
            role: The team member's role

        Returns:
            Webhook URL or None if no role-specific webhook configured
        """
        category = self._get_role_category(role)

        if category and self.role_webhooks.get(category):
            return self.role_webhooks[category]

        return None

    async def get_assignee_role(self, assignee: str) -> Optional[str]:
        """
        Look up an assignee's role from the team database.

        Args:
            assignee: The assignee name

        Returns:
            The role string or None
        """
        if not assignee:
            return None

        try:
            from ..database.repositories import get_team_repository
            team_repo = get_team_repository()
            member = await team_repo.find_member(assignee)
            if member:
                return member.role
        except Exception as e:
            logger.debug(f"Could not look up role for {assignee}: {e}")

        return None

    async def post_task(self, task: Task, channel: str = "tasks") -> Optional[str]:
        """
        Post a task to Discord as a rich embed.

        Routing priority:
        1. If DISCORD_FORUM_CHANNEL_ID is configured, posts as a forum thread
        2. If role-based webhook is configured for assignee's role, use that
        3. Fall back to default tasks channel webhook

        Args:
            task: The task to post
            channel: Which channel to post to ("tasks", "standup")

        Returns:
            Discord message/thread ID if successful, None otherwise
        """
        # Check if forum channel is configured - use forum posts for better organization
        if settings.discord_forum_channel_id:
            return await self._post_task_to_forum(task)

        # Try role-based routing first
        webhook_url = None
        role_category = None

        if task.assignee:
            # Look up assignee's role
            assignee_role = await self.get_assignee_role(task.assignee)
            if assignee_role:
                role_webhook = self._get_webhook_for_role(assignee_role)
                if role_webhook:
                    webhook_url = role_webhook
                    role_category = self._get_role_category(assignee_role)
                    logger.info(f"Routing task {task.id} to {role_category} channel (assignee: {task.assignee}, role: {assignee_role})")

        # Fall back to default webhook
        if not webhook_url:
            webhook_url = self._get_webhook_url(channel)

        if not webhook_url:
            logger.warning(f"No webhook configured for channel: {channel}")
            return None

        embed = task.to_discord_embed_dict()

        # Add reaction guide to footer
        if "footer" in embed:
            embed["footer"]["text"] = f"{embed['footer']['text']} | {self.REACTION_HELP}"
        else:
            embed["footer"] = {"text": self.REACTION_HELP}

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
                        channel_id = data.get("channel_id")
                        logger.info(f"Posted task {task.id} to Discord: {message_id}")

                        # Register message-task mapping for reaction tracking
                        if message_id:
                            _register_message_task_mapping(message_id, task.id)

                        # Create thread for the task if bot is available
                        if message_id and channel_id:
                            await self._create_thread_for_task(
                                channel_id=int(channel_id),
                                message_id=int(message_id),
                                task=task
                            )

                        return message_id
                    else:
                        error = await response.text()
                        logger.error(f"Discord webhook error: {response.status} - {error}")
                        return None

        except Exception as e:
            logger.error(f"Error posting to Discord: {e}")
            return None

    async def _post_task_to_forum(self, task: Task) -> Optional[str]:
        """
        Post a task as a forum thread for better organization.

        Args:
            task: The task to post

        Returns:
            Thread ID if successful, None otherwise
        """
        try:
            from .discord_bot import create_forum_post, get_discord_bot
            import asyncio

            forum_channel_id = int(settings.discord_forum_channel_id)

            # Check if bot token is configured
            if not settings.discord_bot_token:
                logger.warning("Discord bot token required for forum posts, falling back to webhook")
                return None

            # Build the embed
            embed = task.to_discord_embed_dict()
            if "footer" in embed:
                embed["footer"]["text"] = f"{embed['footer']['text']} | {self.REACTION_HELP}"
            else:
                embed["footer"] = {"text": self.REACTION_HELP}

            # Retry up to 3 times (bot might not be ready yet)
            max_retries = 3
            for attempt in range(max_retries):
                bot = get_discord_bot()

                if bot and bot.is_ready():
                    thread_id = await create_forum_post(
                        forum_channel_id=forum_channel_id,
                        task_id=task.id,
                        task_title=task.title,
                        task_embed=embed,
                        assignee=task.assignee,
                        assignee_discord_id=task.assignee_discord_id,
                        priority=task.priority.value if task.priority else None,
                        status=task.status.value if task.status else None
                    )

                    if thread_id:
                        logger.info(f"Posted task {task.id} to forum as thread {thread_id}")
                        return str(thread_id)
                    else:
                        logger.warning(f"Forum post creation failed for {task.id}")
                        return None

                # Bot not ready, wait and retry
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.debug(f"Discord bot not ready for forum post, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)

            logger.warning(f"Discord bot not ready after {max_retries} attempts for forum post")
            return None

        except ValueError as e:
            logger.error(f"Invalid DISCORD_FORUM_CHANNEL_ID: {settings.discord_forum_channel_id}")
            return None
        except Exception as e:
            logger.error(f"Error posting task to forum: {e}")
            return None

    async def _create_thread_for_task(
        self,
        channel_id: int,
        message_id: int,
        task: Task
    ) -> bool:
        """Create a discussion thread for a task with retry logic."""
        try:
            from .discord_bot import create_task_thread, get_discord_bot
            import asyncio

            # Check if bot token is configured
            if not settings.discord_bot_token:
                logger.debug("Discord bot token not configured, skipping thread creation")
                return False

            # Retry up to 3 times with delays (bot might not be ready yet)
            max_retries = 3
            for attempt in range(max_retries):
                bot = get_discord_bot()

                if bot and bot.is_ready():
                    result = await create_task_thread(
                        channel_id=channel_id,
                        message_id=message_id,
                        task_id=task.id,
                        task_title=task.title,
                        assignee=task.assignee,
                        assignee_discord_id=task.assignee_discord_id
                    )

                    if result:
                        logger.info(f"Created thread for task {task.id}")
                        return True
                    else:
                        logger.warning(f"Thread creation failed for {task.id}")
                        return False

                # Bot not ready, wait and retry
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                    logger.debug(f"Discord bot not ready, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)

            logger.warning(f"Discord bot not ready after {max_retries} attempts, skipping thread for {task.id}")
            return False

        except Exception as e:
            logger.warning(f"Thread creation error for {task.id}: {e}")
            return False

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

    async def delete_message(
        self,
        message_id: str,
        channel: str = "tasks"
    ) -> bool:
        """
        Delete a Discord message (task embed).

        Args:
            message_id: The Discord message ID to delete
            channel: Which channel the message is in

        Returns:
            True if deleted successfully, False otherwise
        """
        if not message_id:
            return False

        webhook_url = self._get_webhook_url(channel)
        if not webhook_url:
            logger.warning(f"No webhook configured for channel: {channel}")
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{webhook_url}/messages/{message_id}"
                ) as response:
                    if response.status == 204:
                        logger.info(f"Deleted Discord message: {message_id}")
                        return True
                    elif response.status == 404:
                        logger.warning(f"Discord message already deleted or not found: {message_id}")
                        return True  # Consider it a success if already gone
                    else:
                        error = await response.text()
                        logger.error(f"Discord delete error: {response.status} - {error}")
                        return False

        except Exception as e:
            logger.error(f"Error deleting Discord message: {e}")
            return False

    async def delete_thread(self, thread_id: str) -> bool:
        """
        Delete a Discord thread (forum post or message thread).

        Requires bot token - threads can't be deleted via webhooks.

        Args:
            thread_id: The Discord thread/channel ID to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        if not thread_id:
            return False

        if not settings.discord_bot_token:
            logger.warning("Bot token required to delete threads")
            return False

        try:
            # Use Discord API directly to delete the thread/channel
            headers = {
                "Authorization": f"Bot {settings.discord_bot_token}",
                "Content-Type": "application/json"
            }

            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"https://discord.com/api/v10/channels/{thread_id}",
                    headers=headers
                ) as response:
                    if response.status == 200 or response.status == 204:
                        logger.info(f"Deleted Discord thread: {thread_id}")
                        return True
                    elif response.status == 404:
                        logger.warning(f"Discord thread already deleted or not found: {thread_id}")
                        return True
                    else:
                        error = await response.text()
                        logger.error(f"Discord thread delete error: {response.status} - {error}")
                        return False

        except Exception as e:
            logger.error(f"Error deleting Discord thread: {e}")
            return False

    async def delete_task_message(self, task_id: str, message_id: str, is_forum_thread: bool = False) -> bool:
        """
        Delete a task's Discord message or forum thread.

        This is a convenience method that handles both regular messages and forum threads.

        Args:
            task_id: The task ID (for logging)
            message_id: The Discord message or thread ID
            is_forum_thread: Whether this is a forum thread (requires different API)

        Returns:
            True if deleted successfully
        """
        if not message_id:
            logger.debug(f"No Discord message ID for task {task_id}")
            return False

        if is_forum_thread or settings.discord_forum_channel_id:
            # Try to delete as thread first (forum posts are threads)
            result = await self.delete_thread(message_id)
            if result:
                return True

        # Fall back to webhook message deletion
        return await self.delete_message(message_id)

    async def get_channel_threads(self, channel_id: str) -> List[Dict[str, Any]]:
        """
        Get all active threads in a channel.

        Args:
            channel_id: The Discord channel ID

        Returns:
            List of thread objects
        """
        if not settings.discord_bot_token:
            logger.warning("Bot token required to list threads")
            return []

        try:
            headers = {
                "Authorization": f"Bot {settings.discord_bot_token}",
                "Content-Type": "application/json"
            }

            threads = []

            async with aiohttp.ClientSession() as session:
                # Get active threads
                async with session.get(
                    f"https://discord.com/api/v10/channels/{channel_id}/threads/active",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        threads.extend(data.get("threads", []))

                # Get archived threads (public)
                async with session.get(
                    f"https://discord.com/api/v10/channels/{channel_id}/threads/archived/public",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        threads.extend(data.get("threads", []))

            return threads

        except Exception as e:
            logger.error(f"Error getting channel threads: {e}")
            return []

    async def bulk_delete_threads(self, channel_id: str, filter_prefix: str = "TASK-") -> Tuple[int, int]:
        """
        Delete all threads in a channel that match a prefix.

        Args:
            channel_id: The Discord channel ID
            filter_prefix: Only delete threads whose name starts with this (default: "TASK-")

        Returns:
            Tuple of (deleted_count, failed_count)
        """
        if not settings.discord_bot_token:
            logger.warning("Bot token required to delete threads")
            return (0, 0)

        try:
            threads = await self.get_channel_threads(channel_id)

            if not threads:
                logger.info(f"No threads found in channel {channel_id}")
                return (0, 0)

            deleted = 0
            failed = 0

            for thread in threads:
                thread_name = thread.get("name", "")
                thread_id = thread.get("id")

                # Filter by prefix
                if filter_prefix and not thread_name.startswith(filter_prefix):
                    continue

                try:
                    if await self.delete_thread(thread_id):
                        deleted += 1
                        logger.info(f"Deleted thread: {thread_name}")
                    else:
                        failed += 1
                except Exception as e:
                    logger.warning(f"Failed to delete thread {thread_name}: {e}")
                    failed += 1

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)

            logger.info(f"Bulk delete complete: {deleted} deleted, {failed} failed")
            return (deleted, failed)

        except Exception as e:
            logger.error(f"Error in bulk delete threads: {e}")
            return (0, 0)

    async def cleanup_task_channel(self, channel_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Clean up all task-related threads and messages in a channel.

        Args:
            channel_id: Optional channel ID (defaults to tasks channel or forum)

        Returns:
            Dict with cleanup results
        """
        results = {
            "threads_deleted": 0,
            "threads_failed": 0,
            "messages_deleted": 0,
            "messages_failed": 0,
        }

        # Determine channel ID
        target_channel = channel_id
        if not target_channel:
            # Try forum channel first, then get channel ID from webhook
            if settings.discord_forum_channel_id:
                target_channel = settings.discord_forum_channel_id
            else:
                logger.warning("No channel ID provided and no forum channel configured")
                return results

        # Delete threads
        deleted, failed = await self.bulk_delete_threads(target_channel)
        results["threads_deleted"] = deleted
        results["threads_failed"] = failed

        return results

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
            "footer": {"text": f"Boss Workflow | {self.REACTION_HELP}"}
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

    async def post_spec_sheet(
        self,
        task_id: str,
        title: str,
        assignee: str,
        priority: str,
        deadline: Optional[str],
        description: str,
        acceptance_criteria: List[str],
        technical_details: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        notes: Optional[str] = None,
        estimated_effort: Optional[str] = None
    ) -> Optional[str]:
        """
        Post a detailed spec sheet for a task to the specs channel.

        This is a comprehensive document for team members to understand
        exactly what needs to be done.

        Returns:
            Discord message ID if successful, None otherwise
        """
        webhook_url = self._get_webhook_url("specs")
        if not webhook_url:
            logger.warning("No webhook configured for specs channel")
            return None

        # Priority colors and emojis
        priority_colors = {
            "urgent": 0xE74C3C,   # Red
            "high": 0xE67E22,     # Orange
            "medium": 0xF1C40F,   # Yellow
            "low": 0x3498DB,      # Blue
        }
        priority_emoji = {
            "urgent": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🔵",
        }

        color = priority_colors.get(priority.lower(), 0x95A5A6)
        p_emoji = priority_emoji.get(priority.lower(), "⚪")

        # Build acceptance criteria as checklist
        criteria_text = "\n".join([f"☐ {c}" for c in acceptance_criteria]) if acceptance_criteria else "None specified"

        # Build the embed with multiple fields for clarity
        embed = {
            "title": f"📋 SPEC: {title}",
            "description": f"**Task ID:** `{task_id}`\n\n{description}",
            "color": color,
            "fields": [
                {
                    "name": "👤 Assignee",
                    "value": assignee or "Unassigned",
                    "inline": True
                },
                {
                    "name": f"{p_emoji} Priority",
                    "value": priority.upper(),
                    "inline": True
                },
                {
                    "name": "📅 Deadline",
                    "value": deadline or "Not set",
                    "inline": True
                },
            ],
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": f"Spec Sheet | {task_id}"}
        }

        # Add estimated effort if provided
        if estimated_effort:
            embed["fields"].append({
                "name": "⏱️ Estimated Effort",
                "value": estimated_effort,
                "inline": True
            })

        # Add acceptance criteria (important!)
        embed["fields"].append({
            "name": "✅ Acceptance Criteria",
            "value": criteria_text[:1024],  # Discord field limit
            "inline": False
        })

        # Add technical details if provided
        if technical_details:
            embed["fields"].append({
                "name": "🔧 Technical Details",
                "value": technical_details[:1024],
                "inline": False
            })

        # Add dependencies if any
        if dependencies:
            deps_text = "\n".join([f"• {d}" for d in dependencies])
            embed["fields"].append({
                "name": "🔗 Dependencies",
                "value": deps_text[:1024],
                "inline": False
            })

        # Add notes if any
        if notes:
            embed["fields"].append({
                "name": "📝 Additional Notes",
                "value": notes[:1024],
                "inline": False
            })

        payload = {
            "embeds": [embed],
            "username": "Boss Workflow - Specs"
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
                        logger.info(f"Posted spec sheet for {task_id} to Discord: {message_id}")
                        return message_id
                    else:
                        error = await response.text()
                        logger.error(f"Discord specs webhook error: {response.status} - {error}")
                        return None

        except Exception as e:
            logger.error(f"Error posting spec sheet to Discord: {e}")
            return None

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
        elif channel == "specs":
            return self.specs_webhook or self.default_webhook
        return self.default_webhook

    async def post_help(self, channel: str = "tasks") -> bool:
        """Post a help message with reaction guide and available commands."""
        webhook_url = self._get_webhook_url(channel)
        if not webhook_url:
            return False

        embed = {
            "title": "📖 Boss Workflow Help",
            "description": """**React to Update Task Status:**
✅ Complete task
🚧 Mark as in progress
🚫 Block task (can't proceed)
⏸️ Put on hold
🔄 Send for review

**Available via Telegram:**
• `/status` - View current tasks
• `/search @name` - Find tasks by assignee
• `/complete ID` - Mark task done
• `/help` - Full command list

**Natural Language:**
• "What's John working on?"
• "Show blocked tasks"
• "Mark TASK-001 as done"

_Reactions sync task status automatically!_""",
            "color": 0x3498DB,  # Blue
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": "Boss Workflow Automation | Send /help in Telegram for full commands"}
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
            logger.error(f"Error posting help: {e}")
            return False

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
