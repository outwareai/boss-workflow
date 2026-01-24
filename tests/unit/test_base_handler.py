"""
Unit tests for BaseHandler.

Q1 2026: Test base handler functionality.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from src.bot.base_handler import BaseHandler
from telegram import Update, User, Message


class TestHandler(BaseHandler):
    """Concrete implementation for testing."""

    async def can_handle(self, message: str, user_id: str, **kwargs) -> bool:
        return "test" in message.lower()

    async def handle(self, update: Update, context) -> None:
        await self.send_success(update, "Test handled")


@pytest.fixture
def handler():
    """Create test handler."""
    with patch('src.bot.base_handler.get_session_manager'), \
         patch('src.bot.base_handler.get_task_repository'), \
         patch('src.bot.base_handler.get_team_repository'), \
         patch('src.bot.base_handler.get_conversation_repository'), \
         patch('src.bot.base_handler.get_audit_repository'), \
         patch('src.bot.base_handler.get_sheets_integration'), \
         patch('src.bot.base_handler.get_discord_integration'), \
         patch('src.bot.base_handler.get_preferences_manager'):
        return TestHandler()


@pytest.fixture
def mock_update():
    """Create mock Telegram update."""
    user = Mock(spec=User)
    user.id = 12345
    user.username = "testuser"
    user.first_name = "Test"
    user.last_name = "User"
    user.full_name = "Test User"

    message = Mock(spec=Message)
    message.text = "test message"
    message.reply_text = AsyncMock()

    update = Mock(spec=Update)
    update.effective_user = user
    update.message = message

    return update


@pytest.mark.asyncio
async def test_can_handle(handler):
    """Test can_handle method."""
    assert await handler.can_handle("This is a test", "123") == True
    assert await handler.can_handle("No match", "123") == False


@pytest.mark.asyncio
async def test_get_user_info(handler, mock_update):
    """Test extracting user info."""
    user_info = await handler.get_user_info(mock_update)

    assert user_info["user_id"] == "12345"
    assert user_info["username"] == "testuser"
    assert user_info["first_name"] == "Test"
    assert user_info["full_name"] == "Test User"


@pytest.mark.asyncio
async def test_send_message(handler, mock_update):
    """Test sending messages."""
    await handler.send_message(mock_update, "Test message")
    mock_update.message.reply_text.assert_called_once_with("Test message", parse_mode="Markdown")


@pytest.mark.asyncio
async def test_send_error(handler, mock_update):
    """Test sending error messages."""
    await handler.send_error(mock_update, "Something went wrong")
    mock_update.message.reply_text.assert_called_once_with("❌ Error: Something went wrong")


@pytest.mark.asyncio
async def test_send_success(handler, mock_update):
    """Test sending success messages."""
    await handler.send_success(mock_update, "Operation complete")
    mock_update.message.reply_text.assert_called_once_with("✅ Operation complete")


def test_format_task(handler):
    """Test task formatting."""
    task = {
        "title": "Test Task",
        "task_id": "TASK-001",
        "status": "pending",
        "priority": "high",
        "assignee": "John Doe",
    }

    formatted = handler.format_task(task)

    assert "Test Task" in formatted
    assert "TASK-001" in formatted
    assert "pending" in formatted
    assert "high" in formatted
    assert "John Doe" in formatted


def test_truncate(handler):
    """Test text truncation."""
    short = "Short text"
    assert handler.truncate(short, 20) == "Short text"

    long = "This is a very long text that should be truncated"
    truncated = handler.truncate(long, 20)
    assert len(truncated) == 20
    assert truncated.endswith("...")


@pytest.mark.asyncio
async def test_is_boss(handler):
    """Test boss detection."""
    with patch('config.settings.get_settings') as mock_settings:
        mock_settings.return_value = Mock(telegram_boss_chat_id="999")

        # Boss user
        assert await handler.is_boss("999") == True

        # Non-boss user
        assert await handler.is_boss("123") == False


@pytest.mark.asyncio
async def test_get_user_permissions(handler):
    """Test user permissions."""
    # Mock is_boss
    handler.is_boss = AsyncMock(return_value=True)

    # Mock team_repo
    handler.team_repo = Mock()
    handler.team_repo.get_by_telegram_id = AsyncMock(return_value=None)

    # Test boss permissions
    perms = await handler.get_user_permissions("999")

    assert perms["is_boss"] == True
    assert perms["can_create_tasks"] == True
    assert perms["can_approve_tasks"] == True
    assert perms["can_manage_team"] == True


@pytest.mark.asyncio
async def test_session_management(handler):
    """Test session get/set/clear."""
    # Mock session manager
    handler.session_manager = Mock()
    handler.session_manager.get_validation_session = AsyncMock(return_value={"key": "value"})
    handler.session_manager.set_validation_session = AsyncMock(return_value=True)
    handler.session_manager.clear_validation_session = AsyncMock(return_value=True)

    # Test get
    session = await handler.get_session("validation", "user123")
    assert session == {"key": "value"}
    handler.session_manager.get_validation_session.assert_called_once_with("user123")

    # Test set
    result = await handler.set_session("validation", "user123", {"data": "test"}, 600)
    assert result == True
    handler.session_manager.set_validation_session.assert_called_once_with("user123", {"data": "test"}, 600)

    # Test clear
    result = await handler.clear_session("validation", "user123")
    assert result == True
    handler.session_manager.clear_validation_session.assert_called_once_with("user123")


@pytest.mark.asyncio
async def test_log_action(handler):
    """Test audit logging."""
    # Mock audit_repo
    handler.audit_repo = Mock()
    handler.audit_repo.create = AsyncMock(return_value={"id": 1})

    # Log an action
    await handler.log_action("test_action", "user123", {"detail": "test"})

    # Verify call
    handler.audit_repo.create.assert_called_once()
    call_args = handler.audit_repo.create.call_args[0][0]
    assert call_args["action"] == "test_action"
    assert call_args["user_id"] == "user123"
    assert call_args["details"]["detail"] == "test"
    assert call_args["source"] == "TestHandler"
