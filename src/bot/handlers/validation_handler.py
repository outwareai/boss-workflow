"""
ValidationHandler - Handles task validation and approval flows.

Q1 2026: Extracted from UnifiedHandler (Task #4.3).
Manages boss validation of staff task submissions.
"""
from typing import Optional, Dict, Any, Tuple
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from ..base_handler import BaseHandler
from ...ai.intent import UserIntent

logger = logging.getLogger(__name__)


class ValidationHandler(BaseHandler):
    """
    Handles task validation flows for boss approval/rejection.

    Responsibilities:
    - Track pending validations (tasks awaiting boss approval)
    - Process /approve commands
    - Process /reject commands
    - Notify staff of validation results
    - Update task status based on validation outcome
    - Send validation requests to boss
    - Handle proof submission flow
    """

    def __init__(self):
        """Initialize validation handler."""
        super().__init__()
        self.logger = logging.getLogger("ValidationHandler")

    async def can_handle(self, message: str, user_id: str, **kwargs) -> bool:
        """
        Check if this message is a validation-related command.

        Handles:
        - /approve {task_id}
        - /reject {task_id} [reason]
        - Task validation requests
        - Proof submission flow
        """
        message_lower = message.lower().strip()

        # Check for approval/rejection commands
        if message_lower.startswith('/approve') or message_lower.startswith('/reject'):
            return True

        # Check if user has pending validation session
        validation_session = await self.get_session("validation", user_id)
        if validation_session:
            return True

        # Check for intent-based validation commands
        intent = kwargs.get("intent")
        if intent in [UserIntent.APPROVE_TASK, UserIntent.REJECT_TASK]:
            return True

        return False

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process validation-related messages."""
        message = update.message.text.strip() if update.message.text else ""
        user_info = await self.get_user_info(update)
        user_id = user_info["user_id"]
        user_name = user_info.get("full_name", "Unknown")

        # Get any existing validation session
        validation_session = await self.get_session("validation", user_id)

        # Route to appropriate handler
        if message.lower().startswith('/approve'):
            response, meta = await self._handle_approve(user_id, message, {}, {}, user_name)
            await self.send_message(update, response)
        elif message.lower().startswith('/reject'):
            response, meta = await self._handle_reject(user_id, message, {}, {}, user_name)
            await self.send_message(update, response)
        elif validation_session:
            # Handle validation flow response
            await self._handle_validation_flow(update, context, message, validation_session)
        else:
            await self.send_error(update, "No active validation session")

    # ==================== VALIDATION REQUEST ====================

    async def request_validation(
        self,
        task_id: str,
        staff_user_id: str,
        boss_user_id: str,
        description: str,
        proof_items: list = None,
        notes: Optional[str] = None
    ) -> bool:
        """
        Send validation request to boss for task approval.

        Args:
            task_id: Task ID to validate
            staff_user_id: User who submitted the task
            boss_user_id: Boss who will validate
            description: Task description
            proof_items: List of proof items (screenshots, links, etc.)
            notes: Optional notes from staff

        Returns:
            True if request sent successfully
        """
        try:
            # Update task status to awaiting_validation
            task = await self.task_repo.get_by_id(task_id)
            if task:
                await self.task_repo.update(task_id, {"status": "awaiting_validation"})

            # Track pending validation
            await self.set_session("pending_validation", task_id, {
                "task_id": task_id,
                "staff_user_id": staff_user_id,
                "description": description,
                "proof_items": proof_items or [],
                "notes": notes,
                "submitted_at": datetime.now().isoformat(),
            }, ttl=86400)  # 24 hour TTL

            # Create validation message for boss
            validation_message = self._format_validation_request(
                task_id,
                staff_user_id,
                description,
                proof_items or [],
                notes
            )

            # Send to boss via Telegram
            from config.settings import get_settings
            settings = get_settings()

            import aiohttp
            telegram_api = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
            timeout = aiohttp.ClientTimeout(total=30.0)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                await session.post(
                    telegram_api,
                    json={
                        "chat_id": boss_user_id,
                        "text": validation_message,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    }
                )

            # Log action
            await self.log_action(
                "validation_requested",
                staff_user_id,
                {"task_id": task_id, "proof_items_count": len(proof_items or [])}
            )

            self.logger.info(f"Validation requested for task {task_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to request validation: {e}")
            return False

    # ==================== APPROVAL HANDLING ====================

    async def _handle_approve(
        self,
        user_id: str,
        message: str,
        data: Dict,
        context: Dict,
        user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle boss approval."""
        # Check if boss
        is_boss = await self.is_boss(user_id)
        if not is_boss:
            return "Only the boss can approve tasks.", None

        # Get all pending validations
        pending_validations = await self.session_manager.list_pending_validations()

        if not pending_validations:
            return "Nothing pending approval.", None

        # Parse task ID from command if provided
        parts = message.split()
        task_id = None
        if len(parts) >= 2:
            task_id = parts[1]

        # Find the validation to approve
        validation = None
        if task_id:
            # Find specific task
            for v in pending_validations:
                if v.get("task_id") == task_id:
                    validation = v
                    break
            if not validation:
                return f"No pending validation found for task {task_id}", None
        else:
            # Get most recent
            validation = pending_validations[-1]
            task_id = validation.get("task_id")

        # Update task status to completed
        success = await self.task_repo.update(task_id, {
            "status": "completed",
            "completed_at": datetime.now(),
        })

        if not success:
            return f"Failed to approve task {task_id}", None

        # Post to Discord
        staff_user_id = validation.get("staff_user_id")
        description = validation.get("description", "")

        await self.discord.post_alert(
            title="Task Approved ✅",
            message=f"**{validation.get('user_name', 'Team member')}** - {description[:50]}",
            alert_type="success"
        )

        # Notify staff
        approval_msg = data.get("approval_message", message)
        await self._notify_staff(
            staff_user_id,
            f"""🎉 **APPROVED!**

Your work on "{description[:50]}..." was approved!

Boss said: "{approval_msg}"

Great job! ✅"""
        )

        # Clear pending validation
        await self.clear_session("pending_validation", task_id)

        # Log action
        await self.log_action(
            "task_approved",
            user_id,
            {"task_id": task_id, "staff_user_id": staff_user_id}
        )

        # Sync to sheets
        await self.sheets.sync_task_to_sheet(task_id)

        return f"✅ Approved! Notified team member.", {
            "notify_user": staff_user_id,
        }

    # ==================== REJECTION HANDLING ====================

    async def _handle_reject(
        self,
        user_id: str,
        message: str,
        data: Dict,
        context: Dict,
        user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle boss rejection with feedback."""
        # Check if boss
        is_boss = await self.is_boss(user_id)
        if not is_boss:
            return "Only the boss can reject tasks.", None

        # Get all pending validations
        pending_validations = await self.session_manager.list_pending_validations()

        if not pending_validations:
            return "Nothing pending review.", None

        # Parse command
        parts = message.split(maxsplit=2)
        task_id = None
        reason = "No reason provided"

        if len(parts) >= 2:
            task_id = parts[1]
            if len(parts) >= 3:
                reason = parts[2]

        # Find the validation to reject
        validation = None
        if task_id:
            # Find specific task
            for v in pending_validations:
                if v.get("task_id") == task_id:
                    validation = v
                    break
            if not validation:
                return f"No pending validation found for task {task_id}", None
        else:
            # Get most recent
            validation = pending_validations[-1]
            task_id = validation.get("task_id")

        # Update task status to needs_revision
        success = await self.task_repo.update(task_id, {
            "status": "needs_revision",
            "delay_reason": reason,
        })

        if not success:
            return f"Failed to reject task {task_id}", None

        # Post to Discord
        staff_user_id = validation.get("staff_user_id")
        description = validation.get("description", "")

        await self.discord.post_alert(
            title="Revision Requested",
            message=f"**{validation.get('user_name', 'Team member')}** - {reason[:100]}",
            alert_type="warning"
        )

        # Notify staff
        await self._notify_staff(
            staff_user_id,
            f"""🔄 **Changes Requested**

Your submission needs some work.

**Feedback:**
{reason}

Make the changes and submit again when ready!"""
        )

        # Clear pending validation
        await self.clear_session("pending_validation", task_id)

        # Log action
        await self.log_action(
            "task_rejected",
            user_id,
            {"task_id": task_id, "staff_user_id": staff_user_id, "reason": reason}
        )

        # Sync to sheets
        await self.sheets.sync_task_to_sheet(task_id)

        return f"Sent feedback to team member.", {
            "notify_user": staff_user_id,
        }

    # ==================== VALIDATION FLOW ====================

    async def _handle_validation_flow(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        message: str,
        session: Dict[str, Any]
    ) -> None:
        """Handle multi-step validation flow (proof collection, etc.)."""
        stage = session.get("stage", "collecting_proof")

        if stage == "collecting_proof":
            # User is adding proof items
            if message.lower() in ["that's all", "done", "finish"]:
                # Move to notes stage
                session["stage"] = "awaiting_notes"
                await self.set_session("validation", update.effective_user.id, session)
                await self.send_message(
                    update,
                    f"""Got {len(session.get('proof_items', []))} proof item(s)!

Any notes for the boss? (what you did, issues, etc.)
Or say "no" to skip."""
                )
            else:
                # Add proof item
                proof_items = session.get("proof_items", [])
                proof_items.append({
                    "type": "note",
                    "content": message,
                    "timestamp": datetime.now().isoformat()
                })
                session["proof_items"] = proof_items
                await self.set_session("validation", update.effective_user.id, session)

                count = len(proof_items)
                await self.send_message(
                    update,
                    f"📝 Got it! ({count} item{'s' if count > 1 else ''} so far)\n\nMore proof, or say \"that's all\""
                )

        elif stage == "awaiting_notes":
            # User is adding notes
            notes = None if message.lower() in ["no", "skip", "none"] else message
            session["notes"] = notes
            session["stage"] = "awaiting_confirm"
            await self.set_session("validation", update.effective_user.id, session)

            proof_count = len(session.get("proof_items", []))
            summary = f"""**Ready to submit:**

📋 Task: {session.get('message', 'Task completion')[:50]}...
📎 Proof: {proof_count} item(s)
📝 Notes: {notes if notes else '(none)'}

Send to boss for review? (yes/no)"""
            await self.send_message(update, summary)

        elif stage == "awaiting_confirm":
            # User is confirming submission
            if message.lower() in ["yes", "y", "send", "submit"]:
                # Send to boss
                user_info = await self.get_user_info(update)
                user_id = user_info["user_id"]
                user_name = user_info.get("full_name", "Unknown")

                # Generate task reference
                task_ref = f"TASK-{datetime.now().strftime('%m%d')}-{user_id[-3:]}"

                # Request validation from boss
                success = await self.request_validation(
                    task_id=task_ref,
                    staff_user_id=user_id,
                    boss_user_id=str((await self._get_boss_id())),
                    description=session.get("message", ""),
                    proof_items=session.get("proof_items", []),
                    notes=session.get("notes")
                )

                # Clear session
                await self.clear_session("validation", user_id)

                if success:
                    await self.send_success(
                        update,
                        "Sent to boss for review! I'll let you know when they respond."
                    )
                else:
                    await self.send_error(update, "Failed to send validation request")
            else:
                # Cancel submission
                await self.clear_session("validation", update.effective_user.id)
                await self.send_message(update, "Cancelled. Let me know when you're ready to submit!")

    # ==================== HELPERS ====================

    def _format_validation_request(
        self,
        task_id: str,
        staff_user_id: str,
        description: str,
        proof_items: list,
        notes: Optional[str]
    ) -> str:
        """Format validation request message for boss."""
        lines = [
            f"📋 **Task Validation Request**",
            "",
            f"**Task:** {task_id}",
            f"**Description:** {description[:100]}",
            "",
            f"📎 **Proof:** {len(proof_items)} item(s)",
        ]

        # List proof items
        for i, proof in enumerate(proof_items[:5], 1):
            ptype = proof.get("type", "item")
            emoji = {"screenshot": "🖼️", "link": "🔗", "note": "📝"}.get(ptype, "📎")
            content = proof.get("content", "")[:50]
            lines.append(f"  {emoji} {content}")

        if notes:
            lines.extend(["", f"📝 **Notes:** {notes}"])

        lines.extend([
            "",
            "─────────────────",
            f"_Ref: {task_id}_",
            "",
            "**Reply:**",
            "• `/approve {task_id}` - Mark as completed",
            "• `/reject {task_id} [reason]` - Request revision"
        ])

        return "\n".join(lines)

    async def _notify_staff(self, staff_user_id: str, message: str) -> None:
        """Send notification to staff member."""
        try:
            from config.settings import get_settings
            settings = get_settings()

            import aiohttp
            telegram_api = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
            timeout = aiohttp.ClientTimeout(total=30.0)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                await session.post(
                    telegram_api,
                    json={
                        "chat_id": staff_user_id,
                        "text": message,
                        "parse_mode": "Markdown",
                    }
                )
        except Exception as e:
            self.logger.error(f"Failed to notify staff {staff_user_id}: {e}")

    async def _get_boss_id(self) -> int:
        """Get boss user ID from settings."""
        from config.settings import get_settings
        settings = get_settings()
        return settings.telegram_boss_chat_id

    # ==================== PENDING VALIDATIONS ====================

    async def get_pending_validations(self) -> list:
        """Get all pending validations."""
        return await self.session_manager.list_pending_validations()

    async def get_validation_count(self) -> int:
        """Get count of pending validations."""
        validations = await self.get_pending_validations()
        return len(validations)
