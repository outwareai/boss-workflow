"""
Unit tests for Phase 7: Enhanced Multi-Turn Planning Sessions

Tests:
- Session manager functionality
- Timeout handler behavior
- Save/resume operations
- Stale session detection
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.bot.planning_session_manager import PlanningSessionManager, get_planning_session_manager
from src.bot.planning_session_timeout import SessionTimeoutHandler, get_timeout_handler
from src.database.models import PlanningStateEnum


class TestPlanningSessionManager:
    """Test planning session manager"""

    @pytest.fixture
    def mock_ai_client(self):
        """Mock AI client"""
        client = Mock()
        client.chat_completion = AsyncMock(return_value="AI-generated summary")
        return client

    @pytest.fixture
    def session_manager(self, mock_ai_client):
        """Create session manager instance"""
        return PlanningSessionManager(mock_ai_client)

    @pytest.mark.asyncio
    async def test_get_or_create_session_no_sessions(self, session_manager):
        """Test get_or_create when no sessions exist"""
        with patch('src.bot.planning_session_manager.get_session') as mock_get_session:
            # Mock database
            mock_db = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_db

            # Mock planning repo
            mock_repo = Mock()
            mock_repo.get_active_for_user = AsyncMock(return_value=None)

            with patch('src.bot.planning_session_manager.get_planning_repository', return_value=mock_repo):
                with patch.object(session_manager, '_get_saved_sessions', return_value=[]):
                    result = await session_manager.get_or_create_session(
                        "user123",
                        "Build admin dashboard"
                    )

                    assert result["status"] == "ready"
                    assert "new planning session" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_get_or_create_session_with_active(self, session_manager):
        """Test get_or_create when active session exists"""
        with patch('src.bot.planning_session_manager.get_session') as mock_get_session:
            # Mock database
            mock_db = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_db

            # Mock active session
            mock_session = Mock()
            mock_session.session_id = "PLAN-20260125-ABC123"
            mock_session.last_activity_at = datetime.utcnow()  # Recent activity

            # Mock planning repo
            mock_repo = Mock()
            mock_repo.get_active_for_user = AsyncMock(return_value=mock_session)

            with patch('src.bot.planning_session_manager.get_planning_repository', return_value=mock_repo):
                result = await session_manager.get_or_create_session(
                    "user123",
                    "Build admin dashboard"
                )

                assert result["status"] == "active"
                assert result["session_id"] == "PLAN-20260125-ABC123"

    @pytest.mark.asyncio
    async def test_get_or_create_session_stale_auto_save(self, session_manager):
        """Test auto-save of stale sessions (>24 hours)"""
        with patch('src.bot.planning_session_manager.get_session') as mock_get_session:
            # Mock database
            mock_db = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_db

            # Mock stale session (25 hours old)
            mock_session = Mock()
            mock_session.session_id = "PLAN-20260124-OLD123"
            mock_session.last_activity_at = datetime.utcnow() - timedelta(hours=25)

            # Mock planning repo
            mock_repo = Mock()
            mock_repo.get_active_for_user = AsyncMock(return_value=mock_session)

            with patch('src.bot.planning_session_manager.get_planning_repository', return_value=mock_repo):
                with patch.object(session_manager, 'save_session_snapshot', return_value={"success": True}):
                    result = await session_manager.get_or_create_session(
                        "user123",
                        "Build admin dashboard"
                    )

                    assert result["status"] == "created"
                    assert "previous_session_saved" in result
                    assert "24 hours" in result["message"]

    @pytest.mark.asyncio
    async def test_save_session_snapshot(self, session_manager):
        """Test saving session snapshot"""
        with patch('src.bot.planning_session_manager.get_session') as mock_get_session:
            # Mock database
            mock_db = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_db

            # Mock active session
            mock_session = Mock()
            mock_session.session_id = "PLAN-20260125-ABC123"
            mock_session.state = PlanningStateEnum.REVIEWING_BREAKDOWN.value

            # Mock planning repo
            mock_repo = Mock()
            mock_repo.get_by_id_or_fail = AsyncMock(return_value=mock_session)
            mock_repo.update_state = AsyncMock()

            with patch('src.bot.planning_session_manager.get_planning_repository', return_value=mock_repo):
                result = await session_manager.save_session_snapshot("PLAN-20260125-ABC123")

                assert result["success"] is True
                assert result["session_id"] == "PLAN-20260125-ABC123"
                assert "saved_at" in result

                # Verify state was updated to SAVED
                mock_repo.update_state.assert_called_once()
                call_args = mock_repo.update_state.call_args
                assert call_args[0][1] == PlanningStateEnum.SAVED

    @pytest.mark.asyncio
    async def test_resume_session_with_context(self, session_manager):
        """Test resuming session with AI context generation"""
        with patch('src.bot.planning_session_manager.get_session') as mock_get_session:
            # Mock database
            mock_db = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_db

            # Mock saved session
            mock_session = Mock()
            mock_session.session_id = "PLAN-20260125-ABC123"
            mock_session.state = PlanningStateEnum.SAVED.value
            mock_session.project_name = "Admin Dashboard"
            mock_session.raw_input = "Build admin dashboard with user management"
            mock_session.ai_breakdown = {"tasks": []}
            mock_session.clarifying_questions = ["Question 1"]
            mock_session.user_edits = []
            mock_session.last_activity_at = datetime.utcnow()
            mock_session.task_drafts = []

            # Mock planning repo
            mock_repo = Mock()
            mock_repo.get_by_id_or_fail = AsyncMock(return_value=mock_session)
            mock_repo.update_state = AsyncMock()

            # Mock draft repo
            mock_draft_repo = Mock()

            with patch('src.bot.planning_session_manager.get_planning_repository', return_value=mock_repo):
                with patch('src.bot.planning_session_manager.get_task_draft_repository', return_value=mock_draft_repo):
                    result = await session_manager.resume_session_with_context("PLAN-20260125-ABC123")

                    assert result["success"] is True
                    assert result["session_id"] == "PLAN-20260125-ABC123"
                    assert "context_summary" in result
                    assert result["state"] == PlanningStateEnum.REVIEWING_BREAKDOWN.value

                    # Verify session was restored from SAVED
                    mock_repo.update_state.assert_called_once()


class TestSessionTimeoutHandler:
    """Test session timeout handler"""

    @pytest.fixture
    def mock_telegram(self):
        """Mock Telegram client"""
        client = Mock()
        client.send_message = AsyncMock()
        return client

    @pytest.fixture
    def timeout_handler(self, mock_telegram):
        """Create timeout handler with 1 second timeout for testing"""
        return SessionTimeoutHandler(mock_telegram, timeout_minutes=1/60)  # 1 second

    def test_start_timeout_timer(self, timeout_handler):
        """Test starting timeout timer"""
        timeout_handler.start_timeout_timer("SESSION-001", "user123", "chat456")

        assert "SESSION-001" in timeout_handler.active_timers
        assert not timeout_handler.active_timers["SESSION-001"].done()

    def test_cancel_timeout_timer(self, timeout_handler):
        """Test cancelling timeout timer"""
        timeout_handler.start_timeout_timer("SESSION-001", "user123", "chat456")
        timeout_handler.cancel_timeout_timer("SESSION-001")

        assert "SESSION-001" not in timeout_handler.active_timers

    def test_reset_timeout_timer(self, timeout_handler):
        """Test resetting timeout timer restarts it"""
        timeout_handler.start_timeout_timer("SESSION-001", "user123", "chat456")
        first_task = timeout_handler.active_timers["SESSION-001"]

        timeout_handler.reset_timeout_timer("SESSION-001", "user123", "chat456")
        second_task = timeout_handler.active_timers["SESSION-001"]

        # Should be a different task
        assert first_task != second_task
        assert first_task.cancelled()

    @pytest.mark.asyncio
    async def test_timeout_triggers_auto_save(self, timeout_handler, mock_telegram):
        """Test that timeout triggers auto-save and notification"""
        with patch('src.bot.planning_session_timeout.get_deepseek_client') as mock_ai:
            with patch('src.bot.planning_session_timeout.get_planning_session_manager') as mock_sm:
                # Mock session manager
                mock_manager = Mock()
                mock_manager.save_session_snapshot = AsyncMock(return_value={"success": True})
                mock_sm.return_value = mock_manager

                # Start timer with very short timeout (1 second)
                timeout_handler.start_timeout_timer("SESSION-001", "user123", "chat456")

                # Wait for timeout
                await asyncio.sleep(1.5)

                # Verify save was called
                mock_manager.save_session_snapshot.assert_called_once_with("SESSION-001")

                # Verify notification was sent
                mock_telegram.send_message.assert_called_once()
                call_args = mock_telegram.send_message.call_args
                assert "chat456" in call_args[0]
                assert "auto-saved" in call_args[0][1].lower()

    def test_get_session_timer_status(self, timeout_handler):
        """Test getting timer status"""
        # No timer
        assert timeout_handler.get_session_timer_status("SESSION-001") is None

        # Active timer
        timeout_handler.start_timeout_timer("SESSION-001", "user123", "chat456")
        assert timeout_handler.get_session_timer_status("SESSION-001") == "active"

        # Cancelled timer
        timeout_handler.cancel_timeout_timer("SESSION-001")
        assert timeout_handler.get_session_timer_status("SESSION-001") is None

    @pytest.mark.asyncio
    async def test_cancel_all_timers(self, timeout_handler):
        """Test cancelling all timers"""
        # Start multiple timers
        timeout_handler.start_timeout_timer("SESSION-001", "user1", "chat1")
        timeout_handler.start_timeout_timer("SESSION-002", "user2", "chat2")
        timeout_handler.start_timeout_timer("SESSION-003", "user3", "chat3")

        assert timeout_handler.get_active_timer_count() == 3

        # Cancel all
        await timeout_handler.cancel_all_timers()

        assert timeout_handler.get_active_timer_count() == 0


@pytest.mark.asyncio
async def test_full_session_lifecycle():
    """
    Integration test: Full session lifecycle

    1. Create session
    2. Activity resets timer
    3. Timeout triggers save
    4. Resume session
    """
    # This would be an integration test requiring full DB setup
    # Placeholder for future implementation
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
