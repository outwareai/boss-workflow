"""
Telegram Client Adapter - Provides send_message API for planning_handler.

Adapts TelegramBotSimple to the interface expected by PlanningHandler.
"""
import logging
from typing import Optional
from telegram import Bot

logger = logging.getLogger(__name__)


class TelegramClientAdapter:
    """
    Adapter that provides send_message(chat_id, text) interface.

    Wraps TelegramBotSimple to work with PlanningHandler's expectations.
    """

    def __init__(self, telegram_bot_simple):
        """
        Initialize adapter.

        Args:
            telegram_bot_simple: TelegramBotSimple instance
        """
        self.bot_simple = telegram_bot_simple
        self.token = telegram_bot_simple.token
        self._bot: Optional[Bot] = None

    async def _get_bot(self) -> Bot:
        """Get or create Bot instance."""
        if not self._bot:
            self._bot = Bot(self.token)
        return self._bot

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "Markdown",
        **kwargs
    ):
        """
        Send a message to a Telegram chat.

        Args:
            chat_id: Telegram chat ID
            text: Message text
            parse_mode: Parse mode (Markdown, HTML, or None)
            **kwargs: Additional arguments for send_message
        """
        try:
            bot = await self._get_bot()
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                **kwargs
            )
            logger.debug(f"Sent message to chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send message to chat {chat_id}: {e}")
            raise


def get_telegram_client_adapter(telegram_bot_simple):
    """
    Create a TelegramClientAdapter.

    Args:
        telegram_bot_simple: TelegramBotSimple instance

    Returns:
        TelegramClientAdapter instance
    """
    return TelegramClientAdapter(telegram_bot_simple)
