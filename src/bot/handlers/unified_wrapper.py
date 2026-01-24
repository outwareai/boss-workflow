"""
UnifiedHandlerWrapper - Adapter to bridge UnifiedHandler with the modular handler architecture.

Q1 2026: Routes detected intents from RoutingHandler to UnifiedHandler.
"""
from typing import Optional, Dict, Any
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..base_handler import BaseHandler
from ..handler import get_unified_handler

logger = logging.getLogger(__name__)


class UnifiedHandlerWrapper(BaseHandler):
    """
    Wraps UnifiedHandler to work with the modular handler architecture.

    This handler:
    - Accepts pre-detected intents from RoutingHandler
    - Calls UnifiedHandler.handle_message() with the appropriate parameters
    - Returns the response via Telegram
    """

    def __init__(self):
        """Initialize wrapper."""
        super().__init__()
        self.unified_handler = get_unified_handler()
        self.logger = logging.getLogger("UnifiedHandlerWrapper")

    async def can_handle(self, message: str, user_id: str, **kwargs) -> bool:
        """
        This handler is called directly by RoutingHandler for detected intents.
        It doesn't use can_handle() for routing.
        """
        return False  # Never auto-matched, only called explicitly

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle message by delegating to UnifiedHandler.

        Uses pre-detected intent from context.user_data if available.
        """
        message = update.message.text.strip() if update.message.text else ""
        user_info = await self.get_user_info(update)
        user_id = user_info["user_id"]
        user_name = user_info.get("first_name", "User")

        try:
            # Get pre-detected intent and data from context (set by RoutingHandler)
            detected_intent = context.user_data.get("detected_intent")
            detected_data = context.user_data.get("detected_data", {})

            if detected_intent:
                self.logger.info(f"Processing pre-detected intent: {detected_intent.value}")
                # Clear the stored intent/data
                context.user_data.pop("detected_intent", None)
                context.user_data.pop("detected_data", None)

            # Call UnifiedHandler.handle_message()
            response, action_data = await self.unified_handler.handle_message(
                user_id=user_id,
                message=message,
                user_name=user_name,
                is_boss=True,  # Telegram is boss-only
                source="telegram"
            )

            # Send response
            if response:
                await self.send_message(update, response)

            # Handle any action data (notifications, etc.)
            if action_data:
                await self._process_action_data(update, action_data)

        except Exception as e:
            self.logger.error(f"UnifiedHandler error: {e}", exc_info=True)
            await self.send_error(update, f"Error processing request: {str(e)}")

    async def _process_action_data(self, update: Update, action_data: Dict[str, Any]) -> None:
        """Process any action data returned by UnifiedHandler."""
        # Handle special actions like notifications, redirects, etc.
        if action_data.get("send_to_boss"):
            # Already in boss context, might need to forward
            pass

        if action_data.get("notify_user"):
            # Handle user notifications
            pass
