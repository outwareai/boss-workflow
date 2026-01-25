"""
Unit tests for UndoManager.

Tests the enterprise undo/redo system functionality.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.operations.undo_manager import UndoManager, get_undo_manager


@pytest.fixture
def undo_manager():
    """Create a fresh undo manager instance for testing."""
    return UndoManager()


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


class TestUndoManager:
    """Test suite for UndoManager."""

    @pytest.mark.asyncio
    async def test_record_action(self, undo_manager, mock_db_session):
        """Test recording an undoable action."""
        with patch.object(undo_manager.db, 'session') as mock_session_context:
            mock_session_context.return_value.__aenter__.return_value = mock_db_session

            # Mock the UndoHistoryDB creation
            mock_db_session.flush = AsyncMock()

            action_id = await undo_manager.record_action(
                user_id="123",
                action_type="delete_task",
                action_data={"task_id": "TASK-001"},
                undo_function="restore_task",
                undo_data={"task_data": {"task_id": "TASK-001", "title": "Test"}},
                description="Deleted task TASK-001"
            )

            # Verify session operations
            assert mock_db_session.add.called
            assert mock_db_session.flush.called

    @pytest.mark.asyncio
    async def test_get_undo_history(self, undo_manager):
        """Test retrieving undo history."""
        # Mock cache miss
        with patch('src.operations.undo_manager.cache') as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()

            with patch.object(undo_manager.db, 'session') as mock_session_context:
                mock_db_session = AsyncMock()
                mock_session_context.return_value.__aenter__.return_value = mock_db_session

                # Mock database result
                mock_result = MagicMock()
                mock_record = MagicMock()
                mock_record.id = 1
                mock_record.action_type = "delete_task"
                mock_record.description = "Deleted task TASK-001"
                mock_record.timestamp = datetime.utcnow()
                mock_record.metadata = {}

                mock_result.scalars.return_value.all.return_value = [mock_record]
                mock_db_session.execute = AsyncMock(return_value=mock_result)

                history = await undo_manager.get_undo_history("123", limit=10)

                assert len(history) == 1
                assert history[0]["id"] == 1
                assert history[0]["action_type"] == "delete_task"

    @pytest.mark.asyncio
    async def test_undo_no_actions(self, undo_manager):
        """Test undo when no actions are available."""
        with patch.object(undo_manager.db, 'session') as mock_session_context:
            mock_db_session = AsyncMock()
            mock_session_context.return_value.__aenter__.return_value = mock_db_session

            # Mock no records found
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db_session.execute = AsyncMock(return_value=mock_result)

            result = await undo_manager.undo_action("123")

            assert result["success"] is False
            assert "No action to undo" in result["message"]

    @pytest.mark.asyncio
    async def test_undo_already_undone(self, undo_manager):
        """Test undo when action is already undone."""
        with patch.object(undo_manager.db, 'session') as mock_session_context:
            mock_db_session = AsyncMock()
            mock_session_context.return_value.__aenter__.return_value = mock_db_session

            # Mock already undone record
            mock_record = MagicMock()
            mock_record.is_undone = True

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_record
            mock_db_session.execute = AsyncMock(return_value=mock_result)

            result = await undo_manager.undo_action("123")

            assert result["success"] is False
            assert "already undone" in result["message"]

    @pytest.mark.asyncio
    async def test_cleanup_old_history(self, undo_manager):
        """Test cleanup of old undo records."""
        with patch.object(undo_manager.db, 'session') as mock_session_context:
            mock_db_session = AsyncMock()
            mock_session_context.return_value.__aenter__.return_value = mock_db_session

            # Mock deletion result
            mock_result = MagicMock()
            mock_result.rowcount = 5
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            mock_db_session.commit = AsyncMock()

            count = await undo_manager.cleanup_old_history()

            assert count == 5
            assert mock_db_session.execute.called
            assert mock_db_session.commit.called

    def test_get_undo_manager_singleton(self):
        """Test that get_undo_manager returns singleton instance."""
        manager1 = get_undo_manager()
        manager2 = get_undo_manager()

        assert manager1 is manager2


class TestUndoFunctions:
    """Test undo function execution."""

    @pytest.mark.asyncio
    async def test_undo_delete_task(self, undo_manager):
        """Test undoing a task deletion."""
        mock_session = AsyncMock()

        with patch('src.operations.undo_manager.get_task_repository') as mock_repo:
            mock_task_repo = AsyncMock()
            mock_task = MagicMock()
            mock_task.task_id = "TASK-001"
            mock_task_repo.create = AsyncMock(return_value=mock_task)
            mock_repo.return_value = mock_task_repo

            result = await undo_manager._undo_delete_task(
                mock_session,
                {"task_data": {"task_id": "TASK-001", "title": "Test"}}
            )

            assert result["task_id"] == "TASK-001"
            assert result["restored"] is True

    @pytest.mark.asyncio
    async def test_undo_status_change(self, undo_manager):
        """Test undoing a status change."""
        mock_session = AsyncMock()

        with patch('src.operations.undo_manager.get_task_repository') as mock_repo:
            mock_task_repo = AsyncMock()
            mock_task_repo.update = AsyncMock()
            mock_repo.return_value = mock_task_repo

            result = await undo_manager._undo_status_change(
                mock_session,
                {"task_id": "TASK-001", "old_status": "pending"}
            )

            assert result["task_id"] == "TASK-001"
            assert result["status"] == "pending"
            mock_task_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_undo_unknown_function(self, undo_manager):
        """Test executing unknown undo function raises error."""
        mock_session = AsyncMock()

        with pytest.raises(ValueError, match="Unknown undo function"):
            await undo_manager._execute_undo(
                mock_session,
                "unknown_function",
                {}
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
