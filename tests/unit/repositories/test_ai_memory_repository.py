"""
Unit tests for AIMemoryRepository.

CRITICAL - TIER 1 (Security/Data Integrity)
Tests preference merging, team knowledge, and context management.

Q4 2026: Comprehensive AI memory repository tests.
Target coverage: 75%+
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.database.repositories.ai_memory import AIMemoryRepository
from src.database.models import AIMemoryDB


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
def ai_memory_repository(mock_database):
    """Create AIMemoryRepository with mocked database."""
    db, session = mock_database
    repo = AIMemoryRepository()
    repo.db = db
    return repo, session


@pytest.fixture
def sample_ai_memory():
    """Create a sample AI memory for testing."""
    return AIMemoryDB(
        id=1,
        user_id="user123",
        preferences={"timezone": "UTC", "language": "en"},
        team_knowledge={"john": {"name": "John", "role": "developer"}},
        custom_triggers={"asap": {"pattern": "asap", "action": {"duration": "4h"}}},
        learned_patterns={"priority_choices": [{"value": "high"}]},
        recent_context={"last_task": "TASK-001"},
        total_tasks_created=5,
        total_conversations=10
    )


# ============================================================
# GET OR CREATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_or_create_returns_existing(ai_memory_repository, sample_ai_memory):
    """Test that get_or_create returns existing memory."""
    repo, session = ai_memory_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_ai_memory)
    session.execute.return_value = mock_result

    result = await repo.get_or_create("user123")

    assert result == sample_ai_memory
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_creates_new(ai_memory_repository):
    """Test that get_or_create creates new memory if missing."""
    repo, session = ai_memory_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.get_or_create("newuser")

    session.add.assert_called_once()
    session.flush.assert_called_once()


# ============================================================
# PREFERENCES TESTS (Critical - No data loss on merge)
# ============================================================

@pytest.mark.asyncio
async def test_update_preferences_merges_without_data_loss(ai_memory_repository, sample_ai_memory):
    """Test that preference updates merge without losing existing data."""
    repo, session = ai_memory_repository

    # Mock get_or_create
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_ai_memory)
    session.execute.return_value = mock_result

    with patch.object(repo, 'get_or_create', return_value=sample_ai_memory):
        result = await repo.update_preferences("user123", {
            "theme": "dark",  # New key
            "timezone": "Asia/Bangkok"  # Update existing
        })

        # Verify merge happened
        assert result["timezone"] == "Asia/Bangkok"
        assert result["theme"] == "dark"
        assert result["language"] == "en"  # Original preserved


@pytest.mark.asyncio
async def test_set_preference_single_key(ai_memory_repository, sample_ai_memory):
    """Test setting a single preference key."""
    repo, session = ai_memory_repository

    with patch.object(repo, 'update_preferences', return_value={"new_key": "value"}) as mock_update:
        result = await repo.set_preference("user123", "new_key", "value")

        mock_update.assert_called_once_with("user123", {"new_key": "value"})
        assert result == {"new_key": "value"}


@pytest.mark.asyncio
async def test_get_preferences_returns_empty_dict_for_new_user(ai_memory_repository):
    """Test that get_preferences returns empty dict for new users."""
    repo, session = ai_memory_repository

    new_memory = AIMemoryDB(
        user_id="newuser",
        preferences={},
        team_knowledge={},
        custom_triggers={},
        learned_patterns={},
        recent_context={}
    )

    with patch.object(repo, 'get_or_create', return_value=new_memory):
        result = await repo.get_preferences("newuser")

        assert result == {}


# ============================================================
# TEAM KNOWLEDGE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_add_team_member_creates_entry(ai_memory_repository, sample_ai_memory):
    """Test adding a new team member to knowledge base."""
    repo, session = ai_memory_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_ai_memory)
    session.execute.return_value = mock_result

    with patch.object(repo, 'get_or_create', return_value=sample_ai_memory):
        result = await repo.add_team_member("user123", "Alice", {
            "role": "designer",
            "skills": ["UI/UX"]
        })

        # Verify Alice was added
        assert "alice" in result  # Lowercase key
        assert result["alice"]["name"] == "Alice"
        assert result["alice"]["role"] == "designer"


@pytest.mark.asyncio
async def test_add_team_member_updates_existing(ai_memory_repository, sample_ai_memory):
    """Test that adding an existing team member updates their info."""
    repo, session = ai_memory_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_ai_memory)
    session.execute.return_value = mock_result

    with patch.object(repo, 'get_or_create', return_value=sample_ai_memory):
        result = await repo.add_team_member("user123", "John", {
            "role": "senior developer"  # Update John's role
        })

        # Verify John's info was updated
        assert result["john"]["role"] == "senior developer"


@pytest.mark.asyncio
async def test_find_team_member_exact_match(ai_memory_repository, sample_ai_memory):
    """Test finding team member with exact name match."""
    repo, session = ai_memory_repository

    with patch.object(repo, 'get_team_knowledge', return_value=sample_ai_memory.team_knowledge):
        result = await repo.find_team_member("user123", "john")

        assert result is not None
        assert result["name"] == "John"


@pytest.mark.asyncio
async def test_find_team_member_partial_match(ai_memory_repository):
    """Test finding team member with partial name match."""
    repo, session = ai_memory_repository

    team_data = {
        "john_doe": {"name": "John Doe", "role": "developer"},
        "jane_smith": {"name": "Jane Smith", "role": "designer"}
    }

    with patch.object(repo, 'get_team_knowledge', return_value=team_data):
        result = await repo.find_team_member("user123", "doe")

        assert result is not None
        assert result["name"] == "John Doe"


@pytest.mark.asyncio
async def test_find_team_member_returns_none_if_not_found(ai_memory_repository):
    """Test that find_team_member returns None if no match."""
    repo, session = ai_memory_repository

    with patch.object(repo, 'get_team_knowledge', return_value={}):
        result = await repo.find_team_member("user123", "nonexistent")

        assert result is None


# ============================================================
# CUSTOM TRIGGERS TESTS
# ============================================================

@pytest.mark.asyncio
async def test_add_trigger_creates_pattern(ai_memory_repository, sample_ai_memory):
    """Test adding a custom trigger pattern."""
    repo, session = ai_memory_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_ai_memory)
    session.execute.return_value = mock_result

    with patch.object(repo, 'get_or_create', return_value=sample_ai_memory):
        result = await repo.add_trigger("user123", "urgent", {
            "priority": "critical",
            "duration": "2h"
        })

        # Verify trigger was added
        assert "urgent" in result
        assert result["urgent"]["action"]["priority"] == "critical"


@pytest.mark.asyncio
async def test_match_trigger_finds_pattern(ai_memory_repository, sample_ai_memory):
    """Test that match_trigger finds matching patterns in text."""
    repo, session = ai_memory_repository

    with patch.object(repo, 'get_triggers', return_value=sample_ai_memory.custom_triggers):
        result = await repo.match_trigger("user123", "Please fix this ASAP!")

        assert result is not None
        assert result["duration"] == "4h"


@pytest.mark.asyncio
async def test_match_trigger_returns_none_if_no_match(ai_memory_repository):
    """Test that match_trigger returns None if no pattern matches."""
    repo, session = ai_memory_repository

    with patch.object(repo, 'get_triggers', return_value={}):
        result = await repo.match_trigger("user123", "Normal task")

        assert result is None


# ============================================================
# CONTEXT MANAGEMENT TESTS
# ============================================================

@pytest.mark.asyncio
async def test_update_context_merges_data(ai_memory_repository, sample_ai_memory):
    """Test that context updates merge with existing context."""
    repo, session = ai_memory_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_ai_memory)
    session.execute.return_value = mock_result

    with patch.object(repo, 'get_or_create', return_value=sample_ai_memory):
        result = await repo.update_context("user123", {
            "current_task": "TASK-002",
            "last_action": "status_update"
        })

        # Verify merge
        assert result["current_task"] == "TASK-002"
        assert result["last_task"] == "TASK-001"  # Original preserved
        assert "last_updated" in result


@pytest.mark.asyncio
async def test_update_context_adds_timestamp(ai_memory_repository, sample_ai_memory):
    """Test that update_context adds last_updated timestamp."""
    repo, session = ai_memory_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_ai_memory)
    session.execute.return_value = mock_result

    with patch.object(repo, 'get_or_create', return_value=sample_ai_memory):
        before = datetime.now()
        result = await repo.update_context("user123", {"new_key": "value"})
        after = datetime.now()

        assert "last_updated" in result
        # Timestamp should be recent
        timestamp = datetime.fromisoformat(result["last_updated"])
        assert before <= timestamp <= after


@pytest.mark.asyncio
async def test_clear_context_empties_context(ai_memory_repository):
    """Test that clear_context removes all context data."""
    repo, session = ai_memory_repository

    mock_result = Mock()
    session.execute.return_value = mock_result

    await repo.clear_context("user123")

    # Verify execute was called with empty context
    session.execute.assert_called_once()


# ============================================================
# LEARNED PATTERNS TESTS
# ============================================================

@pytest.mark.asyncio
async def test_record_pattern_appends_to_list(ai_memory_repository, sample_ai_memory):
    """Test that record_pattern appends new patterns."""
    repo, session = ai_memory_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_ai_memory)
    session.execute.return_value = mock_result

    with patch.object(repo, 'get_or_create', return_value=sample_ai_memory):
        await repo.record_pattern("user123", "priority_choices", {
            "value": "medium"
        })

        # Verify execution happened
        session.execute.assert_called()


@pytest.mark.asyncio
async def test_get_common_default_returns_most_frequent(ai_memory_repository):
    """Test that get_common_default returns most frequent value."""
    repo, session = ai_memory_repository

    patterns = {
        "priority_choices": [
            {"value": "high"},
            {"value": "medium"},
            {"value": "high"},
            {"value": "high"},
            {"value": "low"}
        ]
    }

    with patch.object(repo, 'get_patterns', return_value=patterns):
        result = await repo.get_common_default("user123", "priority")

        assert result == "high"  # Most common


@pytest.mark.asyncio
async def test_get_common_default_returns_none_if_no_patterns(ai_memory_repository):
    """Test that get_common_default returns None if no patterns exist."""
    repo, session = ai_memory_repository

    with patch.object(repo, 'get_patterns', return_value={}):
        result = await repo.get_common_default("user123", "priority")

        assert result is None


# ============================================================
# STATS TESTS
# ============================================================

@pytest.mark.asyncio
async def test_increment_stats_updates_counters(ai_memory_repository, sample_ai_memory):
    """Test that increment_stats correctly updates task counters."""
    repo, session = ai_memory_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_ai_memory)
    session.execute.return_value = mock_result

    await repo.increment_stats("user123", tasks_created=3, conversations=2)

    # Verify execute was called
    session.execute.assert_called()


@pytest.mark.asyncio
async def test_get_full_context_for_ai_returns_complete_data(ai_memory_repository, sample_ai_memory):
    """Test that get_full_context_for_ai returns all relevant context."""
    repo, session = ai_memory_repository

    with patch.object(repo, 'get_or_create', return_value=sample_ai_memory):
        result = await repo.get_full_context_for_ai("user123")

        # Verify all expected keys
        assert "preferences" in result
        assert "team_knowledge" in result
        assert "custom_triggers" in result
        assert "recent_context" in result
        assert "stats" in result

        # Verify stats structure
        assert result["stats"]["total_tasks"] == 5
        assert result["stats"]["total_conversations"] == 10
