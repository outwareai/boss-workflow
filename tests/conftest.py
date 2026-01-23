"""
Pytest configuration and shared fixtures.
"""

import pytest
import asyncio
from typing import AsyncGenerator

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_task_data():
    """Sample task data for testing."""
    return {
        "id": "TASK-20260123-001",
        "title": "Test Task",
        "description": "Test description",
        "assignee": "TestUser",
        "priority": "high",
        "status": "pending",
        "tags": ["test", "sample"],
    }


@pytest.fixture
def sample_team_member():
    """Sample team member data."""
    return {
        "name": "John Doe",
        "role": "Developer",
        "telegram_id": "123456789",
        "discord_id": "987654321012345678",
        "email": "john@example.com",
        "is_active": True,
    }
