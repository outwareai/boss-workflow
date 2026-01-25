"""
Tests for src/utils/team_utils.py

Tests team member lookup, assignee info retrieval, role lookup,
and Discord ID validation.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.utils.team_utils import (
    TeamMemberInfo,
    lookup_team_member,
    get_assignee_info,
    get_role_for_assignee,
    validate_discord_id,
)


class TestTeamMemberInfo:
    """Tests for TeamMemberInfo dataclass."""

    def test_create_with_all_fields(self):
        """Test creating TeamMemberInfo with all fields."""
        member = TeamMemberInfo(
            name="John Doe",
            discord_id="123456789012345678",
            email="john@example.com",
            telegram_id="987654321",
            role="Developer",
            calendar_id="calendar@example.com"
        )
        assert member.name == "John Doe"
        assert member.discord_id == "123456789012345678"
        assert member.email == "john@example.com"
        assert member.telegram_id == "987654321"
        assert member.role == "Developer"
        assert member.calendar_id == "calendar@example.com"

    def test_create_with_minimal_fields(self):
        """Test creating TeamMemberInfo with only required fields."""
        member = TeamMemberInfo(name="Jane Doe")
        assert member.name == "Jane Doe"
        assert member.discord_id is None
        assert member.email is None
        assert member.telegram_id is None
        assert member.role is None
        assert member.calendar_id is None


class TestValidateDiscordId:
    """Tests for validate_discord_id function."""

    def test_valid_discord_id_string(self):
        """Test valid Discord ID as string."""
        assert validate_discord_id("123456789012345678") is True
        assert validate_discord_id("1234567890123456789") is True

    def test_valid_discord_id_integer(self):
        """Test valid Discord ID as integer."""
        assert validate_discord_id(123456789012345678) is True

    def test_valid_discord_id_with_at_prefix(self):
        """Test Discord ID with @ prefix is accepted."""
        assert validate_discord_id("@123456789012345678") is True

    def test_invalid_discord_id_too_short(self):
        """Test Discord ID that is too short."""
        assert validate_discord_id("1234567890123456") is False  # 16 digits

    def test_invalid_discord_id_too_long(self):
        """Test Discord ID that is too long."""
        assert validate_discord_id("12345678901234567890") is False  # 20 digits

    def test_invalid_discord_id_non_numeric(self):
        """Test Discord ID with non-numeric characters."""
        assert validate_discord_id("abc123def456xyz789") is False

    def test_empty_discord_id(self):
        """Test empty Discord ID."""
        assert validate_discord_id("") is False
        assert validate_discord_id(None) is False


@pytest.mark.asyncio
class TestLookupTeamMember:
    """Tests for lookup_team_member function."""

    async def test_empty_name_returns_none(self):
        """Test that empty name returns None."""
        result = await lookup_team_member("")
        assert result is None

        result = await lookup_team_member(None)
        assert result is None

    @patch('src.database.repositories.get_team_repository')
    async def test_database_lookup_success(self, mock_get_repo):
        """Test successful database lookup."""
        # Mock team member from database
        mock_member = MagicMock()
        mock_member.name = "John Doe"
        mock_member.discord_id = "123456789012345678"
        mock_member.email = "john@example.com"
        mock_member.telegram_id = "987654321"
        mock_member.role = "Developer"

        mock_repo = AsyncMock()
        mock_repo.find_member.return_value = mock_member
        mock_get_repo.return_value = mock_repo

        result = await lookup_team_member("John")

        assert result is not None
        assert result.name == "John Doe"
        assert result.discord_id == "123456789012345678"
        assert result.email == "john@example.com"
        assert result.role == "Developer"

    @patch('src.database.repositories.get_team_repository')
    @patch('src.integrations.sheets.get_sheets_integration')
    async def test_sheets_lookup_when_db_fails(self, mock_get_sheets, mock_get_repo):
        """Test falling back to Sheets when database fails."""
        # Database fails
        mock_repo = AsyncMock()
        mock_repo.find_member.side_effect = Exception("DB error")
        mock_get_repo.return_value = mock_repo

        # Sheets succeeds
        mock_sheets = AsyncMock()
        mock_sheets.get_all_team_members.return_value = [
            {
                "Name": "Jane Doe",
                "Discord ID": "987654321098765432",
                "Email": "jane@example.com",
                "Role": "Admin"
            }
        ]
        mock_get_sheets.return_value = mock_sheets

        result = await lookup_team_member("Jane")

        assert result is not None
        assert result.name == "Jane Doe"
        assert result.discord_id == "987654321098765432"
        assert result.email == "jane@example.com"
        assert result.role == "Admin"

    @patch('src.database.repositories.get_team_repository')
    @patch('src.integrations.sheets.get_sheets_integration')
    async def test_partial_name_match_in_sheets(self, mock_get_sheets, mock_get_repo):
        """Test partial name matching in Sheets."""
        mock_repo = AsyncMock()
        mock_repo.find_member.return_value = None
        mock_get_repo.return_value = mock_repo

        mock_sheets = AsyncMock()
        mock_sheets.get_all_team_members.return_value = [
            {
                "Name": "John Smith Doe",
                "Discord ID": "123456789012345678",
                "Email": "john@example.com"
            }
        ]
        mock_get_sheets.return_value = mock_sheets

        result = await lookup_team_member("Smith")

        assert result is not None
        assert "John Smith Doe" in result.name

    @patch('src.database.repositories.get_team_repository')
    @patch('src.integrations.sheets.get_sheets_integration')
    @patch('config.team.get_default_team')
    async def test_config_fallback(self, mock_get_config, mock_get_sheets, mock_get_repo):
        """Test falling back to config/team.py."""
        # Database fails
        mock_repo = AsyncMock()
        mock_repo.find_member.return_value = None
        mock_get_repo.return_value = mock_repo

        # Sheets fails
        mock_sheets = AsyncMock()
        mock_sheets.get_all_team_members.return_value = []
        mock_get_sheets.return_value = mock_sheets

        # Config succeeds
        mock_get_config.return_value = [
            {
                "name": "Config User",
                "discord_id": "111222333444555666",
                "email": "config@example.com",
                "role": "Tester"
            }
        ]

        result = await lookup_team_member("Config")

        assert result is not None
        assert result.name == "Config User"
        assert result.role == "Tester"

    @patch('src.database.repositories.get_team_repository')
    @patch('src.integrations.sheets.get_sheets_integration')
    @patch('config.team.get_default_team')
    async def test_not_found_returns_none(self, mock_get_config, mock_get_sheets, mock_get_repo):
        """Test that unknown member returns None."""
        mock_repo = AsyncMock()
        mock_repo.find_member.return_value = None
        mock_get_repo.return_value = mock_repo

        mock_sheets = AsyncMock()
        mock_sheets.get_all_team_members.return_value = []
        mock_get_sheets.return_value = mock_sheets

        mock_get_config.return_value = []

        result = await lookup_team_member("Unknown Person")
        assert result is None


@pytest.mark.asyncio
class TestGetAssigneeInfo:
    """Tests for get_assignee_info function."""

    async def test_empty_assignee_returns_empty_dict(self):
        """Test that empty assignee returns dict with None values."""
        result = await get_assignee_info("")

        assert result["discord_id"] is None
        assert result["email"] is None
        assert result["telegram_id"] is None
        assert result["role"] is None
        assert result["calendar_id"] is None

    @patch('src.utils.team_utils.lookup_team_member')
    async def test_found_member_returns_full_info(self, mock_lookup):
        """Test that found member returns complete info."""
        mock_lookup.return_value = TeamMemberInfo(
            name="John Doe",
            discord_id="123456789012345678",
            email="john@example.com",
            telegram_id="987654321",
            role="Developer",
            calendar_id="calendar@example.com"
        )

        result = await get_assignee_info("John")

        assert result["discord_id"] == "123456789012345678"
        assert result["email"] == "john@example.com"
        assert result["telegram_id"] == "987654321"
        assert result["role"] == "Developer"
        assert result["calendar_id"] == "calendar@example.com"

    @patch('src.utils.team_utils.lookup_team_member')
    async def test_not_found_returns_none_values(self, mock_lookup):
        """Test that not found member returns None values."""
        mock_lookup.return_value = None

        result = await get_assignee_info("Unknown")

        assert result["discord_id"] is None
        assert result["email"] is None

    @patch('src.utils.team_utils.lookup_team_member')
    async def test_integer_ids_converted_to_string(self, mock_lookup):
        """Test that integer IDs are converted to strings."""
        mock_lookup.return_value = TeamMemberInfo(
            name="Jane Doe",
            discord_id=123456789012345678,  # Integer
            telegram_id=987654321  # Integer
        )

        result = await get_assignee_info("Jane")

        assert isinstance(result["discord_id"], str)
        assert result["discord_id"] == "123456789012345678"
        assert isinstance(result["telegram_id"], str)


@pytest.mark.asyncio
class TestGetRoleForAssignee:
    """Tests for get_role_for_assignee function."""

    @patch('src.utils.team_utils.lookup_team_member')
    async def test_found_member_returns_role(self, mock_lookup):
        """Test that found member returns role."""
        mock_lookup.return_value = TeamMemberInfo(
            name="John Doe",
            role="Developer"
        )

        result = await get_role_for_assignee("John")
        assert result == "Developer"

    @patch('src.utils.team_utils.lookup_team_member')
    async def test_not_found_returns_none(self, mock_lookup):
        """Test that not found member returns None."""
        mock_lookup.return_value = None

        result = await get_role_for_assignee("Unknown")
        assert result is None

    @patch('src.utils.team_utils.lookup_team_member')
    async def test_member_without_role_returns_none(self, mock_lookup):
        """Test that member without role returns None."""
        mock_lookup.return_value = TeamMemberInfo(
            name="Jane Doe",
            role=None
        )

        result = await get_role_for_assignee("Jane")
        assert result is None
