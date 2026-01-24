"""
Unit tests for QueryHandler.

Q1 2026: Task #4.6 Part 1 - Query and reporting tests.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta


@pytest.fixture
def handler():
    """Create query handler."""
    with patch('src.bot.base_handler.get_session_manager'), \
         patch('src.bot.base_handler.get_task_repository'), \
         patch('src.bot.base_handler.get_team_repository'), \
         patch('src.bot.base_handler.get_conversation_repository'), \
         patch('src.bot.base_handler.get_audit_repository'), \
         patch('src.bot.base_handler.get_sheets_integration'), \
         patch('src.bot.base_handler.get_discord_integration'), \
         patch('src.bot.base_handler.get_preferences_manager'):

        from src.bot.handlers.query_handler import QueryHandler
        handler = QueryHandler()

        # Mock session manager
        handler.session_manager = AsyncMock()
        handler.session_manager.get_pending_validation = AsyncMock(return_value=None)

        # Mock task repository
        handler.task_repo = AsyncMock()
        handler.task_repo.get_by_id = AsyncMock(return_value=None)

        # Mock integrations
        handler.sheets = AsyncMock()
        handler.sheets.get_all_tasks = AsyncMock(return_value=[])
        handler.sheets.get_daily_tasks = AsyncMock(return_value=[])
        handler.sheets.get_overdue_tasks = AsyncMock(return_value=[])
        handler.sheets.search_tasks = AsyncMock(return_value=[])

        handler.discord = AsyncMock()

        # Mock audit
        handler.audit_repo = AsyncMock()
        handler.audit_repo.create = AsyncMock()

        return handler


@pytest.mark.asyncio
async def test_can_handle_status_query(handler):
    """Test detecting status queries."""
    assert await handler.can_handle("check status", "123") == True
    assert await handler.can_handle("show my tasks", "123") == True
    assert await handler.can_handle("list overdue", "123") == True
    assert await handler.can_handle("TASK-001", "123") == True
    assert await handler.can_handle("what's john working on", "123") == True


@pytest.mark.asyncio
async def test_can_handle_report_queries(handler):
    """Test detecting report queries."""
    assert await handler.can_handle("daily report", "123") == True
    assert await handler.can_handle("weekly report", "123") == True
    assert await handler.can_handle("monthly standup", "123") == True


@pytest.mark.asyncio
async def test_can_handle_non_query(handler):
    """Test rejecting non-queries."""
    assert await handler.can_handle("create new task", "123") == False
    assert await handler.can_handle("delete task", "123") == False
    assert await handler.can_handle("approve this", "123") == False


@pytest.mark.asyncio
async def test_format_task_details(handler):
    """Test task detail formatting from Sheets."""
    task = {
        "ID": "TASK-001",
        "Title": "Test Task",
        "Description": "Test description",
        "Status": "in_progress",
        "Assignee": "John",
        "Priority": "high",
        "Deadline": "2026-01-25",
        "Created": "2026-01-24"
    }

    result = handler._format_task_details(task)

    assert "TASK-001" in result
    assert "Test Task" in result
    assert "in_progress" in result
    assert "John" in result
    assert "high" in result


@pytest.mark.asyncio
async def test_group_tasks_by_status(handler):
    """Test grouping tasks by status."""
    tasks = [
        {"ID": "T1", "Title": "Task 1", "Status": "pending"},
        {"ID": "T2", "Title": "Task 2", "Status": "in_progress"},
        {"ID": "T3", "Title": "Task 3", "Status": "pending"},
    ]

    grouped = handler._group_tasks_by_status_sheets(tasks)

    assert len(grouped["pending"]) == 2
    assert len(grouped["in_progress"]) == 1


@pytest.mark.asyncio
async def test_handle_task_lookup_success(handler):
    """Test successful task lookup."""
    # Mock update and task
    update = Mock()
    update.message.text = "Show me TASK-001"

    mock_task = Mock()
    mock_task.task_id = "TASK-001"
    mock_task.title = "Test Task"
    mock_task.status = "in_progress"
    mock_task.assignee = "John"
    mock_task.priority = "high"
    mock_task.description = "Test"
    mock_task.deadline = datetime.now() + timedelta(days=1)
    mock_task.created_at = datetime.now()

    handler.task_repo.get_by_id = AsyncMock(return_value=mock_task)
    handler.send_message = AsyncMock()

    await handler._handle_task_lookup(update, "Show me TASK-001")

    # Verify task was looked up and message sent
    handler.task_repo.get_by_id.assert_called_once_with("TASK-001")
    handler.send_message.assert_called_once()
    call_args = handler.send_message.call_args[0]
    assert "TASK-001" in call_args[1]
    assert "Test Task" in call_args[1]


@pytest.mark.asyncio
async def test_handle_task_lookup_not_found(handler):
    """Test task lookup when task not found."""
    update = Mock()
    update.message.text = "Show me TASK-999"

    handler.task_repo.get_by_id = AsyncMock(return_value=None)
    handler.sheets.get_all_tasks = AsyncMock(return_value=[])
    handler.send_error = AsyncMock()

    await handler._handle_task_lookup(update, "Show me TASK-999")

    handler.send_error.assert_called_once()
    call_args = handler.send_error.call_args[0]
    assert "not found" in call_args[1].lower()


@pytest.mark.asyncio
async def test_handle_my_tasks_empty(handler):
    """Test my tasks when user has no tasks."""
    update = Mock()
    user_info = {"user_id": "123", "first_name": "John"}

    handler.sheets.get_all_tasks = AsyncMock(return_value=[])
    handler.send_message = AsyncMock()

    await handler._handle_my_tasks(update, user_info)

    handler.send_message.assert_called_once()
    call_args = handler.send_message.call_args[0]
    assert "No tasks" in call_args[1]


@pytest.mark.asyncio
async def test_handle_overdue_tasks(handler):
    """Test overdue tasks display."""
    update = Mock()
    user_info = {"user_id": "123"}

    overdue_tasks = [
        {
            "ID": "TASK-001",
            "Title": "Overdue Task 1",
            "Assignee": "John",
            "Deadline": "2026-01-20"
        },
        {
            "ID": "TASK-002",
            "Title": "Overdue Task 2",
            "Assignee": "Sarah",
            "Deadline": "2026-01-21"
        }
    ]

    handler.sheets.get_overdue_tasks = AsyncMock(return_value=overdue_tasks)
    handler.send_message = AsyncMock()

    await handler._handle_overdue_tasks(update, user_info)

    handler.send_message.assert_called_once()
    call_args = handler.send_message.call_args[0]
    assert "2 Overdue" in call_args[1]
    assert "TASK-001" in call_args[1]
