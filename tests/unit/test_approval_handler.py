"""
Unit tests for ApprovalHandler.

Q1 2026: Task #4.5 - Approval workflow tests.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.bot.handlers.approval_handler import ApprovalHandler


@pytest.fixture
def handler():
    """Create approval handler with mocked dependencies."""
    handler = ApprovalHandler()

    # Mock session manager
    handler.get_session = AsyncMock()
    handler.set_session = AsyncMock(return_value=True)
    handler.clear_session = AsyncMock(return_value=True)

    # Mock repositories
    handler.task_repo = MagicMock()
    handler.task_repo.delete = AsyncMock(return_value=True)
    handler.task_repo.update = AsyncMock(return_value=True)
    handler.task_repo.get_by_id = AsyncMock(return_value=None)

    # Mock integrations
    handler.sheets = MagicMock()
    handler.sheets.get_all_tasks = AsyncMock(return_value=[])
    handler.sheets.delete_task = AsyncMock(return_value=True)
    handler.sheets.update_task = AsyncMock(return_value=True)

    handler.discord = MagicMock()
    handler.discord.post_alert = AsyncMock()
    handler.discord.delete_task_message = AsyncMock(return_value=True)

    # Mock logging
    handler.log_action = AsyncMock()

    return handler


@pytest.fixture
def mock_update():
    """Create mock Telegram update."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = "yes"
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 123
    update.effective_user.username = "testuser"
    update.effective_user.first_name = "Test"
    update.effective_user.last_name = "User"
    update.effective_user.full_name = "Test User"
    return update


@pytest.fixture
def mock_context():
    """Create mock Telegram context."""
    return MagicMock()


@pytest.mark.asyncio
async def test_can_handle_yes_response(handler):
    """Test detecting yes/no responses."""
    # Mock pending action
    handler.get_session = AsyncMock(return_value={"type": "delete_task"})

    assert await handler.can_handle("yes", "123") == True
    assert await handler.can_handle("no", "123") == True
    assert await handler.can_handle("confirm", "123") == True
    assert await handler.can_handle("cancel", "123") == True
    assert await handler.can_handle("do it", "123") == True


@pytest.mark.asyncio
async def test_can_handle_no_pending(handler):
    """Test no handling when no pending action."""
    handler.get_session = AsyncMock(return_value=None)

    assert await handler.can_handle("yes", "123") == False
    assert await handler.can_handle("no", "123") == False


@pytest.mark.asyncio
async def test_can_handle_non_confirmation(handler):
    """Test ignoring non-confirmation messages."""
    handler.get_session = AsyncMock(return_value={"type": "delete_task"})

    assert await handler.can_handle("hello world", "123") == False
    assert await handler.can_handle("what's up", "123") == False


@pytest.mark.asyncio
async def test_request_approval(handler):
    """Test requesting approval."""
    success = await handler.request_approval(
        user_id="123",
        action_type="delete_task",
        action_data={"task_id": "TASK-001"},
        message="⚠️ Delete task TASK-001?",
        timeout_minutes=5
    )

    assert success == True
    handler.set_session.assert_called_once()

    # Check the stored data
    call_args = handler.set_session.call_args
    assert call_args[0][0] == "action"  # session_type
    assert call_args[0][1] == "123"  # user_id
    assert call_args[0][2]["type"] == "delete_task"
    assert call_args[0][2]["action_data"]["task_id"] == "TASK-001"


@pytest.mark.asyncio
async def test_is_expired_not_expired(handler):
    """Test expiration checking - not expired."""
    pending = {
        "requested_at": datetime.now().isoformat(),
        "timeout_minutes": 5
    }
    assert handler._is_expired(pending) == False


@pytest.mark.asyncio
async def test_is_expired_expired(handler):
    """Test expiration checking - expired."""
    pending_old = {
        "requested_at": (datetime.now() - timedelta(minutes=10)).isoformat(),
        "timeout_minutes": 5
    }
    assert handler._is_expired(pending_old) == True


@pytest.mark.asyncio
async def test_handle_no_pending_action(handler, mock_update, mock_context):
    """Test handling when no pending action."""
    handler.get_session = AsyncMock(return_value=None)
    handler.get_user_info = AsyncMock(return_value={
        "user_id": "123",
        "first_name": "Test"
    })

    await handler.handle(mock_update, mock_context)

    # Should send error
    mock_update.message.reply_text.assert_called_once()
    assert "No pending action" in str(mock_update.message.reply_text.call_args)


@pytest.mark.asyncio
async def test_handle_expired_action(handler, mock_update, mock_context):
    """Test handling expired action."""
    expired_pending = {
        "type": "delete_task",
        "requested_at": (datetime.now() - timedelta(minutes=10)).isoformat(),
        "timeout_minutes": 5
    }
    handler.get_session = AsyncMock(return_value=expired_pending)
    handler.get_user_info = AsyncMock(return_value={
        "user_id": "123",
        "first_name": "Test"
    })

    await handler.handle(mock_update, mock_context)

    # Should clear session and notify
    handler.clear_session.assert_called_once_with("action", "123")
    mock_update.message.reply_text.assert_called_once()
    assert "expired" in str(mock_update.message.reply_text.call_args).lower()


@pytest.mark.asyncio
async def test_handle_approval_clear_tasks(handler, mock_update, mock_context):
    """Test handling approval for clear_tasks."""
    pending = {
        "type": "clear_tasks",
        "action_data": {},
        "requested_at": datetime.now().isoformat(),
        "timeout_minutes": 5
    }
    handler.get_session = AsyncMock(return_value=pending)
    handler.get_user_info = AsyncMock(return_value={
        "user_id": "123",
        "first_name": "Test"
    })

    # Mock task list
    handler.sheets.get_all_tasks = AsyncMock(return_value=[
        {"ID": "TASK-001", "Status": "pending"},
        {"ID": "TASK-002", "Status": "in_progress"},
    ])

    await handler.handle(mock_update, mock_context)

    # Should execute clear_tasks
    assert handler.sheets.delete_task.call_count == 2
    handler.clear_session.assert_called_once_with("action", "123")
    handler.log_action.assert_called_once()


@pytest.mark.asyncio
async def test_handle_rejection(handler, mock_update, mock_context):
    """Test handling rejection."""
    mock_update.message.text = "no"

    pending = {
        "type": "delete_task",
        "action_data": {"task_id": "TASK-001"},
        "requested_at": datetime.now().isoformat(),
        "timeout_minutes": 5
    }
    handler.get_session = AsyncMock(return_value=pending)
    handler.get_user_info = AsyncMock(return_value={
        "user_id": "123",
        "first_name": "Test"
    })

    await handler.handle(mock_update, mock_context)

    # Should clear session and cancel
    handler.clear_session.assert_called_once_with("action", "123")
    handler.log_action.assert_called_once()
    assert "rejected" in handler.log_action.call_args[0][0]
    mock_update.message.reply_text.assert_called_once()
    assert "cancelled" in str(mock_update.message.reply_text.call_args).lower()


@pytest.mark.asyncio
async def test_execute_delete_task(handler, mock_update):
    """Test executing single task deletion."""
    from unittest.mock import patch

    # Mock staff_context_repository - patch where it's imported in the method
    with patch('src.database.repositories.staff_context.get_staff_context_repository') as mock_staff_repo:
        mock_repo = MagicMock()
        mock_repo.get_thread_by_task = AsyncMock(return_value="thread_123")
        mock_staff_repo.return_value = mock_repo

        data = {"task_id": "TASK-001"}
        await handler._execute_delete_task(mock_update, data, "Test User")

        # Should delete from sheets, database, and discord
        handler.sheets.delete_task.assert_called_once_with("TASK-001")
        handler.task_repo.delete.assert_called_once_with("TASK-001")
        handler.discord.delete_task_message.assert_called_once()


@pytest.mark.asyncio
async def test_execute_bulk_update(handler, mock_update):
    """Test executing bulk update."""
    # Mock task object
    mock_task = MagicMock()
    handler.task_repo.get_by_id = AsyncMock(return_value=mock_task)

    data = {
        "task_ids": ["TASK-001", "TASK-002"],
        "updates": {"status": "completed"}
    }

    await handler._execute_bulk_update(mock_update, data, "Test User")

    # Should update both tasks
    assert handler.task_repo.update.call_count == 2
    assert handler.sheets.update_task.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
