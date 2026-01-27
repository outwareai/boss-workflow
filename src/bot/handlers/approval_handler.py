"""
ApprovalHandler - Handles confirmation flows for dangerous actions.

Q1 2026: Task #4.5 - Extracted from UnifiedHandler.
Manages yes/no confirmations for destructive operations.
"""
from typing import Optional, Dict, Any
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from ..base_handler import BaseHandler

logger = logging.getLogger(__name__)


class ApprovalHandler(BaseHandler):
    """
    Handles approval and confirmation workflows.

    Responsibilities:
    - Request confirmation for dangerous actions (delete, bulk operations)
    - Track pending approvals with 5-minute timeout
    - Process yes/no responses
    - Execute approved actions
    - Cancel operations on rejection

    Dangerous Actions:
    - clear_tasks: Delete all active tasks
    - attendance_report: Report absence/late for team member
    - delete_task: Delete a specific task
    - bulk_update: Update multiple tasks at once
    """

    def __init__(self):
        """Initialize approval handler."""
        super().__init__()
        self.logger = logging.getLogger("ApprovalHandler")

    async def can_handle(self, message: str, user_id: str, **kwargs) -> bool:
        """
        Check if this is an approval response.

        Handles:
        - "yes" / "no" responses
        - Messages from users with pending approvals
        """
        message_lower = message.lower().strip()

        # Check for yes/no responses
        if message_lower in ["yes", "no", "y", "n", "confirm", "cancel", "do it", "proceed", "ok", "correct", "wrong", "nevermind"]:
            # Check both new session storage AND legacy _pending_actions dict
            pending = await self.get_session("action", user_id)
            if pending:
                return True

            # LEGACY: Also check UnifiedHandler's _pending_actions for backwards compatibility
            try:
                from ..handler import get_unified_handler
                unified = get_unified_handler()
                if user_id in unified._pending_actions:
                    return True
            except Exception:
                pass

            return False

        return False

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process approval response."""
        message = update.message.text.strip().lower()
        user_info = await self.get_user_info(update)
        user_id = user_info["user_id"]
        user_name = user_info.get("first_name", "User")

        # Get pending action from new session storage
        pending = await self.get_session("action", user_id)

        # LEGACY: Also check UnifiedHandler's _pending_actions
        if not pending:
            try:
                from ..handler import get_unified_handler
                unified = get_unified_handler()
                if user_id in unified._pending_actions:
                    # Delegate to UnifiedHandler for legacy actions
                    response, action_data = await unified.handle_message(
                        user_id=user_id,
                        message=update.message.text,
                        user_name=user_name,
                        is_boss=True,
                        source="telegram"
                    )
                    if response:
                        await self.send_message(update, response)
                    return
            except Exception as e:
                self.logger.error(f"Error checking legacy pending actions: {e}")

        if not pending:
            await self.send_error(update, "No pending action to approve")
            return

        # Check if expired
        if self._is_expired(pending):
            await self.clear_session("action", user_id)
            await self.send_message(update, "❌ Approval request expired (5 minute timeout)")
            return

        # Process response
        if message in ["yes", "y", "confirm", "ok", "do it", "proceed", "correct"]:
            await self._approve_action(update, context, pending, user_id, user_name)
        else:
            await self._reject_action(update, pending, user_id)

    # ==================== REQUEST APPROVAL ====================

    async def request_approval(
        self,
        user_id: str,
        action_type: str,
        action_data: Dict[str, Any],
        message: str,
        timeout_minutes: int = 5
    ) -> bool:
        """
        Request user approval for dangerous action.

        Args:
            user_id: User to request approval from
            action_type: Type of action (clear_tasks, delete_task, etc.)
            action_data: Data needed to execute action
            message: Confirmation message to display
            timeout_minutes: Minutes until approval expires

        Returns:
            True if request created successfully
        """
        try:
            # Store pending action
            await self.set_session(
                "action",
                user_id,
                {
                    "type": action_type,
                    "action_data": action_data,
                    "message": message,
                    "requested_at": datetime.now().isoformat(),
                    "timeout_minutes": timeout_minutes,
                },
                ttl=timeout_minutes * 60
            )

            self.logger.info(f"Approval requested: {action_type} for user {user_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to request approval: {e}")
            return False

    # ==================== APPROVE ACTION ====================

    async def _approve_action(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        pending: Dict[str, Any],
        user_id: str,
        user_name: str
    ) -> None:
        """Execute approved action."""
        try:
            action_type = pending["type"]
            action_data = pending.get("action_data", {})

            self.logger.info(f"Executing approved action: {action_type}")

            # Route to appropriate action handler
            if action_type == "clear_tasks":
                await self._execute_clear_tasks(update, action_data, user_name)
            elif action_type == "attendance_report":
                await self._execute_attendance_report(update, action_data, user_name)
            elif action_type == "delete_task":
                await self._execute_delete_task(update, action_data, user_name)
            elif action_type == "bulk_update":
                await self._execute_bulk_update(update, action_data, user_name)
            else:
                await self.send_error(update, f"Unknown action type: {action_type}")
                return

            # Clear pending action
            await self.clear_session("action", user_id)

            # Log action
            await self.log_action(
                f"approved_{action_type}",
                user_id,
                action_data
            )

        except Exception as e:
            self.logger.error(f"Failed to execute approved action: {e}")
            await self.send_error(update, f"Failed to execute action: {str(e)}")

    # ==================== REJECT ACTION ====================

    async def _reject_action(
        self,
        update: Update,
        pending: Dict[str, Any],
        user_id: str
    ) -> None:
        """Cancel action."""
        action_type = pending["type"]

        # Clear pending action
        await self.clear_session("action", user_id)

        # Log cancellation
        await self.log_action(
            f"rejected_{action_type}",
            user_id,
            {"action": action_type}
        )

        await self.send_message(update, "❌ Action cancelled. No changes were made.")
        self.logger.info(f"Action rejected: {action_type} by user {user_id}")

    # ==================== ACTION EXECUTORS ====================

    async def _execute_clear_tasks(self, update: Update, data: Dict[str, Any], user_name: str) -> None:
        """Execute clear all tasks."""
        from ...database.repositories import get_task_repository
        from ...database.repositories.staff_context import get_staff_context_repository

        try:
            task_repo = get_task_repository()
            staff_repo = get_staff_context_repository()

            # Get all tasks from Sheets
            tasks = await self.sheets.get_all_tasks()
            tasks_to_delete = []

            for task in tasks:
                status = task.get("Status", task.get("status", ""))
                task_id = task.get("ID", task.get("id", ""))
                if status.lower() not in ["completed", "cancelled"] and task_id:
                    tasks_to_delete.append(task_id)

            # Delete each task
            deleted = 0
            failed = 0
            discord_deleted = 0

            for task_id in tasks_to_delete:
                # Delete from Sheets
                success = await self.sheets.delete_task(task_id)
                if success:
                    deleted += 1
                else:
                    failed += 1

                # Delete from database
                try:
                    await task_repo.delete(task_id)
                except Exception as e:
                    self.logger.warning(f"Could not delete task {task_id} from database: {e}")

                # Delete Discord thread
                try:
                    thread_id = await staff_repo.get_thread_by_task(task_id)
                    if thread_id:
                        if await self.discord.delete_task_message(task_id, thread_id):
                            discord_deleted += 1
                    else:
                        # Try getting from task repo
                        db_task = await task_repo.get_by_id(task_id)
                        if db_task and db_task.discord_message_id:
                            if await self.discord.delete_task_message(task_id, db_task.discord_message_id):
                                discord_deleted += 1
                except Exception as e:
                    self.logger.warning(f"Could not delete Discord thread for {task_id}: {e}")

            # Post to Discord
            await self.discord.post_alert(
                title="Tasks Deleted",
                message=f"{deleted} task(s) permanently deleted by {user_name}",
                alert_type="warning"
            )

            # Send response
            response = f"✅ Deleted {deleted} task(s) from Sheets"
            if discord_deleted > 0:
                response += f" and {discord_deleted} Discord thread(s)"
            if failed > 0:
                response += f"\n⚠️ {failed} task(s) could not be deleted"

            await self.send_message(update, response)

        except Exception as e:
            self.logger.error(f"Error clearing tasks: {e}", exc_info=True)
            await self.send_error(update, "Error clearing tasks. Please try again.")

    async def _execute_attendance_report(self, update: Update, data: Dict[str, Any], user_name: str) -> None:
        """Execute attendance report."""
        from ...services.attendance import get_attendance_service

        attendance_service = get_attendance_service()
        result = await attendance_service.record_boss_reported_attendance(
            affected_person=data.get("affected_person"),
            status_type=data.get("status_type"),
            affected_date=data.get("affected_date"),
            reason=data.get("reason"),
            reported_by=user_name,
            reported_at=datetime.now(),
        )

        if result.get("success"):
            response = f"✅ Attendance recorded:\n\n"
            response += f"👤 {data.get('affected_person')}\n"
            response += f"📅 {data.get('affected_date')}\n"
            response += f"📊 Status: {data.get('status_type')}\n"
            if data.get("reason"):
                response += f"📝 Reason: {data.get('reason')}\n"

            await self.send_message(update, response.strip())
        else:
            await self.send_error(update, f"Failed to record attendance: {result.get('error', 'Unknown error')}")

    async def _execute_delete_task(self, update: Update, data: Dict[str, Any], user_name: str) -> None:
        """Execute single task deletion."""
        task_id = data["task_id"]

        success = await self.sheets.delete_task(task_id)

        if success:
            # Delete from database
            await self.task_repo.delete(task_id)

            # Delete from Discord
            from ...database.repositories.staff_context import get_staff_context_repository
            staff_repo = get_staff_context_repository()
            thread_id = await staff_repo.get_thread_by_task(task_id)
            if thread_id:
                await self.discord.delete_task_message(task_id, thread_id)

            await self.send_success(update, f"Task {task_id} deleted")
        else:
            await self.send_error(update, f"Failed to delete task {task_id}")

    async def _execute_bulk_update(self, update: Update, data: Dict[str, Any], user_name: str) -> None:
        """Execute bulk task update."""
        task_ids = data["task_ids"]
        updates = data["updates"]

        success_count = 0
        for task_id in task_ids:
            if await self.task_repo.update(task_id, updates):
                success_count += 1
                # Sync to sheets
                task = await self.task_repo.get_by_id(task_id)
                if task:
                    await self.sheets.update_task(task_id, updates)

        await self.send_success(
            update,
            f"Updated {success_count}/{len(task_ids)} tasks"
        )

    # ==================== HELPERS ====================

    def _is_expired(self, pending: Dict[str, Any]) -> bool:
        """Check if approval request has expired."""
        try:
            requested_at = datetime.fromisoformat(pending["requested_at"])
            timeout_minutes = pending.get("timeout_minutes", 5)
            expires_at = requested_at + timedelta(minutes=timeout_minutes)

            return datetime.now() > expires_at

        except Exception as e:
            self.logger.error(f"Error checking expiration: {e}")
            return True  # Assume expired on error
