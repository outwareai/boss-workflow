"""
Unit tests for CommandHandler.

Q1 2026: Task #4.6 Part 2 tests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.bot.handlers.command_handler import CommandHandler


@pytest.fixture
def handler():
    """Create CommandHandler instance."""
    return CommandHandler()


@pytest.fixture
def mock_update():
    """Create mock Telegram Update."""
    update = MagicMock()
    update.message.text = "/help"
    update.effective_user.id = "123456"
    update.effective_user.first_name = "TestUser"
    update.effective_user.username = "testuser"
    return update


@pytest.fixture
def mock_context():
    """Create mock Telegram Context."""
    return MagicMock()


class TestCommandHandler:
    """Test CommandHandler functionality."""

    @pytest.mark.asyncio
    async def test_can_handle_slash_command(self, handler):
        """Test detection of slash commands."""
        result = await handler.can_handle("/help", "123")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_handle_command_with_args(self, handler):
        """Test detection of commands with arguments."""
        result = await handler.can_handle("/task create new task", "123")
        assert result is True

    @pytest.mark.asyncio
    async def test_cannot_handle_non_command(self, handler):
        """Test rejection of non-command messages."""
        result = await handler.can_handle("not a command", "123")
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_unknown_command(self, handler, mock_update, mock_context):
        """Test handling of unknown commands."""
        mock_update.message.text = "/unknown"
        handler.send_error = AsyncMock()

        await handler.handle(mock_update, mock_context)

        handler.send_error.assert_called_once()
        assert "Unknown command" in handler.send_error.call_args[0][1]

    @pytest.mark.asyncio
    async def test_cmd_start(self, handler, mock_update, mock_context):
        """Test /start command."""
        handler.send_message = AsyncMock()

        await handler._cmd_start(mock_update, mock_context, "")

        handler.send_message.assert_called_once()
        assert "Welcome to Boss Workflow" in handler.send_message.call_args[0][1]

    @pytest.mark.asyncio
    async def test_cmd_help(self, handler, mock_update, mock_context):
        """Test /help command."""
        handler.send_message = AsyncMock()

        await handler._cmd_help(mock_update, mock_context, "")

        handler.send_message.assert_called_once()
        assert "Available Commands" in handler.send_message.call_args[0][1]

    @pytest.mark.asyncio
    async def test_cmd_cancel(self, handler, mock_update, mock_context):
        """Test /cancel command."""
        handler.get_user_info = AsyncMock(return_value={
            "user_id": "123",
            "first_name": "Test"
        })
        handler.clear_session = AsyncMock()
        handler.send_message = AsyncMock()

        await handler._cmd_cancel(mock_update, mock_context, "")

        assert handler.clear_session.call_count == 2
        handler.send_message.assert_called_once()
        assert "Cancelled" in handler.send_message.call_args[0][1]

    @pytest.mark.asyncio
    async def test_cmd_status_with_task_id(self, handler, mock_update, mock_context):
        """Test /status with task ID."""
        mock_task = MagicMock(status="in_progress", assignee="John")
        handler.task_repo.get_by_id = AsyncMock(return_value=mock_task)
        handler.send_message = AsyncMock()

        await handler._cmd_status(mock_update, mock_context, "TASK-001")

        handler.task_repo.get_by_id.assert_called_once_with("TASK-001")
        handler.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_status_task_not_found(self, handler, mock_update, mock_context):
        """Test /status when task doesn't exist."""
        handler.task_repo.get_by_id = AsyncMock(return_value=None)
        handler.send_error = AsyncMock()

        await handler._cmd_status(mock_update, mock_context, "TASK-999")

        handler.send_error.assert_called_once()
        assert "not found" in handler.send_error.call_args[0][1]

    @pytest.mark.asyncio
    async def test_cmd_approve_no_args(self, handler, mock_update, mock_context):
        """Test /approve without task ID."""
        handler.send_error = AsyncMock()

        await handler._cmd_approve(mock_update, mock_context, "")

        handler.send_error.assert_called_once()
        assert "Usage:" in handler.send_error.call_args[0][1]

    @pytest.mark.asyncio
    async def test_cmd_search_no_args(self, handler, mock_update, mock_context):
        """Test /search without keyword."""
        handler.send_error = AsyncMock()

        await handler._cmd_search(mock_update, mock_context, "")

        handler.send_error.assert_called_once()
        assert "Usage:" in handler.send_error.call_args[0][1]

    @pytest.mark.asyncio
    async def test_handle_command_execution_error(self, handler, mock_update, mock_context):
        """Test error handling during command execution."""
        mock_update.message.text = "/start"
        handler._cmd_start = AsyncMock(side_effect=Exception("Test error"))
        handler.send_error = AsyncMock()

        await handler.handle(mock_update, mock_context)

        handler.send_error.assert_called_once()
        assert "Command failed" in handler.send_error.call_args[0][1]

    @pytest.mark.asyncio
    async def test_cmd_task_no_args(self, handler, mock_update, mock_context):
        """Test /task without description."""
        handler.send_message = AsyncMock()

        await handler._cmd_create_task(mock_update, mock_context, "")

        handler.send_message.assert_called_once()
        assert "Usage:" in handler.send_message.call_args[0][1]

    @pytest.mark.asyncio
    async def test_cmd_task_with_args(self, handler, mock_update, mock_context):
        """Test /task with description."""
        handler.send_message = AsyncMock()

        await handler._cmd_create_task(mock_update, mock_context, "Fix login bug")

        handler.send_message.assert_called_once()
        assert "Creating task" in handler.send_message.call_args[0][1]
