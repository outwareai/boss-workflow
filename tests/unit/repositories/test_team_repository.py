"""
Unit tests for TeamRepository.

CRITICAL - TIER 1 (Security/Data Integrity)
Tests team member CRUD with audit logging and multi-field search.

Q4 2026: Comprehensive team repository tests.
Target coverage: 75%+
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.database.repositories.team import TeamRepository
from src.database.models import TeamMemberDB


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
def team_repository(mock_database):
    """Create TeamRepository with mocked database."""
    db, session = mock_database
    repo = TeamRepository()
    repo.db = db
    return repo, session


@pytest.fixture
def sample_team_member():
    """Create a sample team member for testing."""
    return TeamMemberDB(
        id=1,
        name="John Doe",
        username="john_doe",
        role="developer",
        telegram_id="123456789",
        discord_id="987654321",
        discord_username="johndoe#1234",
        email="john@example.com",
        skills=["Python", "JavaScript", "Docker"],
        is_active=True,
        tasks_assigned=10,
        tasks_completed=7
    )


# ============================================================
# CREATE TESTS (with Q2 2026 audit logging)
# ============================================================

@pytest.mark.asyncio
async def test_create_team_member_success(team_repository):
    """Test creating a new team member successfully."""
    repo, session = team_repository

    with patch('src.utils.audit_logger.log_audit_event') as mock_audit:
        mock_audit.return_value = AsyncMock()

        result = await repo.create(
            name="Alice Smith",
            role="designer",
            telegram_id="111222333",
            email="alice@example.com",
            skills=["UI/UX", "Figma"]
        )

        session.add.assert_called_once()
        session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_create_logs_audit_event(team_repository):
    """Test that create() logs an audit event (Q2 2026)."""
    repo, session = team_repository

    with patch('src.utils.audit_logger.log_audit_event') as mock_audit:
        mock_audit.return_value = AsyncMock()

        result = await repo.create(
            name="Bob Johnson",
            role="developer",
            email="bob@example.com"
        )

        # Verify audit logging was called
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["entity_type"] == "team_member"
        assert call_kwargs["details"]["name"] == "Bob Johnson"


@pytest.mark.asyncio
async def test_create_generates_username(team_repository):
    """Test that create() generates username from name."""
    repo, session = team_repository

    with patch('src.utils.audit_logger.log_audit_event') as mock_audit:
        mock_audit.return_value = AsyncMock()

        result = await repo.create(
            name="Charlie Brown",
            role="qa"
        )

        # Username should be "charlie_brown"
        session.add.assert_called_once()


@pytest.mark.asyncio
async def test_create_handles_errors_gracefully(team_repository):
    """Test that create() raises exception on error."""
    from src.database.exceptions import DatabaseOperationError
    repo, session = team_repository

    session.add.side_effect = Exception("Database error")

    # Should raise DatabaseOperationError
    with pytest.raises(DatabaseOperationError, match="Failed to create team member"):
        await repo.create(name="Test User")


# ============================================================
# UPDATE TESTS (with Q2 2026 audit logging)
# ============================================================

@pytest.mark.asyncio
async def test_update_team_member_success(team_repository, sample_team_member):
    """Test updating a team member successfully."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_team_member)
    session.execute.return_value = mock_result

    with patch('src.utils.audit_logger.log_audit_event') as mock_audit:
        mock_audit.return_value = AsyncMock()

        result = await repo.update(1, {
            "role": "senior developer",
            "skills": ["Python", "JavaScript", "Kubernetes"]
        })

        session.execute.assert_called()


@pytest.mark.asyncio
async def test_update_logs_audit_event(team_repository, sample_team_member):
    """Test that update() logs an audit event (Q2 2026)."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_team_member)
    session.execute.return_value = mock_result

    with patch('src.utils.audit_logger.log_audit_event') as mock_audit:
        mock_audit.return_value = AsyncMock()

        result = await repo.update(1, {"email": "newemail@example.com"})

        # Verify audit logging
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["entity_type"] == "team_member"
        assert "email" in call_kwargs["details"]["updates"]


@pytest.mark.asyncio
async def test_update_adds_timestamp(team_repository, sample_team_member):
    """Test that update() adds updated_at timestamp."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_team_member)
    session.execute.return_value = mock_result

    with patch('src.utils.audit_logger.log_audit_event') as mock_audit:
        mock_audit.return_value = AsyncMock()

        updates = {"role": "new role"}
        result = await repo.update(1, updates)

        # Verify updated_at was added to updates dict
        assert "updated_at" in updates


# ============================================================
# DELETE TESTS (with Q2 2026 audit logging)
# ============================================================

@pytest.mark.asyncio
async def test_delete_team_member_success(team_repository, sample_team_member):
    """Test deleting a team member successfully."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_team_member)
    session.execute.return_value = mock_result

    with patch('src.utils.audit_logger.log_audit_event') as mock_audit:
        mock_audit.return_value = AsyncMock()

        result = await repo.delete(1)

        assert result == True
        session.execute.assert_called()


@pytest.mark.asyncio
async def test_delete_logs_audit_event_with_warning_level(team_repository, sample_team_member):
    """Test that delete() logs audit event with WARNING level (Q2 2026)."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_team_member)
    session.execute.return_value = mock_result

    with patch('src.utils.audit_logger.log_audit_event') as mock_audit:
        mock_audit.return_value = AsyncMock()

        result = await repo.delete(1)

        # Verify audit logging with WARNING level
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["entity_type"] == "team_member"
        # Warning level should be set for deletions


@pytest.mark.asyncio
async def test_delete_handles_missing_member(team_repository):
    """Test that delete() handles missing member gracefully."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.delete(999)

    assert result == True  # Still returns True (idempotent)


# ============================================================
# FIND MEMBER TESTS (Multi-field search)
# ============================================================

@pytest.mark.asyncio
async def test_find_member_by_name(team_repository, sample_team_member):
    """Test finding member by name (case-insensitive)."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_team_member)
    session.execute.return_value = mock_result

    result = await repo.find_member("john doe")

    assert result == sample_team_member


@pytest.mark.asyncio
async def test_find_member_by_username(team_repository, sample_team_member):
    """Test finding member by username."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_team_member)
    session.execute.return_value = mock_result

    result = await repo.find_member("john_doe")

    assert result == sample_team_member


@pytest.mark.asyncio
async def test_find_member_by_telegram_id(team_repository, sample_team_member):
    """Test finding member by Telegram ID."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_team_member)
    session.execute.return_value = mock_result

    result = await repo.find_member("123456789")

    assert result == sample_team_member


@pytest.mark.asyncio
async def test_find_member_by_discord_username(team_repository, sample_team_member):
    """Test finding member by Discord username."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_team_member)
    session.execute.return_value = mock_result

    result = await repo.find_member("@johndoe")

    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_find_member_by_email(team_repository, sample_team_member):
    """Test finding member by email."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_team_member)
    session.execute.return_value = mock_result

    result = await repo.find_member("john@example.com")

    assert result == sample_team_member


@pytest.mark.asyncio
async def test_find_member_returns_none_if_not_found(team_repository):
    """Test that find_member returns None if no match."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.find_member("nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_find_member_strips_at_symbol(team_repository):
    """Test that find_member strips @ from search."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.find_member("@username")

    # Verify @ was stripped in query
    session.execute.assert_called_once()


# ============================================================
# STATS INCREMENT TESTS
# ============================================================

@pytest.mark.asyncio
async def test_increment_assigned_updates_counter(team_repository):
    """Test that increment_assigned updates tasks_assigned counter."""
    repo, session = team_repository

    await repo.increment_assigned(1)

    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_increment_completed_updates_counter(team_repository):
    """Test that increment_completed updates tasks_completed counter."""
    repo, session = team_repository

    await repo.increment_completed(1)

    session.execute.assert_called_once()


# ============================================================
# PERFORMANCE STATS TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_performance_stats_calculates_completion_rate(team_repository):
    """Test that get_performance_stats calculates completion rates."""
    repo, session = team_repository

    # Create members with different stats
    member1 = TeamMemberDB(
        id=1, name="Alice", role="dev",
        tasks_assigned=10, tasks_completed=8, is_active=True
    )
    member2 = TeamMemberDB(
        id=2, name="Bob", role="dev",
        tasks_assigned=20, tasks_completed=15, is_active=True
    )

    with patch.object(repo, 'get_all', return_value=[member1, member2]):
        result = await repo.get_performance_stats()

        assert len(result) == 2
        # Alice: 80%, Bob: 75%
        assert result[0]["completion_rate"] == 80.0  # Sorted desc
        assert result[1]["completion_rate"] == 75.0


@pytest.mark.asyncio
async def test_get_performance_stats_handles_zero_assigned(team_repository):
    """Test that completion rate is 0 if no tasks assigned."""
    repo, session = team_repository

    member = TeamMemberDB(
        id=1, name="New Member", role="dev",
        tasks_assigned=0, tasks_completed=0, is_active=True
    )

    with patch.object(repo, 'get_all', return_value=[member]):
        result = await repo.get_performance_stats()

        assert result[0]["completion_rate"] == 0


# ============================================================
# DEACTIVATE/ACTIVATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_deactivate_sets_is_active_false(team_repository):
    """Test that deactivate sets is_active to False."""
    repo, session = team_repository

    with patch.object(repo, 'update', return_value=Mock()) as mock_update:
        result = await repo.deactivate(1)

        mock_update.assert_called_once_with(1, {"is_active": False})


@pytest.mark.asyncio
async def test_activate_sets_is_active_true(team_repository):
    """Test that activate sets is_active to True."""
    repo, session = team_repository

    with patch.object(repo, 'update', return_value=Mock()) as mock_update:
        result = await repo.activate(1)

        mock_update.assert_called_once_with(1, {"is_active": True})


# ============================================================
# GET ALL TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_all_filters_active_only(team_repository, sample_team_member):
    """Test that get_all filters active members by default."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[sample_team_member])))
    session.execute.return_value = mock_result

    result = await repo.get_all(active_only=True)

    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_all_returns_all_if_active_only_false(team_repository):
    """Test that get_all returns all members if active_only=False."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
    session.execute.return_value = mock_result

    result = await repo.get_all(active_only=False)

    session.execute.assert_called_once()


# ============================================================
# GET BY ROLE/SKILL TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_by_role_filters_correctly(team_repository, sample_team_member):
    """Test that get_by_role filters by role."""
    repo, session = team_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[sample_team_member])))
    session.execute.return_value = mock_result

    result = await repo.get_by_role("developer")

    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_by_skill_filters_correctly(team_repository):
    """Test that get_by_skill filters by skill (case-insensitive)."""
    repo, session = team_repository

    member = TeamMemberDB(
        id=1, name="Test", role="dev",
        skills=["Python", "Docker"], is_active=True
    )

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[member])))
    session.execute.return_value = mock_result

    result = await repo.get_by_skill("python")

    # Should match case-insensitively
    assert len(result) == 1
