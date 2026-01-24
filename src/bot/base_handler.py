"""
Base handler for all bot message handlers.

Provides common functionality for session management, logging,
permissions, and integration access.

Q1 2026: Foundation for handler refactoring (Task #4).
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..database.repositories import (
    get_task_repository,
    get_team_repository,
    get_conversation_repository,
    get_audit_repository,
)
from ..integrations.sheets import get_sheets_integration
from ..integrations.discord import get_discord_integration
from ..memory.preferences import get_preferences_manager
from .session_manager import get_session_manager


logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    """
    Abstract base class for all message handlers.

    Provides:
    - Session management (via SessionManager)
    - Repository access (tasks, team, conversations, audit)
    - Integration access (Sheets, Discord)
    - User preferences
    - Common utilities (logging, permissions, formatting)

    Subclasses must implement:
    - can_handle(message) -> bool
    - handle(update, context) -> None
    """

    def __init__(self):
        """Initialize base handler with all dependencies."""
        # Session management
        self.session_manager = get_session_manager()

        # Repositories
        self.task_repo = get_task_repository()
        self.team_repo = get_team_repository()
        self.conversation_repo = get_conversation_repository()
        self.audit_repo = get_audit_repository()

        # Integrations
        self.sheets = get_sheets_integration()
        self.discord = get_discord_integration()

        # Preferences
        self.preferences = get_preferences_manager()

        # Logger for this handler
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def can_handle(self, message: str, user_id: str, **kwargs) -> bool:
        """
        Determine if this handler can process the message.

        Args:
            message: The message text
            user_id: User ID who sent the message
            **kwargs: Additional context (update, context, etc.)

        Returns:
            True if this handler should process the message
        """
        pass

    @abstractmethod
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Process the message.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        pass

    # ==================== SESSION MANAGEMENT ====================

    async def get_session(self, session_type: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user session data."""
        method_map = {
            "validation": self.session_manager.get_validation_session,
            "pending_validation": self.session_manager.get_pending_validation,
            "review": self.session_manager.get_pending_review,
            "action": self.session_manager.get_pending_action,
            "batch": self.session_manager.get_batch_task,
            "spec": self.session_manager.get_spec_session,
            "message": self.session_manager.get_recent_message,
            "active_handler": self.session_manager.get_active_handler_session,
        }
        method = method_map.get(session_type)
        if method:
            return await method(user_id)
        return None

    async def set_session(self, session_type: str, user_id: str, data: Dict[str, Any], ttl: int = 3600) -> bool:
        """Set user session data."""
        method_map = {
            "validation": self.session_manager.set_validation_session,
            "pending_validation": self.session_manager.add_pending_validation,
            "review": self.session_manager.set_pending_review,
            "action": self.session_manager.set_pending_action,
            "batch": self.session_manager.set_batch_task,
            "spec": self.session_manager.set_spec_session,
            "message": self.session_manager.set_recent_message,
            "active_handler": self.session_manager.set_active_handler_session,
        }
        method = method_map.get(session_type)
        if method:
            return await method(user_id, data, ttl)
        return False

    async def clear_session(self, session_type: str, user_id: str) -> bool:
        """Clear user session data."""
        method_map = {
            "validation": self.session_manager.clear_validation_session,
            "pending_validation": self.session_manager.remove_pending_validation,
            "review": self.session_manager.clear_pending_review,
            "action": self.session_manager.clear_pending_action,
            "batch": self.session_manager.clear_batch_task,
            "spec": self.session_manager.clear_spec_session,
            "message": self.session_manager.clear_recent_message,
            "active_handler": self.session_manager.clear_active_handler_session,
        }
        method = method_map.get(session_type)
        if method:
            return await method(user_id)
        return False

    # ==================== USER CONTEXT ====================

    async def get_user_info(self, update: Update) -> Dict[str, Any]:
        """Extract user information from update."""
        user = update.effective_user
        return {
            "user_id": str(user.id),
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
        }

    async def is_boss(self, user_id: str) -> bool:
        """Check if user is the boss."""
        from config.settings import get_settings
        settings = get_settings()
        return user_id == str(settings.telegram_boss_chat_id)

    async def get_user_permissions(self, user_id: str) -> Dict[str, bool]:
        """Get user permissions."""
        # Check if boss
        is_boss = await self.is_boss(user_id)

        # Get team member info
        team_member = await self.team_repo.get_by_telegram_id(user_id)

        return {
            "is_boss": is_boss,
            "is_team_member": team_member is not None,
            "can_create_tasks": is_boss,
            "can_approve_tasks": is_boss,
            "can_manage_team": is_boss,
            "can_submit_work": team_member is not None,
        }

    # ==================== LOGGING & AUDIT ====================

    async def log_action(self, action: str, user_id: str, details: Dict[str, Any]):
        """Log user action to audit trail."""
        try:
            await self.audit_repo.create({
                "action": action,
                "user_id": user_id,
                "details": details,
                "source": self.__class__.__name__,
            })
        except Exception as e:
            self.logger.error(f"Failed to log action: {e}")

    # ==================== RESPONSE HELPERS ====================

    async def send_message(self, update: Update, text: str, parse_mode: str = "Markdown"):
        """Send a message to the user."""
        await update.message.reply_text(text, parse_mode=parse_mode)

    async def send_error(self, update: Update, error: str):
        """Send an error message to the user."""
        await update.message.reply_text(f"❌ Error: {error}")

    async def send_success(self, update: Update, message: str):
        """Send a success message to the user."""
        await update.message.reply_text(f"✅ {message}")

    # ==================== FORMATTING HELPERS ====================

    def format_task(self, task: Dict[str, Any]) -> str:
        """Format task for display."""
        return f"""
📋 **{task.get('title', 'Untitled')}**
ID: `{task.get('task_id', 'N/A')}`
Status: {task.get('status', 'unknown')}
Priority: {task.get('priority', 'medium')}
Assignee: {task.get('assignee', 'Unassigned')}
""".strip()

    def truncate(self, text: str, max_length: int = 100) -> str:
        """Truncate text with ellipsis."""
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + "..."
