"""
PlanningHandler - Handles conversational project planning.

Q1 2026: v3.0 Natural Conversational Planning System
Integrates planning_handler.py with the modular handler architecture.
"""
from typing import Optional, Dict, Any
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..base_handler import BaseHandler
from src.bot.planning_handler import get_planning_handler
from src.ai.deepseek import get_deepseek_client
from src.integrations.sheets import get_sheets_integration
from src.database.connection import get_session
from src.database.repositories import get_planning_repository
from config.settings import settings

logger = logging.getLogger(__name__)


class PlanningHandler(BaseHandler):
    """
    Handles project planning requests.

    Responsibilities:
    - Detect planning intent from natural language
    - Route to conversational planning flow
    - Handle planning session management (/approve, /refine, /cancel)
    """

    def __init__(self):
        """Initialize planning handler."""
        super().__init__()
        self.logger = logging.getLogger("PlanningHandler")
        self.ai = get_deepseek_client()
        self.sheets = get_sheets_integration()

    async def can_handle(self, message: str, user_id: str, **kwargs) -> bool:
        """
        Check if this is a planning request.

        Handles:
        - Natural language planning ("plan", "organize", "break down")
        - Planning commands (/plan, /approve, /refine)
        - Active planning sessions

        Priority: HIGH - should be checked before other handlers
        """
        message_lower = message.lower().strip()

        # Planning keywords (natural language)
        planning_keywords = [
            "plan", "planning", "let's plan", "help me plan",
            "break down", "organize", "project for",
            "i want to build", "let's build", "create a project"
        ]

        # Check for planning keywords
        if any(keyword in message_lower for keyword in planning_keywords):
            self.logger.info(f"Planning keyword detected: {message_lower[:100]}")
            return True

        # Check for slash commands
        if message_lower.startswith(("/plan", "/approve", "/refine")):
            return True

        # Check for active planning session
        try:
            async with get_session() as db:
                planning_repo = get_planning_repository(db)
                active_session = await planning_repo.get_active_for_user(user_id)
                if active_session:
                    self.logger.info(f"Active planning session found for user {user_id}")
                    return True
        except Exception as e:
            self.logger.error(f"Error checking active planning session: {e}")

        return False

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process planning request."""
        message = update.message.text.strip() if update.message.text else ""
        user_info = await self.get_user_info(update)
        user_id = user_info["user_id"]
        chat_id = str(update.effective_chat.id)

        try:
            # Initialize planning handler
            from src.bot.telegram_simple import telegram_client
            planning_handler = get_planning_handler(
                telegram_client=telegram_client,
                ai_client=self.ai,
                sheets_client=self.sheets
            )

            # Handle slash commands
            if message.startswith("/plan"):
                await self._handle_plan_command(message, user_id, chat_id, planning_handler)
            elif message.startswith("/approve"):
                await self._handle_approve_command(user_id, chat_id, planning_handler)
            elif message.startswith("/refine"):
                await self._handle_refine_command(message, user_id, chat_id, planning_handler)
            else:
                # Natural language planning or answering questions
                await self._handle_natural_planning(message, user_id, chat_id, planning_handler)

        except Exception as e:
            self.logger.error(f"Planning error: {e}", exc_info=True)
            await self.send_error(update, f"Planning failed: {str(e)}")

    async def _handle_plan_command(
        self,
        message: str,
        user_id: str,
        chat_id: str,
        planning_handler
    ):
        """Handle /plan command."""
        # Extract planning request
        parts = message.split(maxsplit=1)
        planning_request = parts[1] if len(parts) > 1 else "Start new project planning"

        result = await planning_handler.start_planning_session(
            user_id=user_id,
            raw_input=planning_request,
            conversation_id=None,
            chat_id=chat_id
        )

        if result.get("success"):
            # Trigger information gathering
            await planning_handler.gather_information(
                session_id=result["session_id"],
                chat_id=chat_id
            )

    async def _handle_approve_command(
        self,
        user_id: str,
        chat_id: str,
        planning_handler
    ):
        """Handle /approve command."""
        async with get_session() as db:
            planning_repo = get_planning_repository(db)
            active_session = await planning_repo.get_active_for_user(user_id)

            if not active_session:
                await planning_handler.telegram.send_message(
                    chat_id,
                    "❌ No active planning session to approve.",
                    parse_mode="Markdown"
                )
                return

            await planning_handler.approve_plan(
                active_session.session_id,
                chat_id
            )

    async def _handle_refine_command(
        self,
        message: str,
        user_id: str,
        chat_id: str,
        planning_handler
    ):
        """Handle /refine command."""
        async with get_session() as db:
            planning_repo = get_planning_repository(db)
            active_session = await planning_repo.get_active_for_user(user_id)

            if not active_session:
                await planning_handler.telegram.send_message(
                    chat_id,
                    "❌ No active planning session to refine.",
                    parse_mode="Markdown"
                )
                return

            # Extract refinement request
            parts = message.split(maxsplit=1)
            refinement_request = parts[1] if len(parts) > 1 else "Refine the plan"

            await planning_handler.refine_plan(
                active_session.session_id,
                refinement_request,
                chat_id
            )

    async def _handle_natural_planning(
        self,
        message: str,
        user_id: str,
        chat_id: str,
        planning_handler
    ):
        """Handle natural language planning or answering questions."""
        async with get_session() as db:
            planning_repo = get_planning_repository(db)
            active_session = await planning_repo.get_active_for_user(user_id)

            if active_session:
                # User is responding to questions or continuing conversation
                await planning_handler.process_answer(
                    session_id=active_session.session_id,
                    answer=message,
                    chat_id=chat_id
                )
            else:
                # Start new planning session
                result = await planning_handler.start_planning_session(
                    user_id=user_id,
                    raw_input=message,
                    conversation_id=None,
                    chat_id=chat_id
                )

                if result.get("success"):
                    # Trigger information gathering
                    await planning_handler.gather_information(
                        session_id=result["session_id"],
                        chat_id=chat_id
                    )
