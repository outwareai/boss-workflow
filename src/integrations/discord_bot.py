"""
Discord Bot for reaction-based task status updates.

Listens for emoji reactions on task messages and updates status accordingly.

Reaction mapping:
- ✅ → completed
- 🚧 → in_progress
- 🚫 → blocked
- ⏸️ → on_hold
- 🔄 → in_review
- ❌ → cancelled
"""

import logging
import asyncio
from typing import Optional, Dict
from datetime import datetime

import discord
from discord.ext import commands

from config import settings

logger = logging.getLogger(__name__)


# Reaction to status mapping
REACTION_STATUS_MAP = {
    "✅": "completed",
    "🚧": "in_progress",
    "🚫": "blocked",
    "⏸️": "on_hold",
    "⏸": "on_hold",  # Alternative pause emoji
    "🔄": "in_review",
    "❌": "cancelled",
    "🔴": "urgent",  # Special: changes priority, not status
    "⏳": "pending",
    "👀": "in_review",
}

# Status to reaction (for bot to add reactions to new messages)
STATUS_REACTION_MAP = {
    "completed": "✅",
    "in_progress": "🚧",
    "blocked": "🚫",
    "on_hold": "⏸️",
    "in_review": "🔄",
    "cancelled": "❌",
    "pending": "⏳",
}

# Attendance channel mapping (channel_id -> department name)
# These are the channels where staff send "in", "out", "break" messages
ATTENDANCE_CHANNELS = {
    1462451610184843449: "dev",    # Dev attendance channel
    1462451782470078628: "admin",  # Admin attendance channel
}

# Attendance command reactions
ATTENDANCE_REACTIONS = {
    "in": "✅",      # Clock in
    "out": "👋",     # Clock out
    "break_start": "☕",  # Break started
    "break_end": "💪",   # Break ended
    "late": "⏰",     # Late indicator
    "error": "⚠️",    # Error
}


class TaskingBot(commands.Bot):
    """Discord bot for task management via reactions."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix="/",
            intents=intents,
            help_command=None
        )

        # Track message_id -> task_id mapping
        self._message_task_map: Dict[int, str] = {}

        # Callback for status updates (set by main app)
        self.on_status_update_callback = None
        self.on_priority_update_callback = None

        # Callback for attendance events (set by main app)
        self.on_attendance_callback = None

        # Callback for task submissions (staff completing tasks with proof)
        self.on_task_submission_callback = None

        # Callback for staff messages (AI assistant conversations)
        self.on_staff_message_callback = None

        # Channels where the AI assistant should respond
        # These are the general/tasks channels where staff can chat
        self._ai_assistant_channels: set = set()

    def enable_ai_assistant_for_channel(self, channel_id: int) -> None:
        """Enable AI assistant responses in a channel."""
        self._ai_assistant_channels.add(channel_id)
        logger.info(f"AI assistant enabled for channel {channel_id}")

    def disable_ai_assistant_for_channel(self, channel_id: int) -> None:
        """Disable AI assistant responses in a channel."""
        self._ai_assistant_channels.discard(channel_id)

    async def setup_hook(self):
        """Called when bot is ready to set up."""
        logger.info("Discord bot setup hook called")

        # Register slash commands
        @self.command(name="help")
        async def help_command(ctx):
            """Show help message for team members."""
            embed = discord.Embed(
                title="📖 Team Member Guide",
                description="""**Your Tasks Appear Here**
When boss assigns you a task, it shows up in this channel.

**Update Status by Reacting:**
✅ I'm done (completed)
🚧 Working on it (in progress)
🚫 I'm stuck (blocked)
⏸️ Paused (on hold)
🔄 Ready for review
❌ Can't do this (cancelled)
⏳ Haven't started (pending)
🔴 This is urgent!

**How It Works:**
1. Find your task message
2. Click a reaction emoji
3. Status updates automatically
4. Boss gets notified

**Need to Submit Work?**
Message the boss on Telegram with proof (screenshots, links).

**Questions?**
Contact boss directly on Telegram.""",
                color=0x2ECC71  # Green for team
            )
            embed.set_footer(text="Boss Workflow | Your reactions sync instantly")
            await ctx.send(embed=embed)
            logger.info(f"Help command used by {ctx.author}")

    async def on_ready(self):
        """Called when bot successfully connects."""
        logger.info(f"Discord bot connected as {self.user.name} ({self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")

        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="tasks | React to update status"
            )
        )

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handle reaction added to any message."""
        # Ignore bot's own reactions
        if payload.user_id == self.user.id:
            return

        emoji = str(payload.emoji)
        logger.debug(f"Reaction added: {emoji} on message {payload.message_id} by user {payload.user_id}")

        # Check if this reaction maps to a status
        if emoji not in REACTION_STATUS_MAP:
            return

        new_status = REACTION_STATUS_MAP[emoji]

        # Special case: priority change
        if new_status == "urgent":
            await self._handle_priority_change(payload, "urgent")
            return

        # Try to find the task for this message
        task_id = await self._get_task_for_message(payload.message_id, payload.channel_id)

        if not task_id:
            logger.debug(f"No task found for message {payload.message_id}")
            return

        # Get user info
        user = self.get_user(payload.user_id)
        if not user:
            try:
                user = await self.fetch_user(payload.user_id)
            except:
                user = None

        user_name = user.display_name if user else f"User {payload.user_id}"

        logger.info(f"Status update via reaction: {task_id} -> {new_status} by {user_name}")

        # Call the callback to update status
        if self.on_status_update_callback:
            try:
                await self.on_status_update_callback(
                    task_id=task_id,
                    new_status=new_status,
                    changed_by=user_name,
                    source="discord_reaction"
                )

                # React with checkmark to confirm
                channel = self.get_channel(payload.channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(payload.message_id)
                        # Add a confirmation reaction
                        await message.add_reaction("👍")
                        # Remove it after 2 seconds
                        await asyncio.sleep(2)
                        await message.remove_reaction("👍", self.user)
                    except:
                        pass

            except Exception as e:
                logger.error(f"Error updating task status: {e}")

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Handle reaction removed - optional: could revert status."""
        # For now, we don't revert on reaction remove
        # Could implement "undo" logic here if needed
        pass

    async def on_message(self, message: discord.Message):
        """
        Handle messages for:
        1. Attendance tracking ("in", "out", "break")
        2. Task completion submissions ("I finished TASK-XXX")
        3. AI Assistant conversations (staff questions, help)
        """
        # Ignore bot's own messages
        if message.author.bot:
            return

        # Check if this is an attendance channel
        channel_name = ATTENDANCE_CHANNELS.get(message.channel.id)
        if channel_name:
            # Handle attendance in attendance channels
            await self._handle_attendance_message(message, channel_name)
            return

        # Check for task completion messages in any other channel
        await self._handle_potential_submission(message)

        # Check if AI assistant should respond in this channel
        # Respond in: enabled channels, threads, or when bot is mentioned
        should_respond_ai = (
            message.channel.id in self._ai_assistant_channels or
            isinstance(message.channel, discord.Thread) or
            self.user in message.mentions
        )

        if should_respond_ai and self.on_staff_message_callback:
            await self._handle_staff_ai_message(message)

        # Process commands normally
        await self.process_commands(message)

    async def _handle_staff_ai_message(self, message: discord.Message):
        """Handle a message that should be processed by the AI assistant."""
        try:
            # Get thread ID if in a thread
            thread_id = None
            if isinstance(message.channel, discord.Thread):
                thread_id = str(message.channel.id)

            # Extract attachment URLs
            attachments = [att.url for att in message.attachments]

            # Call the staff message handler
            result = await self.on_staff_message_callback(
                user_id=str(message.author.id),
                user_name=message.author.display_name,
                message=message.content,
                channel_id=str(message.channel.id),
                channel_name=message.channel.name if hasattr(message.channel, 'name') else "thread",
                message_url=message.jump_url,
                attachments=attachments,
                thread_id=thread_id
            )

            if result.get("success") and result.get("response"):
                # Send the AI response
                response_text = result.get("response", "")

                # Split long messages
                if len(response_text) > 2000:
                    chunks = [response_text[i:i+1990] for i in range(0, len(response_text), 1990)]
                    for chunk in chunks:
                        await message.reply(chunk, mention_author=False)
                else:
                    await message.reply(response_text, mention_author=False)

                # Add reactions based on action
                action = result.get("action")
                if action == "escalate":
                    await message.add_reaction("📣")  # Escalated
                elif action == "submit_for_review":
                    await message.add_reaction("📥")  # Submitted

            elif not result.get("success") and result.get("response"):
                # Error response
                await message.reply(result.get("response"), mention_author=False)

        except Exception as e:
            logger.error(f"Error in staff AI message handler: {e}", exc_info=True)
            try:
                await message.add_reaction("⚠️")
            except:
                pass

    async def _handle_attendance_message(self, message: discord.Message, channel_name: str):
        """Handle attendance commands in attendance channels."""

        # Parse attendance command (case-insensitive, strip whitespace)
        cmd = message.content.strip().lower()

        # Only handle recognized attendance commands
        if cmd not in ["in", "out", "break"]:
            return

        logger.info(f"Attendance command: {cmd} from {message.author.display_name} in {channel_name}")

        # Call the attendance callback if registered
        if self.on_attendance_callback:
            try:
                result = await self.on_attendance_callback(
                    user_id=str(message.author.id),
                    user_name=message.author.display_name,
                    event_type=cmd,
                    channel_id=str(message.channel.id),
                    channel_name=channel_name,
                )

                # React based on result
                if result.get("success"):
                    # Add primary reaction
                    emoji = result.get("emoji", "✅")
                    await message.add_reaction(emoji)

                    # Add late indicator if applicable
                    if result.get("is_late"):
                        await message.add_reaction(ATTENDANCE_REACTIONS["late"])

                    logger.info(f"Attendance recorded: {result.get('message', 'Success')}")
                else:
                    # Error - add warning reaction
                    await message.add_reaction(ATTENDANCE_REACTIONS["error"])
                    logger.warning(f"Attendance failed: {result.get('message', 'Unknown error')}")

            except Exception as e:
                logger.error(f"Error processing attendance command: {e}")
                try:
                    await message.add_reaction(ATTENDANCE_REACTIONS["error"])
                except:
                    pass
        else:
            logger.warning("Attendance callback not registered, ignoring attendance command")

    async def _handle_potential_submission(self, message: discord.Message):
        """
        Check if message contains task completion/submission.

        Detects patterns like:
        - "I have finished TASK-XXX"
        - "Completed TASK-XXX, TASK-YYY"
        - "Done with TASK-XXX"
        - "TASK-XXX is complete, here is proof"
        """
        import re

        content = message.content.lower()

        # Keywords indicating task completion
        completion_keywords = [
            "finished", "completed", "done", "complete",
            "submission", "submitting", "submit",
            "proof of work", "proof", "here is", "attached"
        ]

        # Check if message contains completion indicators
        has_completion_keyword = any(kw in content for kw in completion_keywords)

        # Extract task IDs (TASK-YYYYMMDD-XXX pattern)
        task_pattern = r'TASK-\d{8}-[A-Z0-9]+'
        task_ids = re.findall(task_pattern, message.content, re.IGNORECASE)

        # If no task IDs or no completion keywords, skip
        if not task_ids or not has_completion_keyword:
            return

        logger.info(f"Detected task submission from {message.author.display_name}: {task_ids}")

        # Extract attachment URLs (images as proof)
        attachment_urls = []
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                attachment_urls.append(attachment.url)

        # Call the submission callback if registered
        if self.on_task_submission_callback:
            try:
                result = await self.on_task_submission_callback(
                    user_id=str(message.author.id),
                    user_name=message.author.display_name,
                    task_ids=task_ids,
                    message_content=message.content,
                    attachment_urls=attachment_urls,
                    channel_id=str(message.channel.id),
                    channel_name=message.channel.name if hasattr(message.channel, 'name') else "unknown",
                    message_url=message.jump_url,
                )

                # React based on result
                if result.get("success"):
                    await message.add_reaction("📨")  # Submission received
                    logger.info(f"Task submission processed: {result.get('message', 'Success')}")

                    # Optionally reply to confirm
                    if result.get("reply_message"):
                        await message.reply(result.get("reply_message"), mention_author=False)
                else:
                    await message.add_reaction("⚠️")  # Issue
                    logger.warning(f"Task submission issue: {result.get('message', 'Unknown error')}")

            except Exception as e:
                logger.error(f"Error processing task submission: {e}")
                try:
                    await message.add_reaction("⚠️")
                except:
                    pass
        else:
            logger.warning("Task submission callback not registered")

    async def _get_task_for_message(self, message_id: int, channel_id: int) -> Optional[str]:
        """Look up task ID for a Discord message."""
        # First check local cache
        if message_id in self._message_task_map:
            return self._message_task_map[message_id]

        # Try to find in database
        try:
            from ..database.connection import get_database
            from sqlalchemy import select
            from ..database.models import TaskDB

            db = get_database()
            async with db.session() as session:
                result = await session.execute(
                    select(TaskDB.task_id).where(TaskDB.discord_message_id == str(message_id))
                )
                row = result.first()
                if row:
                    task_id = row[0]
                    # Cache it
                    self._message_task_map[message_id] = task_id
                    return task_id
        except Exception as e:
            logger.error(f"Error looking up task for message {message_id}: {e}")

        # Try to extract from message embed
        try:
            channel = self.get_channel(channel_id)
            if channel:
                message = await channel.fetch_message(message_id)
                if message.embeds:
                    embed = message.embeds[0]
                    # Look for task ID in footer or fields
                    if embed.footer and embed.footer.text:
                        # Footer format: "TASK-YYYYMMDD-XXX | React to update..."
                        footer_text = embed.footer.text
                        if "TASK-" in footer_text:
                            import re
                            match = re.search(r'(TASK-[\w\-]+)', footer_text)
                            if match:
                                task_id = match.group(1)
                                self._message_task_map[message_id] = task_id
                                return task_id

                    # Check fields
                    for field in embed.fields:
                        if field.name.lower() in ["task id", "id"]:
                            task_id = field.value.strip()
                            self._message_task_map[message_id] = task_id
                            return task_id
        except Exception as e:
            logger.debug(f"Could not extract task ID from message: {e}")

        return None

    async def _handle_priority_change(self, payload: discord.RawReactionActionEvent, priority: str):
        """Handle priority change via reaction."""
        task_id = await self._get_task_for_message(payload.message_id, payload.channel_id)
        if not task_id:
            return

        user = self.get_user(payload.user_id)
        user_name = user.display_name if user else f"User {payload.user_id}"

        if self.on_priority_update_callback:
            try:
                await self.on_priority_update_callback(
                    task_id=task_id,
                    new_priority=priority,
                    changed_by=user_name,
                    source="discord_reaction"
                )
            except Exception as e:
                logger.error(f"Error updating task priority: {e}")

    def register_message_task(self, message_id: int, task_id: str):
        """Register a message -> task mapping."""
        self._message_task_map[message_id] = task_id
        logger.debug(f"Registered message {message_id} -> task {task_id}")

    async def add_status_reactions(self, message: discord.Message):
        """Add reaction options to a task message."""
        reactions = ["✅", "🚧", "🚫", "⏸️", "🔄"]
        for emoji in reactions:
            try:
                await message.add_reaction(emoji)
            except Exception as e:
                logger.warning(f"Could not add reaction {emoji}: {e}")

    async def create_task_thread(
        self,
        channel_id: int,
        message_id: int,
        task_id: str,
        task_title: str,
        assignee: str = None,
        assignee_discord_id: str = None
    ) -> Optional[discord.Thread]:
        """
        Create a thread on a task message for discussion.

        Args:
            channel_id: Discord channel ID where message was posted
            message_id: Discord message ID to create thread on
            task_id: Task ID for thread name
            task_title: Task title for thread name
            assignee: Optional assignee name to display in thread
            assignee_discord_id: Optional Discord user ID for @mention (numeric ID like '123456789')

        Returns:
            Created thread or None if failed
        """
        try:
            channel = self.get_channel(channel_id)
            if not channel:
                channel = await self.fetch_channel(channel_id)

            if not channel:
                logger.error(f"Could not find channel {channel_id}")
                return None

            # Fetch the message
            message = await channel.fetch_message(message_id)
            if not message:
                logger.error(f"Could not find message {message_id}")
                return None

            # Create thread name: "TASK-XXX | Short title"
            # Discord thread names max 100 chars
            short_title = task_title[:60] if len(task_title) > 60 else task_title
            thread_name = f"{task_id} | {short_title}"
            if len(thread_name) > 100:
                thread_name = thread_name[:97] + "..."

            # Create thread on the message
            thread = await message.create_thread(
                name=thread_name,
                auto_archive_duration=10080  # 7 days
            )

            logger.info(f"Created Discord thread '{thread_name}' for task {task_id}")

            # Post initial message in thread
            intro_lines = [
                f"**Task Discussion Thread**",
                f"Use this thread to discuss {task_id}.",
                "",
                "**Quick Actions:**",
                "- Share updates and progress here",
                "- Post screenshots or links as proof",
                "- Ask questions about the task",
                "",
                "When done, react with ✅ on the main message above."
            ]

            if assignee:
                # Try to @mention if we have a numeric Discord user ID
                if assignee_discord_id and assignee_discord_id.isdigit():
                    # Proper Discord mention format: <@USER_ID>
                    intro_lines.insert(2, f"Assigned to: <@{assignee_discord_id}> ({assignee})")
                else:
                    # Fallback to just showing the name
                    intro_lines.insert(2, f"Assigned to: **{assignee}**")

            await thread.send("\n".join(intro_lines))

            # Add status reactions to the original message
            await self.add_status_reactions(message)

            return thread

        except discord.Forbidden as e:
            logger.error(f"Bot lacks permission to create threads in channel {channel_id}. Error: {e}. "
                        f"Bot permissions: Make sure 'Create Public Threads' is enabled for the bot role.")
            # Try to log what permissions the bot actually has
            try:
                if channel:
                    perms = channel.permissions_for(channel.guild.me)
                    logger.error(f"Bot permissions in channel: create_public_threads={perms.create_public_threads}, "
                                f"send_messages={perms.send_messages}, "
                                f"send_messages_in_threads={perms.send_messages_in_threads}, "
                                f"read_message_history={perms.read_message_history}")
            except Exception as perm_err:
                logger.error(f"Could not check permissions: {perm_err}")
            return None
        except Exception as e:
            logger.error(f"Error creating thread for task {task_id}: {type(e).__name__}: {e}")
            return None

    async def create_forum_post(
        self,
        forum_channel_id: int,
        task_id: str,
        task_title: str,
        task_embed: dict,
        assignee: str = None,
        assignee_discord_id: str = None,
        priority: str = None,
        status: str = None
    ) -> Optional[discord.Thread]:
        """
        Create a forum post for a task in a Discord Forum channel.

        Args:
            forum_channel_id: Discord Forum channel ID
            task_id: Task ID for post title
            task_title: Task title
            task_embed: Discord embed dict for the task
            assignee: Assignee name
            assignee_discord_id: Numeric Discord user ID for @mention
            priority: Task priority for tag (urgent, high, medium, low)
            status: Task status for tag

        Returns:
            Created thread (forum post) or None if failed
        """
        try:
            channel = self.get_channel(forum_channel_id)
            if not channel:
                channel = await self.fetch_channel(forum_channel_id)

            if not channel:
                logger.error(f"Could not find forum channel {forum_channel_id}")
                return None

            # Verify it's a forum channel
            if not isinstance(channel, discord.ForumChannel):
                logger.error(f"Channel {forum_channel_id} is not a Forum channel (type: {type(channel).__name__})")
                return None

            # Create post title: "TASK-XXX | Short title"
            short_title = task_title[:80] if len(task_title) > 80 else task_title
            post_name = f"{task_id} | {short_title}"
            if len(post_name) > 100:
                post_name = post_name[:97] + "..."

            # Build the initial message content
            content_lines = []

            # Add assignee mention at the top
            if assignee:
                if assignee_discord_id and assignee_discord_id.isdigit():
                    content_lines.append(f"**Assigned to:** <@{assignee_discord_id}>")
                else:
                    content_lines.append(f"**Assigned to:** {assignee}")

            content_lines.extend([
                "",
                "**Quick Actions:**",
                "• Share updates and progress in this thread",
                "• Post screenshots or links as proof of completion",
                "• Ask questions about the task",
                "",
                "React to update status: ✅=Done 🚧=Working 🚫=Blocked ⏸️=Paused 🔄=Review"
            ])

            # Find applicable tags from the forum channel
            applied_tags = []
            if channel.available_tags:
                # Look for priority tag
                if priority:
                    priority_lower = priority.lower()
                    for tag in channel.available_tags:
                        tag_name_lower = tag.name.lower()
                        if priority_lower in tag_name_lower or tag_name_lower in priority_lower:
                            applied_tags.append(tag)
                            break

                # Look for status tag
                if status:
                    status_lower = status.lower().replace("_", " ")
                    for tag in channel.available_tags:
                        tag_name_lower = tag.name.lower()
                        if status_lower in tag_name_lower or tag_name_lower in status_lower:
                            applied_tags.append(tag)
                            break

            # Create the forum post
            thread_with_message = await channel.create_thread(
                name=post_name,
                content="\n".join(content_lines),
                embed=discord.Embed.from_dict(task_embed),
                applied_tags=applied_tags[:5] if applied_tags else None,  # Max 5 tags
                auto_archive_duration=10080  # 7 days
            )

            # Handle the return value - discord.py 2.0+ returns ThreadWithMessage object
            # with .thread and .message attributes
            thread = None
            message = None

            if thread_with_message is None:
                logger.error(f"Forum thread creation returned None for task {task_id}")
                return None

            # Check if it's a ThreadWithMessage object (has .thread and .message attributes)
            if hasattr(thread_with_message, 'thread') and hasattr(thread_with_message, 'message'):
                thread = thread_with_message.thread
                message = thread_with_message.message
            # Fallback for older discord.py versions that might return a tuple
            elif isinstance(thread_with_message, tuple):
                thread = thread_with_message[0]
                message = thread_with_message[1] if len(thread_with_message) > 1 else None
            else:
                # Assume it's just the thread
                thread = thread_with_message

            if thread is None:
                logger.error(f"Failed to get thread from forum post response for task {task_id}")
                return None

            logger.info(f"Created forum post '{post_name}' for task {task_id} in forum {forum_channel_id}")

            # Add status reactions to the first message
            if message:
                await self.add_status_reactions(message)
                self.register_message_task(message.id, task_id)
            else:
                # Try to get the first message
                try:
                    async for msg in thread.history(limit=1, oldest_first=True):
                        await self.add_status_reactions(msg)
                        # Register for reaction tracking
                        self.register_message_task(msg.id, task_id)
                        break
                except Exception as e:
                    logger.warning(f"Could not add reactions to forum post: {e}")

            return thread

        except discord.Forbidden as e:
            logger.error(f"Bot lacks permission to create forum posts. Error: {e}")
            try:
                if channel:
                    perms = channel.permissions_for(channel.guild.me)
                    logger.error(f"Bot permissions: send_messages={perms.send_messages}, "
                                f"create_public_threads={perms.create_public_threads}")
            except Exception as perm_err:
                logger.error(f"Could not check permissions: {perm_err}")
            return None
        except Exception as e:
            logger.error(f"Error creating forum post for task {task_id}: {type(e).__name__}: {e}")
            return None


# Singleton instance
_bot: Optional[TaskingBot] = None


def get_discord_bot() -> Optional[TaskingBot]:
    """Get the Discord bot instance."""
    global _bot
    if _bot is None and settings.discord_bot_token:
        _bot = TaskingBot()
    return _bot


async def start_discord_bot():
    """Start the Discord bot in the background."""
    bot = get_discord_bot()
    if not bot:
        logger.warning("Discord bot token not configured, skipping bot startup")
        return

    try:
        logger.info("Starting Discord bot...")
        await bot.start(settings.discord_bot_token)
    except Exception as e:
        logger.error(f"Discord bot error: {e}")


async def stop_discord_bot():
    """Stop the Discord bot gracefully."""
    global _bot
    if _bot and not _bot.is_closed():
        await _bot.close()
        logger.info("Discord bot stopped")


def setup_status_callback(callback):
    """Set the callback function for status updates."""
    bot = get_discord_bot()
    if bot:
        bot.on_status_update_callback = callback
        logger.info("Discord bot status callback registered")


def setup_priority_callback(callback):
    """Set the callback function for priority updates."""
    bot = get_discord_bot()
    if bot:
        bot.on_priority_update_callback = callback
        logger.info("Discord bot priority callback registered")


def setup_attendance_callback(callback):
    """Set the callback function for attendance events."""
    bot = get_discord_bot()
    if bot:
        bot.on_attendance_callback = callback
        logger.info("Discord bot attendance callback registered")


def setup_task_submission_callback(callback):
    """Set the callback function for task submissions from staff."""
    bot = get_discord_bot()
    if bot:
        bot.on_task_submission_callback = callback
        logger.info("Discord bot task submission callback registered")


def setup_staff_message_callback(callback):
    """Set the callback function for staff AI assistant messages."""
    bot = get_discord_bot()
    if bot:
        bot.on_staff_message_callback = callback
        logger.info("Discord bot staff message callback registered")


async def create_task_thread(
    channel_id: int,
    message_id: int,
    task_id: str,
    task_title: str,
    assignee: str = None,
    assignee_discord_id: str = None
) -> bool:
    """
    Create a thread for a task message.

    This is a helper function that can be called from discord.py integration
    after posting a task via webhook.

    Args:
        channel_id: Discord channel ID
        message_id: Discord message ID to create thread on
        task_id: Task ID
        task_title: Task title
        assignee: Assignee name
        assignee_discord_id: Numeric Discord user ID for @mention

    Returns:
        True if thread created successfully, False otherwise
    """
    bot = get_discord_bot()
    if not bot or not bot.is_ready():
        logger.warning("Discord bot not ready, cannot create thread")
        return False

    thread = await bot.create_task_thread(
        channel_id=channel_id,
        message_id=message_id,
        task_id=task_id,
        task_title=task_title,
        assignee=assignee,
        assignee_discord_id=assignee_discord_id
    )

    return thread is not None


async def create_forum_post(
    forum_channel_id: int,
    task_id: str,
    task_title: str,
    task_embed: dict,
    assignee: str = None,
    assignee_discord_id: str = None,
    priority: str = None,
    status: str = None
) -> Optional[int]:
    """
    Create a forum post for a task.

    Args:
        forum_channel_id: Discord Forum channel ID
        task_id: Task ID
        task_title: Task title
        task_embed: Discord embed dict
        assignee: Assignee name
        assignee_discord_id: Numeric Discord user ID for @mention
        priority: Task priority for tags
        status: Task status for tags

    Returns:
        Thread ID if created successfully, None otherwise
    """
    bot = get_discord_bot()
    if not bot or not bot.is_ready():
        logger.warning("Discord bot not ready, cannot create forum post")
        return None

    thread = await bot.create_forum_post(
        forum_channel_id=forum_channel_id,
        task_id=task_id,
        task_title=task_title,
        task_embed=task_embed,
        assignee=assignee,
        assignee_discord_id=assignee_discord_id,
        priority=priority,
        status=status
    )

    return thread.id if thread else None


async def send_to_channel(
    channel_id: int,
    content: str = None,
    embed: dict = None,
    embeds: list = None
) -> Optional[int]:
    """
    Send a message to a text channel using the bot.

    Args:
        channel_id: Discord text channel ID
        content: Text content (optional)
        embed: Single embed dict (optional)
        embeds: List of embed dicts (optional)

    Returns:
        Message ID if sent successfully, None otherwise
    """
    bot = get_discord_bot()
    if not bot or not bot.is_ready():
        logger.warning("Discord bot not ready, cannot send to channel")
        return None

    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            channel = await bot.fetch_channel(channel_id)

        if not channel:
            logger.error(f"Could not find channel {channel_id}")
            return None

        # Build embed objects
        discord_embeds = []
        if embed:
            discord_embeds.append(discord.Embed.from_dict(embed))
        if embeds:
            for e in embeds:
                discord_embeds.append(discord.Embed.from_dict(e))

        # Send message
        message = await channel.send(
            content=content,
            embeds=discord_embeds if discord_embeds else None
        )

        logger.info(f"Sent message {message.id} to channel {channel_id}")
        return message.id

    except discord.Forbidden as e:
        logger.error(f"Bot lacks permission to send to channel {channel_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error sending to channel {channel_id}: {type(e).__name__}: {e}")
        return None


async def send_standup_to_channel(channel_id: int, summary: str) -> bool:
    """
    Send daily standup summary to a specific channel.

    Args:
        channel_id: Discord channel ID
        summary: Standup summary text

    Returns:
        True if sent successfully
    """
    from datetime import datetime

    embed = {
        "title": "☀️ Daily Standup",
        "description": summary,
        "color": 0x3498DB,
        "timestamp": datetime.now().isoformat(),
        "footer": {"text": "Boss Workflow | React to update status"}
    }

    message_id = await send_to_channel(channel_id, embed=embed)
    return message_id is not None


async def send_alert_to_channel(
    channel_id: int,
    title: str,
    message: str,
    alert_type: str = "info"
) -> bool:
    """
    Send an alert to a specific channel.

    Args:
        channel_id: Discord channel ID
        title: Alert title
        message: Alert message
        alert_type: "warning", "error", "info", "success"

    Returns:
        True if sent successfully
    """
    from datetime import datetime

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

    message_id = await send_to_channel(channel_id, embed=embed)
    return message_id is not None
