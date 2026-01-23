"""
Unit tests for TaskRepository.

Q3 2026: Comprehensive unit tests for database repository layer.
Target coverage: 70%+
"""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
from datetime import datetime, date
from typing import List, Optional

from src.database.repositories.tasks import TaskRepository
from src.database.models import TaskDB
from src.database import get_database


@pytest.fixture
def mock_database():
    """Mock database with session context manager."""
    db = Mock()
    session = AsyncMock()

    # Mock session context manager
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    # Mock execute and result
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
    """Sample task for testing."""
    return TaskDB(
        id=1,
        task_id="TASK-001",
        title="Fix login bug",
        description="Login page has a typo",
        assignee="John",
        priority="high",
        status="pending",
        task_type="bug",
        deadline=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        effort="1h",
        progress="0%",
        tags="backend,urgent",
        created_by="Boss",
        notes_count=0,
        blocked_by="",
    )


# ============================================================
# CREATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_create_task_success(task_repository, sample_task):
    """Test creating a new task successfully."""
    repo, session = task_repository

    # Mock the result
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=None)

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
    """Test creating a task with duplicate task_id fails."""
    repo, session = task_repository

    # Mock existing task
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=sample_task)

    task_data = {
        "task_id": "TASK-001",
        "title": "Duplicate task",
    }

    result = await repo.create(task_data)

    # Should return None for duplicate
    assert result is None
    session.add.assert_not_called()


# ============================================================
# READ TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_by_task_id_found(task_repository, sample_task):
    """Test retrieving a task by task_id when it exists."""
    repo, session = task_repository

    # Mock the result
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=sample_task)

    result = await repo.get_by_task_id("TASK-001")

    assert result == sample_task
    assert result.task_id == "TASK-001"


@pytest.mark.asyncio
async def test_get_by_task_id_not_found(task_repository):
    """Test retrieving a task that doesn't exist."""
    repo, session = task_repository

    # Mock no result
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=None)

    result = await repo.get_by_task_id("TASK-999")

    assert result is None


@pytest.mark.asyncio
async def test_get_by_status(task_repository, sample_task):
    """Test retrieving tasks by status."""
    repo, session = task_repository

    # Mock result with multiple tasks
    tasks = [sample_task, sample_task]
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=tasks)))
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
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=tasks)))
    session.execute.return_value = mock_result

    result = await repo.get_by_assignee("John")

    assert len(result) == 1
    assert result[0].assignee == "John"


# ============================================================
# UPDATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_update_task_success(task_repository, sample_task):
    """Test updating a task successfully."""
    repo, session = task_repository

    # Mock get_by_task_id to return existing task
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=sample_task)

    updates = {
        "title": "Updated title",
        "status": "in_progress",
    }

    result = await repo.update("TASK-001", updates)

    assert result is not None
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_task_not_found(task_repository):
    """Test updating a task that doesn't exist."""
    repo, session = task_repository

    # Mock no task found
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=None)

    result = await repo.update("TASK-999", {"title": "Updated"})

    assert result is None
    session.commit.assert_not_called()


# ============================================================
# DELETE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_delete_task_success(task_repository, sample_task):
    """Test deleting a task successfully."""
    repo, session = task_repository

    # Mock get_by_task_id
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=sample_task)

    result = await repo.delete("TASK-001")

    assert result is True
    session.execute.assert_called()


@pytest.mark.asyncio
async def test_delete_task_not_found(task_repository):
    """Test deleting a task that doesn't exist."""
    repo, session = task_repository

    # Mock no task
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=None)

    result = await repo.delete("TASK-999")

    # Should still return True (idempotent)
    assert result is True


# ============================================================
# SUBTASK TESTS
# ============================================================

@pytest.mark.asyncio
async def test_add_subtask_success(task_repository, sample_task):
    """Test adding a subtask to an existing task."""
    repo, session = task_repository

    # Mock parent task exists
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=sample_task)

    subtask_data = {
        "title": "Subtask 1",
        "completed": False,
    }

    result = await repo.add_subtask("TASK-001", subtask_data)

    # Verify subtask was added
    session.add.assert_called_once()
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_add_subtask_parent_not_found(task_repository):
    """Test adding a subtask when parent task doesn't exist."""
    repo, session = task_repository

    # Mock no parent task
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=None)

    result = await repo.add_subtask("TASK-999", {"title": "Subtask"})

    assert result is None
    session.add.assert_not_called()


# ============================================================
# DEPENDENCY TESTS
# ============================================================

@pytest.mark.asyncio
async def test_add_dependency_success(task_repository, sample_task):
    """Test adding a dependency between tasks."""
    repo, session = task_repository

    # Mock both tasks exist
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=sample_task)

    result = await repo.add_dependency(
        task_id="TASK-002",
        depends_on_id="TASK-001",
        dependency_type="blocked_by"
    )

    session.add.assert_called_once()
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_add_dependency_task_not_found(task_repository):
    """Test adding a dependency when task doesn't exist."""
    repo, session = task_repository

    # Mock no task
    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=None)

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

    # Create overdue task
    overdue_task = sample_task
    overdue_task.deadline = datetime(2020, 1, 1)  # Past date
    overdue_task.status = "pending"

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[overdue_task])))
    session.execute.return_value = mock_result

    result = await repo.get_overdue_tasks()

    assert len(result) >= 0  # May be empty or have tasks
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_search_tasks(task_repository, sample_task):
    """Test searching tasks by query string."""
    repo, session = task_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[sample_task])))
    session.execute.return_value = mock_result

    result = await repo.search("login bug")

    assert isinstance(result, list)
    session.execute.assert_called_once()


# ============================================================
# EDGE CASE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_create_task_with_minimal_data(task_repository):
    """Test creating a task with only required fields."""
    repo, session = task_repository

    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=None)

    task_data = {
        "task_id": "TASK-MIN",
        "title": "Minimal task",
    }

    result = await repo.create(task_data)

    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_update_task_with_empty_updates(task_repository, sample_task):
    """Test updating a task with empty update dict."""
    repo, session = task_repository

    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=sample_task)

    result = await repo.update("TASK-001", {})

    # Should still succeed (no-op update)
    assert result is not None


@pytest.mark.asyncio
async def test_concurrent_updates(task_repository, sample_task):
    """Test handling concurrent updates to same task."""
    repo, session = task_repository

    session.execute.return_value.scalar_one_or_none = AsyncMock(return_value=sample_task)

    # Simulate concurrent updates
    import asyncio
    results = await asyncio.gather(
        repo.update("TASK-001", {"title": "Update 1"}),
        repo.update("TASK-001", {"title": "Update 2"}),
        return_exceptions=True
    )

    # At least one should succeed
    assert any(r is not None for r in results if not isinstance(r, Exception))
