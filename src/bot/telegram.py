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
from .validation import get_validation_workflow, ValidationStage
from ..models.validation import ProofType
from ..scheduler.reminders import get_reminder_service

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
        self.validation = get_validation_workflow()
        self.reminders = get_reminder_service()
        self.app: Optional[Application] = None
        self.boss_chat_id = settings.telegram_boss_chat_id

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
        self.app.add_handler(TGCommandHandler("syncteam", self._handle_syncteam))
        self.app.add_handler(TGCommandHandler("clearteam", self._handle_clearteam))
        self.app.add_handler(TGCommandHandler("cleandiscord", self._handle_cleandiscord))
        self.app.add_handler(TGCommandHandler("note", self._handle_note))
        self.app.add_handler(TGCommandHandler("delay", self._handle_delay))

        # Validation commands
        self.app.add_handler(TGCommandHandler("submit", self._handle_submit))
        self.app.add_handler(TGCommandHandler("submitproof", self._handle_submitproof))
        self.app.add_handler(TGCommandHandler("pending", self._handle_pending))
        self.app.add_handler(TGCommandHandler("approve", self._handle_approve))
        self.app.add_handler(TGCommandHandler("reject", self._handle_reject))

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

    async def _handle_syncteam(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /syncteam command - sync team from config to Sheets and database."""
        user_id = str(update.effective_user.id)

        # Check for optional --clear flag
        clear_first = "--clear" in context.args if context.args else False

        await update.message.reply_text("🔄 Syncing team members...", parse_mode='Markdown')
        response = await self.commands.handle_syncteam(user_id, clear_first=clear_first)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_clearteam(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /clearteam command - clear mock data from Team sheet."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_clearteam(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_cleandiscord(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /cleandiscord command - delete all task threads from Discord."""
        user_id = str(update.effective_user.id)

        # Get optional channel ID from args
        channel_id = context.args[0] if context.args else None

        await update.message.reply_text("🔄 Cleaning Discord threads... This may take a moment.", parse_mode='Markdown')
        response = await self.commands.handle_cleandiscord(user_id, channel_id)
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
        """Handle general text messages - main conversation flow and validation flow."""
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        message = update.message.text
        message_id = str(update.message.message_id)
        message_lower = message.lower().strip()

        try:
            # Check if user is in validation submission mode
            session = await self.validation._get_session(user_id)

            if session:
                stage = session.get("stage", "")

                # Collecting proof - check for "done" signal
                if stage == ValidationStage.COLLECTING_PROOF.value:
                    if message_lower in ["done", "finish", "submit", "that's all", "thats all"]:
                        response = await self.commands.handle_submit_proof(user_id)
                        await update.message.reply_text(response, parse_mode='Markdown')
                        return
                    elif message_lower.startswith("http"):
                        # User sent a link as proof
                        response = await self.commands.handle_add_proof(
                            user_id=user_id,
                            proof_type=ProofType.LINK,
                            content=message,
                            caption="Link proof"
                        )
                        await update.message.reply_text(response, parse_mode='Markdown')
                        return
                    else:
                        # Treat as a note/text proof
                        response = await self.commands.handle_add_proof(
                            user_id=user_id,
                            proof_type=ProofType.NOTE,
                            content=message,
                            caption="Text note"
                        )
                        await update.message.reply_text(response, parse_mode='Markdown')
                        return

                # Collecting notes stage
                elif stage == ValidationStage.COLLECTING_NOTES.value:
                    response = await self.commands.handle_submission_notes(user_id, message)
                    await update.message.reply_text(response, parse_mode='Markdown')
                    return

                # Confirming submission
                elif stage == ValidationStage.CONFIRMING.value:
                    if message_lower in ["yes", "y", "confirm", "ok", "submit"]:
                        response, request = await self.commands.handle_confirm_submission(user_id)
                        await update.message.reply_text(response, parse_mode='Markdown')

                        # Send validation request to boss
                        if request and self.boss_chat_id:
                            await self._send_validation_to_boss(request, context)
                        return

                    elif message_lower in ["no", "cancel", "abort"]:
                        response = await self.commands.handle_cancel_submission(user_id)
                        await update.message.reply_text(response, parse_mode='Markdown')
                        return

            # Check if boss is responding to validation request
            if str(chat_id) == str(self.boss_chat_id):
                if message_lower.startswith("approve"):
                    # Boss approving - need to determine which task from reply context
                    response, feedback, assignee_id = await self.commands.handle_approve(
                        boss_id=user_id,
                        task_id="",  # Would get from context
                        message=message[7:].strip() or "Great work!"
                    )
                    if response:
                        await update.message.reply_text(response, parse_mode='Markdown')
                        if feedback and assignee_id:
                            await self._notify_assignee(
                                assignee_id, feedback, "", "", context
                            )
                    return

                elif message_lower.startswith("reject"):
                    feedback_text = message[6:].strip()
                    if not feedback_text:
                        await update.message.reply_text(
                            "❌ Please provide feedback:\n`reject [what needs to change]`",
                            parse_mode='Markdown'
                        )
                        return
                    response, feedback, assignee_id = await self.commands.handle_reject(
                        boss_id=user_id,
                        task_id="",
                        feedback=feedback_text
                    )
                    if response:
                        await update.message.reply_text(response, parse_mode='Markdown')
                        if feedback and assignee_id:
                            await self._notify_assignee(
                                assignee_id, feedback, "", "", context
                            )
                    return

            # Default: regular conversation flow
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

    # ==================== VALIDATION HANDLERS ====================

    async def _handle_submit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /submit command - Start validation submission."""
        user_id = str(update.effective_user.id)
        user_name = update.effective_user.full_name or update.effective_user.username or "Team Member"

        if len(context.args) < 1:
            await update.message.reply_text(
                "Usage: /submit [task-id]\n"
                "Example: /submit TASK-20260116-001\n\n"
                "This will start the proof submission process."
            )
            return

        task_id = context.args[0]
        # In a full implementation, we'd look up the task title
        task_title = f"Task {task_id}"

        response = await self.commands.handle_submit(
            user_id=user_id,
            task_id=task_id,
            task_title=task_title,
            assignee_name=user_name
        )
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_submitproof(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /submitproof command - Finish collecting proof."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_submit_proof(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_pending(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /pending command - Show pending validations (for boss)."""
        user_id = str(update.effective_user.id)
        response = await self.commands.handle_pending_validations(user_id)
        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /approve command."""
        user_id = str(update.effective_user.id)

        if len(context.args) < 1:
            await update.message.reply_text(
                "Usage: /approve [task-id] [optional message]\n"
                "Example: /approve TASK-20260116-001 Great work!"
            )
            return

        task_id = context.args[0]
        message = ' '.join(context.args[1:]) if len(context.args) > 1 else "Great work!"

        response, feedback, assignee_id = await self.commands.handle_approve(
            boss_id=user_id,
            task_id=task_id,
            message=message
        )

        if response:
            await update.message.reply_text(response, parse_mode='Markdown')

            # Notify assignee
            if feedback and assignee_id:
                await self._notify_assignee(assignee_id, feedback, task_id, "", context)

    async def _handle_reject(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /reject command."""
        user_id = str(update.effective_user.id)

        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: /reject [task-id] [feedback]\n"
                "Example: /reject TASK-20260116-001 Please add mobile screenshots\n\n"
                "You can list multiple issues separated by newlines or semicolons."
            )
            return

        task_id = context.args[0]
        feedback_text = ' '.join(context.args[1:])

        response, feedback, assignee_id = await self.commands.handle_reject(
            boss_id=user_id,
            task_id=task_id,
            feedback=feedback_text
        )

        if response:
            await update.message.reply_text(response, parse_mode='Markdown')

            # Notify assignee
            if feedback and assignee_id:
                await self._notify_assignee(assignee_id, feedback, task_id, "", context)

    async def _send_validation_to_boss(
        self,
        request,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Send validation request to boss's Telegram."""
        if not self.boss_chat_id:
            logger.warning("Boss chat ID not configured")
            return

        try:
            message = request.to_telegram_message()
            await context.bot.send_message(
                chat_id=self.boss_chat_id,
                text=message,
                parse_mode='Markdown'
            )

            # Send proof items (photos)
            for proof in request.attempt.proof_items:
                if proof.proof_type == ProofType.SCREENSHOT and proof.file_id:
                    await context.bot.send_photo(
                        chat_id=self.boss_chat_id,
                        photo=proof.file_id,
                        caption=f"Proof: {proof.caption or 'Screenshot'}"
                    )
                elif proof.proof_type == ProofType.LINK:
                    await context.bot.send_message(
                        chat_id=self.boss_chat_id,
                        text=f"🔗 Link proof: {proof.content}"
                    )

            logger.info(f"Sent validation request to boss for task {request.task_id}")

        except Exception as e:
            logger.error(f"Error sending validation to boss: {e}")

    async def _notify_assignee(
        self,
        assignee_id: str,
        feedback,
        task_id: str,
        task_title: str,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Notify assignee of validation result."""
        try:
            notification = await self.commands.build_validation_notification(
                feedback=feedback,
                task_id=task_id,
                task_title=task_title
            )

            await context.bot.send_message(
                chat_id=assignee_id,
                text=notification,
                parse_mode='Markdown'
            )
            logger.info(f"Notified assignee {assignee_id} of validation result")

        except Exception as e:
            logger.error(f"Error notifying assignee: {e}")

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
        """Handle photo messages (screenshots) - for both task creation and proof submission."""
        user_id = str(update.effective_user.id)
        caption = update.message.caption or ""
        photo = update.message.photo[-1]  # Get highest resolution
        file_id = photo.file_id

        # Check if user is in validation submission mode
        session = await self.validation._get_session(user_id)

        if session and session.get("stage") == ValidationStage.COLLECTING_PROOF.value:
            # User is submitting proof - add the photo as proof
            response = await self.commands.handle_add_proof(
                user_id=user_id,
                proof_type=ProofType.SCREENSHOT,
                content=file_id,
                caption=caption,
                file_id=file_id
            )
            await update.message.reply_text(response, parse_mode='Markdown')
        else:
            # Regular photo for task context
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
