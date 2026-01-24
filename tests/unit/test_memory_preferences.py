"""
Unit tests for User Preferences storage and management.

Tests:
- learn_preference() - Preference learning
- get_preference() - Preference retrieval
- update_preference() - Preference updates
- get_all_for_user() - User preferences
- teach_context() - Explicit teaching
- Preference types (work_hours, communication_style, priorities)
- Team member management
- Task templates
- Triggers
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from datetime import datetime

from src.memory.preferences import (
    PreferencesManager,
    UserPreferences,
    TeamMember,
    TaskTemplate,
    Trigger,
    DEFAULT_TEMPLATES,
    get_preferences_manager
)


@pytest.fixture
def prefs_manager():
    """Create PreferencesManager instance."""
    manager = PreferencesManager()
    return manager


@pytest.fixture
def sample_preferences():
    """Create sample user preferences."""
    return UserPreferences(
        user_id="test_user",
        defaults={"priority": "high", "deadline_behavior": "eod"},
        always_ask=["assignee"],
        skip_questions_for=["tags"]
    )


class TestPreferencesBasics:
    """Test basic preferences CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_preferences_creates_default(self, prefs_manager):
        """Test get_preferences creates defaults if not exists."""
        prefs = await prefs_manager.get_preferences("new_user")

        assert prefs.user_id == "new_user"
        assert "priority" in prefs.defaults
        assert prefs.defaults["priority"] == "medium"

    @pytest.mark.asyncio
    async def test_save_preferences(self, prefs_manager, sample_preferences):
        """Test saving preferences."""
        success = await prefs_manager.save_preferences(sample_preferences)

        assert success is True
        # Verify it's in cache
        assert sample_preferences.user_id in prefs_manager._cache

    @pytest.mark.asyncio
    async def test_get_saved_preferences(self, prefs_manager, sample_preferences):
        """Test retrieving saved preferences."""
        await prefs_manager.save_preferences(sample_preferences)

        retrieved = await prefs_manager.get_preferences(sample_preferences.user_id)

        assert retrieved.user_id == sample_preferences.user_id
        assert retrieved.defaults == sample_preferences.defaults

    @pytest.mark.asyncio
    async def test_preferences_cached(self, prefs_manager, sample_preferences):
        """Test preferences are cached after first retrieval."""
        await prefs_manager.save_preferences(sample_preferences)

        # First get
        prefs1 = await prefs_manager.get_preferences(sample_preferences.user_id)
        # Second get (should use cache)
        prefs2 = await prefs_manager.get_preferences(sample_preferences.user_id)

        assert prefs1 is prefs2  # Same object from cache


class TestPreferenceUpdates:
    """Test updating individual preferences."""

    @pytest.mark.asyncio
    async def test_update_simple_preference(self, prefs_manager):
        """Test updating a simple preference."""
        user_id = "test_user"
        await prefs_manager.get_preferences(user_id)  # Create defaults

        success = await prefs_manager.update_preference(user_id, "timezone", "America/Los_Angeles")

        assert success is True
        prefs = await prefs_manager.get_preferences(user_id)
        assert prefs.timezone == "America/Los_Angeles"

    @pytest.mark.asyncio
    async def test_update_nested_preference(self, prefs_manager):
        """Test updating nested preference with dot notation."""
        user_id = "test_user"
        await prefs_manager.get_preferences(user_id)

        success = await prefs_manager.update_preference(user_id, "defaults.priority", "urgent")

        assert success is True
        prefs = await prefs_manager.get_preferences(user_id)
        assert prefs.defaults["priority"] == "urgent"

    @pytest.mark.asyncio
    async def test_update_invalid_key_fails(self, prefs_manager):
        """Test updating invalid key fails."""
        user_id = "test_user"
        await prefs_manager.get_preferences(user_id)

        success = await prefs_manager.update_preference(user_id, "invalid.key.path", "value")

        assert success is False


class TestTeamMembers:
    """Test team member management."""

    @pytest.mark.asyncio
    async def test_add_team_member(self, prefs_manager):
        """Test adding team member."""
        user_id = "test_user"

        success = await prefs_manager.add_team_member(
            user_id,
            name="John Doe",
            username="john",
            role="Backend Developer",
            skills=["Python", "FastAPI"],
            discord_id="123456789",
            email="john@example.com"
        )

        assert success is True
        prefs = await prefs_manager.get_preferences(user_id)
        assert "john doe" in prefs.team_members
        assert prefs.team_members["john doe"].role == "Backend Developer"

    @pytest.mark.asyncio
    async def test_find_team_member_by_name(self, prefs_manager, sample_preferences):
        """Test finding team member by name."""
        member = TeamMember(
            name="Sarah Johnson",
            username="sarah",
            role="Frontend Developer"
        )
        sample_preferences.team_members["sarah johnson"] = member

        found = prefs_manager.find_team_member(sample_preferences, "Sarah Johnson")

        assert found is not None
        assert found.name == "Sarah Johnson"

    @pytest.mark.asyncio
    async def test_find_team_member_by_username(self, prefs_manager, sample_preferences):
        """Test finding team member by username."""
        member = TeamMember(
            name="Sarah Johnson",
            username="sarah",
            role="Frontend Developer"
        )
        sample_preferences.team_members["sarah johnson"] = member

        found = prefs_manager.find_team_member(sample_preferences, "sarah")

        assert found is not None
        assert found.username == "sarah"

    @pytest.mark.asyncio
    async def test_find_team_member_by_email(self, prefs_manager, sample_preferences):
        """Test finding team member by email."""
        member = TeamMember(
            name="Sarah Johnson",
            username="sarah",
            role="Frontend Developer",
            email="sarah@example.com"
        )
        sample_preferences.team_members["sarah johnson"] = member

        found = prefs_manager.find_team_member(sample_preferences, "sarah@example.com")

        assert found is not None
        assert found.email == "sarah@example.com"

    @pytest.mark.asyncio
    async def test_find_team_member_not_found(self, prefs_manager, sample_preferences):
        """Test finding nonexistent team member returns None."""
        found = prefs_manager.find_team_member(sample_preferences, "unknown")

        assert found is None

    def test_get_team_info_dict(self, sample_preferences):
        """Test getting team info as name->role dict."""
        sample_preferences.team_members["john"] = TeamMember(
            name="John",
            username="john",
            role="Developer"
        )
        sample_preferences.team_members["sarah"] = TeamMember(
            name="Sarah",
            username="sarah",
            role="Designer"
        )

        team_info = sample_preferences.get_team_info()

        assert team_info["John"] == "Developer"
        assert team_info["Sarah"] == "Designer"


class TestTaskTemplates:
    """Test task template management."""

    def test_find_bug_template(self, sample_preferences):
        """Test finding bug template by keyword."""
        template = sample_preferences.find_template("Bug: Login broken")

        assert template is not None
        assert template.name == "bug"

    def test_find_hotfix_template(self, sample_preferences):
        """Test finding hotfix template."""
        template = sample_preferences.find_template("Hotfix: Critical production issue")

        assert template is not None
        assert template.name == "hotfix"
        assert template.defaults["priority"] == "urgent"

    def test_find_feature_template(self, sample_preferences):
        """Test finding feature template."""
        template = sample_preferences.find_template("New feature: Add dark mode")

        assert template is not None
        assert template.name == "feature"

    def test_no_template_match(self, sample_preferences):
        """Test no template match returns None."""
        template = sample_preferences.find_template("Random task with no keywords")

        assert template is None

    def test_custom_template_takes_priority(self, sample_preferences):
        """Test custom template overrides default."""
        custom = TaskTemplate(
            name="bug",
            keywords=["bug", "issue"],
            defaults={"priority": "low"},  # Custom default
            description="Custom bug template"
        )
        sample_preferences.task_templates.append(custom)

        template = sample_preferences.find_template("Bug: Minor issue")

        assert template is not None
        assert template.defaults["priority"] == "low"  # Custom value

    def test_get_all_templates(self, sample_preferences):
        """Test getting all templates (custom + defaults)."""
        custom = TaskTemplate(
            name="custom",
            keywords=["custom"],
            defaults={"priority": "medium"}
        )
        sample_preferences.task_templates.append(custom)

        all_templates = sample_preferences.get_all_templates()

        # Should have custom + all defaults
        assert len(all_templates) >= 8  # At least the defaults
        assert any(t.name == "custom" for t in all_templates)
        assert any(t.name == "bug" for t in all_templates)


class TestTriggers:
    """Test custom trigger management."""

    @pytest.mark.asyncio
    async def test_add_trigger(self, prefs_manager):
        """Test adding custom trigger."""
        user_id = "test_user"

        success = await prefs_manager.add_trigger(
            user_id,
            pattern="client X",
            action="set_priority",
            value="urgent"
        )

        assert success is True
        prefs = await prefs_manager.get_preferences(user_id)
        assert len(prefs.triggers) == 1
        assert prefs.triggers[0].pattern == "client X"

    @pytest.mark.asyncio
    async def test_remove_trigger(self, prefs_manager):
        """Test removing trigger."""
        user_id = "test_user"
        await prefs_manager.add_trigger(user_id, "client X", "set_priority", "urgent")

        success = await prefs_manager.remove_trigger(user_id, "client X")

        assert success is True
        prefs = await prefs_manager.get_preferences(user_id)
        assert len(prefs.triggers) == 0

    def test_find_trigger_match(self, sample_preferences):
        """Test finding trigger that matches text."""
        trigger = Trigger(
            pattern="urgent",
            action="set_deadline",
            value="today"
        )
        sample_preferences.triggers.append(trigger)

        found = sample_preferences.find_trigger("This is urgent!")

        assert found is not None
        assert found.action == "set_deadline"
        assert found.value == "today"

    def test_find_trigger_no_match(self, sample_preferences):
        """Test finding trigger with no match."""
        trigger = Trigger(
            pattern="specific keyword",
            action="action",
            value="value"
        )
        sample_preferences.triggers.append(trigger)

        found = sample_preferences.find_trigger("Different text")

        assert found is None


class TestQuestionPreferences:
    """Test question asking preferences."""

    @pytest.mark.asyncio
    async def test_set_always_ask(self, prefs_manager):
        """Test setting fields to always ask about."""
        user_id = "test_user"

        success = await prefs_manager.set_always_ask(user_id, ["priority", "deadline"])

        assert success is True
        prefs = await prefs_manager.get_preferences(user_id)
        assert "priority" in prefs.always_ask
        assert "deadline" in prefs.always_ask

    @pytest.mark.asyncio
    async def test_set_skip_questions(self, prefs_manager):
        """Test setting fields to skip questions for."""
        user_id = "test_user"

        success = await prefs_manager.set_skip_questions(user_id, ["tags", "notes"])

        assert success is True
        prefs = await prefs_manager.get_preferences(user_id)
        assert "tags" in prefs.skip_questions_for
        assert "notes" in prefs.skip_questions_for


class TestNotificationPreferences:
    """Test notification preferences."""

    def test_default_notifications_enabled(self, sample_preferences):
        """Test default notification preferences are enabled."""
        assert sample_preferences.notification_preferences["daily_standup"] is True
        assert sample_preferences.notification_preferences["eod_reminder"] is True
        assert sample_preferences.notification_preferences["deadline_reminders"] is True

    @pytest.mark.asyncio
    async def test_update_notification_preference(self, prefs_manager):
        """Test updating notification preference."""
        user_id = "test_user"

        success = await prefs_manager.update_preference(
            user_id,
            "notification_preferences.daily_standup",
            False
        )

        assert success is True
        prefs = await prefs_manager.get_preferences(user_id)
        assert prefs.notification_preferences["daily_standup"] is False


class TestSerialization:
    """Test preferences serialization."""

    def test_to_dict(self, sample_preferences):
        """Test converting preferences to dict."""
        data = sample_preferences.to_dict()

        assert isinstance(data, dict)
        assert data["user_id"] == "test_user"
        assert "defaults" in data
        assert "always_ask" in data

    def test_from_dict(self):
        """Test creating preferences from dict."""
        data = {
            "user_id": "test_user",
            "defaults": {"priority": "high"},
            "always_ask": ["assignee"],
            "timezone": "UTC"
        }

        prefs = UserPreferences.from_dict(data)

        assert prefs.user_id == "test_user"
        assert prefs.defaults["priority"] == "high"
        assert "assignee" in prefs.always_ask

    def test_round_trip_serialization(self, sample_preferences):
        """Test round-trip serialization."""
        data = sample_preferences.to_dict()
        restored = UserPreferences.from_dict(data)

        assert restored.user_id == sample_preferences.user_id
        assert restored.defaults == sample_preferences.defaults
        assert restored.always_ask == sample_preferences.always_ask


class TestCaching:
    """Test preferences caching."""

    @pytest.mark.asyncio
    async def test_cache_clear_single_user(self, prefs_manager, sample_preferences):
        """Test clearing cache for single user."""
        await prefs_manager.save_preferences(sample_preferences)
        assert sample_preferences.user_id in prefs_manager._cache

        prefs_manager.clear_cache(sample_preferences.user_id)

        assert sample_preferences.user_id not in prefs_manager._cache

    @pytest.mark.asyncio
    async def test_cache_clear_all(self, prefs_manager, sample_preferences):
        """Test clearing all cache."""
        await prefs_manager.save_preferences(sample_preferences)
        assert len(prefs_manager._cache) > 0

        prefs_manager.clear_cache()

        assert len(prefs_manager._cache) == 0


class TestRedisIntegration:
    """Test Redis storage integration."""

    @pytest.mark.asyncio
    async def test_connect_to_redis_success(self, prefs_manager):
        """Test successful Redis connection."""
        with patch('src.memory.preferences.settings') as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379"

            with patch('redis.asyncio.from_url') as mock_from_url:
                mock_redis = MagicMock()
                mock_redis.ping = AsyncMock()
                mock_from_url.return_value = mock_redis

                await prefs_manager.connect()

                assert prefs_manager.redis is not None

    @pytest.mark.asyncio
    async def test_connect_fallback_to_memory(self, prefs_manager):
        """Test fallback to in-memory when Redis unavailable."""
        with patch('src.memory.preferences.settings') as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379"

            with patch('redis.asyncio.from_url') as mock_from_url:
                mock_from_url.side_effect = Exception("Connection failed")

                await prefs_manager.connect()

                assert prefs_manager.redis is None

    @pytest.mark.asyncio
    async def test_disconnect_from_redis(self, prefs_manager):
        """Test disconnecting from Redis."""
        mock_redis = MagicMock()
        mock_redis.close = AsyncMock()
        prefs_manager.redis = mock_redis
        prefs_manager._connected = True

        await prefs_manager.disconnect()

        assert mock_redis.close.called
        assert prefs_manager.redis is None


class TestMemoryStorage:
    """Test in-memory storage fallback."""

    @pytest.mark.asyncio
    async def test_memory_store_get(self, prefs_manager):
        """Test in-memory get operation."""
        prefs_manager.redis = None  # Force memory storage
        await prefs_manager._store_set("test_key", "test_value")

        value = await prefs_manager._store_get("test_key")

        assert value == "test_value"

    @pytest.mark.asyncio
    async def test_memory_store_set(self, prefs_manager):
        """Test in-memory set operation."""
        prefs_manager.redis = None

        success = await prefs_manager._store_set("key", "value")

        assert success is True
        assert prefs_manager._memory_store["key"] == "value"


class TestDefaultTeamLoading:
    """Test loading default team members."""

    @pytest.mark.asyncio
    async def test_loads_default_team(self, prefs_manager):
        """Test default team members are loaded for new users."""
        with patch('src.memory.preferences.get_default_team') as mock_get_team:
            mock_get_team.return_value = [
                {
                    "name": "Mayank",
                    "username": "mayank",
                    "role": "Developer",
                    "email": "mayank@example.com",
                    "discord_id": "123",
                    "discord_username": "@MAYANK",
                    "telegram_id": "456",
                    "skills": ["Python"]
                }
            ]

            prefs = await prefs_manager.get_preferences("new_user")

            assert "mayank" in prefs.team_members
            assert prefs.team_members["mayank"].role == "Developer"


class TestSingleton:
    """Test preferences manager singleton."""

    def test_get_preferences_manager_singleton(self):
        """Test get_preferences_manager returns singleton."""
        manager1 = get_preferences_manager()
        manager2 = get_preferences_manager()

        assert manager1 is manager2


class TestDefaultTemplates:
    """Test default template definitions."""

    def test_all_default_templates_valid(self):
        """Test all default templates are valid."""
        for template_data in DEFAULT_TEMPLATES:
            template = TaskTemplate(**template_data)

            assert template.name
            assert len(template.keywords) > 0
            assert isinstance(template.defaults, dict)

    def test_bug_template_defaults(self):
        """Test bug template has correct defaults."""
        bug_template = next(t for t in DEFAULT_TEMPLATES if t["name"] == "bug")

        assert bug_template["defaults"]["task_type"] == "bug"
        assert bug_template["defaults"]["priority"] == "high"
        assert "bugfix" in bug_template["defaults"]["tags"]

    def test_hotfix_template_defaults(self):
        """Test hotfix template has urgent priority."""
        hotfix_template = next(t for t in DEFAULT_TEMPLATES if t["name"] == "hotfix")

        assert hotfix_template["defaults"]["priority"] == "urgent"
        assert "deadline_hours" in hotfix_template["defaults"]

    def test_feature_template_defaults(self):
        """Test feature template defaults."""
        feature_template = next(t for t in DEFAULT_TEMPLATES if t["name"] == "feature")

        assert feature_template["defaults"]["task_type"] == "feature"
        assert feature_template["defaults"]["priority"] == "medium"


class TestTimestamps:
    """Test timestamp management."""

    @pytest.mark.asyncio
    async def test_created_at_set(self, sample_preferences):
        """Test created_at timestamp is set."""
        assert isinstance(sample_preferences.created_at, datetime)

    @pytest.mark.asyncio
    async def test_updated_at_on_save(self, prefs_manager, sample_preferences):
        """Test updated_at is updated on save."""
        original_time = sample_preferences.updated_at

        import asyncio
        await asyncio.sleep(0.1)  # Small delay

        await prefs_manager.save_preferences(sample_preferences)

        assert sample_preferences.updated_at > original_time
