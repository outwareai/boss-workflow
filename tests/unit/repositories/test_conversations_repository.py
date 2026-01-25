"""
Unit tests for ConversationRepository.

Tier 2 Repository Tests: Comprehensive coverage for conversation history operations.
Tests cover conversation lifecycle, message threading, stale cleanup, and statistics.
"""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
from datetime import datetime, timedelta

from src.database.repositories.conversations import ConversationRepository
from src.database.models import ConversationDB, MessageDB


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
def conversation_repository(mock_database):
    """Create ConversationRepository with mocked database."""
    db, session = mock_database
    repo = ConversationRepository()
    repo.db = db
    return repo, session


@pytest.fixture
def sample_conversation():
    """Create a sample ConversationDB instance for testing."""
    return ConversationDB(
        id=1,
        conversation_id="CONV-20260124120000-abc123",
        user_id="123456789",
        user_name="John Doe",
        chat_id="987654321",
        intent="create_task",
        stage="initial",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )


@pytest.fixture
def sample_message():
    """Create a sample MessageDB instance for testing."""
    return MessageDB(
        id=1,
        conversation_id=1,
        role="user",
        content="Create a task for fixing login bug",
        message_type="text",
        timestamp=datetime.now()
    )


# ============================================================
# CONVERSATION CREATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_create_conversation_success(conversation_repository):
    """Test creating a new conversation successfully."""
    repo, session = conversation_repository

    result = await repo.create(
        user_id="123456789",
        user_name="John Doe",
        chat_id="987654321",
        intent="create_task"
    )

    session.add.assert_called_once()
    session.flush.assert_called_once()

    # Verify conversation was created with correct data
    added_conv = session.add.call_args[0][0]
    assert added_conv.user_id == "123456789"
    assert added_conv.user_name == "John Doe"
    assert added_conv.intent == "create_task"
    assert added_conv.stage == "initial"
    assert added_conv.conversation_id.startswith("CONV-")


@pytest.mark.asyncio
async def test_create_conversation_minimal_fields(conversation_repository):
    """Test creating a conversation with only required fields."""
    repo, session = conversation_repository

    result = await repo.create(user_id="123456789")

    session.add.assert_called_once()
    added_conv = session.add.call_args[0][0]
    assert added_conv.user_id == "123456789"
    assert added_conv.user_name is None
    assert added_conv.chat_id is None
    assert added_conv.intent is None


@pytest.mark.asyncio
async def test_create_conversation_error_handling(conversation_repository):
    """Test conversation creation error handling raises exception."""
    from src.database.exceptions import DatabaseOperationError
    repo, session = conversation_repository

    session.flush.side_effect = Exception("Database error")

    # Should raise DatabaseOperationError
    with pytest.raises(DatabaseOperationError, match="Failed to create conversation"):
        await repo.create(user_id="123456789")


# ============================================================
# CONVERSATION READ TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_by_id_found(conversation_repository, sample_conversation):
    """Test retrieving a conversation by ID when it exists."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_conversation)
    session.execute.return_value = mock_result

    result = await repo.get_by_id("CONV-20260124120000-abc123")

    assert result == sample_conversation
    assert result.conversation_id == "CONV-20260124120000-abc123"


@pytest.mark.asyncio
async def test_get_by_id_not_found(conversation_repository):
    """Test retrieving a conversation by ID when it doesn't exist."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.get_by_id("CONV-nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_get_active_for_user_found(conversation_repository, sample_conversation):
    """Test retrieving active conversation for a user."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_conversation)
    session.execute.return_value = mock_result

    result = await repo.get_active_for_user("123456789")

    assert result == sample_conversation
    assert result.user_id == "123456789"


@pytest.mark.asyncio
async def test_get_active_for_user_not_found(conversation_repository):
    """Test retrieving active conversation when none exists."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.get_active_for_user("999999999")

    assert result is None


@pytest.mark.asyncio
async def test_get_user_history(conversation_repository):
    """Test retrieving conversation history for a user."""
    repo, session = conversation_repository

    conversations = [
        ConversationDB(id=1, conversation_id="CONV-001", user_id="123"),
        ConversationDB(id=2, conversation_id="CONV-002", user_id="123"),
        ConversationDB(id=3, conversation_id="CONV-003", user_id="123")
    ]

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=conversations)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_user_history("123", limit=20)

    assert len(result) == 3
    assert all(c.user_id == "123" for c in result)


@pytest.mark.asyncio
async def test_get_recent_conversations(conversation_repository):
    """Test retrieving recent conversations."""
    repo, session = conversation_repository

    conversations = [
        ConversationDB(id=1, conversation_id="CONV-001", user_id="123"),
        ConversationDB(id=2, conversation_id="CONV-002", user_id="456")
    ]

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=conversations)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_recent(limit=50)

    assert len(result) == 2


# ============================================================
# CONVERSATION UPDATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_update_stage(conversation_repository, sample_conversation):
    """Test updating conversation stage."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_conversation)
    session.execute.return_value = mock_result

    result = await repo.update_stage(
        "CONV-20260124120000-abc123",
        stage="clarifying",
        context={"questions_asked": 2}
    )

    # Verify execute was called for update and select
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_update_stage_with_spec(conversation_repository, sample_conversation):
    """Test updating conversation stage with generated spec."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_conversation)
    session.execute.return_value = mock_result

    spec = {
        "title": "Fix login bug",
        "assignee": "John",
        "priority": "high"
    }

    result = await repo.update_stage(
        "CONV-20260124120000-abc123",
        stage="confirmed",
        generated_spec=spec
    )

    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_complete_conversation(conversation_repository, sample_conversation):
    """Test marking conversation as completed."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_conversation)
    session.execute.return_value = mock_result

    result = await repo.complete(
        "CONV-20260124120000-abc123",
        outcome="task_created",
        task_id="TASK-001"
    )

    # Verify execute called for update and select
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_complete_conversation_cancelled(conversation_repository, sample_conversation):
    """Test marking conversation as cancelled."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_conversation)
    session.execute.return_value = mock_result

    result = await repo.complete(
        "CONV-20260124120000-abc123",
        outcome="cancelled"
    )

    assert session.execute.call_count == 2


# ============================================================
# CONVERSATION CLEANUP TESTS
# ============================================================

@pytest.mark.asyncio
async def test_clear_user_conversations(conversation_repository):
    """Test clearing all active conversations for a user."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.rowcount = 3
    session.execute.return_value = mock_result

    count = await repo.clear_user_conversations("123456789")

    assert count == 3
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_clear_user_conversations_none_active(conversation_repository):
    """Test clearing conversations when user has none active."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.rowcount = 0
    session.execute.return_value = mock_result

    count = await repo.clear_user_conversations("999999999")

    assert count == 0


@pytest.mark.asyncio
async def test_get_stale_conversations(conversation_repository):
    """Test retrieving stale conversations."""
    repo, session = conversation_repository

    stale_convs = [
        ConversationDB(
            id=1,
            conversation_id="CONV-001",
            user_id="123",
            updated_at=datetime.now() - timedelta(hours=2)
        )
    ]

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=stale_convs)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_stale_conversations(timeout_minutes=30)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_cleanup_stale_conversations(conversation_repository):
    """Test cleaning up stale conversations."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.rowcount = 5
    session.execute.return_value = mock_result

    count = await repo.cleanup_stale(timeout_minutes=30)

    assert count == 5
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_stale_none_found(conversation_repository):
    """Test cleanup when no stale conversations exist."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.rowcount = 0
    session.execute.return_value = mock_result

    count = await repo.cleanup_stale(timeout_minutes=30)

    assert count == 0


# ============================================================
# MESSAGE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_add_message_success(conversation_repository, sample_conversation):
    """Test adding a message to a conversation."""
    repo, session = conversation_repository

    # Mock conversation lookup
    mock_conv_result = Mock()
    mock_conv_result.scalar_one_or_none = Mock(return_value=sample_conversation)
    session.execute.return_value = mock_conv_result

    result = await repo.add_message(
        conversation_id="CONV-20260124120000-abc123",
        role="user",
        content="Create a task for fixing login bug",
        message_type="text"
    )

    session.add.assert_called_once()
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_add_message_with_intent(conversation_repository, sample_conversation):
    """Test adding a message with intent detection."""
    repo, session = conversation_repository

    mock_conv_result = Mock()
    mock_conv_result.scalar_one_or_none = Mock(return_value=sample_conversation)
    session.execute.return_value = mock_conv_result

    result = await repo.add_message(
        conversation_id="CONV-20260124120000-abc123",
        role="user",
        content="Create a task",
        intent_detected="create_task",
        confidence=0.95
    )

    session.add.assert_called_once()
    added_msg = session.add.call_args[0][0]
    assert added_msg.intent_detected == "create_task"
    assert added_msg.confidence == 95  # Converted to int percentage


@pytest.mark.asyncio
async def test_add_message_conversation_not_found(conversation_repository):
    """Test adding a message when conversation doesn't exist raises exception."""
    from src.database.exceptions import EntityNotFoundError
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    # Should raise EntityNotFoundError
    with pytest.raises(EntityNotFoundError, match="Conversation CONV-nonexistent not found"):
        await repo.add_message(
            conversation_id="CONV-nonexistent",
            role="user",
            content="Test message"
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_messages(conversation_repository, sample_conversation):
    """Test retrieving all messages in a conversation."""
    repo, session = conversation_repository

    messages = [
        MessageDB(id=1, conversation_id=1, role="user", content="Hello"),
        MessageDB(id=2, conversation_id=1, role="assistant", content="Hi there")
    ]

    # Mock conversation lookup
    mock_conv_result = Mock()
    mock_conv_result.scalar_one_or_none = Mock(return_value=sample_conversation)

    # Mock messages query
    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=messages)
    mock_msg_result = Mock()
    mock_msg_result.scalars = Mock(return_value=mock_scalars)

    session.execute.side_effect = [mock_conv_result, mock_msg_result]

    result = await repo.get_messages("CONV-20260124120000-abc123")

    assert len(result) == 2
    assert result[0].role == "user"
    assert result[1].role == "assistant"


@pytest.mark.asyncio
async def test_get_messages_conversation_not_found(conversation_repository):
    """Test retrieving messages when conversation doesn't exist."""
    repo, session = conversation_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.get_messages("CONV-nonexistent")

    assert result == []


# ============================================================
# STATISTICS TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_stats(conversation_repository):
    """Test getting conversation statistics."""
    repo, session = conversation_repository

    # Mock total count
    mock_total = Mock()
    mock_total.scalar = Mock(return_value=50)

    # Mock outcome counts
    outcome_rows = [
        ("task_created", 30),
        ("cancelled", 15),
        (None, 5)  # Active conversations
    ]
    mock_outcomes = Mock()
    mock_outcomes.__iter__ = Mock(return_value=iter(outcome_rows))

    # Mock tasks created count
    mock_tasks = Mock()
    mock_tasks.scalar = Mock(return_value=30)

    # Mock average messages (not used in return but queried)
    mock_avg = Mock()
    mock_avg.scalar = Mock(return_value=3.5)

    session.execute.side_effect = [mock_total, mock_outcomes, mock_tasks, mock_avg]

    stats = await repo.get_stats(days=7)

    assert stats["total_conversations"] == 50
    assert stats["by_outcome"]["task_created"] == 30
    assert stats["by_outcome"]["cancelled"] == 15
    assert stats["by_outcome"]["active"] == 5
    assert stats["tasks_created"] == 30
    assert stats["conversion_rate"] == 60.0
    assert stats["period_days"] == 7


@pytest.mark.asyncio
async def test_get_stats_no_conversations(conversation_repository):
    """Test getting statistics when no conversations exist."""
    repo, session = conversation_repository

    mock_total = Mock()
    mock_total.scalar = Mock(return_value=0)

    mock_outcomes = Mock()
    mock_outcomes.__iter__ = Mock(return_value=iter([]))

    mock_tasks = Mock()
    mock_tasks.scalar = Mock(return_value=0)

    mock_avg = Mock()
    mock_avg.scalar = Mock(return_value=0)

    session.execute.side_effect = [mock_total, mock_outcomes, mock_tasks, mock_avg]

    stats = await repo.get_stats(days=30)

    assert stats["total_conversations"] == 0
    assert stats["tasks_created"] == 0
    assert stats["conversion_rate"] == 0
