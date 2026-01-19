"""
Discord integration using Bot API with channel IDs.

Supports:
- Direct channel posting via Bot API (full permissions)
- Role-based routing to different category channels
- Forum threads for detailed tasks/specs
- Text channels for regular tasks, reports, alerts
- Full edit/delete capabilities
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum
import aiohttp
import asyncio

from config import settings
from ..models.task import Task, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)

# Discord API base URL
DISCORD_API_BASE = "https://discord.com/api/v10"


class ChannelType(str, Enum):
    """Types of Discord channels for different content."""
    FORUM = "forum"      # Detailed specs, creates threads per task
    TASKS = "tasks"      # Regular tasks, overdue, cancel notifications
    REPORT = "report"    # Standup and reports
    GENERAL = "general"  # General messages


class RoleCategory(str, Enum):
    """Role categories for channel routing."""
    DEV = "dev"
    ADMIN = "admin"
    MARKETING = "marketing"
    DESIGN = "design"


class DiscordIntegration:
    """
    Discord Bot API integration for posting to channels.

    Uses channel IDs directly with Bot API for full permissions:
    - Create/edit/delete messages
    - Create/manage threads
    - Add reactions
    - @mention users
    """

    # Reaction guide for status updates
    REACTION_GUIDE = "React: ✅ Done | 🚧 In Progress | 🚫 Blocked | ⏸️ On Hold | 🔄 In Review"
    REACTION_HELP = "React to update status: ✅=Done 🚧=Working 🚫=Blocked ⏸️=Paused 🔄=Review"

    # Role to category mapping keywords
    ROLE_KEYWORDS = {
        RoleCategory.DEV: ["developer", "dev", "backend", "frontend", "engineer", "programmer", "software", "qa", "devops"],
        RoleCategory.ADMIN: ["admin", "administrator", "manager", "lead", "director", "executive"],
        RoleCategory.MARKETING: ["marketing", "content", "social", "growth", "seo", "ads"],
        RoleCategory.DESIGN: ["design", "designer", "ui", "ux", "graphic", "creative", "artist"],
    }

    def __init__(self):
        self.bot_token = settings.discord_bot_token

        # Channel IDs by role category
        self.channels = {
            RoleCategory.DEV: {
                ChannelType.FORUM: settings.discord_dev_forum_channel_id,
                ChannelType.TASKS: settings.discord_dev_tasks_channel_id,
                ChannelType.REPORT: settings.discord_dev_report_channel_id,
                ChannelType.GENERAL: settings.discord_dev_general_channel_id,
            },
            RoleCategory.ADMIN: {
                ChannelType.FORUM: settings.discord_admin_forum_channel_id,
                ChannelType.TASKS: settings.discord_admin_tasks_channel_id,
                ChannelType.REPORT: settings.discord_admin_report_channel_id,
                ChannelType.GENERAL: settings.discord_admin_general_channel_id,
            },
            RoleCategory.MARKETING: {
                ChannelType.FORUM: settings.discord_marketing_forum_channel_id,
                ChannelType.TASKS: settings.discord_marketing_tasks_channel_id,
                ChannelType.REPORT: settings.discord_marketing_report_channel_id,
                ChannelType.GENERAL: settings.discord_marketing_general_channel_id,
            },
            RoleCategory.DESIGN: {
                ChannelType.FORUM: settings.discord_design_forum_channel_id,
                ChannelType.TASKS: settings.discord_design_tasks_channel_id,
                ChannelType.REPORT: settings.discord_design_report_channel_id,
                ChannelType.GENERAL: settings.discord_design_general_channel_id,
            },
        }

    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers for Discord API."""
        return {
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json"
        }

    def _get_role_category(self, role: str) -> RoleCategory:
        """
        Determine which category a role belongs to.

        Args:
            role: The team member's role (e.g., "Developer", "Marketing Lead")

        Returns:
            RoleCategory (defaults to DEV if no match)
        """
        if not role:
            return RoleCategory.DEV

        role_lower = role.lower()

        for category, keywords in self.ROLE_KEYWORDS.items():
            if any(keyword in role_lower for keyword in keywords):
                return category

        return RoleCategory.DEV  # Default to dev

    def _get_channel_id(self, channel_type: ChannelType, role_category: RoleCategory = RoleCategory.DEV) -> Optional[str]:
        """
        Get the channel ID for a given type and role category.

        Falls back to DEV category if the specific category's channel is not configured.
        """
        # Try the specific category first
        channel_id = self.channels.get(role_category, {}).get(channel_type, "")

        # Fall back to DEV category if not configured
        if not channel_id and role_category != RoleCategory.DEV:
            channel_id = self.channels.get(RoleCategory.DEV, {}).get(channel_type, "")

        return channel_id if channel_id else None

    async def get_assignee_role(self, assignee: str) -> Optional[str]:
        """
        Look up an assignee's role from database or Google Sheets.

        Checks in order:
        1. PostgreSQL database (fast)
        2. Google Sheets Team tab (fallback, always up-to-date)
        """
        if not assignee:
            return None

        # Try database first (faster)
        try:
            from ..database.repositories import get_team_repository
            team_repo = get_team_repository()
            member = await team_repo.find_member(assignee)
            if member and member.role:
                logger.debug(f"Found role for {assignee} in database: {member.role}")
                return member.role
        except Exception as e:
            logger.debug(f"Database lookup failed for {assignee}: {e}")

        # Fallback to Google Sheets (source of truth)
        try:
            from .sheets import sheets_integration
            team_members = await sheets_integration.get_all_team_members()
            for member in team_members:
                member_name = member.get("Name", "").strip().lower()
                if member_name == assignee.lower() or assignee.lower() in member_name:
                    role = member.get("Role", "")
                    if role:
                        logger.info(f"Found role for {assignee} in Sheets: {role}")
                        return role
        except Exception as e:
            logger.debug(f"Sheets lookup failed for {assignee}: {e}")

        return None

    async def _api_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None
    ) -> Tuple[int, Optional[Dict]]:
        """
        Make a Discord API request.

        Returns:
            Tuple of (status_code, response_data)
        """
        if not self.bot_token:
            logger.error("Discord bot token not configured")
            return (0, None)

        url = f"{DISCORD_API_BASE}{endpoint}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    url,
                    headers=self._get_headers(),
                    json=json_data
                ) as response:
                    if response.status in [200, 201, 204]:
                        if response.status == 204:
                            return (response.status, None)
                        return (response.status, await response.json())
                    else:
                        error = await response.text()
                        logger.error(f"Discord API error: {response.status} - {error}")
                        return (response.status, None)
        except Exception as e:
            logger.error(f"Discord API request failed: {e}")
            return (0, None)

    async def send_message(
        self,
        channel_id: str,
        content: Optional[str] = None,
        embed: Optional[Dict] = None,
        embeds: Optional[List[Dict]] = None
    ) -> Optional[str]:
        """
        Send a message to a Discord channel.

        Args:
            channel_id: The channel ID to send to
            content: Text content (optional)
            embed: Single embed dict (optional)
            embeds: List of embed dicts (optional)

        Returns:
            Message ID if successful, None otherwise
        """
        if not channel_id:
            logger.warning("No channel ID provided for message")
            return None

        payload = {}
        if content:
            payload["content"] = content
        if embed:
            payload["embeds"] = [embed]
        elif embeds:
            payload["embeds"] = embeds

        if not payload:
            logger.warning("No content or embeds provided for message")
            return None

        status, data = await self._api_request("POST", f"/channels/{channel_id}/messages", payload)

        if data:
            message_id = data.get("id")
            logger.info(f"Sent message to channel {channel_id}: {message_id}")
            return message_id

        return None

    async def edit_message(
        self,
        channel_id: str,
        message_id: str,
        content: Optional[str] = None,
        embed: Optional[Dict] = None
    ) -> bool:
        """Edit an existing message."""
        if not channel_id or not message_id:
            return False

        payload = {}
        if content is not None:
            payload["content"] = content
        if embed:
            payload["embeds"] = [embed]

        status, _ = await self._api_request("PATCH", f"/channels/{channel_id}/messages/{message_id}", payload)
        return status == 200

    async def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Delete a message from a channel."""
        if not channel_id or not message_id:
            return False

        status, _ = await self._api_request("DELETE", f"/channels/{channel_id}/messages/{message_id}")

        if status in [200, 204, 404]:  # 404 means already deleted
            logger.info(f"Deleted message {message_id} from channel {channel_id}")
            return True
        return False

    async def create_forum_thread(
        self,
        forum_channel_id: str,
        name: str,
        content: Optional[str] = None,
        embed: Optional[Dict] = None,
        auto_archive_duration: int = 1440  # 24 hours
    ) -> Optional[str]:
        """
        Create a new forum thread (post).

        Args:
            forum_channel_id: The forum channel ID
            name: Thread name (e.g., "TASK-001: Build login page")
            content: Initial message content
            embed: Initial message embed
            auto_archive_duration: Minutes until auto-archive (60, 1440, 4320, 10080)

        Returns:
            Thread ID if successful, None otherwise
        """
        if not forum_channel_id:
            logger.warning("No forum channel ID provided")
            return None

        payload = {
            "name": name[:100],  # Discord limit
            "auto_archive_duration": auto_archive_duration,
            "message": {}
        }

        if content:
            payload["message"]["content"] = content
        if embed:
            payload["message"]["embeds"] = [embed]

        if not payload["message"]:
            payload["message"]["content"] = "Thread created"

        status, data = await self._api_request("POST", f"/channels/{forum_channel_id}/threads", payload)

        if data:
            thread_id = data.get("id")
            logger.info(f"Created forum thread: {name} (ID: {thread_id})")
            return thread_id

        return None

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread/channel."""
        if not thread_id:
            return False

        status, _ = await self._api_request("DELETE", f"/channels/{thread_id}")

        if status in [200, 204, 404]:
            logger.info(f"Deleted thread {thread_id}")
            return True
        return False

    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Add a reaction to a message."""
        if not channel_id or not message_id:
            return False

        # URL encode the emoji
        import urllib.parse
        encoded_emoji = urllib.parse.quote(emoji)

        status, _ = await self._api_request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
        )
        return status in [200, 204]

    async def get_channel_threads(self, channel_id: str) -> List[Dict[str, Any]]:
        """Get all active and archived threads in a channel."""
        if not channel_id:
            return []

        threads = []

        # Get active threads
        status, data = await self._api_request("GET", f"/channels/{channel_id}/threads/active")
        if data:
            threads.extend(data.get("threads", []))

        # Get archived public threads
        status, data = await self._api_request("GET", f"/channels/{channel_id}/threads/archived/public")
        if data:
            threads.extend(data.get("threads", []))

        return threads

    async def bulk_delete_threads(self, channel_id: str, filter_prefix: str = "TASK-") -> Tuple[int, int]:
        """
        Delete all threads in a channel matching a prefix.

        Returns:
            Tuple of (deleted_count, failed_count)
        """
        threads = await self.get_channel_threads(channel_id)

        if not threads:
            logger.info(f"No threads found in channel {channel_id}")
            return (0, 0)

        deleted = 0
        failed = 0

        for thread in threads:
            thread_name = thread.get("name", "")
            thread_id = thread.get("id")

            if filter_prefix and not thread_name.startswith(filter_prefix):
                continue

            if await self.delete_thread(thread_id):
                deleted += 1
                logger.info(f"Deleted thread: {thread_name}")
            else:
                failed += 1

            await asyncio.sleep(0.5)  # Rate limit protection

        logger.info(f"Bulk delete complete: {deleted} deleted, {failed} failed")
        return (deleted, failed)

    # ==================== HIGH-LEVEL TASK METHODS ====================

    async def post_task(self, task: Task, channel: str = "tasks") -> Optional[str]:
        """
        Post a task to Discord.

        Routing:
        - Detailed specs → Forum channel (creates thread)
        - Regular tasks → Tasks channel (simple message)

        Args:
            task: The task to post
            channel: Hint for channel type ("tasks", "specs", "forum")

        Returns:
            Discord message/thread ID if successful
        """
        # Determine role category for routing
        role_category = RoleCategory.DEV
        if task.assignee:
            assignee_role = await self.get_assignee_role(task.assignee)
            if assignee_role:
                role_category = self._get_role_category(assignee_role)
                logger.info(f"Routing task {task.id} to {role_category.value} channels (assignee: {task.assignee})")

        # Build the embed
        embed = task.to_discord_embed_dict()
        if "footer" in embed:
            embed["footer"]["text"] = f"{embed['footer']['text']} | {self.REACTION_HELP}"
        else:
            embed["footer"] = {"text": self.REACTION_HELP}

        # Add @mention for assignee if they have a Discord ID
        mention_content = None
        if task.assignee_discord_id:
            mention_content = f"<@{task.assignee_discord_id}> - New task assigned to you!"

        # Check if tasks channel is configured for this category
        tasks_channel_id = self._get_channel_id(ChannelType.TASKS, role_category)
        forum_channel_id = self._get_channel_id(ChannelType.FORUM, role_category)

        # Post to forum channel (creates a thread) if:
        # - Explicitly requested (channel="specs" or "forum")
        # - Task has spec sheet URL (if attribute exists)
        # - No tasks channel configured (fallback to forum for all tasks)
        has_spec_url = getattr(task, 'spec_sheet_url', None)
        use_forum = (
            channel in ["specs", "forum"] or
            has_spec_url or
            not tasks_channel_id  # Fallback to forum when no tasks channel
        )

        if use_forum and forum_channel_id:
            thread_name = f"{task.id}: {task.title}"[:100]
            thread_id = await self.create_forum_thread(
                forum_channel_id=forum_channel_id,
                name=thread_name,
                content=mention_content,
                embed=embed
            )
            if thread_id:
                logger.info(f"Posted task {task.id} to forum channel {forum_channel_id}")
                return thread_id

        # Post to tasks channel (regular message)
        if tasks_channel_id:
            message_id = await self.send_message(
                channel_id=tasks_channel_id,
                content=mention_content,
                embed=embed
            )
            if message_id:
                logger.info(f"Posted task {task.id} to tasks channel {tasks_channel_id}")
                return message_id

        logger.warning(f"No channel configured for task {task.id} (role: {role_category.value})")
        return None

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
        estimated_effort: Optional[str] = None,
        assignee_discord_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Post a detailed spec sheet to the forum channel as a thread.

        Returns:
            Thread ID if successful
        """
        # Determine role category
        role_category = RoleCategory.DEV
        if assignee:
            assignee_role = await self.get_assignee_role(assignee)
            if assignee_role:
                role_category = self._get_role_category(assignee_role)

        forum_channel_id = self._get_channel_id(ChannelType.FORUM, role_category)
        if not forum_channel_id:
            logger.warning("No forum channel configured for spec sheets")
            return None

        # Build the embed
        priority_colors = {
            "urgent": 0xE74C3C,
            "high": 0xE67E22,
            "medium": 0xF1C40F,
            "low": 0x3498DB,
        }
        priority_emoji = {
            "urgent": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🔵",
        }

        color = priority_colors.get(priority.lower(), 0x95A5A6)
        p_emoji = priority_emoji.get(priority.lower(), "⚪")

        criteria_text = "\n".join([f"☐ {c}" for c in acceptance_criteria]) if acceptance_criteria else "None specified"

        embed = {
            "title": f"📋 SPEC: {title}",
            "description": f"**Task ID:** `{task_id}`\n\n{description}",
            "color": color,
            "fields": [
                {"name": "👤 Assignee", "value": assignee or "Unassigned", "inline": True},
                {"name": f"{p_emoji} Priority", "value": priority.upper(), "inline": True},
                {"name": "📅 Deadline", "value": deadline or "Not set", "inline": True},
            ],
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": f"Spec Sheet | {task_id}"}
        }

        if estimated_effort:
            embed["fields"].append({"name": "⏱️ Estimated Effort", "value": estimated_effort, "inline": True})

        embed["fields"].append({"name": "✅ Acceptance Criteria", "value": criteria_text[:1024], "inline": False})

        if technical_details:
            embed["fields"].append({"name": "🔧 Technical Details", "value": technical_details[:1024], "inline": False})

        if dependencies:
            deps_text = "\n".join([f"• {d}" for d in dependencies])
            embed["fields"].append({"name": "🔗 Dependencies", "value": deps_text[:1024], "inline": False})

        if notes:
            embed["fields"].append({"name": "📝 Additional Notes", "value": notes[:1024], "inline": False})

        # Build mention content
        mention_content = None
        if assignee_discord_id:
            mention_content = f"<@{assignee_discord_id}> - New spec sheet for your review!"

        thread_name = f"{task_id}: {title}"[:100]
        return await self.create_forum_thread(
            forum_channel_id=forum_channel_id,
            name=thread_name,
            content=mention_content,
            embed=embed
        )

    async def update_task_embed(self, task: Task, message_id: str, channel_id: Optional[str] = None) -> bool:
        """Update an existing task embed."""
        if not channel_id:
            # Try to find the channel for this task
            role_category = RoleCategory.DEV
            if task.assignee:
                assignee_role = await self.get_assignee_role(task.assignee)
                if assignee_role:
                    role_category = self._get_role_category(assignee_role)
            channel_id = self._get_channel_id(ChannelType.TASKS, role_category)

        if not channel_id:
            return False

        embed = task.to_discord_embed_dict()
        return await self.edit_message(channel_id, message_id, embed=embed)

    async def delete_task_message(self, task_id: str, message_id: str, is_forum_thread: bool = False) -> bool:
        """
        Delete a task's Discord message or forum thread.

        Args:
            task_id: The task ID (for logging)
            message_id: The Discord message or thread ID
            is_forum_thread: Whether this is a forum thread

        Returns:
            True if deleted successfully
        """
        if not message_id:
            logger.debug(f"No Discord message ID for task {task_id}")
            return False

        if is_forum_thread:
            return await self.delete_thread(message_id)

        # For regular messages, we need the channel ID
        # Try to delete as thread first (in case it's a forum post)
        if await self.delete_thread(message_id):
            return True

        # If not a thread, try to find and delete the message
        # This is a limitation - we'd need to store channel_id with the task
        logger.warning(f"Cannot delete message {message_id} - need channel ID for non-thread messages")
        return False

    # ==================== REPORT/ALERT METHODS ====================

    async def post_standup(self, summary: str, role_category: RoleCategory = RoleCategory.DEV) -> bool:
        """Post daily standup summary to the report channel."""
        report_channel_id = self._get_channel_id(ChannelType.REPORT, role_category)
        if not report_channel_id:
            logger.warning("No report channel configured for standup")
            return False

        embed = {
            "title": "☀️ Daily Standup",
            "description": summary,
            "color": 0x3498DB,
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": f"Boss Workflow | {self.REACTION_HELP}"}
        }

        message_id = await self.send_message(report_channel_id, embed=embed)
        return message_id is not None

    async def post_weekly_summary(self, summary: str, role_category: RoleCategory = RoleCategory.DEV) -> bool:
        """Post weekly summary report to the report channel."""
        report_channel_id = self._get_channel_id(ChannelType.REPORT, role_category)
        if not report_channel_id:
            return False

        embed = {
            "title": "📊 Weekly Summary Report",
            "description": summary,
            "color": 0x9B59B6,
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": "Boss Workflow Automation"}
        }

        message_id = await self.send_message(report_channel_id, embed=embed)
        return message_id is not None

    def get_configured_categories(self) -> List[RoleCategory]:
        """Get all role categories that have at least one channel configured."""
        configured = []
        for category in RoleCategory:
            # Check if any channel is configured for this category
            has_channel = any(
                self.channels.get(category, {}).get(channel_type)
                for channel_type in ChannelType
            )
            if has_channel:
                configured.append(category)
        return configured

    async def post_standup_to_all(self, summary: str) -> Dict[str, bool]:
        """
        Post standup to all configured department report channels.

        Returns:
            Dict mapping category name to success status
        """
        results = {}
        for category in self.get_configured_categories():
            report_channel_id = self._get_channel_id(ChannelType.REPORT, category)
            if report_channel_id:
                success = await self.post_standup(summary, category)
                results[category.value] = success
        return results

    async def post_alert(
        self,
        title: str,
        message: str,
        alert_type: str = "warning",
        task: Optional[Task] = None,
        role_category: RoleCategory = RoleCategory.DEV
    ) -> bool:
        """
        Post an alert message to the tasks or general channel.

        Args:
            title: Alert title
            message: Alert message
            alert_type: "warning", "error", "info", "success"
            task: Optional task to include details for
            role_category: Which category's channels to use
        """
        # Try tasks channel first, fall back to general
        channel_id = self._get_channel_id(ChannelType.TASKS, role_category)
        if not channel_id:
            channel_id = self._get_channel_id(ChannelType.GENERAL, role_category)
        if not channel_id:
            logger.warning(f"No channel configured for alerts in {role_category.value}")
            return False

        color_map = {
            "warning": 0xF39C12,
            "error": 0xE74C3C,
            "info": 0x3498DB,
            "success": 0x2ECC71,
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

        message_id = await self.send_message(channel_id, embed=embed)
        return message_id is not None

    async def post_status_change(
        self,
        task: Task,
        old_status: TaskStatus,
        new_status: TaskStatus,
        changed_by: str,
        reason: Optional[str] = None
    ) -> bool:
        """Post a status change notification to the tasks channel."""
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

    async def post_general_message(
        self,
        content: str,
        embed: Optional[Dict] = None,
        role_category: RoleCategory = RoleCategory.DEV
    ) -> Optional[str]:
        """Post a general message to the general channel."""
        general_channel_id = self._get_channel_id(ChannelType.GENERAL, role_category)
        if not general_channel_id:
            logger.warning("No general channel configured")
            return None

        return await self.send_message(general_channel_id, content=content, embed=embed)

    async def post_help(self, role_category: RoleCategory = RoleCategory.DEV) -> bool:
        """Post a help message with reaction guide and available commands."""
        general_channel_id = self._get_channel_id(ChannelType.GENERAL, role_category)
        if not general_channel_id:
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
            "color": 0x3498DB,
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": "Boss Workflow Automation | Send /help in Telegram for full commands"}
        }

        message_id = await self.send_message(general_channel_id, embed=embed)
        return message_id is not None

    async def cleanup_task_channel(self, channel_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Clean up all task-related threads in a channel.

        Args:
            channel_id: Optional channel ID (defaults to dev forum channel)

        Returns:
            Dict with cleanup results
        """
        results = {
            "threads_deleted": 0,
            "threads_failed": 0,
        }

        target_channel = channel_id or self._get_channel_id(ChannelType.FORUM, RoleCategory.DEV)
        if not target_channel:
            logger.warning("No channel ID provided for cleanup")
            return results

        deleted, failed = await self.bulk_delete_threads(target_channel)
        results["threads_deleted"] = deleted
        results["threads_failed"] = failed

        return results

    # ==================== ATTENDANCE NOTIFICATION ====================

    async def send_attendance_notification(
        self,
        embed: Dict,
        channel_type: str = "dev",
        mention_user_id: Optional[str] = None,
    ) -> bool:
        """
        Send an attendance notification to the appropriate general channel.

        Args:
            embed: The Discord embed to send
            channel_type: "dev" or "admin" to determine which channel
            mention_user_id: Optional Discord user ID to @mention

        Returns:
            True if sent successfully
        """
        # Determine role category
        role_category = RoleCategory.ADMIN if channel_type == "admin" else RoleCategory.DEV

        # Get the general channel for this category
        general_channel_id = self._get_channel_id(ChannelType.GENERAL, role_category)
        if not general_channel_id:
            logger.warning(f"No general channel configured for {channel_type}")
            return False

        # Build content with mention if provided
        content = None
        if mention_user_id:
            content = f"<@{mention_user_id}>"

        message_id = await self.send_message(
            channel_id=general_channel_id,
            content=content,
            embed=embed
        )

        if message_id:
            logger.info(f"Sent attendance notification to {channel_type} channel")
            return True

        logger.warning(f"Failed to send attendance notification to {channel_type} channel")
        return False


# Singleton instance
discord_integration = DiscordIntegration()


def get_discord_integration() -> DiscordIntegration:
    """Get the Discord integration instance."""
    return discord_integration
