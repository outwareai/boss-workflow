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
            # Check if this is a reply to an escalation message (boss reply routing)
            if is_boss and update.message.reply_to_message:
                reply_to_msg_id = str(update.message.reply_to_message.message_id)
                result = await self._handle_boss_reply_to_escalation(reply_to_msg_id, message)
                if result.get("handled"):
                    # Successfully routed to Discord
                    task_id = result.get("task_id", "")
                    await update.message.reply_text(
                        f"✅ Reply sent to staff in Discord for {task_id}",
                        parse_mode='Markdown'
                    )
                    return
                # If not handled (not a reply to escalation), continue with normal processing

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
            error_type = type(e).__name__
            await update.message.reply_text(
                f"⚠️ Something unexpected happened ({error_type}). "
                "Please try again or rephrase your request."
            )

    async def _handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle photo messages with AI vision analysis."""
        user_id = str(update.effective_user.id)
        user_name = update.effective_user.first_name or "User"
        photo = update.message.photo[-1]  # Get highest resolution
        file_id = photo.file_id
        caption = update.message.caption

        is_boss = str(update.effective_chat.id) == str(self.boss_chat_id)

        try:
            # Download the photo for vision analysis
            photo_file = await context.bot.get_file(file_id)
            photo_bytes = await photo_file.download_as_bytearray()

            # Analyze with DeepSeek Vision
            from ..ai.vision import get_vision
            vision = get_vision()

            # Check if caption indicates task creation - don't analyze image content in that case
            task_creation_keywords = [
                "add a new task", "add new task", "new task", "create task", "fix", "update",
                "add a task", "task for", "assign", "spec sheet", "specsheet"
            ]
            caption_lower = (caption or "").lower()
            is_task_creation = any(kw in caption_lower for kw in task_creation_keywords)

            if is_task_creation and caption:
                # Task creation with reference image - don't analyze image content
                # Just pass the caption as the task description with image attached
                logger.info("Image sent with task creation caption - treating as task with reference image")
                message_with_analysis = f"{caption}\n\n[📷 Reference image attached]"
                analysis = "Reference image for task"
            else:
                await update.message.reply_text("🔍 Analyzing image...")

                # Choose analysis type based on context
                if caption:
                    # User provided context, use it
                    analysis = await vision.analyze_image(
                        bytes(photo_bytes),
                        prompt=f"The user sent this image with the message: '{caption}'\n\nAnalyze the image in this context. What does it show? What action might be needed?"
                    )
                else:
                    # No caption, do general analysis
                    analysis = await vision.describe_for_task(bytes(photo_bytes))

                # Build message with analysis
                if analysis:
                    message_with_analysis = f"[Image Analysis: {analysis}]"
                    if caption:
                        message_with_analysis = f"{caption}\n\n{message_with_analysis}"
                else:
                    message_with_analysis = caption or "[Photo received]"

            response, action = await self.handler.handle_message(
                user_id=user_id,
                message=message_with_analysis,
                photo_file_id=file_id,
                photo_caption=caption,
                photo_analysis=analysis,  # Pass vision analysis
                user_name=user_name,
                is_boss=is_boss
            )

            await update.message.reply_text(response, parse_mode='Markdown')

            if action:
                await self._handle_action(action, context)

        except Exception as e:
            logger.error(f"Error handling photo: {e}", exc_info=True)
            await update.message.reply_text("Got the photo! What's it for?")

    async def _handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice messages - transcribe using OpenAI Whisper and process."""
        user_id = str(update.effective_user.id)
        user_name = update.effective_user.first_name or "User"

        await update.message.reply_text("🎤 Got your voice message, transcribing...")

        try:
            # Download voice file
            voice = update.message.voice
            voice_file = await context.bot.get_file(voice.file_id)

            # Download to bytes
            voice_bytes = await voice_file.download_as_bytearray()

            # Transcribe using Whisper
            from ..ai.transcriber import transcribe_voice_message
            transcription = await transcribe_voice_message(
                audio_data=bytes(voice_bytes),
                filename=f"voice_{voice.file_id}.ogg"
            )

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
                await update.message.reply_text("Couldn't catch that. Try typing instead?\n\n_Voice transcription requires OPENAI_API_KEY to be set._", parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error with voice: {e}", exc_info=True)
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

    async def _handle_boss_reply_to_escalation(
        self,
        reply_to_message_id: str,
        boss_message: str
    ) -> dict:
        """
        Handle boss replying to an escalation message.

        Routes the reply to the appropriate staff member via Discord.

        Args:
            reply_to_message_id: The Telegram message ID being replied to
            boss_message: The boss's reply text

        Returns:
            Dict with 'handled' bool and optional 'task_id'
        """
        try:
            from .staff_handler import get_staff_handler
            staff_handler = get_staff_handler()

            result = await staff_handler.handle_boss_reply_to_escalation(
                reply_to_message_id=reply_to_message_id,
                boss_message=boss_message
            )

            return result

        except Exception as e:
            logger.error(f"Error handling boss reply to escalation: {e}", exc_info=True)
            return {"handled": False, "error": str(e)}

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
