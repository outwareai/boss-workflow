"""
Unit tests for ValidationHandler.

Q1 2026: Task #4.3 - Validation flow extraction.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime


@pytest.fixture
def handler():
    """Create validation handler."""
    with patch('src.bot.base_handler.get_session_manager'), \
         patch('src.bot.base_handler.get_task_repository'), \
         patch('src.bot.base_handler.get_team_repository'), \
         patch('src.bot.base_handler.get_conversation_repository'), \
         patch('src.bot.base_handler.get_audit_repository'), \
         patch('src.bot.base_handler.get_sheets_integration'), \
         patch('src.bot.base_handler.get_discord_integration'), \
         patch('src.bot.base_handler.get_preferences_manager'):

        from src.bot.handlers.validation_handler import ValidationHandler
        handler = ValidationHandler()

        # Mock session manager
        handler.session_manager = AsyncMock()
        handler.session_manager.list_pending_validations = AsyncMock(return_value=[])

        # Mock task repository
        handler.task_repo = AsyncMock()
        handler.task_repo.get_by_id = AsyncMock(return_value=None)
        handler.task_repo.update = AsyncMock(return_value=True)

        # Mock integrations
        handler.sheets = AsyncMock()
        handler.sheets.sync_task_to_sheet = AsyncMock()
        handler.discord = AsyncMock()
        handler.discord.post_alert = AsyncMock()

        # Mock audit
        handler.audit_repo = AsyncMock()
        handler.audit_repo.create = AsyncMock()

        return handler


@pytest.fixture
def mock_update():
    """Create mock Telegram update."""
    user = Mock()
    user.id = 12345
    user.username = "boss"
    user.first_name = "Boss"
    user.last_name = "User"
    user.full_name = "Boss User"

    message = Mock()
    message.text = "/approve TASK-001"
    message.reply_text = AsyncMock()

    update = Mock()
    update.effective_user = user
    update.message = message

    return update


@pytest.mark.asyncio
async def test_can_handle_approve(handler):
    """Test can_handle detects /approve commands."""
    # Mock get_session to return None
    handler.get_session = AsyncMock(return_value=None)

    result = await handler.can_handle("/approve TASK-001", "123")
    assert result == True


@pytest.mark.asyncio
async def test_can_handle_reject(handler):
    """Test can_handle detects /reject commands."""
    handler.get_session = AsyncMock(return_value=None)

    result = await handler.can_handle("/reject TASK-001", "123")
    assert result == True


@pytest.mark.asyncio
async def test_can_handle_normal_message(handler):
    """Test can_handle rejects normal messages."""
    handler.get_session = AsyncMock(return_value=None)

    result = await handler.can_handle("normal message", "123")
    assert result == False


@pytest.mark.asyncio
async def test_handle_approve(handler, mock_update):
    """Test handling /approve command."""
    # Mock is_boss
    handler.is_boss = AsyncMock(return_value=True)

    # Mock session data
    handler.session_manager.list_pending_validations = AsyncMock(return_value=[
        {
            "task_id": "TASK-001",
            "staff_user_id": "67890",
            "description": "Test task",
            "submitted_at": "2026-01-24T10:00:00",
        }
    ])

    # Mock clear_session
    handler.clear_session = AsyncMock(return_value=True)

    # Mock log_action
    handler.log_action = AsyncMock()

    # Mock notify_staff
    handler._notify_staff = AsyncMock()

    # Handle approve
    await handler.handle(mock_update, None)

    # Verify task was updated
    handler.task_repo.update.assert_called_once()
    call_args = handler.task_repo.update.call_args
    assert call_args[0][0] == "TASK-001"
    assert call_args[0][1]["status"] == "completed"

    # Verify Discord notification
    handler.discord.post_alert.assert_called_once()

    # Verify staff was notified
    handler._notify_staff.assert_called_once()

    # Verify session was cleared
    handler.clear_session.assert_called_once()


@pytest.mark.asyncio
async def test_handle_approve_no_pending(handler, mock_update):
    """Test /approve with no pending validations."""
    # Mock is_boss
    handler.is_boss = AsyncMock(return_value=True)

    # Mock empty pending validations
    handler.session_manager.list_pending_validations = AsyncMock(return_value=[])

    # Mock send_message
    handler.send_message = AsyncMock()

    # Handle approve
    await handler.handle(mock_update, None)

    # Verify message sent
    handler.send_message.assert_called_once()
    call_args = handler.send_message.call_args
    assert "Nothing pending approval" in call_args[0][1]


@pytest.mark.asyncio
async def test_request_validation(handler):
    """Test requesting validation from boss."""
    # Mock task
    mock_task = Mock()
    mock_task.task_id = "TASK-001"
    mock_task.title = "Test Task"

    handler.task_repo.get_by_id = AsyncMock(return_value=mock_task)

    # Mock set_session
    handler.set_session = AsyncMock(return_value=True)

    # Mock settings in the right location
    with patch('config.settings.get_settings') as mock_settings:
        settings = Mock()
        settings.telegram_bot_token = "test_token"
        mock_settings.return_value = settings

        # Mock HTTP request
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.post = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            success = await handler.request_validation(
                task_id="TASK-001",
                staff_user_id="12345",
                boss_user_id="67890",
                description="Test task description",
                proof_items=[{"type": "note", "content": "Test proof"}],
                notes="Test notes"
            )

            assert success == True

            # Verify task status updated
            handler.task_repo.update.assert_called_once()

            # Verify session created
            handler.set_session.assert_called_once()


@pytest.mark.asyncio
async def test_handle_reject(handler, mock_update):
    """Test handling /reject command."""
    # Update mock to reject command
    mock_update.message.text = "/reject TASK-001 Needs improvement"

    # Mock is_boss
    handler.is_boss = AsyncMock(return_value=True)

    # Mock session data
    handler.session_manager.list_pending_validations = AsyncMock(return_value=[
        {
            "task_id": "TASK-001",
            "staff_user_id": "67890",
            "description": "Test task",
            "submitted_at": "2026-01-24T10:00:00",
        }
    ])

    # Mock clear_session
    handler.clear_session = AsyncMock(return_value=True)

    # Mock log_action
    handler.log_action = AsyncMock()

    # Mock notify_staff
    handler._notify_staff = AsyncMock()

    # Mock send_message
    handler.send_message = AsyncMock()

    # Handle reject
    await handler.handle(mock_update, None)

    # Verify task was updated to needs_revision
    handler.task_repo.update.assert_called_once()
    call_args = handler.task_repo.update.call_args
    assert call_args[0][0] == "TASK-001"
    assert call_args[0][1]["status"] == "needs_revision"
    assert "reason" in call_args[0][1]["delay_reason"].lower() or "improvement" in call_args[0][1]["delay_reason"].lower()

    # Verify Discord notification
    handler.discord.post_alert.assert_called_once()

    # Verify staff was notified
    handler._notify_staff.assert_called_once()

    # Verify session was cleared
    handler.clear_session.assert_called_once()


@pytest.mark.asyncio
async def test_get_pending_validations(handler):
    """Test getting pending validations."""
    expected_validations = [
        {"task_id": "TASK-001", "staff_user_id": "123"},
        {"task_id": "TASK-002", "staff_user_id": "456"},
    ]

    handler.session_manager.list_pending_validations = AsyncMock(return_value=expected_validations)

    result = await handler.get_pending_validations()

    assert result == expected_validations
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_validation_count(handler):
    """Test getting validation count."""
    handler.session_manager.list_pending_validations = AsyncMock(return_value=[
        {"task_id": "TASK-001"},
        {"task_id": "TASK-002"},
        {"task_id": "TASK-003"},
    ])

    count = await handler.get_validation_count()

    assert count == 3
