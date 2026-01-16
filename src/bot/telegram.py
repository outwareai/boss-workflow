"""
Telegram bot implementation using python-telegram-bot.

Main entry point for the Telegram integration with webhook support.
"""

import logging
from typing import Optional
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler as TGCommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import settings
from .commands import get_command_handler
from .conversation import get_conversation_manager

logger = logging.getLogger(__name__)


class TelegramBot:
    """
    Telegram bot for Boss Workflow Automation.

    Handles:
    - Webhook setup and processing
    - Command routing
    - Message handling
    - Voice message support
    """

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.webhook_url = f"{settings.webhook_base_url}/webhook/telegram"
        self.commands = get_command_handler()
        self.conversation = get_conversation_manager()
        self.app: Optional[Application] = None

    async def initialize(self) -> None:
        """Initialize the Telegram bot application."""
        if not self.token:
            logger.error("Telegram bot token not configured")
            return

        # Build the application
        self.app = Application.builder().token(self.token).build()

        # Register handlers
        self._register_handlers()

        logger.info("Telegram bot initialized")

    def _register_handlers(self) -> None:
        """Register all command and message handlers."""
        if not self.app:
            return

        # Command handlers
        self.app.add_handler(TGCommandHandler("start", self._handle_start))
        self.app.add_handler(TGCommandHandler("help", self._handle_help))
        self.app.add_handler(TGCommandHandler("task", self._handle_task))
        self.app.add_handler(TGCommandHandler("urgent", self._handle_urgent))
        self.app.add_handler(TGCommandHandler("skip", self._handle_skip))
        self.app.add_handler(TGCommandHandler("done", self._handle_done))
        self.app.add_handler(TGCommandHandler("cancel", self._handle_cancel))
        self.app.add_handler(TGCommandHandler("status", self._handle_status))
        self.app.add_handler(TGCommandHandler("weekly", self._handle_weekly))
        self.app.add_handler(TGCommandHandler("daily", self._handle_daily))
        self.app.add_handler(TGCommandHandler("overdue", self._handle_overdue))
        self.app.add_handler(TGCommandHandler("preferences", self._handle_preferences))
        self.app.add_handler(TGCommandHandler("teach", self._handle_teach))
        self.app.add_handler(TGCommandHandler("team", self._handle_team))
        self.app.add_handler(TGCommandHandler("addteam", self._handle_addteam))
        self.app.add_handler(TGCommandHandler("note", self._handle_note))
        self.app.add_handler(TGCommandHandler("delay", self._handle_delay))

        # Voice message handler
        self.app.add_handler(MessageHandler(filters.VOICE, self._handle_voice))

        # Photo handler (for screenshots)
        self.app.add_handler(MessageHandler(filters.PHOTO, self._handle_photo))

        # General text message handler (for conversation flow)
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self._handle_message
        ))

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_start(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_help(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /task command."""
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        message = ' '.join(context.args) if context.args else ""

        if not message:
            await update.message.reply_text(
                "What task would you like to create? Send a description."
            )
            return

        response = await self.commands.handle_task(user_id, chat_id, message)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_urgent(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /urgent command."""
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        message = ' '.join(context.args) if context.args else ""

        if not message:
            await update.message.reply_text(
                "🔴 What urgent task would you like to create?"
            )
            return

        response = await self.commands.handle_urgent(user_id, chat_id, message)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_skip(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /skip command."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_skip(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /done command."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_done(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /cancel command."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_cancel(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_status(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_weekly(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /weekly command."""
        user_id = str(update.effective_user.id)
        await update.message.reply_text("📊 Generating weekly summary...")
        response = await self.commands.handle_weekly(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_daily(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /daily command."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_daily(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_overdue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /overdue command."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_overdue(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_preferences(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /preferences command."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_preferences(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_teach(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /teach command."""
        user_id = str(update.effective_user.id)
        teaching_text = ' '.join(context.args) if context.args else ""
        response = await self.commands.handle_teach(user_id, teaching_text)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_team(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /team command."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_team(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_addteam(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /addteam command."""
        user_id = str(update.effective_user.id)

        if len(context.args) < 1:
            await update.message.reply_text(
                "Usage: /addteam [name] [role]\nExample: /addteam John Backend Developer"
            )
            return

        name = context.args[0]
        role = ' '.join(context.args[1:]) if len(context.args) > 1 else ""

        response = await self.commands.handle_addteam(user_id, name, role)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /note command."""
        user_id = str(update.effective_user.id)

        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: /note [task-id] [note content]\n"
                "Example: /note TASK-20260116-001 Discussed with client, need more info"
            )
            return

        task_id = context.args[0]
        note_content = ' '.join(context.args[1:])

        response = await self.commands.handle_note(user_id, task_id, note_content)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_delay(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /delay command."""
        user_id = str(update.effective_user.id)

        if len(context.args) < 3:
            await update.message.reply_text(
                "Usage: /delay [task-id] [new-deadline] [reason]\n"
                "Example: /delay TASK-20260116-001 tomorrow Waiting for client approval"
            )
            return

        task_id = context.args[0]
        new_deadline = context.args[1]
        reason = ' '.join(context.args[2:])

        response = await self.commands.handle_delay(user_id, task_id, new_deadline, reason)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle general text messages - main conversation flow."""
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        message = update.message.text
        message_id = str(update.message.message_id)

        try:
            response, _ = await self.conversation.process_message(
                user_id=user_id,
                message=message,
                message_id=message_id
            )
            await update.message.reply_text(response, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await update.message.reply_text(
                "Sorry, I encountered an error. Please try again."
            )

    async def _handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice messages."""
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)

        await update.message.reply_text("🎤 Processing voice message...")

        try:
            # Download voice file
            voice = update.message.voice
            voice_file = await context.bot.get_file(voice.file_id)

            # Save temporarily
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
                await voice_file.download_to_drive(f.name)
                temp_path = f.name

            # Transcribe using DeepSeek/Whisper
            from ..ai.deepseek import get_deepseek_client
            ai = get_deepseek_client()
            transcription = await ai.transcribe_voice(temp_path)

            # Clean up
            import os
            os.unlink(temp_path)

            if transcription and not transcription.startswith("["):
                await update.message.reply_text(f"📝 Transcribed: {transcription}")

                # Process as a regular message
                response, _ = await self.conversation.process_message(
                    user_id=user_id,
                    message=transcription
                )
                await update.message.reply_text(response, parse_mode='Markdown')
            else:
                await update.message.reply_text(
                    "Sorry, I couldn't transcribe the voice message. "
                    "Please try typing your request."
                )

        except Exception as e:
            logger.error(f"Error processing voice: {e}")
            await update.message.reply_text(
                "Sorry, I couldn't process the voice message. Please type your request."
            )

    async def _handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle photo messages (screenshots)."""
        user_id = str(update.effective_user.id)
        caption = update.message.caption or ""

        await update.message.reply_text(
            "📸 Photo received! " +
            (f"Processing with caption: {caption}" if caption else "Please describe what this is about.")
        )

        if caption:
            # Process the caption as a message with attachment context
            response, _ = await self.conversation.process_message(
                user_id=user_id,
                message=f"[Photo attached] {caption}"
            )
            await update.message.reply_text(response, parse_mode='Markdown')

    async def process_webhook(self, update_data: dict) -> None:
        """Process an incoming webhook update."""
        if not self.app:
            await self.initialize()

        update = Update.de_json(update_data, self.app.bot)
        await self.app.process_update(update)

    async def set_webhook(self) -> bool:
        """Set the webhook URL with Telegram."""
        if not self.token or not self.webhook_url:
            logger.error("Cannot set webhook: missing token or webhook URL")
            return False

        try:
            bot = Bot(self.token)
            await bot.set_webhook(url=self.webhook_url)
            logger.info(f"Webhook set to: {self.webhook_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
            return False

    async def remove_webhook(self) -> bool:
        """Remove the webhook (for polling mode)."""
        try:
            bot = Bot(self.token)
            await bot.delete_webhook()
            logger.info("Webhook removed")
            return True
        except Exception as e:
            logger.error(f"Failed to remove webhook: {e}")
            return False


# Singleton instance
telegram_bot = TelegramBot()


def get_telegram_bot() -> TelegramBot:
    """Get the Telegram bot instance."""
    return telegram_bot
