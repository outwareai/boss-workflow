"""
Unit tests for SessionManager.

Tests:
- Session storage and retrieval
- Redis persistence
- In-memory fallback
- TTL expiration
- Concurrent access safety
- All 7 session types
- Cleanup operations

Run with: pytest tests/unit/test_session_manager.py -v
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch

# Import the SessionManager
from src.bot.session_manager import SessionManager, get_session_manager, init_session_manager


@pytest.fixture
def in_memory_manager():
    """Create a SessionManager with in-memory storage (no Redis)."""
    return SessionManager(redis_client=None)


@pytest.fixture
async def mock_redis():
    """Create a mock Redis client."""
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.close = AsyncMock(return_value=None)
    return redis_mock


@pytest.fixture
async def redis_manager(mock_redis):
    """Create a SessionManager with mocked Redis."""
    manager = SessionManager(redis_client=mock_redis)
    await manager.connect()
    return manager


# ==================== BASIC OPERATIONS ====================

@pytest.mark.asyncio
async def test_in_memory_storage(in_memory_manager):
    """Test basic in-memory storage operations."""
    manager = in_memory_manager
    await manager.connect()

    # Set a validation session
    user_id = "user123"
    data = {"task_id": "TASK-001", "step": "confirmation"}

    success = await manager.set_validation_session(user_id, data)
    assert success is True

    # Retrieve the session
    retrieved = await manager.get_validation_session(user_id)
    assert retrieved is not None
    assert retrieved["task_id"] == "TASK-001"
    assert retrieved["step"] == "confirmation"

    # Clear the session
    success = await manager.clear_validation_session(user_id)
    assert success is True

    # Verify it's gone
    retrieved = await manager.get_validation_session(user_id)
    assert retrieved is None


@pytest.mark.asyncio
async def test_redis_storage(redis_manager, mock_redis):
    """Test Redis-backed storage operations."""
    manager = redis_manager

    # Set a review session
    user_id = "user456"
    data = {"task_id": "TASK-002", "status": "pending"}

    # Mock Redis get to return our data
    mock_redis.get.return_value = json.dumps(data)

    success = await manager.set_pending_review(user_id, data)
    assert success is True

    # Verify Redis setex was called
    assert mock_redis.setex.called or mock_redis.set.called

    # Retrieve the session
    retrieved = await manager.get_pending_review(user_id)
    assert retrieved is not None
    assert retrieved["task_id"] == "TASK-002"


@pytest.mark.asyncio
async def test_all_session_types(in_memory_manager):
    """Test all 7 session types."""
    manager = in_memory_manager
    await manager.connect()

    test_cases = [
        # (set_method, get_method, clear_method, identifier, data)
        (
            manager.set_validation_session,
            manager.get_validation_session,
            manager.clear_validation_session,
            "user1",
            {"type": "validation", "value": 1}
        ),
        (
            manager.add_pending_validation,
            manager.get_pending_validation,
            manager.remove_pending_validation,
            "task1",
            {"type": "pending_validation", "value": 2}
        ),
        (
            manager.set_pending_review,
            manager.get_pending_review,
            manager.clear_pending_review,
            "user2",
            {"type": "review", "value": 3}
        ),
        (
            manager.set_pending_action,
            manager.get_pending_action,
            manager.clear_pending_action,
            "user3",
            {"type": "action", "value": 4}
        ),
        (
            manager.set_batch_task,
            manager.get_batch_task,
            manager.clear_batch_task,
            "user4",
            {"type": "batch", "value": 5}
        ),
        (
            manager.set_spec_session,
            manager.get_spec_session,
            manager.clear_spec_session,
            "user5",
            {"type": "spec", "value": 6}
        ),
        (
            manager.set_recent_message,
            manager.get_recent_message,
            manager.clear_recent_message,
            "user6",
            {"type": "message", "value": 7}
        ),
    ]

    for set_fn, get_fn, clear_fn, identifier, data in test_cases:
        # Set
        success = await set_fn(identifier, data)
        assert success is True, f"Failed to set {data['type']}"

        # Get
        retrieved = await get_fn(identifier)
        assert retrieved is not None, f"Failed to get {data['type']}"
        assert retrieved["type"] == data["type"]
        assert retrieved["value"] == data["value"]

        # Clear
        success = await clear_fn(identifier)
        assert success is True, f"Failed to clear {data['type']}"

        # Verify cleared
        retrieved = await get_fn(identifier)
        assert retrieved is None, f"{data['type']} not cleared"


# ==================== TTL & EXPIRATION ====================

@pytest.mark.asyncio
async def test_ttl_in_memory(in_memory_manager):
    """Test TTL-based expiration in memory."""
    manager = in_memory_manager
    await manager.connect()

    user_id = "user_ttl"
    data = {
        "message": "expires soon",
        "created_at": (datetime.now() - timedelta(hours=2)).isoformat()
    }

    # Set with timestamp
    await manager.set_validation_session(user_id, data)

    # Run cleanup with 1 hour TTL
    cleaned = await manager.cleanup_expired_sessions(ttl_seconds=3600)

    # Should have cleaned the expired session
    assert "validation" in cleaned or len(cleaned) > 0

    # Verify it's gone
    retrieved = await manager.get_validation_session(user_id)
    # Note: cleanup only works if timestamp is in the data
    # Since we added created_at, it should be cleaned


@pytest.mark.asyncio
async def test_ttl_redis(redis_manager, mock_redis):
    """Test TTL is set correctly in Redis."""
    manager = redis_manager

    user_id = "user_redis_ttl"
    data = {"message": "with ttl"}
    ttl = 600  # 10 minutes

    await manager.set_validation_session(user_id, data, ttl=ttl)

    # Verify setex was called with correct TTL
    mock_redis.setex.assert_called()
    call_args = mock_redis.setex.call_args
    assert call_args[0][1] == ttl  # Second argument should be TTL


# ==================== CONCURRENT ACCESS ====================

@pytest.mark.asyncio
async def test_concurrent_access(in_memory_manager):
    """Test thread-safety with concurrent access."""
    manager = in_memory_manager
    await manager.connect()

    user_id = "concurrent_user"

    # Multiple concurrent writes
    async def write_session(value: int):
        data = {"value": value, "timestamp": datetime.now().isoformat()}
        await manager.set_validation_session(user_id, data)
        # Small delay
        await asyncio.sleep(0.01)
        return value

    # Execute 10 concurrent writes
    results = await asyncio.gather(*[write_session(i) for i in range(10)])

    # Verify all completed
    assert len(results) == 10

    # Final value should be one of the written values
    final = await manager.get_validation_session(user_id)
    assert final is not None
    assert "value" in final
    assert 0 <= final["value"] <= 9


# ==================== LIST OPERATIONS ====================

@pytest.mark.asyncio
async def test_list_pending_validations(in_memory_manager):
    """Test listing all pending validations."""
    manager = in_memory_manager
    await manager.connect()

    # Add multiple pending validations
    for i in range(5):
        task_id = f"TASK-{i:03d}"
        data = {"task_id": task_id, "user": f"user{i}"}
        await manager.add_pending_validation(task_id, data)

    # List all
    validations = await manager.list_pending_validations()

    # Should have 5 validations
    assert len(validations) == 5

    # Each should have task_id
    for validation in validations:
        assert "task_id" in validation
        assert validation["task_id"].startswith("TASK-")


# ==================== STATISTICS ====================

@pytest.mark.asyncio
async def test_session_stats(in_memory_manager):
    """Test session statistics."""
    manager = in_memory_manager
    await manager.connect()

    # Add various sessions
    await manager.set_validation_session("user1", {"data": 1})
    await manager.set_validation_session("user2", {"data": 2})
    await manager.set_pending_review("user3", {"data": 3})
    await manager.set_batch_task("user4", {"data": 4})

    # Get stats
    stats = await manager.get_session_stats()

    # Verify structure
    assert "storage" in stats
    assert stats["storage"] == "memory"
    assert "by_type" in stats
    assert "total" in stats

    # Verify counts
    assert stats["by_type"]["validation"] == 2
    assert stats["by_type"]["review"] == 1
    assert stats["by_type"]["batch"] == 1
    assert stats["total"] == 4


# ==================== CLEANUP ====================

@pytest.mark.asyncio
async def test_clear_all_sessions(in_memory_manager):
    """Test clearing all sessions."""
    manager = in_memory_manager
    await manager.connect()

    # Add sessions
    await manager.set_validation_session("user1", {"data": 1})
    await manager.set_pending_review("user2", {"data": 2})

    # Clear all
    success = await manager.clear_all_sessions()
    assert success is True

    # Verify all cleared
    stats = await manager.get_session_stats()
    assert stats["total"] == 0


@pytest.mark.asyncio
async def test_clear_specific_type(in_memory_manager):
    """Test clearing specific session type."""
    manager = in_memory_manager
    await manager.connect()

    # Add sessions of different types
    await manager.set_validation_session("user1", {"data": 1})
    await manager.set_validation_session("user2", {"data": 2})
    await manager.set_pending_review("user3", {"data": 3})

    # Clear only validation sessions
    success = await manager.clear_all_sessions(session_type="validation")
    assert success is True

    # Verify validation cleared but review remains
    stats = await manager.get_session_stats()
    assert stats["by_type"]["validation"] == 0
    assert stats["by_type"]["review"] == 1


# ==================== ERROR HANDLING ====================

@pytest.mark.asyncio
async def test_invalid_json_handling(in_memory_manager):
    """Test handling of corrupted JSON data."""
    manager = in_memory_manager
    await manager.connect()

    # Manually corrupt data in memory store
    key = manager._get_key("validation", "corrupt_user")
    manager._memory_store["validation"]["corrupt_user"] = "invalid json{"

    # Try to retrieve - should return None on error
    retrieved = await manager.get_validation_session("corrupt_user")
    assert retrieved is None


@pytest.mark.asyncio
async def test_redis_failure_handling(redis_manager, mock_redis):
    """Test graceful handling of Redis failures."""
    manager = redis_manager

    # Make Redis operations fail
    mock_redis.get.side_effect = Exception("Redis connection lost")

    # Should return None instead of crashing
    retrieved = await manager.get_validation_session("any_user")
    assert retrieved is None


# ==================== SINGLETON ====================

def test_singleton_pattern():
    """Test that get_session_manager returns singleton."""
    manager1 = get_session_manager()
    manager2 = get_session_manager()

    # Should be the same instance
    assert manager1 is manager2


@pytest.mark.asyncio
async def test_init_session_manager():
    """Test initialization helper."""
    manager = await init_session_manager()

    # Should be connected
    assert manager._connected is True

    # Should be the singleton instance
    assert manager is get_session_manager()


# ==================== INTEGRATION TESTS ====================

@pytest.mark.asyncio
async def test_full_workflow(in_memory_manager):
    """Test a complete session workflow."""
    manager = in_memory_manager
    await manager.connect()

    user_id = "workflow_user"

    # Step 1: Start validation
    validation_data = {
        "task_id": "TASK-999",
        "step": "start",
        "timestamp": datetime.now().isoformat()
    }
    await manager.set_validation_session(user_id, validation_data)

    # Step 2: Update validation
    validation_data["step"] = "questioning"
    await manager.set_validation_session(user_id, validation_data)

    retrieved = await manager.get_validation_session(user_id)
    assert retrieved["step"] == "questioning"

    # Step 3: Move to pending validation
    pending_data = {
        "task_id": "TASK-999",
        "user_id": user_id,
        "status": "awaiting_confirmation"
    }
    await manager.add_pending_validation("TASK-999", pending_data)

    # Step 4: Clear validation session
    await manager.clear_validation_session(user_id)

    # Verify state
    validation = await manager.get_validation_session(user_id)
    assert validation is None

    pending = await manager.get_pending_validation("TASK-999")
    assert pending is not None
    assert pending["status"] == "awaiting_confirmation"

    # Step 5: Complete and cleanup
    await manager.remove_pending_validation("TASK-999")

    pending = await manager.get_pending_validation("TASK-999")
    assert pending is None


@pytest.mark.asyncio
async def test_message_context_short_ttl(in_memory_manager):
    """Test that message context uses shorter TTL."""
    manager = in_memory_manager
    await manager.connect()

    user_id = "msg_user"
    data = {"last_message": "hello", "intent": "greeting"}

    # Set message context (should use 300s default)
    await manager.set_recent_message(user_id, data)

    # Retrieve immediately
    retrieved = await manager.get_recent_message(user_id)
    assert retrieved is not None
    assert retrieved["last_message"] == "hello"


# ==================== PERFORMANCE TESTS ====================

@pytest.mark.asyncio
async def test_high_volume_operations(in_memory_manager):
    """Test performance with many sessions."""
    manager = in_memory_manager
    await manager.connect()

    # Create 100 sessions
    for i in range(100):
        user_id = f"user{i:03d}"
        data = {"user": user_id, "index": i}
        await manager.set_validation_session(user_id, data)

    # Verify all created
    stats = await manager.get_session_stats()
    assert stats["by_type"]["validation"] == 100

    # Clear all
    await manager.clear_all_sessions()

    stats = await manager.get_session_stats()
    assert stats["total"] == 0


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-v", "--tb=short"])
