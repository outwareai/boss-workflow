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

    # v2.2: Task keyword to role mapping for smart routing
    TASK_KEYWORD_ROLES = {
        # Dev keywords
        "bug": RoleCategory.DEV,
        "fix": RoleCategory.DEV,
        "code": RoleCategory.DEV,
        "api": RoleCategory.DEV,
        "database": RoleCategory.DEV,
        "deploy": RoleCategory.DEV,
        "refactor": RoleCategory.DEV,
        "test": RoleCategory.DEV,
        "implement": RoleCategory.DEV,
        "debug": RoleCategory.DEV,
        "backend": RoleCategory.DEV,
        "frontend": RoleCategory.DEV,
        "server": RoleCategory.DEV,
        "integration": RoleCategory.DEV,
        # Admin keywords
        "meeting": RoleCategory.ADMIN,
        "schedule": RoleCategory.ADMIN,
        "report": RoleCategory.ADMIN,
        "document": RoleCategory.ADMIN,
        "process": RoleCategory.ADMIN,
        "review": RoleCategory.ADMIN,
        "approve": RoleCategory.ADMIN,
        "coordinate": RoleCategory.ADMIN,
        "organize": RoleCategory.ADMIN,
        "plan": RoleCategory.ADMIN,
        # Marketing keywords
        "campaign": RoleCategory.MARKETING,
        "social": RoleCategory.MARKETING,
        "content": RoleCategory.MARKETING,
        "email": RoleCategory.MARKETING,
        "influencer": RoleCategory.MARKETING,
        "seo": RoleCategory.MARKETING,
        "ads": RoleCategory.MARKETING,
        "post": RoleCategory.MARKETING,
        "brand": RoleCategory.MARKETING,
        "outreach": RoleCategory.MARKETING,
        # Design keywords
        "design": RoleCategory.DESIGN,
        "mockup": RoleCategory.DESIGN,
        "ui": RoleCategory.DESIGN,
        "ux": RoleCategory.DESIGN,
        "logo": RoleCategory.DESIGN,
        "graphic": RoleCategory.DESIGN,
        "wireframe": RoleCategory.DESIGN,
        "prototype": RoleCategory.DESIGN,
        "visual": RoleCategory.DESIGN,
    }

    def _infer_role_from_task_content(self, task_title: str, task_description: str = "") -> RoleCategory:
        """
        v2.2: Infer the appropriate role category from task content.

        Used when no assignee is specified to route to the right channel.
        """
        text = f"{task_title} {task_description}".lower()

        # Count keyword matches for each category
        role_scores = {
            RoleCategory.DEV: 0,
            RoleCategory.ADMIN: 0,
            RoleCategory.MARKETING: 0,
            RoleCategory.DESIGN: 0,
        }

        for keyword, category in self.TASK_KEYWORD_ROLES.items():
            if keyword in text:
                role_scores[category] += 1

        # Find category with highest score
        max_score = max(role_scores.values())
        if max_score > 0:
            for category, score in role_scores.items():
                if score == max_score:
                    logger.info(f"v2.2: Inferred role {category.value} from task keywords (score: {score})")
                    return category

        return RoleCategory.DEV  # Default to dev

    def _get_channel_id(self, channel_type: ChannelType, role_category: RoleCategory = RoleCategory.DEV) -> Optional[str]:
        """
        Get the channel ID for a given type and role category.

        Falls back to DEV category if the specific category's channel is not configured,
        EXCEPT for TASKS channels - don't fall back, so forum is used instead.
        """
        # Try the specific category first
        channel_id = self.channels.get(role_category, {}).get(channel_type, "")

        # Fall back to DEV category if not configured
        # BUT NOT for TASKS type - we want to use FORUM instead when tasks channel isn't set
        if not channel_id and role_category != RoleCategory.DEV:
            if channel_type != ChannelType.TASKS:
                channel_id = self.channels.get(RoleCategory.DEV, {}).get(channel_type, "")
            # For TASKS: return None so post_task uses forum channel instead

        return channel_id if channel_id else None

    async def get_assignee_role(self, assignee: str) -> Optional[str]:
        """
        Look up an assignee's role from database or Google Sheets.

        Checks in order:
        1. PostgreSQL database (fast)
        2. Google Sheets Team tab (fallback, always up-to-date)
        """
        if not assignee:
            logger.debug("get_assignee_role: No assignee provided")
            return None

        assignee_lower = assignee.strip().lower()
        logger.info(f"Looking up role for assignee: '{assignee}' (normalized: '{assignee_lower}')")

        # Try database first (faster)
        try:
            from ..database.repositories import get_team_repository
            team_repo = get_team_repository()
            member = await team_repo.find_member(assignee)
            if member and member.role:
                logger.info(f"Found role for '{assignee}': '{member.role}' (source: database)")
                return member.role
            else:
                logger.debug(f"No database match for {assignee}")
        except Exception as e:
            logger.debug(f"Database lookup failed for {assignee}: {e}")

        # Fallback to Google Sheets (source of truth)
        try:
            from .sheets import sheets_integration
            team_members = await sheets_integration.get_all_team_members()
            logger.info(f"Checking {len(team_members)} team members in Sheets")

            # Debug: log the actual keys from first record
            if team_members:
                first_keys = list(team_members[0].keys())
                logger.info(f"Sheet column headers: {first_keys}")

            for member in team_members:
                # Get name from multiple possible columns
                # Try: "Name", empty string "", first value in dict, "Nickname"
                member_name = None

                # Try explicit column names
                for key in ["Name", "", "Nickname", "name", "nickname"]:
                    if key in member and member[key]:
                        member_name = str(member[key]).strip()
                        break

                # Fallback: use FIRST column value (whatever the header is)
                if not member_name:
                    first_key = list(member.keys())[0] if member else None
                    if first_key is not None:
                        member_name = str(member[first_key]).strip()
                        logger.debug(f"Using first column '{first_key}' value: {member_name}")

                if not member_name:
                    continue

                member_name_lower = member_name.lower()

                # Check multiple matching strategies
                if (member_name_lower == assignee_lower or
                    assignee_lower in member_name_lower or
                    member_name_lower in assignee_lower):
                    role = member.get("Role", "") or member.get("role", "")
                    if role:
                        logger.info(f"Found role for '{assignee}' in Sheets: '{role}' (matched name: '{member_name}')")
                        return role
                    else:
                        logger.warning(f"Found '{assignee}' in Sheets but no Role set")

            # Log all names for debugging
            all_names = []
            for m in team_members:
                first_key = list(m.keys())[0] if m else None
                name = m.get("Name") or m.get("") or (m.get(first_key) if first_key else None) or "?"
                all_names.append(str(name))
            logger.warning(f"No match for '{assignee}' in team members: {all_names}")
        except Exception as e:
            logger.error(f"Sheets lookup failed for {assignee}: {e}")

        return None

    async def _api_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        queue_on_failure: bool = True
    ) -> Tuple[int, Optional[Dict]]:
        """
        Make a Discord API request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            json_data: Request body
            queue_on_failure: If True, queue failed POST requests for retry

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

                        # Queue for retry on server errors (5xx) or rate limits (429)
                        if queue_on_failure and method == "POST" and response.status in [429, 500, 502, 503, 504]:
                            await self._queue_failed_request(endpoint, json_data, f"HTTP {response.status}: {error[:200]}")

                        return (response.status, None)
        except Exception as e:
            logger.error(f"Discord API request failed: {e}")

            # Queue for retry on network errors
            if queue_on_failure and method == "POST":
                await self._queue_failed_request(endpoint, json_data, str(e))

            return (0, None)

    async def _queue_failed_request(
        self,
        endpoint: str,
        json_data: Optional[Dict],
        error: str
    ) -> None:
        """Queue a failed Discord API request for retry."""
        try:
            from ..services.message_queue import get_message_queue, MessageType

            queue = get_message_queue()
            msg_id = await queue.enqueue_failed(
                message_type=MessageType.DISCORD_BOT,
                payload={
                    "endpoint": endpoint,
                    "json_data": json_data,
                },
                error=error,
                metadata={"api": "discord_bot"}
            )
            logger.info(f"Queued failed Discord request for retry: {msg_id}")
        except Exception as e:
            logger.warning(f"Could not queue failed request: {e}")

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

    async def get_forum_tags(self, forum_channel_id: str) -> List[Dict]:
        """
        Get available tags for a forum channel.

        Returns list of tag objects with 'id' and 'name' fields.
        """
        if not forum_channel_id:
            return []

        status, data = await self._api_request("GET", f"/channels/{forum_channel_id}")
        if data and "available_tags" in data:
            tags = data.get("available_tags", [])
            logger.info(f"Forum channel {forum_channel_id} has {len(tags)} tags: {[t.get('name') for t in tags]}")
            return tags
        return []

    async def create_forum_thread(
        self,
        forum_channel_id: str,
        name: str,
        content: Optional[str] = None,
        embed: Optional[Dict] = None,
        auto_archive_duration: int = 1440,  # 24 hours
        tag_ids: Optional[List[str]] = None  # Specific tag IDs to apply
    ) -> Optional[str]:
        """
        Create a new forum thread (post).

        Args:
            forum_channel_id: The forum channel ID
            name: Thread name (e.g., "TASK-001: Build login page")
            content: Initial message content
            embed: Initial message embed
            auto_archive_duration: Minutes until auto-archive (60, 1440, 4320, 10080)
            tag_ids: List of tag IDs to apply (if None, uses first available tag)

        Returns:
            Thread ID if successful, None otherwise
        """
        if not forum_channel_id:
            logger.warning("No forum channel ID provided for create_forum_thread")
            return None

        logger.info(f"Creating forum thread in channel {forum_channel_id}: {name}")

        # Get available tags if none specified (some forums require tags)
        applied_tag_ids = tag_ids
        if not applied_tag_ids:
            available_tags = await self.get_forum_tags(forum_channel_id)
            if available_tags:
                # Default to "Pending" tag for new tasks, fall back to first tag
                tag_names = {t.get("name", "").lower(): t.get("id") for t in available_tags}
                default_tag_id = tag_names.get("pending") or available_tags[0].get("id")
                default_tag_name = "Pending" if "pending" in tag_names else available_tags[0].get("name")
                applied_tag_ids = [default_tag_id]
                logger.info(f"Using default tag: {default_tag_name} ({default_tag_id})")

        payload = {
            "name": name[:100],  # Discord limit
            "auto_archive_duration": auto_archive_duration,
            "message": {}
        }

        # Add tags if available (required by some forum channels)
        if applied_tag_ids:
            payload["applied_tags"] = applied_tag_ids

        if content:
            payload["message"]["content"] = content[:2000] if len(content) > 2000 else content  # Discord limit
        if embed:
            payload["message"]["embeds"] = [embed]

        if not payload["message"]:
            payload["message"]["content"] = "Thread created"

        logger.debug(f"Forum thread payload: name={name[:50]}..., tags={applied_tag_ids}")

        status, data = await self._api_request("POST", f"/channels/{forum_channel_id}/threads", payload)

        if data:
            thread_id = data.get("id")
            logger.info(f"Created forum thread successfully: {name} (ID: {thread_id})")
            return thread_id

        logger.error(f"Failed to create forum thread '{name}' in channel {forum_channel_id} - API returned status {status}")
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

    async def pin_thread(self, thread_id: str) -> bool:
        """
        Pin a forum thread so it appears at the top of the forum.

        Args:
            thread_id: The thread/post ID to pin

        Returns:
            True if pinned successfully
        """
        if not thread_id:
            return False

        # Discord forum threads use flags field - PINNED = 1 << 1 = 2
        payload = {"flags": 2}

        status, _ = await self._api_request("PATCH", f"/channels/{thread_id}", payload)

        if status == 200:
            logger.info(f"Pinned forum thread {thread_id}")
            return True
        else:
            logger.warning(f"Failed to pin thread {thread_id}, status: {status}")
            return False

    async def unpin_thread(self, thread_id: str) -> bool:
        """
        Unpin a forum thread.

        Args:
            thread_id: The thread/post ID to unpin

        Returns:
            True if unpinned successfully
        """
        if not thread_id:
            return False

        # Remove PINNED flag by setting flags to 0
        payload = {"flags": 0}

        status, _ = await self._api_request("PATCH", f"/channels/{thread_id}", payload)

        if status == 200:
            logger.info(f"Unpinned forum thread {thread_id}")
            return True
        else:
            logger.warning(f"Failed to unpin thread {thread_id}, status: {status}")
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
        logger.info(f"post_task called for {task.id}, assignee: {task.assignee}, channel hint: {channel}")

        # Determine role category for routing (v2.2: enhanced with keyword inference)
        role_category = RoleCategory.DEV
        if task.assignee:
            assignee_role = await self.get_assignee_role(task.assignee)
            if assignee_role:
                role_category = self._get_role_category(assignee_role)
                logger.info(f"Found role '{assignee_role}' for assignee {task.assignee}")
            else:
                # v2.2: No role found for assignee, try keyword inference
                role_category = self._infer_role_from_task_content(task.title, task.description or "")
                logger.info(f"v2.2: No role for {task.assignee}, inferred {role_category.value} from task keywords")
        else:
            # v2.2: No assignee, infer from task content
            role_category = self._infer_role_from_task_content(task.title, task.description or "")
            logger.info(f"v2.2: No assignee, inferred {role_category.value} from task keywords")

        # Log explicit routing decision (for test parsing)
        logger.info(f"Routing task {task.id} to {role_category.value} channel (assignee: {task.assignee or 'none'})")

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

        # Get forum channel for this role category - v2.1.3 FORUM ONLY
        forum_channel_id = self._get_channel_id(ChannelType.FORUM, role_category)
        logger.info(f"[v2.1.3] FORUM ONLY - {role_category.value}: forum_channel={forum_channel_id}")

        # ALWAYS use forum channel for tasks - each task gets a thread
        # This is the correct workflow: task -> forum thread -> staff replies -> completion
        use_forum = True

        if use_forum and forum_channel_id:
            thread_name = f"{task.id}: {task.title}"[:100]

            # Map task priority to forum tag
            priority_tag_ids = None
            if task.priority:
                available_tags = await self.get_forum_tags(forum_channel_id)
                if available_tags:
                    tag_map = {t.get("name", "").lower(): t.get("id") for t in available_tags}
                    priority_lower = task.priority.value.lower() if hasattr(task.priority, 'value') else str(task.priority).lower()
                    # Map priority to tag: critical->urgent, high->high, medium->medium, low->low
                    priority_to_tag = {
                        "critical": "urgent",
                        "urgent": "urgent",
                        "high": "high",
                        "medium": "medium",
                        "low": "low",
                    }
                    tag_name = priority_to_tag.get(priority_lower, "pending")
                    if tag_name in tag_map:
                        priority_tag_ids = [tag_map[tag_name]]
                        logger.info(f"Using priority-based tag: {tag_name} for task priority {priority_lower}")

            thread_id = await self.create_forum_thread(
                forum_channel_id=forum_channel_id,
                name=thread_name,
                content=mention_content,
                embed=embed,
                tag_ids=priority_tag_ids  # Pass priority-based tag
            )
            if thread_id:
                # Auto-pin the thread so it appears at top of forum
                await self.pin_thread(thread_id)
                logger.info(f"Posted task {task.id} to forum channel {forum_channel_id} (pinned)")

                # Auto-link thread to task for AI assistant routing
                try:
                    from ..memory.task_context import get_task_context_manager
                    context_manager = get_task_context_manager()
                    await context_manager.link_thread_to_task(
                        thread_id=thread_id,
                        task_id=task.id,
                        channel_id=forum_channel_id
                    )
                    logger.info(f"Auto-linked thread {thread_id} to task {task.id}")
                except Exception as link_err:
                    logger.warning(f"Could not auto-link thread to task: {link_err}")

                return thread_id

        logger.warning(f"No forum channel configured for task {task.id} (role: {role_category.value})")
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
        assignee_discord_id: Optional[str] = None,
        subtasks: Optional[List[dict]] = None
    ) -> Optional[str]:
        """
        Post a detailed spec sheet (PRD-style) to the forum channel as a thread.

        Creates a comprehensive specification document with:
        - Full PRD-style content as the first message
        - Task summary embed as the second message

        Returns:
            Thread ID if successful
        """
        logger.info(f"post_spec_sheet called for task {task_id}, assignee: {assignee}")

        # Determine role category
        role_category = RoleCategory.DEV
        if assignee:
            assignee_role = await self.get_assignee_role(assignee)
            if assignee_role:
                role_category = self._get_role_category(assignee_role)
                logger.info(f"Assignee {assignee} has role '{assignee_role}' -> category {role_category.value}")
            else:
                logger.info(f"No role found for assignee {assignee}, using default DEV category")

        forum_channel_id = self._get_channel_id(ChannelType.FORUM, role_category)
        logger.info(f"Forum channel ID for {role_category.value}: {forum_channel_id}")

        if not forum_channel_id:
            logger.warning(f"No forum channel configured for spec sheets (role: {role_category.value})")
            return None

        priority_emoji = {
            "urgent": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🔵",
        }
        p_emoji = priority_emoji.get((priority or "medium").lower(), "⚪")

        # Build PRD-style spec sheet content
        spec_content = []

        # Header with assignee mention
        if assignee_discord_id:
            spec_content.append(f"**Assigned to:** <@{assignee_discord_id}>")
        else:
            spec_content.append(f"**Assigned to:** {assignee or 'Unassigned'}")

        spec_content.append("")
        spec_content.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        spec_content.append(f"# 📋 {title}")
        spec_content.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        spec_content.append("")

        # Metadata section
        spec_content.append("## 📊 Task Metadata")
        spec_content.append(f"- **Task ID:** `{task_id}`")
        spec_content.append(f"- **Priority:** {p_emoji} {(priority or 'medium').upper()}")
        spec_content.append(f"- **Deadline:** {deadline or 'Not specified'}")
        spec_content.append(f"- **Estimated Effort:** {estimated_effort or 'TBD'}")
        spec_content.append(f"- **Status:** ⏳ Pending")
        spec_content.append("")

        # Description section
        spec_content.append("## 📝 Description")
        spec_content.append(description)
        spec_content.append("")

        # Subtasks section - each with full paragraph description
        if subtasks:
            spec_content.append("## 🔨 Implementation Tasks")
            spec_content.append("")
            for i, st in enumerate(subtasks, 1):
                if isinstance(st, dict):
                    st_title = st.get("title", f"Subtask {i}")
                    st_desc = st.get("description", "")
                    spec_content.append(f"### Task {i}: {st_title}")
                    spec_content.append("")
                    if st_desc:
                        # Full paragraph description
                        spec_content.append(st_desc)
                        spec_content.append("")
                else:
                    spec_content.append(f"### Task {i}: {st}")
                    spec_content.append("")

        # Acceptance criteria section
        if acceptance_criteria:
            spec_content.append("## ✅ Acceptance Criteria")
            for c in acceptance_criteria:
                spec_content.append(f"- [ ] {c}")
            spec_content.append("")

        # Technical details
        if technical_details:
            spec_content.append("## 🔧 Technical Considerations")
            spec_content.append(technical_details)
            spec_content.append("")

        # Dependencies
        if dependencies:
            spec_content.append("## 🔗 Dependencies")
            for dep in dependencies:
                spec_content.append(f"- {dep}")
            spec_content.append("")

        # Notes
        if notes:
            spec_content.append("## 📌 Additional Notes")
            spec_content.append(notes)
            spec_content.append("")

        # Footer
        spec_content.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        spec_content.append(f"*Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
        spec_content.append("")
        spec_content.append("**Actions:** React ✅=Done | 🚧=Working | 🚫=Blocked | ⏸️=Paused | 🔄=Review")

        thread_name = f"📋 {task_id}: {title}"[:100]
        full_content = "\n".join(spec_content)

        # Discord has 2000 char limit per message - split if needed
        if len(full_content) <= 2000:
            # Single message fits
            thread_id = await self.create_forum_thread(
                forum_channel_id=forum_channel_id,
                name=thread_name,
                content=full_content,
                embed=None
            )
            if thread_id:
                # Auto-pin the thread so it appears at top of forum
                await self.pin_thread(thread_id)

                # Auto-link thread to task for AI assistant routing
                try:
                    from ..memory.task_context import get_task_context_manager
                    context_manager = get_task_context_manager()
                    await context_manager.link_thread_to_task(
                        thread_id=thread_id,
                        task_id=task_id,
                        channel_id=forum_channel_id
                    )
                    logger.info(f"Auto-linked spec thread {thread_id} to task {task_id}")
                except Exception as link_err:
                    logger.warning(f"Could not auto-link spec thread to task: {link_err}")

            return thread_id

        # Split content into chunks for multiple messages
        # First message: thread creation with initial content
        # Subsequent messages: continuation in the thread
        chunks = self._split_content_for_discord(full_content)
        logger.info(f"Spec sheet content is {len(full_content)} chars, splitting into {len(chunks)} messages")

        # Create thread with first chunk
        thread_id = await self.create_forum_thread(
            forum_channel_id=forum_channel_id,
            name=thread_name,
            content=chunks[0],
            embed=None
        )

        if not thread_id:
            logger.error("Failed to create forum thread for spec sheet")
            return None

        # Auto-pin the thread so it appears at top of forum
        await self.pin_thread(thread_id)

        # Auto-link thread to task for AI assistant routing
        try:
            from ..memory.task_context import get_task_context_manager
            context_manager = get_task_context_manager()
            await context_manager.link_thread_to_task(
                thread_id=thread_id,
                task_id=task_id,
                channel_id=forum_channel_id
            )
            logger.info(f"Auto-linked spec thread {thread_id} to task {task_id}")
        except Exception as link_err:
            logger.warning(f"Could not auto-link spec thread to task: {link_err}")

        # Send remaining chunks as follow-up messages in the thread
        for i, chunk in enumerate(chunks[1:], start=2):
            await asyncio.sleep(0.3)  # Rate limit protection
            msg_id = await self.send_message(
                channel_id=thread_id,  # Thread ID is also a channel ID
                content=chunk
            )
            if msg_id:
                logger.debug(f"Posted continuation message {i}/{len(chunks)} to thread {thread_id}")
            else:
                logger.warning(f"Failed to post continuation message {i}/{len(chunks)} to thread {thread_id}")

        return thread_id

    def _split_content_for_discord(self, content: str, max_length: int = 1900) -> List[str]:
        """
        Split content into chunks that fit Discord's message limit.
        Tries to split at natural boundaries (sections, paragraphs, lines).
        """
        if len(content) <= max_length:
            return [content]

        chunks = []
        remaining = content

        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break

            # Find a good split point
            chunk = remaining[:max_length]

            # Try to split at section boundary (##)
            section_split = chunk.rfind("\n## ")
            if section_split > max_length // 2:
                chunk = remaining[:section_split]
                remaining = remaining[section_split:]
                chunks.append(chunk.strip())
                continue

            # Try to split at double newline (paragraph)
            para_split = chunk.rfind("\n\n")
            if para_split > max_length // 2:
                chunk = remaining[:para_split]
                remaining = remaining[para_split + 2:]
                chunks.append(chunk.strip())
                continue

            # Try to split at single newline
            line_split = chunk.rfind("\n")
            if line_split > max_length // 2:
                chunk = remaining[:line_split]
                remaining = remaining[line_split + 1:]
                chunks.append(chunk.strip())
                continue

            # Hard split at max length (last resort)
            chunks.append(remaining[:max_length].strip())
            remaining = remaining[max_length:]

        return [c for c in chunks if c]  # Remove empty chunks

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

    async def post_simple_message(
        self,
        content: str,
        role_category: RoleCategory = RoleCategory.DEV
    ) -> Optional[str]:
        """
        Post a simple message to the general channel.
        Alias for post_general_message for convenience.
        """
        return await self.post_general_message(content, role_category=role_category)

    async def post_task_update(
        self,
        task_id: str,
        updates: Dict[str, str],
        updated_by: str,
        update_type: str,
        role_category: RoleCategory = RoleCategory.DEV
    ) -> bool:
        """
        Post task update notification to Discord with rich formatting.

        Args:
            task_id: The task ID being updated
            updates: Dict of field -> value changes (e.g. {"priority": "high -> urgent"})
            updated_by: Who made the update
            update_type: Type of update (modification, reassignment, etc.)
            role_category: Which role category's channel to post to

        Returns:
            True if posted successfully
        """
        # Update type to emoji mapping
        update_emoji = {
            "modification": "✏️",
            "reassignment": "👤",
            "priority_change": "⚡",
            "deadline_change": "📅",
            "status_change": "🔄",
            "tags_added": "🏷️",
            "tags_removed": "🏷️",
            "subtask_added": "➕",
            "subtask_completed": "✅",
            "dependency_added": "🔗",
            "dependency_removed": "🔓",
        }

        emoji = update_emoji.get(update_type, "📝")

        # Format changes as embed fields
        changes_text = "\n".join([f"**{k}:** {v}" for k, v in updates.items()])

        embed = {
            "title": f"{emoji} Task Updated: {task_id}",
            "description": changes_text,
            "color": 3447003,  # Blue
            "footer": {
                "text": f"Updated by {updated_by}"
            },
            "timestamp": datetime.now().isoformat()
        }

        # Post to tasks channel
        tasks_channel_id = self._get_channel_id(ChannelType.TASKS, role_category)
        if not tasks_channel_id:
            logger.warning(f"No tasks channel configured for {role_category}")
            return False

        message_id = await self.send_message(tasks_channel_id, embed=embed)
        return message_id is not None

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

    # ==================== DIRECT TEAM COMMUNICATION ====================

    async def send_direct_message_to_team(
        self,
        target_name: str,
        message_content: str,
        from_boss: bool = True
    ) -> Tuple[bool, str]:
        """
        Send a direct message to a team member via Discord.

        Routes to the appropriate general channel based on team member's role.

        Args:
            target_name: The team member's name (e.g., "Mayank")
            message_content: The message to send
            from_boss: Whether this message is from the boss

        Returns:
            Tuple of (success, response_message)
        """
        if not target_name:
            return False, "No target name provided"

        # Look up team member's role to determine channel
        assignee_role = await self.get_assignee_role(target_name)
        role_category = self._get_role_category(assignee_role) if assignee_role else RoleCategory.DEV

        # Get the general channel for this category
        channel_id = self._get_channel_id(ChannelType.GENERAL, role_category)
        if not channel_id:
            return False, f"No Discord channel configured for {target_name}'s team"

        # Try to get Discord user ID for mention
        discord_user_id = None

        # First try Google Sheets (more reliable, always up-to-date)
        try:
            from .sheets import sheets_integration
            team_members = await sheets_integration.get_all_team_members()
            logger.info(f"Looking for {target_name} in {len(team_members)} team members")

            for member in team_members:
                member_name = member.get("Name", "").strip().lower()
                # Try multiple possible column names for Discord ID
                discord_id = (
                    member.get("Discord ID") or
                    member.get("Discord Id") or
                    member.get("DiscordID") or
                    member.get("discord_id") or
                    member.get("Discord") or
                    ""
                )

                if member_name == target_name.lower() or target_name.lower() in member_name:
                    logger.info(f"Found team member: {member_name}, Discord ID: '{discord_id}'")
                    if discord_id and str(discord_id).strip():
                        discord_user_id = str(discord_id).strip()
                    break
        except Exception as e:
            logger.warning(f"Could not get Discord ID from Sheets for {target_name}: {e}")

        # Fallback to database
        if not discord_user_id:
            try:
                from ..database.repositories import get_team_repository
                team_repo = get_team_repository()
                member = await team_repo.find_member(target_name)
                if member and member.discord_id:
                    discord_user_id = str(member.discord_id).strip()
                    logger.info(f"Found Discord ID from database: {discord_user_id}")
            except Exception as e:
                logger.debug(f"Could not get Discord ID from database for {target_name}: {e}")

        # Build the embed - clean and direct
        embed = {
            "description": message_content,
            "color": 0x3498DB,
            "timestamp": datetime.now().isoformat(),
        }

        # Build mention content
        content = None
        if discord_user_id:
            content = f"<@{discord_user_id}>"
        else:
            content = f"**@{target_name}** (no Discord ID configured)"

        # Send the message
        message_id = await self.send_message(
            channel_id=channel_id,
            content=content,
            embed=embed
        )

        if message_id:
            logger.info(f"Sent direct message to {target_name} (channel: {channel_id})")
            return True, f"Message sent to {target_name}"
        else:
            logger.error(f"Failed to send direct message to {target_name}")
            return False, f"Failed to send message to {target_name}"

    async def ask_team_member_status(
        self,
        target_name: str,
        question: str
    ) -> Tuple[bool, str]:
        """
        Ask a team member about their task status or other work-related question.

        Args:
            target_name: The team member's name
            question: The question or request from boss

        Returns:
            Tuple of (success, response_message)
        """
        # Format the question nicely
        formatted_message = f"**Question from Boss:**\n{question}\n\n_Please respond in this channel._"

        return await self.send_direct_message_to_team(
            target_name=target_name,
            message_content=formatted_message,
            from_boss=True
        )

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
