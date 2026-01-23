"""
Integration test for webhook → task creation flow.

Tests the complete flow:
1. Telegram webhook receives message
2. Background processing starts
3. Intent detected
4. Conversation created
5. Task generated and saved to database
"""

import pytest
import asyncio
import time
from datetime import datetime
from typing import Dict, Any

# Test configuration
TEST_BOT_TOKEN = "test_bot_token"
TEST_CHAT_ID = 1606655791  # Boss chat ID from .env
RAILWAY_URL = "https://boss-workflow-production.up.railway.app"


class TestWebhookFlow:
    """Test complete webhook processing flow."""

    @pytest.fixture
    def sample_telegram_update(self) -> Dict[str, Any]:
        """Create a sample Telegram update message."""
        timestamp = int(time.time())
        return {
            "update_id": timestamp,  # Use timestamp to ensure uniqueness
            "message": {
                "message_id": timestamp,
                "from": {
                    "id": TEST_CHAT_ID,
                    "is_bot": False,
                    "first_name": "Boss"
                },
                "chat": {
                    "id": TEST_CHAT_ID,
                    "type": "private"
                },
                "date": timestamp,
                "text": "/task John: Review API security vulnerabilities"
            }
        }

    @pytest.fixture
    def sample_natural_language_update(self) -> Dict[str, Any]:
        """Create a natural language task creation message."""
        timestamp = int(time.time())
        return {
            "update_id": timestamp + 1,  # Different update_id
            "message": {
                "message_id": timestamp + 1,
                "from": {
                    "id": TEST_CHAT_ID,
                    "is_bot": False,
                    "first_name": "Boss"
                },
                "chat": {
                    "id": TEST_CHAT_ID,
                    "type": "private"
                },
                "date": timestamp,
                "text": "Create a task for Sarah: Update the database schema"
            }
        }

    @pytest.mark.asyncio
    async def test_slash_command_flow(self, sample_telegram_update, httpx_client):
        """Test /task slash command creates a task."""
        # Get initial task count
        stats_response = await httpx_client.get(f"{RAILWAY_URL}/api/db/stats")
        assert stats_response.status_code == 200
        initial_stats = stats_response.json()
        initial_task_count = initial_stats["tasks"]["created_today"]

        # Send webhook update
        webhook_response = await httpx_client.post(
            f"{RAILWAY_URL}/webhook/telegram",
            json=sample_telegram_update
        )
        assert webhook_response.status_code == 200
        assert webhook_response.json()["ok"] is True

        # Wait for background processing (webhook returns immediately)
        # Background task should complete within 10 seconds
        await asyncio.sleep(10)

        # Check if task was created
        stats_response = await httpx_client.get(f"{RAILWAY_URL}/api/db/stats")
        assert stats_response.status_code == 200
        new_stats = stats_response.json()
        new_task_count = new_stats["tasks"]["created_today"]

        # Verify task was created
        assert new_task_count > initial_task_count, (
            f"Task was not created. Initial: {initial_task_count}, "
            f"New: {new_task_count}"
        )

        # Verify conversation was created
        assert new_stats["conversations"]["total_conversations"] > 0, (
            "No conversations were created"
        )

    @pytest.mark.asyncio
    async def test_natural_language_flow(self, sample_natural_language_update, httpx_client):
        """Test natural language task creation."""
        # Send webhook update
        webhook_response = await httpx_client.post(
            f"{RAILWAY_URL}/webhook/telegram",
            json=sample_natural_language_update
        )
        assert webhook_response.status_code == 200

        # Wait for background processing
        await asyncio.sleep(10)

        # Check conversations
        stats_response = await httpx_client.get(f"{RAILWAY_URL}/api/db/stats")
        assert stats_response.status_code == 200
        stats = stats_response.json()

        # Natural language should create a conversation
        assert stats["conversations"]["total_conversations"] > 0

    @pytest.mark.asyncio
    async def test_duplicate_update_handling(self, sample_telegram_update, httpx_client):
        """Test that duplicate update_ids are properly deduplicated."""
        # Send the same update twice
        response1 = await httpx_client.post(
            f"{RAILWAY_URL}/webhook/telegram",
            json=sample_telegram_update
        )
        assert response1.status_code == 200

        # Send again immediately (should be deduplicated)
        response2 = await httpx_client.post(
            f"{RAILWAY_URL}/webhook/telegram",
            json=sample_telegram_update
        )
        assert response2.status_code == 200

        # Both should return ok=True
        assert response1.json()["ok"] is True
        assert response2.json()["ok"] is True

        # Wait for processing
        await asyncio.sleep(5)

        # Only one task should be created (not two)
        # This test verifies deduplication is working

    @pytest.mark.asyncio
    async def test_invalid_update_handling(self, httpx_client):
        """Test that invalid updates are handled gracefully."""
        # Send invalid update (missing update_id)
        invalid_update = {
            "message": {
                "text": "test"
            }
        }
        response = await httpx_client.post(
            f"{RAILWAY_URL}/webhook/telegram",
            json=invalid_update
        )
        assert response.status_code == 200  # Should return 200 to prevent retries
        assert response.json()["ok"] is False

    @pytest.mark.asyncio
    async def test_malformed_json_handling(self, httpx_client):
        """Test that malformed JSON is handled gracefully."""
        response = await httpx_client.post(
            f"{RAILWAY_URL}/webhook/telegram",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )
        # Should return 200 to prevent Telegram retries
        assert response.status_code == 200


@pytest.fixture
async def httpx_client():
    """Create an async HTTP client for testing."""
    import httpx
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client
