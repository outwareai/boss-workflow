"""
ModificationHandler - Handles task modifications and updates.

Q1 2026: Task #4.6 Part 2 - Extracted from UnifiedHandler.
Manages all write operations on existing tasks.
"""
from typing import Optional, Dict, Any
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..base_handler import BaseHandler

logger = logging.getLogger(__name__)


class ModificationHandler(BaseHandler):
    """
    Handles task modification operations.

    Responsibilities:
    - Update task fields (title, description, status, assignee)
    - Change task priority
    - Update deadline
    - Reassign tasks
    - Bulk operations (update multiple tasks)
    """

    def __init__(self):
        """Initialize modification handler."""
        super().__init__()
        self.logger = logging.getLogger("ModificationHandler")

    async def can_handle(self, message: str, user_id: str, **kwargs) -> bool:
        """
        Check if this is a modification request.

        Handles:
        - "update", "change", "modify", "edit"
        - "reassign", "change assignee"
        - "set priority", "change deadline"
        """
        message_lower = message.lower().strip()

        modification_keywords = [
            "update", "change", "modify", "edit",
            "reassign", "set priority", "set deadline",
            "change status", "rename"
        ]

        return any(keyword in message_lower for keyword in modification_keywords)

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process modification request."""
        message = update.message.text.strip()
        user_info = await self.get_user_info(update)

        try:
            # Parse modification from natural language
            modification = await self._parse_modification(message)

            if not modification:
                await self.send_error(update, "Could not understand modification request")
                return

            # Execute modification
            await self._execute_modification(update, modification, user_info)

        except Exception as e:
            self.logger.error(f"Modification error: {e}")
            await self.send_error(update, f"Modification failed: {str(e)}")

    async def _parse_modification(self, message: str) -> Optional[Dict[str, Any]]:
        """Parse modification from natural language."""
        # TODO: Implement AI extraction of modification details
        # For now, return None to prevent import errors
        self.logger.warning("_parse_modification not fully implemented, returning None")
        return None

    async def _execute_modification(
        self,
        update: Update,
        modification: Dict[str, Any],
        user_info: Dict
    ) -> None:
        """Execute task modification."""
        task_id = modification.get("task_id")
        updates = modification.get("updates", {})

        if not task_id:
            await self.send_error(update, "No task ID specified")
            return

        # Get existing task
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            await self.send_error(update, f"Task {task_id} not found")
            return

        # Apply updates
        success = await self.task_repo.update(task_id, updates)

        if success:
            # Sync to Sheets
            await self.sheets.sync_task_to_sheet(task_id)

            # Log audit trail
            await self.log_action(
                "task_modified",
                user_info["user_id"],
                {"task_id": task_id, "updates": updates}
            )

            await self.send_success(
                update,
                f"✅ Updated {task_id}: {', '.join(updates.keys())}"
            )
        else:
            await self.send_error(update, f"Failed to update {task_id}")
