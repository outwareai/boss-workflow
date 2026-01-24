"""
CommandHandler - Handles slash commands.

Q1 2026: Task #4.6 Part 2 - Extracted from UnifiedHandler.
Central handler for all /commands.
"""
from typing import Optional, Dict, Callable
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..base_handler import BaseHandler

logger = logging.getLogger(__name__)


class CommandHandler(BaseHandler):
    """
    Handles slash command execution.

    Responsibilities:
    - Route /commands to appropriate handlers
    - Parse command arguments
    - Validate command permissions
    - Provide help text for commands
    """

    def __init__(self):
        """Initialize command handler."""
        super().__init__()
        self.logger = logging.getLogger("CommandHandler")
        self.commands: Dict[str, Callable] = {}
        self._register_commands()

    def _register_commands(self):
        """Register all available commands."""
        self.commands = {
            "start": self._cmd_start,
            "help": self._cmd_help,
            "task": self._cmd_create_task,
            "status": self._cmd_status,
            "approve": self._cmd_approve,
            "reject": self._cmd_reject,
            "cancel": self._cmd_cancel,
            "list": self._cmd_list,
            "search": self._cmd_search,
            "report": self._cmd_report,
        }

    async def can_handle(self, message: str, user_id: str, **kwargs) -> bool:
        """Check if message is a command."""
        return message.strip().startswith('/')

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Execute command."""
        message = update.message.text.strip()

        # Extract command and args
        parts = message.split(maxsplit=1)
        command = parts[0][1:].lower()  # Remove /
        args = parts[1] if len(parts) > 1 else ""

        # Get command handler
        handler = self.commands.get(command)

        if not handler:
            await self.send_error(update, f"Unknown command: /{command}\nTry /help")
            return

        try:
            await handler(update, context, args)
        except Exception as e:
            self.logger.error(f"Command error: /{command} - {e}")
            await self.send_error(update, f"Command failed: {str(e)}")

    # ==================== COMMAND IMPLEMENTATIONS ====================

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: str):
        """Handle /start command."""
        await self.send_message(
            update,
            "👋 Welcome to Boss Workflow!\n\n"
            "I help you manage tasks via Telegram.\n\n"
            "Quick start:\n"
            "• `/task` - Create a new task\n"
            "• `/status` - Check task status\n"
            "• `/help` - See all commands\n\n"
            "Or just chat naturally - I'll understand!"
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: str):
        """Handle /help command."""
        help_text = """
📚 **Available Commands**

**Task Management:**
• `/task` - Create a new task
• `/status [TASK-ID]` - Check task status
• `/list [status]` - List tasks
• `/search <keyword>` - Search tasks

**Approvals:**
• `/approve <TASK-ID>` - Approve a task
• `/reject <TASK-ID>` - Reject a task

**Reports:**
• `/report daily` - Daily standup report
• `/report weekly` - Weekly summary
• `/report monthly` - Monthly overview

**Other:**
• `/cancel` - Cancel current operation
• `/help` - Show this help

💡 **Tip:** You can also chat naturally - I'll understand what you mean!
"""
        await self.send_message(update, help_text)

    async def _cmd_create_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: str):
        """Handle /task command."""
        if not args:
            await self.send_message(
                update,
                "📝 **Create a Task**\n\n"
                "Usage: `/task <description>`\n\n"
                "Example:\n"
                "`/task Fix login bug for John - priority high`"
            )
            return

        # Delegate to task creation logic
        await self.send_message(update, f"Creating task: {args}")
        # TODO: Integrate with TaskCreationHandler

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: str):
        """Handle /status command."""
        if args:
            # Specific task status
            task_id = args.strip().upper()
            task = await self.task_repo.get_by_id(task_id)

            if task:
                await self.send_message(
                    update,
                    f"📊 {task_id}: {task.status}\n"
                    f"Assignee: {task.assignee or 'Unassigned'}"
                )
            else:
                await self.send_error(update, f"Task {task_id} not found")
        else:
            # Overall status
            # TODO: Delegate to QueryHandler
            await self.send_message(update, "Checking overall status...")

    async def _cmd_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: str):
        """Handle /approve command."""
        if not args:
            await self.send_error(update, "Usage: `/approve <TASK-ID>`")
            return

        task_id = args.strip().upper()
        # TODO: Delegate to ValidationHandler
        await self.send_message(update, f"Approving {task_id}...")

    async def _cmd_reject(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: str):
        """Handle /reject command."""
        if not args:
            await self.send_error(update, "Usage: `/reject <TASK-ID>`")
            return

        task_id = args.strip().upper()
        # TODO: Delegate to ValidationHandler
        await self.send_message(update, f"Rejecting {task_id}...")

    async def _cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: str):
        """Handle /cancel command."""
        user_info = await self.get_user_info(update)
        user_id = user_info["user_id"]

        # Clear all sessions
        await self.clear_session("pending_actions", user_id)
        await self.clear_session("active_handler", user_id)

        await self.send_message(update, "❌ Cancelled current operation")

    async def _cmd_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: str):
        """Handle /list command."""
        # TODO: Delegate to QueryHandler
        await self.send_message(update, f"Listing tasks...")

    async def _cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: str):
        """Handle /search command."""
        if not args:
            await self.send_error(update, "Usage: `/search <keyword>`")
            return

        # TODO: Implement search
        await self.send_message(update, f"Searching for: {args}")

    async def _cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: str):
        """Handle /report command."""
        # TODO: Delegate to QueryHandler
        await self.send_message(update, f"Generating {args or 'daily'} report...")
