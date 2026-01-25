"""
Timeout handler for planning sessions with auto-save.

GROUP 3 Phase 7: Enhanced Multi-Turn Planning Sessions

Features:
- 30-minute inactivity timeout
- Auto-save sessions on timeout
- Telegram notifications
- Graceful timer cancellation
"""

import asyncio
import logging
from typing import Dict, Optional, TYPE_CHECKING
from datetime import datetime

from src.bot.planning_session_manager import get_planning_session_manager

if TYPE_CHECKING:
    from src.bot.telegram_simple import TelegramBotSimple as TelegramClient
else:
    TelegramClient = None

logger = logging.getLogger(__name__)


class SessionTimeoutHandler:
    """Monitor and auto-save planning sessions on timeout."""

    def __init__(
        self,
        telegram_client,
        timeout_minutes: int = 30
    ):
        """
        Initialize timeout handler.

        Args:
            telegram_client: Telegram bot client for notifications
            timeout_minutes: Inactivity timeout in minutes (default: 30)
        """
        self.telegram = telegram_client
        self.timeout_minutes = timeout_minutes
        self.timeout_seconds = timeout_minutes * 60
        self.active_timers: Dict[str, asyncio.Task] = {}

    def start_timeout_timer(
        self,
        session_id: str,
        user_id: str,
        chat_id: str
    ):
        """
        Start 30-minute timeout timer for a session.

        Args:
            session_id: Planning session ID
            user_id: User ID (for logging)
            chat_id: Telegram chat ID for notifications
        """
        # Cancel existing timer if any
        self.cancel_timeout_timer(session_id)

        # Create new timer task
        timer_task = asyncio.create_task(
            self._timeout_task(session_id, user_id, chat_id)
        )
        self.active_timers[session_id] = timer_task

        logger.info(
            f"Started {self.timeout_minutes}min timeout timer for session {session_id}"
        )

    def reset_timeout_timer(
        self,
        session_id: str,
        user_id: str,
        chat_id: str
    ):
        """
        Reset timer on user activity.

        Args:
            session_id: Planning session ID
            user_id: User ID
            chat_id: Telegram chat ID
        """
        # Simply restart the timer
        self.start_timeout_timer(session_id, user_id, chat_id)
        logger.debug(f"Reset timeout timer for session {session_id}")

    def cancel_timeout_timer(self, session_id: str):
        """
        Cancel timeout timer when session completes or is cancelled.

        Args:
            session_id: Planning session ID
        """
        if session_id in self.active_timers:
            task = self.active_timers[session_id]

            # Cancel the task
            if not task.done():
                task.cancel()

            # Remove from active timers
            del self.active_timers[session_id]

            logger.info(f"Cancelled timeout timer for session {session_id}")

    async def _timeout_task(
        self,
        session_id: str,
        user_id: str,
        chat_id: str
    ):
        """
        Background task: auto-save session after inactivity.

        Args:
            session_id: Planning session ID
            user_id: User ID
            chat_id: Telegram chat ID for notification
        """
        try:
            # Sleep for timeout duration
            logger.debug(
                f"Timeout timer started for session {session_id} "
                f"({self.timeout_minutes} minutes)"
            )

            await asyncio.sleep(self.timeout_seconds)

            # Timeout reached - auto-save session
            logger.info(
                f"Session {session_id} timed out after {self.timeout_minutes} minutes"
            )

            # Get session manager
            from src.ai.deepseek import get_deepseek_client
            ai_client = get_deepseek_client()
            session_manager = get_planning_session_manager(ai_client)

            # Save session snapshot
            save_result = await session_manager.save_session_snapshot(session_id)

            if save_result.get("success"):
                # Send Telegram notification
                message = (
                    f"⏰ **Planning Session Auto-Saved**\n\n"
                    f"Your planning session was inactive for {self.timeout_minutes} minutes, "
                    f"so I've saved it for later.\n\n"
                    f"Session ID: `{session_id}`\n\n"
                    f"Use `/resume` or `/resume {session_id}` to continue anytime!"
                )

                try:
                    await self.telegram.send_message(
                        chat_id,
                        message,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Failed to send timeout notification: {e}")

                logger.info(f"Auto-saved session {session_id} and notified user")
            else:
                logger.error(
                    f"Failed to auto-save session {session_id}: "
                    f"{save_result.get('error')}"
                )

            # Remove from active timers
            if session_id in self.active_timers:
                del self.active_timers[session_id]

        except asyncio.CancelledError:
            # Timer was cancelled (session completed or user was active)
            logger.debug(f"Timeout timer cancelled for session {session_id}")
        except Exception as e:
            logger.error(
                f"Error in timeout task for session {session_id}: {e}",
                exc_info=True
            )

    def get_active_timer_count(self) -> int:
        """
        Get count of active timeout timers.

        Returns:
            Number of active timers
        """
        return len(self.active_timers)

    def get_session_timer_status(self, session_id: str) -> Optional[str]:
        """
        Get status of timeout timer for a session.

        Args:
            session_id: Planning session ID

        Returns:
            "active", "completed", or None if no timer
        """
        if session_id not in self.active_timers:
            return None

        task = self.active_timers[session_id]

        if task.done():
            return "completed"
        else:
            return "active"

    async def cleanup_completed_timers(self):
        """Remove completed timer tasks from tracking."""
        completed_sessions = [
            session_id
            for session_id, task in self.active_timers.items()
            if task.done()
        ]

        for session_id in completed_sessions:
            del self.active_timers[session_id]

        if completed_sessions:
            logger.info(f"Cleaned up {len(completed_sessions)} completed timers")

    async def cancel_all_timers(self):
        """Cancel all active timers (for shutdown)."""
        session_ids = list(self.active_timers.keys())

        for session_id in session_ids:
            self.cancel_timeout_timer(session_id)

        logger.info(f"Cancelled all timeout timers ({len(session_ids)} total)")


# Global instance
_timeout_handler: Optional[SessionTimeoutHandler] = None


def get_timeout_handler(
    telegram_client,
    timeout_minutes: int = 30
) -> SessionTimeoutHandler:
    """
    Get or create timeout handler singleton.

    Args:
        telegram_client: Telegram bot client
        timeout_minutes: Timeout duration in minutes

    Returns:
        SessionTimeoutHandler instance
    """
    global _timeout_handler
    if _timeout_handler is None:
        _timeout_handler = SessionTimeoutHandler(
            telegram_client,
            timeout_minutes
        )
    return _timeout_handler
