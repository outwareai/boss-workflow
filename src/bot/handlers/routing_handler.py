"""
RoutingHandler - Routes messages to appropriate specialized handlers.

Q1 2026: Task #4.4 - Extracted from UnifiedHandler.
Central router that delegates to ValidationHandler, ApprovalHandler, etc.
"""
from typing import Optional, Dict, Any, List
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..base_handler import BaseHandler
from ...ai.intent import get_intent_detector, UserIntent

logger = logging.getLogger(__name__)


class RoutingHandler(BaseHandler):
    """
    Routes incoming messages to specialized handlers.

    Responsibilities:
    - Route messages to appropriate specialized handlers
    - Detect user intent (AI-powered fallback)
    - Track active multi-turn conversations
    - Command detection and parsing
    """

    def __init__(self, handlers: Optional[List[BaseHandler]] = None):
        """
        Initialize routing handler.

        Args:
            handlers: List of specialized handlers to route to
        """
        super().__init__()
        self.handlers = handlers or []
        self.intent_detector = get_intent_detector()
        self.logger = logging.getLogger("RoutingHandler")

    def register_handler(self, handler: BaseHandler):
        """Register a specialized handler."""
        self.handlers.append(handler)
        self.logger.info(f"Registered handler: {handler.__class__.__name__}")

    async def can_handle(self, message: str, user_id: str, **kwargs) -> bool:
        """
        Router always tries to handle messages.

        Returns True to accept all messages, then delegates to specialized handlers.
        """
        return True

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Route message to appropriate specialized handler.

        Process:
        1. Check for active session (multi-turn conversation)
        2. Try each specialized handler's can_handle()
        3. Delegate to first handler that can handle
        4. Fall back to AI intent detection if no handler matches
        """
        message = update.message.text.strip() if update.message.text else ""
        user_info = await self.get_user_info(update)
        user_id = user_info["user_id"]

        try:
            # Step 1: Check for active conversation session
            active_handler = await self._get_active_handler(user_id)
            if active_handler:
                self.logger.info(f"Routing to active handler: {active_handler.__class__.__name__}")
                await active_handler.handle(update, context)
                return

            # Step 2: Try specialized handlers
            for handler in self.handlers:
                if await handler.can_handle(message, user_id, update=update, context=context):
                    self.logger.info(f"Routing to: {handler.__class__.__name__}")
                    await handler.handle(update, context)
                    return

            # Step 3: No handler matched - use AI intent detection
            await self._handle_with_ai(update, context, message, user_id)

        except Exception as e:
            self.logger.error(f"Routing error: {e}", exc_info=True)
            await self.send_error(update, f"Failed to process message: {str(e)}")

    # ==================== INTENT DETECTION ====================

    async def _handle_with_ai(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        message: str,
        user_id: str
    ) -> None:
        """
        Use AI to detect intent and route accordingly.

        This is the fallback when no specialized handler matches.
        Uses DeepSeek AI to determine user intent.
        """
        try:
            # Get user permissions for context
            permissions = await self.get_user_permissions(user_id)
            is_boss = permissions.get("is_boss", False)

            # Build context for intent detection
            intent_context = {
                "is_boss": is_boss,
                "awaiting_validation": False,
                "collecting_proof": False,
                "awaiting_notes": False,
                "awaiting_confirm": False,
            }

            # Detect intent using AI
            intent, data = await self.intent_detector.detect_intent(message, intent_context)

            self.logger.info(f"AI detected intent: {intent.value}")

            # Route based on detected intent
            if intent == UserIntent.TASK_DONE:
                await self._route_task_creation(update, context, data)
            elif intent == UserIntent.CHECK_STATUS:
                await self._route_status_query(update, context, data)
            elif intent == UserIntent.MODIFY_TASK:
                await self._route_task_modification(update, context, data)
            elif intent in [UserIntent.APPROVE_TASK, UserIntent.REJECT_TASK]:
                await self._route_approval(update, context, data)
            elif intent == UserIntent.HELP:
                await self._route_help(update, context)
            elif intent == UserIntent.GREETING:
                await self.send_message(update, "Hello! How can I help you today?")
            elif intent == UserIntent.CANCEL:
                await self.clear_active_handler(user_id)
                await self.send_message(update, "Cancelled. What would you like to do?")
            else:
                # Route to UnifiedHandler for all other intents
                # This includes: CLEAR_TASKS, CREATE_TASK, SEARCH_TASKS, etc.
                await self._route_to_unified_handler(update, context, intent, data)

        except Exception as e:
            self.logger.error(f"AI intent detection failed: {e}", exc_info=True)
            await self.send_error(update, "Could not understand your request. Please try again.")

    # ==================== ROUTING METHODS ====================

    async def _route_task_creation(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        data: Dict[str, Any]
    ) -> None:
        """Route to task creation handler."""
        # Find task creation handler
        for handler in self.handlers:
            if handler.__class__.__name__ == "TaskCreationHandler":
                await handler.handle(update, context)
                return

        # Fallback: inline task creation
        await self.send_message(update, "Creating task... (TaskCreationHandler not registered)")

    async def _route_status_query(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        data: Dict[str, Any]
    ) -> None:
        """Route to query handler."""
        for handler in self.handlers:
            if handler.__class__.__name__ == "QueryHandler":
                await handler.handle(update, context)
                return

        await self.send_message(update, "Checking status... (QueryHandler not registered)")

    async def _route_task_modification(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        data: Dict[str, Any]
    ) -> None:
        """Route to modification handler."""
        for handler in self.handlers:
            if handler.__class__.__name__ == "ModificationHandler":
                await handler.handle(update, context)
                return

        await self.send_message(update, "Modifying task... (ModificationHandler not registered)")

    async def _route_approval(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        data: Dict[str, Any]
    ) -> None:
        """Route to approval handler."""
        for handler in self.handlers:
            if handler.__class__.__name__ == "ValidationHandler":
                await handler.handle(update, context)
                return

        await self.send_message(update, "Processing approval... (ValidationHandler not registered)")

    async def _route_to_unified_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        intent: UserIntent,
        data: Dict[str, Any]
    ) -> None:
        """
        Route to UnifiedHandler for intents not explicitly handled here.

        This catches all intents like CLEAR_TASKS, SEARCH_TASKS, CREATE_TASK, etc.
        that the specialized handlers don't claim.
        """
        for handler in self.handlers:
            if handler.__class__.__name__ == "UnifiedHandlerWrapper":
                # Store intent and data in context for UnifiedHandler to use
                context.user_data["detected_intent"] = intent
                context.user_data["detected_data"] = data
                await handler.handle(update, context)
                return

        # Fallback if UnifiedHandlerWrapper not registered
        self.logger.warning(f"UnifiedHandlerWrapper not registered, cannot route intent: {intent.value}")
        await self.send_message(
            update,
            "I'm not sure what you want to do. Try:\n"
            "• `/task` - Create a new task\n"
            "• `/status` - Check task status\n"
            "• `/help` - See all commands"
        )

    async def _route_help(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Route to help handler."""
        # Provide basic help message
        help_text = """**Available Commands:**

• `/task [description]` - Create a new task
• `/status` - Check task status
• `/approve [task_id]` - Approve a task
• `/reject [task_id] [reason]` - Reject a task
• `/help` - Show this help message
• `/cancel` - Cancel current action

You can also just talk naturally - I'll understand!"""

        await self.send_message(update, help_text)

    # ==================== SESSION TRACKING ====================

    async def _get_active_handler(self, user_id: str) -> Optional[BaseHandler]:
        """
        Get handler for active multi-turn conversation.

        Checks session storage to see if user is in middle of conversation
        with a specific handler (e.g., task creation flow).
        """
        # Check for active session - use the generic session mechanism
        # We'll add this to session manager if needed
        session = await self.get_session("active_handler", user_id)
        if not session:
            return None

        # Find handler by name
        handler_name = session.get("handler_name")
        for handler in self.handlers:
            if handler.__class__.__name__ == handler_name:
                return handler

        return None

    async def set_active_handler(self, user_id: str, handler: BaseHandler, ttl: int = 3600):
        """
        Set active handler for multi-turn conversation.

        Args:
            user_id: User ID
            handler: Handler to set as active
            ttl: Session timeout (default 1 hour)
        """
        await self.set_session(
            "active_handler",
            user_id,
            {"handler_name": handler.__class__.__name__},
            ttl=ttl
        )

    async def clear_active_handler(self, user_id: str):
        """Clear active handler session."""
        await self.clear_session("active_handler", user_id)

    # ==================== COMMAND DETECTION ====================

    def is_command(self, message: str) -> bool:
        """Check if message is a slash command."""
        return message.strip().startswith('/')

    def extract_command(self, message: str) -> tuple:
        """
        Extract command and arguments.

        Returns:
            (command, args) tuple

        Example:
            "/approve TASK-001" -> ("approve", "TASK-001")
        """
        parts = message.strip().split(maxsplit=1)
        command = parts[0][1:] if parts[0].startswith('/') else parts[0]
        args = parts[1] if len(parts) > 1 else ""
        return command, args
