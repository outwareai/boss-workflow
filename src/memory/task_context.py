"""
Task Context Manager - Per-task conversation history and context.

Stores and retrieves conversation history for each task, enabling
the Staff AI Assistant to have contextual conversations.

v2.0.4: Now persists to PostgreSQL database for durability across restarts.
Falls back to in-memory storage if database is unavailable.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import asyncio

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

    Uses PostgreSQL for persistence with in-memory cache for performance.
    """

    def __init__(self):
        # In-memory cache: {task_id: TaskContext}
        self._contexts: Dict[str, Dict[str, Any]] = {}
        # Map Discord thread/channel to task: {channel_id: task_id}
        self._channel_to_task: Dict[str, str] = {}
        # Map staff to their active task: {staff_id: task_id}
        self._staff_active_task: Dict[str, str] = {}
        # Database repository (lazy loaded)
        self._repo = None
        self._db_available = None

    def _get_repo(self):
        """Lazy load the repository."""
        if self._repo is None:
            try:
                from ..database.repositories import get_staff_context_repository
                self._repo = get_staff_context_repository()
                self._db_available = True
            except Exception as e:
                logger.warning(f"Database not available for staff context: {e}")
                self._db_available = False
        return self._repo

    async def _try_db_operation(self, operation, *args, **kwargs):
        """Try a database operation, return None on failure."""
        repo = self._get_repo()
        if not repo or not self._db_available:
            return None
        try:
            return await operation(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Database operation failed, using in-memory: {e}")
            return None

    def get_context(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the context for a task (from cache)."""
        return self._contexts.get(task_id)

    async def get_context_async(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get context with database fallback."""
        # Check cache first
        if task_id in self._contexts:
            return self._contexts[task_id]

        # Try database
        repo = self._get_repo()
        if repo and self._db_available:
            try:
                db_context = await repo.get_context(task_id)
                if db_context:
                    # Populate cache from database
                    context = {
                        "task_id": db_context.task_id,
                        "task_details": db_context.task_details or {},
                        "conversation_history": [],
                        "created_at": db_context.created_at.isoformat(),
                        "last_activity": db_context.last_activity.isoformat(),
                        "staff_id": db_context.staff_id,
                        "channel_id": db_context.channel_id,
                        "submission_attempts": db_context.submission_attempts,
                        "escalations": [],
                        "status": db_context.status,
                    }
                    # Load messages
                    if db_context.messages:
                        context["conversation_history"] = [
                            {
                                "role": msg.role,
                                "content": msg.content,
                                "timestamp": msg.timestamp.isoformat(),
                                "metadata": msg.metadata or {}
                            }
                            for msg in db_context.messages
                        ]
                    # Load escalations
                    if db_context.escalations:
                        context["escalations"] = [
                            {
                                "timestamp": esc.timestamp.isoformat(),
                                "reason": esc.reason
                            }
                            for esc in db_context.escalations
                        ]

                    # Update cache
                    self._contexts[task_id] = context
                    if db_context.channel_id:
                        self._channel_to_task[db_context.channel_id] = task_id
                    if db_context.thread_id:
                        self._channel_to_task[db_context.thread_id] = task_id
                    if db_context.staff_id:
                        self._staff_active_task[db_context.staff_id] = task_id

                    return context
            except Exception as e:
                logger.error(f"Error loading context from database: {e}")

        return None

    def create_context(
        self,
        task_id: str,
        task_details: Dict[str, Any],
        channel_id: str = None,
        staff_id: str = None
    ) -> Dict[str, Any]:
        """
        Create or update context for a task (sync version for compatibility).
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

        # Schedule async database save
        asyncio.create_task(self._save_context_to_db(task_id, context, channel_id, staff_id))

        logger.info(f"Created context for task {task_id}")
        return context

    async def _save_context_to_db(
        self,
        task_id: str,
        context: Dict[str, Any],
        channel_id: str = None,
        staff_id: str = None
    ):
        """Save context to database asynchronously."""
        repo = self._get_repo()
        if not repo or not self._db_available:
            return

        try:
            existing = await repo.get_context(task_id)
            if existing:
                # Update existing
                await repo.update_context(task_id, {
                    "task_details": context.get("task_details"),
                    "staff_id": staff_id,
                    "channel_id": channel_id,
                })
            else:
                # Create new
                await repo.create_context(
                    task_id=task_id,
                    task_details=context.get("task_details"),
                    staff_id=staff_id,
                    channel_id=channel_id,
                )
        except Exception as e:
            logger.error(f"Error saving context to database: {e}")

    def add_message(
        self,
        task_id: str,
        role: str,  # "staff", "assistant", or "boss"
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

        # Schedule async database save
        asyncio.create_task(self._save_message_to_db(task_id, role, content, metadata))

    async def _save_message_to_db(
        self,
        task_id: str,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ):
        """Save message to database asynchronously."""
        repo = self._get_repo()
        if not repo or not self._db_available:
            return

        try:
            await repo.add_message(task_id, role, content, metadata)
        except Exception as e:
            logger.error(f"Error saving message to database: {e}")

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

    async def update_context_async(self, task_id: str, context_updates: Dict[str, Any]) -> bool:
        """Update context with arbitrary updates."""
        context = self._contexts.get(task_id)
        if context:
            context.update(context_updates)
            context["last_activity"] = datetime.now().isoformat()

            # Save to database
            repo = self._get_repo()
            if repo and self._db_available:
                try:
                    await repo.update_context(task_id, context_updates)
                except Exception as e:
                    logger.error(f"Error updating context in database: {e}")

            return True
        return False

    def record_submission(self, task_id: str, validation_result: Dict[str, Any]) -> None:
        """Record a submission attempt."""
        context = self._contexts.get(task_id)
        if context:
            context["submission_attempts"] += 1
            context["last_submission"] = {
                "timestamp": datetime.now().isoformat(),
                "result": validation_result
            }

            # Schedule async database save
            asyncio.create_task(self._save_submission_to_db(task_id, validation_result))

    async def _save_submission_to_db(self, task_id: str, validation_result: Dict[str, Any]):
        """Save submission to database asynchronously."""
        repo = self._get_repo()
        if not repo or not self._db_available:
            return
        try:
            await repo.record_submission(task_id, validation_result)
        except Exception as e:
            logger.error(f"Error saving submission to database: {e}")

    def record_escalation(self, task_id: str, reason: str) -> None:
        """Record an escalation to boss."""
        context = self._contexts.get(task_id)
        if context:
            context["escalations"].append({
                "timestamp": datetime.now().isoformat(),
                "reason": reason
            })

    async def record_escalation_async(
        self,
        task_id: str,
        reason: str,
        staff_message: str = None,
        message_url: str = None,
        telegram_message_id: str = None
    ) -> Optional[int]:
        """Record escalation with database persistence. Returns escalation ID."""
        # Update in-memory
        context = self._contexts.get(task_id)
        if context:
            context["escalations"].append({
                "timestamp": datetime.now().isoformat(),
                "reason": reason
            })

        # Save to database
        repo = self._get_repo()
        if repo and self._db_available:
            try:
                escalation = await repo.record_escalation(
                    task_id=task_id,
                    reason=reason,
                    staff_message=staff_message,
                    message_url=message_url,
                    telegram_message_id=telegram_message_id
                )
                return escalation.id if escalation else None
            except Exception as e:
                logger.error(f"Error saving escalation to database: {e}")
        return None

    def get_task_by_channel(self, channel_id: str) -> Optional[str]:
        """Get task ID from Discord channel/thread ID."""
        return self._channel_to_task.get(channel_id)

    async def get_task_by_channel_async(self, channel_id: str) -> Optional[str]:
        """Get task ID from Discord channel/thread ID with database lookup."""
        # Check cache first
        if channel_id in self._channel_to_task:
            return self._channel_to_task[channel_id]

        # Try database for thread links
        repo = self._get_repo()
        if repo and self._db_available:
            try:
                task_id = await repo.get_task_by_thread(channel_id)
                if task_id:
                    self._channel_to_task[channel_id] = task_id
                    return task_id
            except Exception as e:
                logger.error(f"Error looking up thread link: {e}")

        return None

    def get_task_by_staff(self, staff_id: str) -> Optional[str]:
        """Get active task for a staff member."""
        return self._staff_active_task.get(staff_id)

    async def get_task_by_staff_async(self, staff_id: str) -> Optional[str]:
        """Get active task for a staff member with database lookup."""
        # Check cache first
        if staff_id in self._staff_active_task:
            return self._staff_active_task[staff_id]

        # Try database
        repo = self._get_repo()
        if repo and self._db_available:
            try:
                context = await repo.get_context_by_staff(staff_id)
                if context:
                    self._staff_active_task[staff_id] = context.task_id
                    return context.task_id
            except Exception as e:
                logger.error(f"Error looking up staff context: {e}")

        return None

    def set_staff_active_task(self, staff_id: str, task_id: str) -> None:
        """Set the active task for a staff member."""
        self._staff_active_task[staff_id] = task_id

    def link_channel_to_task(self, channel_id: str, task_id: str) -> None:
        """Link a Discord channel/thread to a task."""
        self._channel_to_task[channel_id] = task_id

    async def link_thread_to_task(
        self,
        thread_id: str,
        task_id: str,
        channel_id: str,
        message_id: str = None
    ) -> None:
        """Link a Discord thread to a task with database persistence."""
        # Update in-memory
        self._channel_to_task[thread_id] = task_id

        # Save to database
        repo = self._get_repo()
        if repo and self._db_available:
            try:
                await repo.link_thread_to_task(
                    thread_id=thread_id,
                    task_id=task_id,
                    channel_id=channel_id,
                    message_id=message_id
                )
            except Exception as e:
                logger.error(f"Error linking thread to task: {e}")

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

            # Schedule async database save
            asyncio.create_task(self._close_context_in_db(task_id))

    async def _close_context_in_db(self, task_id: str):
        """Close context in database asynchronously."""
        repo = self._get_repo()
        if not repo or not self._db_available:
            return
        try:
            await repo.close_context(task_id)
        except Exception as e:
            logger.error(f"Error closing context in database: {e}")

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

        # Also cleanup database
        asyncio.create_task(self._cleanup_db_contexts(hours))

        return len(to_remove)

    async def _cleanup_db_contexts(self, hours: int):
        """Cleanup old contexts in database."""
        repo = self._get_repo()
        if not repo or not self._db_available:
            return
        try:
            await repo.cleanup_old_contexts(hours)
        except Exception as e:
            logger.error(f"Error cleaning up database contexts: {e}")

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

    # ==================== BOSS REPLY ROUTING ====================

    async def get_pending_escalation_by_telegram(
        self,
        telegram_message_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get pending escalation by Telegram message ID for boss reply routing."""
        repo = self._get_repo()
        if not repo or not self._db_available:
            return None

        try:
            escalation = await repo.get_pending_escalation_by_telegram(telegram_message_id)
            if escalation:
                return {
                    "id": escalation.id,
                    "task_id": escalation.context.task_id,
                    "staff_id": escalation.context.staff_id,
                    "channel_id": escalation.context.channel_id,
                    "thread_id": escalation.context.thread_id,
                    "reason": escalation.reason,
                    "staff_message": escalation.staff_message,
                }
            return None
        except Exception as e:
            logger.error(f"Error getting escalation by telegram ID: {e}")
            return None

    async def mark_escalation_responded(
        self,
        escalation_id: int,
        boss_response: str
    ) -> bool:
        """Mark an escalation as responded to."""
        repo = self._get_repo()
        if not repo or not self._db_available:
            return False

        try:
            return await repo.mark_escalation_responded(escalation_id, boss_response)
        except Exception as e:
            logger.error(f"Error marking escalation responded: {e}")
            return False


# Singleton
_task_context_manager = None


def get_task_context_manager() -> TaskContextManager:
    global _task_context_manager
    if _task_context_manager is None:
        _task_context_manager = TaskContextManager()
    return _task_context_manager
