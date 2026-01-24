"""
Unit tests for RoutingHandler.

Q1 2026: Task #4.4 - Routing and delegation tests.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.bot.handlers.routing_handler import RoutingHandler
from src.bot.base_handler import BaseHandler
from src.ai.intent import UserIntent


class MockHandler(BaseHandler):
    """Mock handler for testing."""

    def __init__(self, name: str, pattern: str):
        super().__init__()
        self.name = name
        self.pattern = pattern
        self.handled = False

    async def can_handle(self, message: str, user_id: str, **kwargs) -> bool:
        return self.pattern in message.lower()

    async def handle(self, update, context) -> None:
        self.handled = True


@pytest.fixture
def router():
    """Create routing handler."""
    return RoutingHandler()


@pytest.fixture
def mock_handlers():
    """Create mock specialized handlers."""
    return [
        MockHandler("ValidationHandler", "approve"),
        MockHandler("QueryHandler", "status"),
        MockHandler("TaskCreationHandler", "create task"),
    ]


@pytest.mark.asyncio
async def test_register_handler(router, mock_handlers):
    """Test registering handlers."""
    for handler in mock_handlers:
        router.register_handler(handler)

    assert len(router.handlers) == 3


@pytest.mark.asyncio
async def test_route_to_matching_handler(router, mock_handlers):
    """Test routing to handler that matches."""
    for handler in mock_handlers:
        router.register_handler(handler)

    # Create mock update
    from telegram import Update, User, Message, Chat

    user = Mock(spec=User)
    user.id = 123
    user.username = "test"
    user.first_name = "Test"
    user.last_name = "User"
    user.full_name = "Test User"

    chat = Mock(spec=Chat)
    chat.id = 123

    message = Mock(spec=Message)
    message.text = "check status please"
    message.reply_text = AsyncMock()
    message.chat = chat

    update = Mock(spec=Update)
    update.effective_user = user
    update.message = message

    context = Mock()

    # Route message
    await router.handle(update, context)

    # Verify QueryHandler was called
    assert mock_handlers[1].handled == True
    assert mock_handlers[0].handled == False  # ValidationHandler not called
    assert mock_handlers[2].handled == False  # TaskCreationHandler not called


@pytest.mark.asyncio
async def test_is_command(router):
    """Test command detection."""
    assert router.is_command("/approve TASK-001") == True
    assert router.is_command("/status") == True
    assert router.is_command("normal message") == False


@pytest.mark.asyncio
async def test_extract_command(router):
    """Test command extraction."""
    cmd, args = router.extract_command("/approve TASK-001")
    assert cmd == "approve"
    assert args == "TASK-001"

    cmd, args = router.extract_command("/status")
    assert cmd == "status"
    assert args == ""


@pytest.mark.asyncio
async def test_active_handler_session(router, mock_handlers):
    """Test active handler session tracking."""
    # Register the first handler (ValidationHandler mock)
    router.register_handler(mock_handlers[0])

    # Mock session manager methods
    router.session_manager.set_active_handler_session = AsyncMock(return_value=True)
    router.session_manager.get_active_handler_session = AsyncMock(
        return_value={"handler_name": "MockHandler"}  # Use MockHandler, not ValidationHandler
    )
    router.session_manager.clear_active_handler_session = AsyncMock(return_value=True)

    # Set active handler
    await router.set_active_handler("user123", mock_handlers[0])

    # Verify session was set
    router.session_manager.set_active_handler_session.assert_called_once()

    # Get active handler
    active = await router._get_active_handler("user123")
    assert active is not None
    assert active.__class__.__name__ == "MockHandler"

    # Clear active handler
    await router.clear_active_handler("user123")
    router.session_manager.clear_active_handler_session.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_to_ai_intent(router):
    """Test fallback to AI intent detection when no handler matches."""
    # Create mock update for unknown message
    from telegram import Update, User, Message, Chat

    user = Mock(spec=User)
    user.id = 123
    user.username = "test"
    user.first_name = "Test"
    user.last_name = "User"
    user.full_name = "Test User"

    chat = Mock(spec=Chat)
    chat.id = 123

    message = Mock(spec=Message)
    message.text = "hello there"  # No handler matches this
    message.reply_text = AsyncMock()
    message.chat = chat

    update = Mock(spec=Update)
    update.effective_user = user
    update.message = message

    context = Mock()

    # Mock get_user_permissions to avoid database call
    with patch.object(
        router,
        'get_user_permissions',
        new_callable=AsyncMock,
        return_value={"is_boss": False}
    ):
        # Mock AI intent detection
        with patch.object(
            router.intent_detector,
            'detect_intent',
            new_callable=AsyncMock,
            return_value=(UserIntent.GREETING, {})
        ):
            await router.handle(update, context)

            # Verify reply was sent
            message.reply_text.assert_called_once()
            call_args = message.reply_text.call_args
            assert "Hello" in call_args[0][0] or "Hello" in str(call_args)


@pytest.mark.asyncio
async def test_can_handle_always_true(router):
    """Test that router always accepts messages."""
    result = await router.can_handle("any message", "user123")
    assert result == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
