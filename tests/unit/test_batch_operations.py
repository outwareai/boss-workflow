"""
Unit tests for batch operations.

Q1 2026: Tests for enterprise batch system with dry-run, transactions, and progress tracking.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.operations.batch import BatchOperations, BatchOperationResult


@pytest.fixture
def batch_ops():
    """Create a BatchOperations instance for testing."""
    return BatchOperations()


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_task_repo(monkeypatch):
    """Mock task repository."""
    repo = MagicMock()
    repo.get_by_assignee = AsyncMock(return_value=[
        {"task_id": "TASK-001", "status": "pending", "assignee": "John"},
        {"task_id": "TASK-002", "status": "in_progress", "assignee": "John"},
        {"task_id": "TASK-003", "status": "completed", "assignee": "John"},
    ])
    repo.update = AsyncMock()
    repo.get_by_id = AsyncMock(return_value={"task_id": "TASK-001", "title": "Test"})
    repo.delete = AsyncMock()

    def mock_get_task_repo():
        return repo

    monkeypatch.setattr("src.operations.batch.get_task_repository", mock_get_task_repo)
    return repo


class TestBatchOperationResult:
    """Test BatchOperationResult class."""

    def test_add_success(self):
        """Test adding successful operations."""
        result = BatchOperationResult()
        result.add_success("TASK-001")
        result.add_success("TASK-002")

        assert len(result.succeeded) == 2
        assert "TASK-001" in result.succeeded

    def test_add_failure(self):
        """Test adding failed operations."""
        result = BatchOperationResult()
        result.add_failure("TASK-001", "Task not found")

        assert len(result.failed) == 1
        assert result.failed[0]["id"] == "TASK-001"
        assert result.failed[0]["error"] == "Task not found"

    def test_add_skip(self):
        """Test adding skipped operations."""
        result = BatchOperationResult()
        result.add_skip("TASK-001", "Already completed")

        assert len(result.skipped) == 1
        assert result.skipped[0]["id"] == "TASK-001"
        assert result.skipped[0]["reason"] == "Already completed"

    def test_finalize(self):
        """Test finalizing result."""
        result = BatchOperationResult()
        result.add_success("TASK-001")
        result.add_failure("TASK-002", "Error")
        result.add_skip("TASK-003", "Skip reason")

        result.finalize()

        assert result.total == 3
        assert result.end_time is not None

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = BatchOperationResult()
        result.add_success("TASK-001")
        result.add_failure("TASK-002", "Error")
        result.finalize()

        data = result.to_dict()

        assert data["success_count"] == 1
        assert data["failure_count"] == 1
        assert data["total"] == 2
        assert "duration_seconds" in data


@pytest.mark.asyncio
class TestBatchOperations:
    """Test BatchOperations class."""

    async def test_execute_batch_success(self, batch_ops, mock_session, mock_task_repo):
        """Test successful batch execution."""
        items = ["TASK-001", "TASK-002"]

        async def mock_operation(sess, item_id):
            await mock_task_repo.update(item_id, {"status": "completed"})

        result = await batch_ops.execute_batch(
            session=mock_session,
            operation_name="test_operation",
            items=items,
            operation_func=mock_operation,
            dry_run=False,
            user_id="test_user"
        )

        assert result.total == 2
        assert len(result.succeeded) == 2
        assert len(result.failed) == 0
        mock_session.commit.assert_called_once()

    async def test_execute_batch_dry_run(self, batch_ops, mock_session, mock_task_repo):
        """Test dry-run mode doesn't modify database."""
        items = ["TASK-001", "TASK-002"]

        async def mock_operation(sess, item_id):
            await mock_task_repo.update(item_id, {"status": "completed"})

        result = await batch_ops.execute_batch(
            session=mock_session,
            operation_name="test_operation",
            items=items,
            operation_func=mock_operation,
            dry_run=True,
            user_id="test_user"
        )

        # Dry run should rollback, not commit
        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    async def test_execute_batch_exceeds_max_size(self, batch_ops, mock_session):
        """Test batch size validation."""
        items = [f"TASK-{i:03d}" for i in range(150)]  # Exceeds max of 100

        async def mock_operation(sess, item_id):
            pass

        with pytest.raises(ValueError, match="exceeds max"):
            await batch_ops.execute_batch(
                session=mock_session,
                operation_name="test_operation",
                items=items,
                operation_func=mock_operation
            )

    async def test_execute_batch_partial_failure(self, batch_ops, mock_session, mock_task_repo):
        """Test batch with some failures."""
        items = ["TASK-001", "TASK-002", "TASK-003"]

        async def mock_operation(sess, item_id):
            if item_id == "TASK-002":
                raise ValueError("Task validation failed")
            await mock_task_repo.update(item_id, {"status": "completed"})

        result = await batch_ops.execute_batch(
            session=mock_session,
            operation_name="test_operation",
            items=items,
            operation_func=mock_operation,
            dry_run=False
        )

        assert result.total == 3
        assert len(result.succeeded) == 2
        assert len(result.failed) == 1
        assert result.failed[0]["id"] == "TASK-002"

    async def test_complete_all_for_assignee(self, batch_ops, mock_session, mock_task_repo):
        """Test completing all tasks for an assignee."""
        result = await batch_ops.complete_all_for_assignee(
            session=mock_session,
            assignee="John",
            dry_run=False,
            user_id="boss"
        )

        assert result["success"] is True
        assert result["assignee"] == "John"
        # Should only complete pending and in_progress tasks (2 out of 3)
        assert result["result"]["total"] == 2

    async def test_complete_all_no_tasks(self, batch_ops, mock_session, mock_task_repo):
        """Test completing when no tasks exist."""
        # Mock empty task list
        mock_task_repo.get_by_assignee = AsyncMock(return_value=[])

        result = await batch_ops.complete_all_for_assignee(
            session=mock_session,
            assignee="NonExistent",
            dry_run=False
        )

        assert "No tasks to complete" in result["message"]

    async def test_reassign_all(self, batch_ops, mock_session, mock_task_repo):
        """Test reassigning all tasks."""
        result = await batch_ops.reassign_all(
            session=mock_session,
            from_assignee="John",
            to_assignee="Sarah",
            dry_run=False,
            user_id="boss"
        )

        assert result["success"] is True
        assert result["from_assignee"] == "John"
        assert result["to_assignee"] == "Sarah"
        assert result["result"]["total"] == 3

    async def test_reassign_with_status_filter(self, batch_ops, mock_session, mock_task_repo):
        """Test reassigning with status filter."""
        result = await batch_ops.reassign_all(
            session=mock_session,
            from_assignee="John",
            to_assignee="Sarah",
            status_filter=["pending"],
            dry_run=False
        )

        assert result["success"] is True
        # Should only reassign pending tasks (1 out of 3)
        assert result["result"]["total"] == 1

    async def test_bulk_status_change(self, batch_ops, mock_session, mock_task_repo):
        """Test bulk status change."""
        task_ids = ["TASK-001", "TASK-002"]

        result = await batch_ops.bulk_status_change(
            session=mock_session,
            task_ids=task_ids,
            new_status="blocked",
            dry_run=False,
            user_id="boss"
        )

        assert result["success"] is True
        assert result["status"] == "blocked"
        assert result["result"]["total"] == 2

    async def test_bulk_delete(self, batch_ops, mock_session, mock_task_repo):
        """Test bulk delete."""
        task_ids = ["TASK-001", "TASK-002"]

        result = await batch_ops.bulk_delete(
            session=mock_session,
            task_ids=task_ids,
            dry_run=False,
            user_id="boss"
        )

        assert result["success"] is True
        assert result["result"]["total"] == 2
        assert mock_task_repo.delete.call_count == 2

    async def test_bulk_add_tags(self, batch_ops, mock_session, mock_task_repo):
        """Test bulk add tags."""
        task_ids = ["TASK-001", "TASK-002"]
        tags = ["urgent", "frontend"]

        # Mock task with existing tags
        mock_task_repo.get_by_id = AsyncMock(return_value={
            "task_id": "TASK-001",
            "tags": ["backend"]
        })

        result = await batch_ops.bulk_add_tags(
            session=mock_session,
            task_ids=task_ids,
            tags=tags,
            dry_run=False,
            user_id="boss"
        )

        assert result["success"] is True
        assert result["tags"] == tags
        assert result["result"]["total"] == 2

    async def test_batch_cancellation(self, batch_ops, mock_session, mock_task_repo, monkeypatch):
        """Test cancelling a batch operation."""
        from src.cache.redis_client import cache

        # Mock cache to simulate cancellation
        async def mock_get(key):
            if ":cancel" in key:
                return True  # Simulate cancellation flag
            return None

        monkeypatch.setattr(cache, "get", mock_get)
        monkeypatch.setattr(cache, "set", AsyncMock())
        monkeypatch.setattr(cache, "delete", AsyncMock())

        items = ["TASK-001", "TASK-002", "TASK-003"]

        async def mock_operation(sess, item_id):
            pass

        result = await batch_ops.execute_batch(
            session=mock_session,
            operation_name="test_cancel",
            items=items,
            operation_func=mock_operation,
            dry_run=False
        )

        # All items should be skipped due to cancellation
        assert len(result.skipped) == 3
        assert all("cancelled" in s["reason"].lower() for s in result.skipped)

    async def test_progress_tracking(self, batch_ops, mock_session, mock_task_repo, monkeypatch):
        """Test progress tracking during batch execution."""
        from src.cache.redis_client import cache

        progress_updates = []

        async def mock_set(key, value, ttl=None):
            if "batch:" in key and ":cancel" not in key:
                progress_updates.append(value)

        monkeypatch.setattr(cache, "set", mock_set)
        monkeypatch.setattr(cache, "get", AsyncMock(return_value=None))
        monkeypatch.setattr(cache, "delete", AsyncMock())

        items = ["TASK-001", "TASK-002", "TASK-003"]

        async def mock_operation(sess, item_id):
            pass

        await batch_ops.execute_batch(
            session=mock_session,
            operation_name="test_progress",
            items=items,
            operation_func=mock_operation,
            dry_run=False
        )

        # Should have progress updates for each item
        assert len(progress_updates) == 3
        assert progress_updates[0]["current"] == 1
        assert progress_updates[-1]["current"] == 3
        assert progress_updates[-1]["percent"] == 100.0
