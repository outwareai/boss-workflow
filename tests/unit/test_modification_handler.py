"""
Unit tests for ModificationHandler.

Q1 2026: Task #4.6 Part 2 tests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot.handlers.modification_handler import ModificationHandler


@pytest.fixture
def handler():
    """Create ModificationHandler instance."""
    return ModificationHandler()


@pytest.fixture
def mock_update():
    """Create mock Telegram Update."""
    update = MagicMock()
    update.message.text = "update TASK-001 status to completed"
    update.effective_user.id = "123456"
    update.effective_user.first_name = "TestUser"
    update.effective_user.username = "testuser"
    return update


@pytest.fixture
def mock_context():
    """Create mock Telegram Context."""
    return MagicMock()


class TestModificationHandler:
    """Test ModificationHandler functionality."""

    @pytest.mark.asyncio
    async def test_can_handle_update_keyword(self, handler):
        """Test detection of 'update' keyword."""
        result = await handler.can_handle("update TASK-001 status to completed", "123")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_handle_change_keyword(self, handler):
        """Test detection of 'change' keyword."""
        result = await handler.can_handle("change title to new title", "123")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_handle_modify_keyword(self, handler):
        """Test detection of 'modify' keyword."""
        result = await handler.can_handle("modify task description", "123")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_handle_reassign_keyword(self, handler):
        """Test detection of 'reassign' keyword."""
        result = await handler.can_handle("reassign to John", "123")
        assert result is True

    @pytest.mark.asyncio
    async def test_cannot_handle_non_modification(self, handler):
        """Test rejection of non-modification messages."""
        result = await handler.can_handle("what's the status of tasks", "123")
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_modification_no_task_id(self, handler, mock_update):
        """Test error when task ID is missing."""
        modification = {"updates": {"status": "completed"}}
        handler.send_error = AsyncMock()

        await handler._execute_modification(
            mock_update,
            modification,
            {"user_id": "123", "first_name": "Test"}
        )

        handler.send_error.assert_called_once()
        assert "No task ID specified" in handler.send_error.call_args[0][1]

    @pytest.mark.asyncio
    async def test_execute_modification_task_not_found(self, handler, mock_update):
        """Test error when task doesn't exist."""
        modification = {"task_id": "TASK-999", "updates": {"status": "completed"}}
        handler.task_repo.get_by_id = AsyncMock(return_value=None)
        handler.send_error = AsyncMock()

        await handler._execute_modification(
            mock_update,
            modification,
            {"user_id": "123", "first_name": "Test"}
        )

        handler.send_error.assert_called_once()
        assert "TASK-999 not found" in handler.send_error.call_args[0][1]

    @pytest.mark.asyncio
    async def test_execute_modification_success(self, handler, mock_update):
        """Test successful task modification."""
        modification = {"task_id": "TASK-001", "updates": {"status": "completed"}}
        mock_task = MagicMock(task_id="TASK-001")

        handler.task_repo.get_by_id = AsyncMock(return_value=mock_task)
        handler.task_repo.update = AsyncMock(return_value=True)
        handler.sheets.sync_task_to_sheet = AsyncMock()
        handler.log_action = AsyncMock()
        handler.send_success = AsyncMock()

        await handler._execute_modification(
            mock_update,
            modification,
            {"user_id": "123", "first_name": "Test"}
        )

        handler.task_repo.update.assert_called_once_with("TASK-001", {"status": "completed"})
        handler.sheets.sync_task_to_sheet.assert_called_once_with("TASK-001")
        handler.send_success.assert_called_once()
