"""
Safe background task execution with error handling.

Prevents silent failures by:
- Logging all errors with stack traces
- Sending system alerts to boss
- Tracking task references to prevent GC
"""

import asyncio
import logging
from typing import Coroutine, Any

logger = logging.getLogger(__name__)

# Track active tasks to prevent garbage collection
_active_background_tasks: set = set()


async def safe_background_task(coro: Coroutine, task_name: str) -> Any:
    """
    Wrapper for background tasks with error handling.

    Args:
        coro: Coroutine to execute
        task_name: Human-readable task name for logging

    Returns:
        Result of the coroutine if successful, None on error
    """
    try:
        result = await coro
        logger.info(f"✓ Background task completed: {task_name}")
        return result
    except Exception as e:
        logger.error(
            f"✗ Background task failed: {task_name} - {e}",
            exc_info=True
        )

        # Send system alert for critical failures
        try:
            from ..bot.telegram_simple import get_telegram_bot_simple
            from ..config.settings import settings

            telegram_bot = get_telegram_bot_simple()
            await telegram_bot.send_message(
                chat_id=settings.telegram_boss_chat_id,
                text=f"⚠️ **Background Task Failed**\n\n"
                     f"Task: {task_name}\n\n"
                     f"Error: {str(e)[:200]}"
            )
        except Exception as notify_error:
            logger.error(
                f"Could not send alert for {task_name}: {notify_error}"
            )

        return None


def create_safe_task(coro: Coroutine, task_name: str) -> asyncio.Task:
    """
    Create a background task with error handling.

    Args:
        coro: Coroutine to execute
        task_name: Human-readable task name

    Returns:
        asyncio.Task object

    Example:
        task = create_safe_task(
            process_webhook(update_data),
            "webhook-telegram-12345"
        )
    """
    task = asyncio.create_task(
        safe_background_task(coro, task_name)
    )

    # Store reference to prevent garbage collection
    _active_background_tasks.add(task)

    # Remove from tracking when done
    task.add_done_callback(_active_background_tasks.discard)

    logger.debug(f"Created safe background task: {task_name}")
    return task
