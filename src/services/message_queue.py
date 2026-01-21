"""
Message Queue Service - Handles retry logic for failed messages.

Features:
- Queue failed Discord/Telegram messages for retry
- Exponential backoff with configurable max retries
- Background worker for processing queue
- Persistence to database for durability

v2.0.5: Initial implementation
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json

from config import settings

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages that can be queued."""
    DISCORD_WEBHOOK = "discord_webhook"
    DISCORD_BOT = "discord_bot"
    TELEGRAM = "telegram"
    SHEETS_UPDATE = "sheets_update"


class MessageStatus(Enum):
    """Status of queued messages."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"  # Max retries exceeded


@dataclass
class QueuedMessage:
    """A message queued for sending or retry."""
    id: str
    message_type: MessageType
    payload: Dict[str, Any]
    status: MessageStatus = MessageStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MessageQueueService:
    """
    Manages message queue with retry logic.

    Features:
    - In-memory queue with optional database persistence
    - Exponential backoff for retries
    - Background worker for processing
    - Configurable retry policies
    """

    def __init__(self):
        # In-memory queue
        self._queue: Dict[str, QueuedMessage] = {}
        self._dead_letter: List[QueuedMessage] = []

        # Message handlers by type
        self._handlers: Dict[MessageType, Callable] = {}

        # Background worker
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

        # Configuration
        self.base_retry_delay_seconds = 30
        self.max_retry_delay_seconds = 3600  # 1 hour max
        self.worker_interval_seconds = 15

        # Database repository (lazy loaded)
        self._repo = None
        self._db_available = None

        # Counter for unique IDs
        self._counter = 0

    def _generate_id(self) -> str:
        """Generate a unique message ID."""
        self._counter += 1
        return f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._counter:04d}"

    # ==================== QUEUE OPERATIONS ====================

    async def enqueue(
        self,
        message_type: MessageType,
        payload: Dict[str, Any],
        max_retries: int = 3,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Add a message to the queue.

        Args:
            message_type: Type of message (discord, telegram, etc.)
            payload: Message payload (varies by type)
            max_retries: Maximum retry attempts
            metadata: Optional metadata for tracking

        Returns:
            Message ID
        """
        msg_id = self._generate_id()

        message = QueuedMessage(
            id=msg_id,
            message_type=message_type,
            payload=payload,
            max_retries=max_retries,
            metadata=metadata or {}
        )

        self._queue[msg_id] = message

        logger.debug(f"Enqueued message {msg_id} of type {message_type.value}")

        return msg_id

    async def enqueue_failed(
        self,
        message_type: MessageType,
        payload: Dict[str, Any],
        error: str,
        max_retries: int = 3,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Queue a message that already failed once (from external call).
        Sets up for first retry with exponential backoff.
        """
        msg_id = self._generate_id()

        # Calculate first retry time
        retry_delay = self.base_retry_delay_seconds
        next_retry = datetime.now() + timedelta(seconds=retry_delay)

        message = QueuedMessage(
            id=msg_id,
            message_type=message_type,
            payload=payload,
            max_retries=max_retries,
            retry_count=1,  # Already failed once
            next_retry_at=next_retry,
            last_error=error,
            metadata=metadata or {}
        )

        self._queue[msg_id] = message

        logger.info(f"Queued failed message {msg_id} for retry at {next_retry}")

        return msg_id

    def register_handler(self, message_type: MessageType, handler: Callable) -> None:
        """
        Register a handler function for a message type.

        Handler should be async and accept (payload: Dict) -> bool
        Returns True on success, False on failure.
        """
        self._handlers[message_type] = handler
        logger.debug(f"Registered handler for {message_type.value}")

    # ==================== PROCESSING ====================

    async def process_message(self, message: QueuedMessage) -> bool:
        """
        Process a single message.

        Returns True if successful, False if failed.
        """
        handler = self._handlers.get(message.message_type)
        if not handler:
            logger.error(f"No handler for message type {message.message_type.value}")
            return False

        message.status = MessageStatus.PROCESSING

        try:
            success = await handler(message.payload)

            if success:
                message.status = MessageStatus.COMPLETED
                logger.info(f"Successfully processed message {message.id}")
                return True
            else:
                raise Exception("Handler returned False")

        except Exception as e:
            message.last_error = str(e)
            message.retry_count += 1

            if message.retry_count >= message.max_retries:
                # Move to dead letter queue
                message.status = MessageStatus.DEAD_LETTER
                self._dead_letter.append(message)
                logger.error(f"Message {message.id} moved to dead letter queue after {message.retry_count} retries: {e}")
            else:
                # Schedule retry with exponential backoff
                delay = min(
                    self.base_retry_delay_seconds * (2 ** (message.retry_count - 1)),
                    self.max_retry_delay_seconds
                )
                message.next_retry_at = datetime.now() + timedelta(seconds=delay)
                message.status = MessageStatus.PENDING
                logger.warning(f"Message {message.id} retry #{message.retry_count} scheduled for {message.next_retry_at}: {e}")

            return False

    async def process_pending(self) -> int:
        """
        Process all pending messages that are ready for retry.

        Returns number of messages processed.
        """
        now = datetime.now()
        processed = 0

        # Get messages ready for processing
        ready_messages = [
            msg for msg in self._queue.values()
            if msg.status == MessageStatus.PENDING
            and (msg.next_retry_at is None or msg.next_retry_at <= now)
        ]

        for message in ready_messages:
            success = await self.process_message(message)

            if success or message.status == MessageStatus.DEAD_LETTER:
                # Remove from queue
                del self._queue[message.id]

            processed += 1

        if processed > 0:
            logger.info(f"Processed {processed} queued messages")

        return processed

    # ==================== BACKGROUND WORKER ====================

    async def start_worker(self) -> None:
        """Start the background worker for processing queued messages."""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Message queue worker started")

    async def stop_worker(self) -> None:
        """Stop the background worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Message queue worker stopped")

    async def _worker_loop(self) -> None:
        """Background worker loop."""
        while self._running:
            try:
                await self.process_pending()
            except Exception as e:
                logger.error(f"Error in message queue worker: {e}")

            await asyncio.sleep(self.worker_interval_seconds)

    # ==================== STATUS & MONITORING ====================

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get current queue statistics."""
        pending = sum(1 for m in self._queue.values() if m.status == MessageStatus.PENDING)
        processing = sum(1 for m in self._queue.values() if m.status == MessageStatus.PROCESSING)

        by_type = {}
        for msg in self._queue.values():
            msg_type = msg.message_type.value
            by_type[msg_type] = by_type.get(msg_type, 0) + 1

        return {
            "total_queued": len(self._queue),
            "pending": pending,
            "processing": processing,
            "dead_letter": len(self._dead_letter),
            "by_type": by_type,
            "worker_running": self._running,
        }

    def get_dead_letter_messages(self) -> List[Dict[str, Any]]:
        """Get messages in the dead letter queue."""
        return [
            {
                "id": msg.id,
                "type": msg.message_type.value,
                "created_at": msg.created_at.isoformat(),
                "retry_count": msg.retry_count,
                "last_error": msg.last_error,
                "payload_preview": str(msg.payload)[:200],
            }
            for msg in self._dead_letter
        ]

    async def retry_dead_letter(self, message_id: str) -> bool:
        """Manually retry a message from the dead letter queue."""
        for i, msg in enumerate(self._dead_letter):
            if msg.id == message_id:
                # Reset and re-queue
                msg.status = MessageStatus.PENDING
                msg.retry_count = 0
                msg.next_retry_at = None
                self._queue[msg.id] = msg
                del self._dead_letter[i]
                logger.info(f"Re-queued dead letter message {message_id}")
                return True
        return False


# Singleton
_message_queue: Optional[MessageQueueService] = None


def get_message_queue() -> MessageQueueService:
    """Get the message queue singleton."""
    global _message_queue
    if _message_queue is None:
        _message_queue = MessageQueueService()
    return _message_queue


# ==================== INTEGRATION HELPERS ====================

async def queue_discord_webhook_message(
    webhook_url: str,
    content: str = None,
    embeds: list = None,
    username: str = None
) -> str:
    """
    Convenience function to queue a Discord webhook message.

    Returns message ID for tracking.
    """
    queue = get_message_queue()
    return await queue.enqueue(
        message_type=MessageType.DISCORD_WEBHOOK,
        payload={
            "webhook_url": webhook_url,
            "content": content,
            "embeds": embeds,
            "username": username,
        },
        metadata={"destination": "discord"}
    )


async def queue_failed_discord_message(
    webhook_url: str,
    content: str = None,
    embeds: list = None,
    error: str = "Unknown error"
) -> str:
    """
    Queue a Discord message that failed for retry.

    Returns message ID for tracking.
    """
    queue = get_message_queue()
    return await queue.enqueue_failed(
        message_type=MessageType.DISCORD_WEBHOOK,
        payload={
            "webhook_url": webhook_url,
            "content": content,
            "embeds": embeds,
        },
        error=error,
        metadata={"destination": "discord", "failed_at": datetime.now().isoformat()}
    )
