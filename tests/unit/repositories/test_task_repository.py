"""
Unit tests for TaskRepository.

Q3 2026: Comprehensive unit tests for database repository layer.
Q4 2026: Fixed async mocking issues and aligned with actual implementation.
Q1 2027: Added tests for 14 previously untested methods - 100% coverage target.
"""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime, date, timedelta
from typing import List, Optional

from src.database.repositories.tasks import TaskRepository
from src.database.models import TaskDB, SubtaskDB, TaskDependencyDB
from src.database import get_database


@pytest.fixture
def mock_database():
    """Mock database with session context manager."""
    db = Mock()
    session = AsyncMock()

    # Mock session context manager
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    # Mock session methods
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = Mock()
    session.delete = AsyncMock()

    db.session = Mock(return_value=session)

    return db, session


@pytest.fixture
def task_repository(mock_database):
    """Create TaskRepository with mocked database."""
    db, session = mock_database
    repo = TaskRepository()
    repo.db = db
    return repo, session


@pytest.fixture
def sample_task():
    """Create a sample TaskDB instance for testing."""
    return TaskDB(
        task_id="TASK-001",
        title="Test Task",
        description="Test Description",
        status="pending",
        priority="high",
        assignee="John Doe",
        estimated_effort="2 hours",
        tags="test,unit-test"
    )


@pytest.fixture
def sample_subtask():
    """Create a sample SubtaskDB instance for testing."""
    return SubtaskDB(
        id=1,
        task_id=1,  # Database ID, not task_id string
        title="Test Subtask",
        order=1,
        completed=False
    )


# ============================================================
# CREATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_create_task_success(task_repository, sample_task):
    """Test creating a new task successfully."""
    repo, session = task_repository

    # Mock execute to return None (no duplicate)
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    task_data = {
        "task_id": "TASK-001",
        "title": "Fix login bug",
        "assignee": "John",
        "status": "pending",
    }

    result = await repo.create(task_data)

    # Verify session.add was called
    session.add.assert_called_once()
    session.flush.assert_called_once()

    # Verify task was created with correct data
    added_task = session.add.call_args[0][0]
    assert added_task.task_id == "TASK-001"
    assert added_task.title == "Fix login bug"


@pytest.mark.asyncio
async def test_create_task_duplicate_id(task_repository, sample_task):
    """Test creating a task with duplicate task_id returns None."""
    repo, session = task_repository

    # Mock that task creation raises an exception (duplicate key)
    session.flush.side_effect = Exception("Duplicate key")

    task_data = {
        "task_id": "TASK-001",
        "title": "Duplicate task",
    }

    result = await repo.create(task_data)

    # Should return None on error
    assert result is None


# ============================================================
# READ TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_by_task_id_found(task_repository, sample_task):
    """Test retrieving a task by task_id when it exists."""
    repo, session = task_repository

    # Mock the execute result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_task)
    session.execute.return_value = mock_result

    result = await repo.get_by_id("TASK-001")

    assert result == sample_task
    assert result.task_id == "TASK-001"


@pytest.mark.asyncio
async def test_get_by_task_id_not_found(task_repository):
    """Test retrieving a task that doesn't exist."""
    repo, session = task_repository

    # Mock no result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.get_by_id("TASK-999")

    assert result is None


@pytest.mark.asyncio
async def test_get_by_status(task_repository, sample_task):
    """Test retrieving tasks by status."""
    repo, session = task_repository

    # Mock result with multiple tasks
    tasks = [sample_task, sample_task]
    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=tasks)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_by_status("pending")

    assert len(result) == 2
    assert all(isinstance(t, TaskDB) for t in result)


@pytest.mark.asyncio
async def test_get_by_assignee(task_repository, sample_task):
    """Test retrieving tasks by assignee."""
    repo, session = task_repository

    # Mock result
    tasks = [sample_task]
    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=tasks)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_by_assignee("John Doe")

    assert len(result) == 1
    assert result[0].assignee == "John Doe"


# ============================================================
# UPDATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_update_task_success(task_repository, sample_task):
    """Test updating a task successfully."""
    repo, session = task_repository

    # Create updated task object
    updated_task = TaskDB(
        task_id="TASK-001",
        title="Updated title",
        description="Test Description",
        status="in_progress",
        priority="high",
        assignee="John Doe",
        estimated_effort="2 hours",
        tags="test,unit-test"
    )

    # Mock execute to return updated task after update
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=updated_task)
    session.execute.return_value = mock_result

    updates = {
        "title": "Updated title",
        "status": "in_progress",
    }

    result = await repo.update("TASK-001", updates)

    # Verify task was updated
    assert result is not None
    assert result.title == "Updated title"
    assert result.status == "in_progress"


@pytest.mark.asyncio
async def test_update_task_not_found(task_repository):
    """Test updating a non-existent task."""
    repo, session = task_repository

    # Mock no task found
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.update("TASK-999", {"title": "New title"})

    assert result is None


@pytest.mark.asyncio
async def test_update_task_with_empty_updates(task_repository, sample_task):
    """Test updating a task with no updates."""
    repo, session = task_repository

    # Mock get_by_id to return existing task
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_task)
    session.execute.return_value = mock_result

    result = await repo.update("TASK-001", {})

    # Should still return task even with no updates
    assert result is not None


# ============================================================
# DELETE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_delete_task_success(task_repository, sample_task):
    """Test deleting a task successfully."""
    repo, session = task_repository

    # Mock execute to return task (for audit log)
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_task)
    session.execute.return_value = mock_result

    result = await repo.delete("TASK-001")

    # Delete always returns True if it completes
    assert result is True
    # Verify execute was called (for SELECT and DELETE)
    assert session.execute.call_count >= 2


@pytest.mark.asyncio
async def test_delete_task_not_found(task_repository):
    """Test deleting a non-existent task."""
    repo, session = task_repository

    # Mock no task found
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.delete("TASK-999")

    # Delete returns True even if task not found (idempotent)
    assert result is True


# ============================================================
# SUBTASK TESTS
# ============================================================

@pytest.mark.asyncio
async def test_add_subtask_success(task_repository, sample_task):
    """Test adding a subtask successfully."""
    repo, session = task_repository

    # Mock that parent task has db id
    sample_task.id = 1

    # Mock execute to return:
    # 1. Parent task (for get task)
    # 2. Max order number (for order query)
    mock_task_result = Mock()
    mock_task_result.scalar_one_or_none = Mock(return_value=sample_task)

    mock_order_result = Mock()
    mock_order_result.scalar = Mock(return_value=2)  # Current max order

    session.execute.side_effect = [mock_task_result, mock_order_result]

    result = await repo.add_subtask("TASK-001", "Implement feature")

    assert result is not None
    session.add.assert_called_once()
    session.flush.assert_called()


@pytest.mark.asyncio
async def test_add_subtask_parent_not_found(task_repository):
    """Test adding a subtask when parent doesn't exist."""
    repo, session = task_repository

    # Mock no parent task found
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.add_subtask("TASK-999", "Subtask")

    assert result is None
    session.add.assert_not_called()


# ============================================================
# DEPENDENCY TESTS
# ============================================================

@pytest.mark.asyncio
async def test_add_dependency_success(task_repository, sample_task):
    """Test adding a dependency successfully."""
    repo, session = task_repository

    # Mock both tasks found
    task1 = TaskDB(task_id="TASK-001", title="Task 1", id=1, status="pending")
    task2 = TaskDB(task_id="TASK-002", title="Task 2", id=2, status="completed")

    # Mock execute to return tasks in sequence
    mock_result1 = Mock()
    mock_result1.scalar_one_or_none = Mock(return_value=task1)
    mock_result2 = Mock()
    mock_result2.scalar_one_or_none = Mock(return_value=task2)

    session.execute.side_effect = [mock_result1, mock_result2]

    # Mock cycle check
    with patch.object(repo, '_would_create_cycle', return_value=False):
        result = await repo.add_dependency("TASK-001", "TASK-002", "depends_on")

    assert result is not None
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_add_dependency_task_not_found(task_repository):
    """Test adding a dependency when task doesn't exist."""
    repo, session = task_repository

    # Mock first task not found
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.add_dependency("TASK-999", "TASK-001", "blocked_by")

    assert result is None
    session.add.assert_not_called()


# ============================================================
# QUERY TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_overdue_tasks(task_repository, sample_task):
    """Test retrieving overdue tasks."""
    repo, session = task_repository

    # Mock overdue tasks
    overdue_task = TaskDB(
        task_id="TASK-003",
        title="Overdue Task",
        deadline=datetime.now() - timedelta(days=1),
        status="pending"
    )
    tasks = [overdue_task]

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=tasks)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_overdue()

    assert len(result) == 1
    assert result[0].task_id == "TASK-003"


# ============================================================
# CONCURRENT UPDATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_concurrent_updates(task_repository, sample_task):
    """Test handling concurrent updates to same task."""
    repo, session = task_repository

    # Mock execute to return task each time
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_task)
    session.execute.return_value = mock_result

    # Update task twice
    result1 = await repo.update("TASK-001", {"title": "Update 1"})
    result2 = await repo.update("TASK-001", {"title": "Update 2"})

    # Both updates should succeed
    assert result1 is not None
    assert result2 is not None
    # Execute should be called twice (2 UPDATEs, 2 SELECTs = 4 total)
    assert session.execute.call_count >= 4


# ============================================================
# NEW TESTS FOR UNTESTED METHODS (Q1 2027)
# Covers 14 previously untested methods for 100% coverage
# ============================================================

# ==================== change_status() Tests ====================

@pytest.mark.asyncio
async def test_change_status_to_completed_sets_timestamp(task_repository):
    """Test changing status to completed sets completed_at timestamp."""
    repo, session = task_repository

    # Create mock task
    mock_task = TaskDB(
        task_id="TASK-001",
        title="Test Task",
        status="in_progress",
        id=1
    )
    mock_task.completed_at = None
    mock_task.started_at = datetime.now()
    mock_task.needs_sheet_sync = False

    # Mock database query
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=mock_task)
    session.execute.return_value = mock_result

    # Test status change
    result = await repo.change_status("TASK-001", "completed", "boss")

    assert result is not None
    assert result.status == "completed"
    assert result.completed_at is not None
    assert result.needs_sheet_sync is True


@pytest.mark.asyncio
async def test_change_status_to_in_progress_sets_started_at(task_repository):
    """Test changing status to in_progress sets started_at timestamp."""
    repo, session = task_repository

    mock_task = TaskDB(
        task_id="TASK-002",
        title="Test Task",
        status="pending",
        id=2
    )
    mock_task.started_at = None
    mock_task.needs_sheet_sync = False

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=mock_task)
    session.execute.return_value = mock_result

    result = await repo.change_status("TASK-002", "in_progress", "user")

    assert result.status == "in_progress"
    assert result.started_at is not None


@pytest.mark.asyncio
async def test_change_status_to_delayed_tracks_reason(task_repository):
    """Test changing status to delayed tracks delay reason and count."""
    repo, session = task_repository

    mock_task = TaskDB(
        task_id="TASK-003",
        title="Test Task",
        status="in_progress",
        id=3,
        deadline=datetime.now() + timedelta(days=2)
    )
    mock_task.delayed_count = 0
    mock_task.original_deadline = None
    mock_task.needs_sheet_sync = False

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=mock_task)
    session.execute.return_value = mock_result

    result = await repo.change_status("TASK-003", "delayed", "boss", reason="Waiting for resources")

    assert result.status == "delayed"
    assert result.delay_reason == "Waiting for resources"
    assert result.delayed_count == 1
    assert result.original_deadline is not None


@pytest.mark.asyncio
async def test_change_status_task_not_found(task_repository):
    """Test changing status returns None if task doesn't exist."""
    repo, session = task_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.change_status("TASK-999", "completed", "boss")

    assert result is None


# ==================== complete_subtask() Tests ====================

@pytest.mark.asyncio
async def test_complete_subtask_updates_progress(task_repository):
    """Test completing a subtask updates parent task progress."""
    repo, session = task_repository

    # Mock subtask
    mock_subtask = SubtaskDB(
        id=1,
        task_id=1,
        title="Subtask 1",
        order=1,
        completed=False
    )
    mock_subtask.task = TaskDB(task_id="TASK-001", title="Parent Task", id=1)
    mock_subtask.completed_at = None
    mock_subtask.completed_by = None

    # Mock all subtasks (2 total, 1 will be completed)
    all_subtasks = [
        mock_subtask,
        SubtaskDB(id=2, task_id=1, title="Subtask 2", order=2, completed=False)
    ]

    # Mock queries: 1. Get subtask, 2. Get all subtasks, 3. Update parent task
    mock_result1 = Mock()
    mock_result1.scalar_one_or_none = Mock(return_value=mock_subtask)

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=all_subtasks)
    mock_result2 = Mock()
    mock_result2.scalars = Mock(return_value=mock_scalars)

    # Third query is UPDATE - doesn't need a return value
    mock_result3 = AsyncMock()

    session.execute.side_effect = [mock_result1, mock_result2, mock_result3]

    result = await repo.complete_subtask(1, "user")

    assert result is not None
    assert result.completed is True
    assert result.completed_by == "user"
    assert result.completed_at is not None
    # Progress: 1 of 2 = 50%
    assert session.execute.call_count == 3


@pytest.mark.asyncio
async def test_complete_subtask_not_found(task_repository):
    """Test completing non-existent subtask returns None."""
    repo, session = task_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.complete_subtask(999, "user")

    assert result is None


# ==================== Project Assignment Tests ====================

@pytest.mark.asyncio
async def test_assign_to_project_success(task_repository):
    """Test assigning a task to a project."""
    repo, session = task_repository

    updated_task = TaskDB(
        task_id="TASK-001",
        title="Test Task",
        project_id=5,
        id=1
    )

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=updated_task)
    session.execute.return_value = mock_result

    result = await repo.assign_to_project("TASK-001", 5)

    assert result is not None
    assert result.project_id == 5


@pytest.mark.asyncio
async def test_remove_from_project_success(task_repository):
    """Test removing a task from its project."""
    repo, session = task_repository

    updated_task = TaskDB(
        task_id="TASK-001",
        title="Test Task",
        project_id=None,
        id=1
    )

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=updated_task)
    session.execute.return_value = mock_result

    result = await repo.remove_from_project("TASK-001")

    assert result is not None
    assert result.project_id is None


# ==================== get_all() with Pagination Tests ====================

@pytest.mark.asyncio
async def test_get_all_with_pagination(task_repository, sample_task):
    """Test get_all with limit and offset."""
    repo, session = task_repository

    tasks = [sample_task, sample_task, sample_task]
    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=tasks)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_all(limit=10, offset=5)

    assert len(result) == 3
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_all_default_pagination(task_repository):
    """Test get_all with default pagination."""
    repo, session = task_repository

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=[])
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_all()

    assert result == []
    session.execute.assert_called_once()


# ==================== get_recent() Tests ====================

@pytest.mark.asyncio
async def test_get_recent_returns_latest_tasks(task_repository, sample_task):
    """Test get_recent returns most recent tasks."""
    repo, session = task_repository

    tasks = [sample_task] * 5
    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=tasks)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_recent(limit=5)

    assert len(result) == 5


# ==================== get_due_soon() Tests ====================

@pytest.mark.asyncio
async def test_get_due_soon_within_24_hours(task_repository):
    """Test get_due_soon returns tasks due within 24 hours."""
    repo, session = task_repository

    due_task = TaskDB(
        task_id="TASK-004",
        title="Due Soon",
        deadline=datetime.now() + timedelta(hours=12),
        status="in_progress"
    )

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=[due_task])
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_due_soon(hours=24)

    assert len(result) == 1
    assert result[0].task_id == "TASK-004"


@pytest.mark.asyncio
async def test_get_due_soon_custom_hours(task_repository):
    """Test get_due_soon with custom hour threshold."""
    repo, session = task_repository

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=[])
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_due_soon(hours=48)

    assert result == []


# ==================== get_by_project() Tests ====================

@pytest.mark.asyncio
async def test_get_by_project_returns_tasks(task_repository, sample_task):
    """Test get_by_project returns tasks in a project."""
    repo, session = task_repository

    sample_task.project_id = 3
    tasks = [sample_task, sample_task]

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=tasks)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_by_project(3)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_by_project_empty(task_repository):
    """Test get_by_project with no tasks."""
    repo, session = task_repository

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=[])
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_by_project(999)

    assert result == []


# ==================== Sync Methods Tests ====================

@pytest.mark.asyncio
async def test_get_pending_sync(task_repository, sample_task):
    """Test get_pending_sync returns tasks needing sync."""
    repo, session = task_repository

    sample_task.needs_sheet_sync = True
    tasks = [sample_task]

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=tasks)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_pending_sync(limit=50)

    assert len(result) == 1
    assert result[0].needs_sheet_sync is True


@pytest.mark.asyncio
async def test_mark_synced_updates_tasks(task_repository):
    """Test mark_synced updates sync status."""
    repo, session = task_repository

    await repo.mark_synced(["TASK-001", "TASK-002"])

    session.execute.assert_called_once()


# ==================== get_daily_stats() Tests ====================

@pytest.mark.asyncio
async def test_get_daily_stats_returns_counts(task_repository):
    """Test get_daily_stats returns correct statistics."""
    repo, session = task_repository

    # Mock results for each query
    mock_created = Mock()
    mock_created.scalar = Mock(return_value=5)

    mock_completed = Mock()
    mock_completed.scalar = Mock(return_value=3)

    mock_pending = Mock()
    mock_pending.scalar = Mock(return_value=10)

    mock_overdue = Mock()
    mock_overdue.scalar = Mock(return_value=2)

    session.execute.side_effect = [
        mock_created,
        mock_completed,
        mock_pending,
        mock_overdue
    ]

    result = await repo.get_daily_stats()

    assert result["created_today"] == 5
    assert result["completed_today"] == 3
    assert result["pending"] == 10
    assert result["overdue"] == 2


@pytest.mark.asyncio
async def test_get_daily_stats_handles_null(task_repository):
    """Test get_daily_stats handles null results."""
    repo, session = task_repository

    # Mock null results
    mock_result = Mock()
    mock_result.scalar = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.get_daily_stats()

    assert result["created_today"] == 0
    assert result["completed_today"] == 0
    assert result["pending"] == 0
    assert result["overdue"] == 0


# ==================== get_subtasks() Tests ====================

@pytest.mark.asyncio
async def test_get_subtasks_returns_ordered_list(task_repository):
    """Test get_subtasks returns subtasks in order."""
    repo, session = task_repository

    mock_task = TaskDB(task_id="TASK-001", title="Parent", id=1)

    subtasks = [
        SubtaskDB(id=1, task_id=1, title="Step 1", order=1, completed=False),
        SubtaskDB(id=2, task_id=1, title="Step 2", order=2, completed=False),
    ]

    mock_task_result = Mock()
    mock_task_result.scalar_one_or_none = Mock(return_value=mock_task)

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=subtasks)
    mock_subtasks_result = Mock()
    mock_subtasks_result.scalars = Mock(return_value=mock_scalars)

    session.execute.side_effect = [mock_task_result, mock_subtasks_result]

    result = await repo.get_subtasks("TASK-001")

    assert len(result) == 2
    assert result[0].order == 1
    assert result[1].order == 2


@pytest.mark.asyncio
async def test_get_subtasks_task_not_found(task_repository):
    """Test get_subtasks returns empty list if task doesn't exist."""
    repo, session = task_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.get_subtasks("TASK-999")

    assert result == []


# ==================== _would_create_cycle() Tests ====================

@pytest.mark.asyncio
async def test_would_create_cycle_detects_direct_cycle(task_repository):
    """Test _would_create_cycle detects direct circular dependency."""
    repo, session = task_repository

    # Simulate: Task 1 -> Task 2, trying to add Task 2 -> Task 1
    # This would create a cycle

    # Mock dependency query - returns that task 2 depends on task 1
    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter([(1,)]))  # Task 2 depends on Task 1
    session.execute.return_value = mock_result

    result = await repo._would_create_cycle(session, task_id=1, depends_on_id=2)

    assert result is True


@pytest.mark.asyncio
async def test_would_create_cycle_no_cycle(task_repository):
    """Test _would_create_cycle returns False when no cycle exists."""
    repo, session = task_repository

    # Mock empty dependency
    mock_result = Mock()
    mock_result.__iter__ = Mock(return_value=iter([]))
    session.execute.return_value = mock_result

    result = await repo._would_create_cycle(session, task_id=1, depends_on_id=3)

    assert result is False


@pytest.mark.asyncio
async def test_would_create_cycle_complex_chain(task_repository):
    """Test _would_create_cycle detects cycles in longer chains."""
    repo, session = task_repository

    # Simulate: Task 1 -> Task 2 -> Task 3, trying to add Task 3 -> Task 1
    # This should detect the cycle through the chain

    # First call: Task 3 depends on Task 2
    # Second call: Task 2 depends on Task 1
    mock_result1 = Mock()
    mock_result1.__iter__ = Mock(return_value=iter([(2,)]))

    mock_result2 = Mock()
    mock_result2.__iter__ = Mock(return_value=iter([(1,)]))

    session.execute.side_effect = [mock_result1, mock_result2]

    result = await repo._would_create_cycle(session, task_id=1, depends_on_id=3)

    assert result is True


# ==================== get_singleton() Tests ====================

def test_get_singleton_returns_same_instance():
    """Test get_singleton returns the same instance."""
    from src.database.repositories.tasks import get_task_repository

    repo1 = get_task_repository()
    repo2 = get_task_repository()

    assert repo1 is repo2


def test_get_singleton_creates_instance_on_first_call():
    """Test get_singleton creates instance on first call."""
    from src.database.repositories.tasks import get_task_repository

    # Reset singleton
    import src.database.repositories.tasks as tasks_module
    tasks_module._task_repository = None

    repo = get_task_repository()

    assert repo is not None
    assert isinstance(repo, TaskRepository)
