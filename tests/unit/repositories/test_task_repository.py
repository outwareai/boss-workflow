"""
Unit tests for TaskRepository.

Q3 2026: Comprehensive unit tests for database repository layer.
Q4 2026: Fixed async mocking issues and aligned with actual implementation.
Target coverage: 70%+
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
        is_completed=False
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
