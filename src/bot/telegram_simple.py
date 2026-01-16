"""
Simplified Telegram bot - fully conversational, no commands.

Just handles messages naturally and routes to the unified handler.
"""

import logging
from typing import Optional
from telegram import Update, Bot
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import settings
from .handler import get_unified_handler

logger = logging.getLogger(__name__)


class TelegramBotSimple:
    """
    Simple conversational Telegram bot.

    No commands - just natural conversation.
    """

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.webhook_url = f"{settings.webhook_base_url}/webhook/telegram"
        self.handler = get_unified_handler()
        self.boss_chat_id = settings.telegram_boss_chat_id
        self.app: Optional[Application] = None

    async def initialize(self) -> None:
        """Initialize the bot."""
        if not self.token:
            logger.error("Telegram bot token not configured")
            return

        self.app = Application.builder().token(self.token).build()

        # Only message handlers - no commands!
        self.app.add_handler(MessageHandler(filters.PHOTO, self._handle_photo))
        self.app.add_handler(MessageHandler(filters.VOICE, self._handle_voice))
        self.app.add_handler(MessageHandler(filters.TEXT, self._handle_message))

        # Initialize the application (required for v20+)
        await self.app.initialize()

        logger.info("Telegram bot initialized (conversational mode)")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle all text messages."""
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        message = update.message.text
        user_name = update.effective_user.first_name or update.effective_user.username or "User"

        # Check if this is from the boss
        is_boss = str(chat_id) == str(self.boss_chat_id)

        try:
            response, action = await self.handler.handle_message(
                user_id=user_id,
                message=message,
                user_name=user_name,
                is_boss=is_boss
            )

            await update.message.reply_text(response, parse_mode='Markdown')

            # Handle any follow-up actions
            if action:
                await self._handle_action(action, context)

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await update.message.reply_text("Oops, something went wrong. Try again?")

    async def _handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle photo messages."""
        user_id = str(update.effective_user.id)
        user_name = update.effective_user.first_name or "User"
        photo = update.message.photo[-1]
        file_id = photo.file_id
        caption = update.message.caption

        is_boss = str(update.effective_chat.id) == str(self.boss_chat_id)

        try:
            response, action = await self.handler.handle_message(
                user_id=user_id,
                message=caption or "",
                photo_file_id=file_id,
                photo_caption=caption,
                user_name=user_name,
                is_boss=is_boss
            )

            await update.message.reply_text(response, parse_mode='Markdown')

            if action:
                await self._handle_action(action, context)

        except Exception as e:
            logger.error(f"Error handling photo: {e}")
            await update.message.reply_text("Got the photo! What's it for?")

    async def _handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice messages - transcribe and process."""
        user_id = str(update.effective_user.id)
        user_name = update.effective_user.first_name or "User"

        await update.message.reply_text("🎤 Got your voice message, processing...")

        try:
            # Download and transcribe
            voice = update.message.voice
            voice_file = await context.bot.get_file(voice.file_id)

            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
                await voice_file.download_to_drive(f.name)
                temp_path = f.name

            # Transcribe (would use Whisper or similar)
            from ..ai.deepseek import get_deepseek_client
            ai = get_deepseek_client()
            transcription = await ai.transcribe_voice(temp_path)
            os.unlink(temp_path)

            if transcription and not transcription.startswith("["):
                await update.message.reply_text(f"📝 \"{transcription}\"")

                # Process as text
                is_boss = str(update.effective_chat.id) == str(self.boss_chat_id)
                response, action = await self.handler.handle_message(
                    user_id=user_id,
                    message=transcription,
                    user_name=user_name,
                    is_boss=is_boss
                )

                await update.message.reply_text(response, parse_mode='Markdown')

                if action:
                    await self._handle_action(action, context)
            else:
                await update.message.reply_text("Couldn't catch that. Try typing instead?")

        except Exception as e:
            logger.error(f"Error with voice: {e}")
            await update.message.reply_text("Couldn't process voice. Try typing?")

    async def _handle_action(self, action: dict, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle follow-up actions from the handler."""

        # Send to boss
        if action.get("send_to_boss") and self.boss_chat_id:
            try:
                await context.bot.send_message(
                    chat_id=self.boss_chat_id,
                    text=action["boss_message"],
                    parse_mode='Markdown'
                )

                # Send proof photos
                for proof in action.get("proof_items", []):
                    if proof.get("type") == "screenshot" and proof.get("file_id"):
                        await context.bot.send_photo(
                            chat_id=self.boss_chat_id,
                            photo=proof["file_id"],
                            caption=proof.get("caption", "Proof")
                        )
                    elif proof.get("type") == "link":
                        await context.bot.send_message(
                            chat_id=self.boss_chat_id,
                            text=f"🔗 {proof.get('content', '')}"
                        )

                logger.info(f"Sent validation request to boss")

            except Exception as e:
                logger.error(f"Error sending to boss: {e}")

        # Notify a user
        if action.get("notify_user"):
            try:
                await context.bot.send_message(
                    chat_id=action["notify_user"],
                    text=action["notification"],
                    parse_mode='Markdown'
                )
                logger.info(f"Notified user {action['notify_user']}")

            except Exception as e:
                logger.error(f"Error notifying user: {e}")

    async def process_webhook(self, update_data: dict) -> None:
        """Process webhook update."""
        if not self.app:
            await self.initialize()

        update = Update.de_json(update_data, self.app.bot)
        await self.app.process_update(update)

    async def set_webhook(self) -> bool:
        """Set webhook URL."""
        if not self.token or not self.webhook_url:
            return False

        try:
            bot = Bot(self.token)
            await bot.set_webhook(url=self.webhook_url)
            logger.info(f"Webhook set: {self.webhook_url}")
            return True
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return False


# Singleton
telegram_bot_simple = TelegramBotSimple()

def get_telegram_bot_simple() -> TelegramBotSimple:
    return telegram_bot_simple
