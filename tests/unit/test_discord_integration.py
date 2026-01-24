"""
Unit tests for Discord integration.

Tests Discord Bot API integration including:
- Task posting to channels
- Department routing logic
- Reaction handling
- Thread creation
- Report sending
- Notifications
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.integrations.discord import (
    DiscordIntegration,
    ChannelType,
    RoleCategory
)
from src.models.task import Task, TaskStatus, TaskPriority


@pytest.fixture
def discord():
    """Create Discord integration instance."""
    return DiscordIntegration()


@pytest.fixture
def sample_task():
    """Create sample task for testing."""
    return Task(
        id="TASK-001",
        title="Fix login bug",
        description="Users cannot log in",
        assignee="Mayank",
        priority=TaskPriority.HIGH,
        status=TaskStatus.PENDING,
        deadline=datetime(2026, 2, 1, 10, 0)
    )


class TestDiscordIntegration:
    """Test Discord integration functionality."""

    @pytest.mark.asyncio
    async def test_post_task_to_channel_success(self, discord, sample_task):
        """Test successful task posting to Discord channel."""
        with patch.object(discord, '_api_request') as mock_api:
            mock_api.return_value = (200, {"id": "msg_123"})
            with patch.object(discord, 'get_assignee_role') as mock_role:
                mock_role.return_value = "Developer"
                with patch.object(discord, 'create_forum_thread') as mock_thread:
                    mock_thread.return_value = "thread_123"

                    result = await discord.post_task(sample_task)

                    assert result == "thread_123"
                    mock_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_task_to_channel_network_error(self, discord, sample_task):
        """Test task posting with network error."""
        with patch.object(discord, '_api_request') as mock_api:
            mock_api.return_value = (0, None)  # Network error
            with patch.object(discord, 'get_assignee_role') as mock_role:
                mock_role.return_value = "Developer"
                with patch.object(discord, 'create_forum_thread') as mock_thread:
                    mock_thread.return_value = None

                    result = await discord.post_task(sample_task)

                    assert result is None

    @pytest.mark.asyncio
    async def test_route_to_department_dev(self, discord):
        """Test routing developer tasks to DEV channel."""
        role_category = discord._get_role_category("Developer")

        assert role_category == RoleCategory.DEV

    @pytest.mark.asyncio
    async def test_route_to_department_admin(self, discord):
        """Test routing admin tasks to ADMIN channel."""
        role_category = discord._get_role_category("Administrator")

        assert role_category == RoleCategory.ADMIN

    @pytest.mark.asyncio
    async def test_route_to_department_marketing(self, discord):
        """Test routing marketing tasks to MARKETING channel."""
        role_category = discord._get_role_category("Marketing")

        assert role_category == RoleCategory.MARKETING

    @pytest.mark.asyncio
    async def test_route_to_department_design(self, discord):
        """Test routing design tasks to DESIGN channel."""
        role_category = discord._get_role_category("UI Designer")

        assert role_category == RoleCategory.DESIGN

    @pytest.mark.asyncio
    async def test_route_to_department_unknown_defaults_dev(self, discord):
        """Test unknown roles default to DEV channel."""
        role_category = discord._get_role_category("Unknown Role")

        assert role_category == RoleCategory.DEV

    @pytest.mark.asyncio
    async def test_add_reaction_success(self, discord):
        """Test adding reaction to message."""
        with patch.object(discord, '_api_request') as mock_api:
            mock_api.return_value = (204, None)

            result = await discord.add_reaction("channel_123", "msg_123", "✅")

            assert result is True
            mock_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_reaction_failure(self, discord):
        """Test reaction addition failure."""
        with patch.object(discord, '_api_request') as mock_api:
            mock_api.return_value = (403, None)  # Forbidden

            result = await discord.add_reaction("channel_123", "msg_123", "✅")

            assert result is False

    @pytest.mark.asyncio
    async def test_create_thread_success(self, discord):
        """Test forum thread creation."""
        with patch.object(discord, '_api_request') as mock_api:
            mock_api.return_value = (200, {"id": "thread_123"})
            with patch.object(discord, 'get_forum_tags') as mock_tags:
                mock_tags.return_value = [{"id": "tag_1", "name": "Pending"}]

                result = await discord.create_forum_thread(
                    "forum_123",
                    "TASK-001: Test Task",
                    "Task description"
                )

                assert result == "thread_123"

    @pytest.mark.asyncio
    async def test_create_thread_failure(self, discord):
        """Test forum thread creation failure."""
        with patch.object(discord, '_api_request') as mock_api:
            mock_api.return_value = (500, None)

            result = await discord.create_forum_thread(
                "forum_123",
                "TASK-001: Test Task",
                "Task description"
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_send_standup_report_success(self, discord):
        """Test sending standup report."""
        with patch.object(discord, 'send_message') as mock_send:
            mock_send.return_value = "msg_123"
            with patch.object(discord, '_get_channel_id') as mock_channel:
                mock_channel.return_value = "channel_123"

                result = await discord.post_standup(
                    "Daily standup summary",
                    RoleCategory.DEV
                )

                assert result is True
                mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_standup_report_no_channel(self, discord):
        """Test standup report when channel not configured."""
        with patch.object(discord, '_get_channel_id') as mock_channel:
            mock_channel.return_value = None

            result = await discord.post_standup(
                "Daily standup summary",
                RoleCategory.DEV
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_success(self, discord):
        """Test sending generic notification."""
        with patch.object(discord, 'send_message') as mock_send:
            mock_send.return_value = "msg_123"
            with patch.object(discord, '_get_channel_id') as mock_channel:
                mock_channel.return_value = "channel_123"

                result = await discord.post_alert(
                    "Test Alert",
                    "This is a test notification",
                    "info",
                    None,
                    RoleCategory.DEV
                )

                assert result is True

    @pytest.mark.asyncio
    async def test_infer_role_from_task_keywords_dev(self, discord):
        """Test role inference from task keywords - dev task."""
        role = discord._infer_role_from_task_content(
            "Fix API bug in backend",
            "Database connection issue"
        )

        assert role == RoleCategory.DEV

    @pytest.mark.asyncio
    async def test_infer_role_from_task_keywords_marketing(self, discord):
        """Test role inference from task keywords - marketing task."""
        role = discord._infer_role_from_task_content(
            "Create social media campaign",
            "Post on Instagram and Twitter"
        )

        assert role == RoleCategory.MARKETING

    @pytest.mark.asyncio
    async def test_infer_role_from_task_keywords_admin(self, discord):
        """Test role inference from task keywords - admin task."""
        role = discord._infer_role_from_task_content(
            "Schedule team meeting",
            "Organize quarterly review"
        )

        assert role == RoleCategory.ADMIN

    @pytest.mark.asyncio
    async def test_post_spec_sheet_success(self, discord):
        """Test posting detailed spec sheet."""
        with patch.object(discord, 'create_forum_thread') as mock_thread:
            mock_thread.return_value = "thread_123"
            with patch.object(discord, 'get_assignee_role') as mock_role:
                mock_role.return_value = "Developer"
                with patch.object(discord, 'pin_thread') as mock_pin:
                    mock_pin.return_value = True

                    result = await discord.post_spec_sheet(
                        task_id="TASK-001",
                        title="Build login system",
                        assignee="Mayank",
                        priority="high",
                        deadline="2026-02-01",
                        description="Implement authentication",
                        acceptance_criteria=["User can log in", "Session persists"],
                        subtasks=[{"title": "Create login form", "description": "Build UI"}]
                    )

                    assert result == "thread_123"
                    mock_thread.assert_called_once()
                    mock_pin.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_task_message_success(self, discord):
        """Test deleting task message/thread."""
        with patch.object(discord, 'delete_thread') as mock_delete:
            mock_delete.return_value = True

            result = await discord.delete_task_message(
                "TASK-001",
                "thread_123",
                is_forum_thread=True
            )

            assert result is True
            mock_delete.assert_called_once_with("thread_123")

    @pytest.mark.asyncio
    async def test_send_message_success(self, discord):
        """Test sending basic message."""
        with patch.object(discord, '_api_request') as mock_api:
            mock_api.return_value = (200, {"id": "msg_123"})

            result = await discord.send_message(
                "channel_123",
                content="Test message"
            )

            assert result == "msg_123"

    @pytest.mark.asyncio
    async def test_send_message_with_embed(self, discord):
        """Test sending message with embed."""
        with patch.object(discord, '_api_request') as mock_api:
            mock_api.return_value = (200, {"id": "msg_123"})

            embed = {
                "title": "Test",
                "description": "Test description",
                "color": 0x3498DB
            }

            result = await discord.send_message(
                "channel_123",
                embed=embed
            )

            assert result == "msg_123"

    @pytest.mark.asyncio
    async def test_edit_message_success(self, discord):
        """Test editing existing message."""
        with patch.object(discord, '_api_request') as mock_api:
            mock_api.return_value = (200, {})

            result = await discord.edit_message(
                "channel_123",
                "msg_123",
                content="Updated content"
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_get_assignee_role_from_sheets(self, discord):
        """Test looking up assignee role from Google Sheets."""
        with patch('src.integrations.sheets.sheets_integration') as mock_sheets:
            mock_sheets.get_all_team_members = AsyncMock(return_value=[
                {"Name": "Mayank", "Role": "Developer"}
            ])

            role = await discord.get_assignee_role("Mayank")

            assert role == "Developer"

    @pytest.mark.asyncio
    async def test_get_assignee_role_not_found(self, discord):
        """Test looking up non-existent assignee."""
        with patch('src.integrations.sheets.sheets_integration') as mock_sheets:
            mock_sheets.get_all_team_members = AsyncMock(return_value=[])
            with patch('src.database.repositories.get_team_repository') as mock_repo:
                mock_repo.return_value.find_member = AsyncMock(return_value=None)

                role = await discord.get_assignee_role("Unknown")

                assert role is None

    @pytest.mark.asyncio
    async def test_post_weekly_summary(self, discord):
        """Test posting weekly summary report."""
        with patch.object(discord, 'send_message') as mock_send:
            mock_send.return_value = "msg_123"
            with patch.object(discord, '_get_channel_id') as mock_channel:
                mock_channel.return_value = "channel_123"

                result = await discord.post_weekly_summary(
                    "Weekly summary content",
                    RoleCategory.DEV
                )

                assert result is True

    @pytest.mark.asyncio
    async def test_bulk_delete_threads(self, discord):
        """Test bulk thread deletion."""
        with patch.object(discord, 'get_channel_threads') as mock_threads:
            mock_threads.return_value = [
                {"id": "thread_1", "name": "TASK-001: Test"},
                {"id": "thread_2", "name": "TASK-002: Test"}
            ]
            with patch.object(discord, 'delete_thread') as mock_delete:
                mock_delete.return_value = True

                deleted, failed = await discord.bulk_delete_threads(
                    "channel_123",
                    "TASK-"
                )

                assert deleted == 2
                assert failed == 0

    @pytest.mark.asyncio
    async def test_send_direct_message_to_team(self, discord):
        """Test sending direct message to team member."""
        with patch.object(discord, 'get_assignee_role') as mock_role:
            mock_role.return_value = "Developer"
            with patch.object(discord, '_get_channel_id') as mock_channel:
                mock_channel.return_value = "channel_123"
                with patch.object(discord, 'send_message') as mock_send:
                    mock_send.return_value = "msg_123"

                    success, msg = await discord.send_direct_message_to_team(
                        "Mayank",
                        "Please check the deployment"
                    )

                    assert success is True
                    assert "sent" in msg.lower()

    @pytest.mark.asyncio
    async def test_post_task_update(self, discord):
        """Test posting task update notification."""
        with patch.object(discord, 'send_message') as mock_send:
            mock_send.return_value = "msg_123"
            with patch.object(discord, '_get_channel_id') as mock_channel:
                mock_channel.return_value = "channel_123"

                result = await discord.post_task_update(
                    "TASK-001",
                    {"priority": "high -> urgent"},
                    "Boss",
                    "priority_change",
                    RoleCategory.DEV
                )

                assert result is True

    @pytest.mark.asyncio
    async def test_api_request_retry_on_rate_limit(self, discord):
        """Test retry behavior on rate limit (429)."""
        mock_response = MagicMock()
        mock_response.status = 429
        mock_response.text = AsyncMock(return_value="Rate limited")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_request = AsyncMock()
        mock_request.__aenter__ = AsyncMock(return_value=mock_response)
        mock_request.__aexit__ = AsyncMock()

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=mock_request)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch('aiohttp.ClientSession', return_value=mock_session):
            with patch.object(discord, '_queue_failed_request') as mock_queue:
                status, data = await discord._api_request("POST", "/test", {"test": "data"})

                assert status == 429
                assert data is None
                # Should queue for retry
                mock_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_configured_categories(self, discord):
        """Test getting all configured role categories."""
        with patch.object(discord, 'channels') as mock_channels:
            mock_channels.get.return_value = {
                ChannelType.FORUM: "forum_123",
                ChannelType.TASKS: "tasks_123"
            }

            categories = discord.get_configured_categories()

            # Should return categories that have at least one channel configured
            assert isinstance(categories, list)
