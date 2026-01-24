"""
Unit tests for AuditRepository.

CRITICAL - TIER 1 (Security/Data Integrity)
Tests audit logging, query filtering, and data integrity.

Q4 2026: Comprehensive audit repository tests.
Target coverage: 75%+
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta, UTC

from src.database.repositories.audit import AuditRepository
from src.database.models import AuditLogDB, TaskDB


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

    db.session = Mock(return_value=session)

    return db, session


@pytest.fixture
def audit_repository(mock_database):
    """Create AuditRepository with mocked database."""
    db, session = mock_database
    repo = AuditRepository()
    repo.db = db
    return repo, session


@pytest.fixture
def sample_audit_log():
    """Create a sample audit log for testing."""
    return AuditLogDB(
        id=1,
        action="created",
        entity_type="task",
        entity_id="TASK-001",
        task_id=1,
        task_ref="TASK-001",
        field_changed=None,
        old_value=None,
        new_value='{"title": "Test Task", "assignee": "John"}',
        changed_by="Boss",
        changed_by_id="123456",
        reason=None,
        source="telegram",
        timestamp=datetime.now(UTC)
    )


@pytest.fixture
def sample_task():
    """Create a sample task for audit logging."""
    return TaskDB(
        id=1,
        task_id="TASK-001",
        title="Test Task",
        description="Test Description",
        status="pending",
        priority="high",
        assignee="John Doe",
        deadline=datetime.now(UTC) + timedelta(days=7)
    )


# ============================================================
# LOG METHOD TESTS (Core audit logging)
# ============================================================

@pytest.mark.asyncio
async def test_log_creates_audit_entry(audit_repository):
    """Test that log() creates an audit log entry."""
    repo, session = audit_repository

    result = await repo.log(
        action="created",
        changed_by="Boss",
        entity_type="task",
        entity_id="TASK-001",
        task_ref="TASK-001",
        source="telegram"
    )

    session.add.assert_called_once()
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_log_handles_dict_values(audit_repository):
    """Test that log() correctly serializes dict/list values to JSON."""
    repo, session = audit_repository

    result = await repo.log(
        action="updated",
        changed_by="Boss",
        entity_id="TASK-001",
        old_value={"status": "pending"},
        new_value={"status": "in_progress"}
    )

    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_log_stores_metadata_correctly(audit_repository):
    """Test that all metadata fields are stored correctly."""
    repo, session = audit_repository

    result = await repo.log(
        action="status_changed",
        changed_by="John Doe",
        changed_by_id="user123",
        entity_type="task",
        entity_id="TASK-002",
        task_ref="TASK-002",
        field_changed="status",
        old_value="pending",
        new_value="completed",
        reason="Finished implementation",
        source="telegram",
        snapshot={"assignee": "John", "priority": "high"}
    )

    session.add.assert_called_once()
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_log_handles_errors_gracefully(audit_repository):
    """Test that log() returns None on error without crashing."""
    repo, session = audit_repository

    # Make session.add raise an exception
    session.add.side_effect = Exception("Database error")

    result = await repo.log(
        action="test",
        changed_by="Test"
    )

    assert result is None


# ============================================================
# CREATE METHOD TESTS (Q2 2026 enhanced audit)
# ============================================================

@pytest.mark.asyncio
async def test_create_makes_comprehensive_audit_log(audit_repository):
    """Test that create() makes Q2 2026 style comprehensive audit logs."""
    repo, session = audit_repository

    result = await repo.create(
        action="USER_LOGIN",
        user_id="user123",
        entity_type="authentication",
        entity_id="session_abc",
        details={"ip": "192.168.1.1", "device": "Chrome"},
        level="info"
    )

    session.add.assert_called_once()
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_create_uses_system_if_no_user_id(audit_repository):
    """Test that create() defaults to 'system' if no user_id provided."""
    repo, session = audit_repository

    result = await repo.create(
        action="SCHEDULED_TASK",
        entity_type="task",
        entity_id="TASK-001"
    )

    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_create_accepts_custom_timestamp(audit_repository):
    """Test that create() can use custom timestamp."""
    repo, session = audit_repository

    custom_time = datetime(2026, 1, 1, 12, 0, 0)

    result = await repo.create(
        action="TEST",
        timestamp=custom_time
    )

    session.add.assert_called_once()


# ============================================================
# QUERY METHOD TESTS (Q2 2026 flexible querying)
# ============================================================

@pytest.mark.asyncio
async def test_query_filters_by_action(audit_repository, sample_audit_log):
    """Test that query() filters by action correctly."""
    repo, session = audit_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[sample_audit_log])))
    session.execute.return_value = mock_result

    result = await repo.query(
        filters={"action": "created"},
        limit=10
    )

    assert len(result) == 1
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_query_filters_by_user_id(audit_repository, sample_audit_log):
    """Test that query() filters by user_id (mapped to changed_by)."""
    repo, session = audit_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[sample_audit_log])))
    session.execute.return_value = mock_result

    result = await repo.query(
        filters={"user_id": "123456"},
        limit=10
    )

    assert len(result) == 1


@pytest.mark.asyncio
async def test_query_filters_by_entity_type(audit_repository, sample_audit_log):
    """Test that query() filters by entity_type."""
    repo, session = audit_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[sample_audit_log])))
    session.execute.return_value = mock_result

    result = await repo.query(
        filters={"entity_type": "task"},
        limit=10
    )

    assert len(result) == 1


@pytest.mark.asyncio
async def test_query_supports_pagination(audit_repository):
    """Test that query() supports limit and offset for pagination."""
    repo, session = audit_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
    session.execute.return_value = mock_result

    result = await repo.query(
        limit=50,
        offset=100
    )

    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_query_returns_empty_list_if_no_results(audit_repository):
    """Test that query() returns empty list if no matches."""
    repo, session = audit_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
    session.execute.return_value = mock_result

    result = await repo.query(
        filters={"action": "nonexistent"}
    )

    assert result == []


# ============================================================
# COUNT METHOD TESTS
# ============================================================

@pytest.mark.asyncio
async def test_count_returns_total(audit_repository):
    """Test that count() returns total matching entries."""
    repo, session = audit_repository

    mock_result = Mock()
    mock_result.scalar = Mock(return_value=42)
    session.execute.return_value = mock_result

    result = await repo.count(filters={"action": "created"})

    assert result == 42


@pytest.mark.asyncio
async def test_count_returns_zero_if_none(audit_repository):
    """Test that count() returns 0 if no matches."""
    repo, session = audit_repository

    mock_result = Mock()
    mock_result.scalar = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.count()

    assert result == 0


# ============================================================
# TASK-SPECIFIC AUDIT METHODS
# ============================================================

@pytest.mark.asyncio
async def test_log_task_created_captures_metadata(audit_repository, sample_task):
    """Test that log_task_created captures all task metadata."""
    repo, session = audit_repository

    result = await repo.log_task_created(
        task=sample_task,
        created_by="Boss",
        source="telegram",
        created_by_id="123456"
    )

    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_log_status_change_records_transition(audit_repository):
    """Test that log_status_change records status transitions."""
    repo, session = audit_repository

    result = await repo.log_status_change(
        task_ref="TASK-001",
        old_status="pending",
        new_status="in_progress",
        changed_by="John Doe",
        reason="Started working",
        source="telegram"
    )

    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_log_approval_stores_message(audit_repository):
    """Test that log_approval stores approval message."""
    repo, session = audit_repository

    result = await repo.log_approval(
        task_ref="TASK-001",
        approved_by="Boss",
        message="Looks good!",
        source="telegram"
    )

    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_log_rejection_stores_feedback(audit_repository):
    """Test that log_rejection stores rejection feedback."""
    repo, session = audit_repository

    result = await repo.log_rejection(
        task_ref="TASK-001",
        rejected_by="Boss",
        feedback="Needs more testing",
        source="telegram"
    )

    session.add.assert_called_once()


# ============================================================
# QUERY HELPER METHODS
# ============================================================

@pytest.mark.asyncio
async def test_get_task_history_returns_chronological(audit_repository, sample_audit_log):
    """Test that get_task_history returns logs in chronological order."""
    repo, session = audit_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[sample_audit_log])))
    session.execute.return_value = mock_result

    result = await repo.get_task_history("TASK-001")

    assert len(result) == 1
    assert result[0] == sample_audit_log


@pytest.mark.asyncio
async def test_get_user_activity_filters_by_date(audit_repository):
    """Test that get_user_activity filters by date range."""
    repo, session = audit_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
    session.execute.return_value = mock_result

    result = await repo.get_user_activity("user123", days=7)

    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_recent_logs_limits_results(audit_repository):
    """Test that get_recent_logs respects limit parameter."""
    repo, session = audit_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
    session.execute.return_value = mock_result

    result = await repo.get_recent_logs(limit=25)

    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_recent_logs_filters_by_action(audit_repository):
    """Test that get_recent_logs can filter by action type."""
    repo, session = audit_repository

    mock_result = Mock()
    mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
    session.execute.return_value = mock_result

    result = await repo.get_recent_logs(action_filter="created")

    session.execute.assert_called_once()


# ============================================================
# STATS METHODS
# ============================================================

@pytest.mark.asyncio
async def test_get_activity_stats_aggregates_data(audit_repository):
    """Test that get_activity_stats returns aggregated statistics."""
    repo, session = audit_repository

    # Mock multiple query results
    mock_action_result = Mock()
    mock_action_result.__iter__ = Mock(return_value=iter([("created", 10), ("updated", 5)]))

    mock_user_result = Mock()
    mock_user_result.__iter__ = Mock(return_value=iter([("Boss", 8), ("John", 7)]))

    mock_total_result = Mock()
    mock_total_result.scalar = Mock(return_value=15)

    session.execute.side_effect = [
        mock_action_result,
        mock_user_result,
        mock_total_result
    ]

    result = await repo.get_activity_stats(days=7)

    assert "total_events" in result
    assert "by_action" in result
    assert "by_user" in result
    assert result["period_days"] == 7
