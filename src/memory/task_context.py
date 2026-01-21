"""
Task Context Manager - Per-task conversation history and context.

Stores and retrieves conversation history for each task, enabling
the Staff AI Assistant to have contextual conversations.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json

from config import settings

logger = logging.getLogger(__name__)


class TaskContextManager:
    """
    Manages conversation context per task.

    Stores:
    - Conversation history (messages between staff and AI)
    - Task details (fetched from sheets/database)
    - Escalation history
    - Submission attempts
    """

    def __init__(self):
        # In-memory storage: {task_id: TaskContext}
        self._contexts: Dict[str, Dict[str, Any]] = {}
        # Map Discord thread/channel to task: {channel_id: task_id}
        self._channel_to_task: Dict[str, str] = {}
        # Map staff to their active task: {staff_id: task_id}
        self._staff_active_task: Dict[str, str] = {}

    def get_context(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the context for a task."""
        return self._contexts.get(task_id)

    def create_context(
        self,
        task_id: str,
        task_details: Dict[str, Any],
        channel_id: str = None,
        staff_id: str = None
    ) -> Dict[str, Any]:
        """
        Create or update context for a task.

        Args:
            task_id: The task ID
            task_details: Task information (title, description, criteria, etc.)
            channel_id: Discord channel/thread ID for this task
            staff_id: Staff member's Discord ID
        """
        context = {
            "task_id": task_id,
            "task_details": task_details,
            "conversation_history": [],
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "staff_id": staff_id,
            "channel_id": channel_id,
            "submission_attempts": 0,
            "escalations": [],
            "status": "active"
        }

        self._contexts[task_id] = context

        if channel_id:
            self._channel_to_task[channel_id] = task_id

        if staff_id:
            self._staff_active_task[staff_id] = task_id

        logger.info(f"Created context for task {task_id}")
        return context

    def add_message(
        self,
        task_id: str,
        role: str,  # "staff" or "assistant"
        content: str,
        metadata: Dict[str, Any] = None
    ) -> None:
        """Add a message to the conversation history."""
        context = self._contexts.get(task_id)
        if not context:
            logger.warning(f"No context found for task {task_id}")
            return

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }

        context["conversation_history"].append(message)
        context["last_activity"] = datetime.now().isoformat()

        # Keep only last 50 messages to prevent memory bloat
        if len(context["conversation_history"]) > 50:
            context["conversation_history"] = context["conversation_history"][-50:]

    def get_conversation_history(self, task_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent conversation history for a task."""
        context = self._contexts.get(task_id)
        if not context:
            return []

        history = context.get("conversation_history", [])
        return history[-limit:] if limit else history

    def get_task_details(self, task_id: str) -> Dict[str, Any]:
        """Get task details from context."""
        context = self._contexts.get(task_id)
        if not context:
            return {}
        return context.get("task_details", {})

    def update_task_details(self, task_id: str, updates: Dict[str, Any]) -> None:
        """Update task details in context."""
        context = self._contexts.get(task_id)
        if context:
            context["task_details"].update(updates)
            context["last_activity"] = datetime.now().isoformat()

    def record_submission(self, task_id: str, validation_result: Dict[str, Any]) -> None:
        """Record a submission attempt."""
        context = self._contexts.get(task_id)
        if context:
            context["submission_attempts"] += 1
            context["last_submission"] = {
                "timestamp": datetime.now().isoformat(),
                "result": validation_result
            }

    def record_escalation(self, task_id: str, reason: str) -> None:
        """Record an escalation to boss."""
        context = self._contexts.get(task_id)
        if context:
            context["escalations"].append({
                "timestamp": datetime.now().isoformat(),
                "reason": reason
            })

    def get_task_by_channel(self, channel_id: str) -> Optional[str]:
        """Get task ID from Discord channel/thread ID."""
        return self._channel_to_task.get(channel_id)

    def get_task_by_staff(self, staff_id: str) -> Optional[str]:
        """Get active task for a staff member."""
        return self._staff_active_task.get(staff_id)

    def set_staff_active_task(self, staff_id: str, task_id: str) -> None:
        """Set the active task for a staff member."""
        self._staff_active_task[staff_id] = task_id

    def link_channel_to_task(self, channel_id: str, task_id: str) -> None:
        """Link a Discord channel/thread to a task."""
        self._channel_to_task[channel_id] = task_id

    def close_context(self, task_id: str) -> None:
        """Close a task context (task completed/cancelled)."""
        context = self._contexts.get(task_id)
        if context:
            context["status"] = "closed"
            context["closed_at"] = datetime.now().isoformat()

            # Clean up mappings
            channel_id = context.get("channel_id")
            staff_id = context.get("staff_id")

            if channel_id and channel_id in self._channel_to_task:
                del self._channel_to_task[channel_id]

            if staff_id and self._staff_active_task.get(staff_id) == task_id:
                del self._staff_active_task[staff_id]

    def cleanup_old_contexts(self, hours: int = 72) -> int:
        """Remove contexts older than specified hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        to_remove = []

        for task_id, context in self._contexts.items():
            last_activity = datetime.fromisoformat(context.get("last_activity", context.get("created_at")))
            if last_activity < cutoff:
                to_remove.append(task_id)

        for task_id in to_remove:
            self.close_context(task_id)
            del self._contexts[task_id]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old task contexts")

        return len(to_remove)

    def get_all_active_contexts(self) -> Dict[str, Dict[str, Any]]:
        """Get all active task contexts."""
        return {
            task_id: context
            for task_id, context in self._contexts.items()
            if context.get("status") == "active"
        }

    def get_staff_tasks(self, staff_id: str) -> List[str]:
        """Get all tasks assigned to a staff member."""
        tasks = []
        for task_id, context in self._contexts.items():
            if context.get("staff_id") == staff_id and context.get("status") == "active":
                tasks.append(task_id)
        return tasks


# Singleton
_task_context_manager = None


def get_task_context_manager() -> TaskContextManager:
    global _task_context_manager
    if _task_context_manager is None:
        _task_context_manager = TaskContextManager()
    return _task_context_manager
