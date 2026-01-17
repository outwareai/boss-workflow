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

    async def setup_hook(self):
        """Called when bot is ready to set up."""
        logger.info("Discord bot setup hook called")

        # Register slash commands
        @self.command(name="help")
        async def help_command(ctx):
            """Show help message with reaction guide."""
            embed = discord.Embed(
                title="📖 Boss Workflow Help",
                description="""**React to Update Task Status:**
✅ Complete task
🚧 Mark as in progress
🚫 Block task (can't proceed)
⏸️ Put on hold
🔄 Send for review
❌ Cancel task
⏳ Set to pending

**Priority:**
🔴 Mark as urgent

**How It Works:**
1. Tasks are posted here from Telegram
2. React with an emoji to update status
3. Changes sync to database & Google Sheets
4. Boss gets notified of status changes

**Via Telegram Bot:**
• `/status` - View current tasks
• `/search @name` - Find tasks by assignee
• `/complete ID` - Mark task done
• `/help` - Full command list

**Natural Language in Telegram:**
• "What's John working on?"
• "Show blocked tasks"
• "Mark TASK-001 as done"

_Reactions sync task status automatically!_""",
                color=0x3498DB
            )
            embed.set_footer(text="Boss Workflow Automation | React on task messages to update status")
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
