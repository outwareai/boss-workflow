"""
User preferences storage and management.

Stores user preferences in Redis for fast access and PostgreSQL for persistence.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import redis.asyncio as redis

from config import settings
from config.team import get_default_team

logger = logging.getLogger(__name__)


class TeamMember(BaseModel):
    """Team member information."""
    name: str
    username: str  # Primary username
    telegram_id: str = ""  # Telegram user ID for notifications
    discord_id: str = ""  # Discord user ID for mentions (e.g., "123456789")
    discord_username: str = ""  # Discord username (e.g., "@MAYANK")
    email: str = ""  # Google email for Sheets/Calendar
    role: str = ""  # e.g., "backend specialist", "frontend developer"
    skills: List[str] = Field(default_factory=list)
    default_task_types: List[str] = Field(default_factory=list)  # Task types usually assigned


class TaskTemplate(BaseModel):
    """Pre-defined task template with auto-fill defaults."""
    name: str  # Template name (e.g., "bug", "hotfix", "feature")
    keywords: List[str] = Field(default_factory=list)  # Keywords that trigger this template
    defaults: Dict[str, Any] = Field(default_factory=dict)  # Default values to apply
    # Defaults can include: task_type, priority, tags, effort, deadline_hours
    description: str = ""  # Template description


# Default built-in templates
DEFAULT_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "bug",
        "keywords": ["bug", "bug:", "bugfix", "issue", "broken", "not working", "crash", "error"],
        "defaults": {"task_type": "bug", "priority": "high", "tags": ["bugfix"]},
        "description": "Bug fix - high priority by default"
    },
    {
        "name": "hotfix",
        "keywords": ["hotfix", "hotfix:", "critical fix", "production issue", "p0", "sev0"],
        "defaults": {"task_type": "bug", "priority": "urgent", "tags": ["hotfix"], "deadline_hours": 4},
        "description": "Critical hotfix - urgent, 4 hour deadline"
    },
    {
        "name": "feature",
        "keywords": ["feature", "feature:", "new feature", "add feature", "implement"],
        "defaults": {"task_type": "feature", "priority": "medium", "effort": "1 day", "tags": ["feature"]},
        "description": "New feature - medium priority, 1 day effort"
    },
    {
        "name": "research",
        "keywords": ["research", "research:", "investigate", "explore", "look into", "analyze"],
        "defaults": {"task_type": "research", "priority": "low", "tags": ["research"]},
        "description": "Research/investigation - low priority"
    },
    {
        "name": "meeting",
        "keywords": ["meeting", "meeting:", "sync", "call", "standup"],
        "defaults": {"task_type": "meeting", "priority": "medium", "effort": "1 hour", "tags": ["meeting"]},
        "description": "Meeting - 1 hour effort"
    },
    {
        "name": "docs",
        "keywords": ["docs", "docs:", "documentation", "document", "readme", "write docs"],
        "defaults": {"task_type": "task", "priority": "low", "tags": ["documentation"]},
        "description": "Documentation task - low priority"
    },
    {
        "name": "refactor",
        "keywords": ["refactor", "refactor:", "cleanup", "clean up", "improve code", "tech debt"],
        "defaults": {"task_type": "task", "priority": "low", "tags": ["refactor", "tech-debt"]},
        "description": "Refactoring - low priority"
    },
    {
        "name": "test",
        "keywords": ["test", "test:", "testing", "write tests", "add tests", "unit test"],
        "defaults": {"task_type": "task", "priority": "medium", "tags": ["testing"]},
        "description": "Testing task - medium priority"
    }
]


class Trigger(BaseModel):
    """Custom trigger that modifies task behavior."""
    pattern: str  # Text pattern to match (e.g., "client X", "urgent")
    action: str  # What to do (e.g., "set_priority", "set_deadline")
    value: Any  # Value to set
    created_at: datetime = Field(default_factory=datetime.now)


class UserPreferences(BaseModel):
    """User preferences model."""

    user_id: str

    # Default values
    defaults: Dict[str, Any] = Field(default_factory=lambda: {
        "priority": "medium",
        "deadline_behavior": "next_business_day",
        "spec_format": "detailed",
    })

    # Question preferences
    always_ask: List[str] = Field(default_factory=list)  # Fields to always ask about
    skip_questions_for: List[str] = Field(default_factory=list)  # Fields to never ask about
    always_show_preview: bool = True

    # Team knowledge
    team_members: Dict[str, TeamMember] = Field(default_factory=dict)

    # Custom terminology/triggers
    triggers: List[Trigger] = Field(default_factory=list)

    # Task templates
    task_templates: List[TaskTemplate] = Field(default_factory=list)

    # Timezone
    timezone: str = "America/New_York"

    # Communication preferences
    notification_preferences: Dict[str, bool] = Field(default_factory=lambda: {
        "daily_standup": True,
        "eod_reminder": True,
        "weekly_summary": True,
        "deadline_reminders": True,
        "overdue_alerts": True,
    })

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def get_team_info(self) -> Dict[str, str]:
        """Get team info as simple name->role mapping."""
        return {
            member.name: member.role
            for member in self.team_members.values()
        }

    def find_trigger(self, text: str) -> Optional[Trigger]:
        """Find a trigger that matches the given text."""
        text_lower = text.lower()
        for trigger in self.triggers:
            if trigger.pattern.lower() in text_lower:
                return trigger
        return None

    def find_template(self, text: str) -> Optional[TaskTemplate]:
        """Find a task template that matches the given text."""
        text_lower = text.lower()

        # First check user-defined templates
        for template in self.task_templates:
            for keyword in template.keywords:
                if keyword.lower() in text_lower:
                    return template

        # Then check default templates
        for template_data in DEFAULT_TEMPLATES:
            for keyword in template_data["keywords"]:
                if keyword.lower() in text_lower:
                    return TaskTemplate(**template_data)

        return None

    def get_all_templates(self) -> List[TaskTemplate]:
        """Get all available templates (user + defaults)."""
        templates = list(self.task_templates)
        for template_data in DEFAULT_TEMPLATES:
            # Check if user hasn't overridden this template
            if not any(t.name == template_data["name"] for t in templates):
                templates.append(TaskTemplate(**template_data))
        return templates

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserPreferences":
        """Create from dictionary."""
        return cls(**data)


class PreferencesManager:
    """
    Manages user preferences storage and retrieval.

    Uses Redis for fast access and caching.
    Falls back to in-memory storage when Redis isn't available.
    """

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self._cache: Dict[str, UserPreferences] = {}
        self._memory_store: Dict[str, str] = {}  # Fallback in-memory storage
        self._connected: bool = False

    async def connect(self):
        """Connect to Redis (optional - falls back to in-memory)."""
        if self._connected:
            return

        if settings.redis_url:
            try:
                self.redis = await redis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                # Test connection
                await self.redis.ping()
                logger.info("Connected to Redis for preferences")
            except Exception as e:
                logger.warning(f"Redis not available for preferences, using in-memory: {e}")
                self.redis = None

        self._connected = True

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            self.redis = None
        self._connected = False

    async def _store_get(self, key: str) -> Optional[str]:
        """Get value from Redis or memory."""
        if self.redis:
            return await self.redis.get(key)
        return self._memory_store.get(key)

    async def _store_set(self, key: str, value: str) -> bool:
        """Set value in Redis or memory."""
        try:
            if self.redis:
                await self.redis.set(key, value)
            else:
                self._memory_store[key] = value
            return True
        except Exception as e:
            logger.error(f"Error storing key {key}: {e}")
            return False

    def _get_key(self, user_id: str) -> str:
        """Get Redis key for user preferences."""
        return f"preferences:{user_id}"

    async def get_preferences(self, user_id: str) -> UserPreferences:
        """
        Get user preferences, creating defaults if not exists.

        Checks cache first, then Redis/memory.
        """
        # Check cache
        if user_id in self._cache:
            return self._cache[user_id]

        await self.connect()

        # Check storage (Redis or memory)
        key = self._get_key(user_id)
        data = await self._store_get(key)

        if data:
            try:
                prefs = UserPreferences.from_dict(json.loads(data))
                self._cache[user_id] = prefs
                return prefs
            except Exception as e:
                logger.error(f"Error loading preferences for {user_id}: {e}")

        # Create default preferences with default team
        prefs = UserPreferences(user_id=user_id)

        # Load default team members
        for member_data in get_default_team():
            member = TeamMember(
                name=member_data.get("name", ""),
                username=member_data.get("username", ""),
                role=member_data.get("role", ""),
                email=member_data.get("email", ""),
                discord_id=member_data.get("discord_id", ""),
                discord_username=member_data.get("discord_username", ""),
                telegram_id=member_data.get("telegram_id", ""),
                skills=member_data.get("skills", []),
            )
            prefs.team_members[member.name.lower()] = member

        await self.save_preferences(prefs)
        return prefs

    async def save_preferences(self, prefs: UserPreferences) -> bool:
        """Save user preferences to storage."""
        await self.connect()

        try:
            key = self._get_key(prefs.user_id)
            prefs.updated_at = datetime.now()
            await self._store_set(key, json.dumps(prefs.to_dict()))
            self._cache[prefs.user_id] = prefs
            logger.info(f"Saved preferences for user {prefs.user_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving preferences: {e}")
            return False

    async def update_preference(
        self,
        user_id: str,
        key: str,
        value: Any
    ) -> bool:
        """Update a single preference value."""
        prefs = await self.get_preferences(user_id)

        # Handle nested keys (e.g., "defaults.priority")
        keys = key.split(".")
        obj = prefs

        for k in keys[:-1]:
            if hasattr(obj, k):
                obj = getattr(obj, k)
            elif isinstance(obj, dict):
                obj = obj.get(k, {})
            else:
                logger.error(f"Invalid preference key: {key}")
                return False

        final_key = keys[-1]
        if isinstance(obj, dict):
            obj[final_key] = value
        elif hasattr(obj, final_key):
            setattr(obj, final_key, value)
        else:
            logger.error(f"Invalid preference key: {key}")
            return False

        return await self.save_preferences(prefs)

    async def add_team_member(
        self,
        user_id: str,
        name: str,
        username: str,
        role: str = "",
        skills: List[str] = None,
        discord_id: str = "",
        discord_username: str = "",
        email: str = "",
        telegram_id: str = ""
    ) -> bool:
        """Add a team member to user's knowledge."""
        prefs = await self.get_preferences(user_id)

        member = TeamMember(
            name=name,
            username=username,
            role=role,
            skills=skills or [],
            discord_id=discord_id,
            discord_username=discord_username,
            email=email,
            telegram_id=telegram_id
        )

        prefs.team_members[name.lower()] = member
        return await self.save_preferences(prefs)

    def find_team_member(self, prefs: UserPreferences, identifier: str) -> Optional[TeamMember]:
        """Find a team member by name, username, or email."""
        identifier_lower = identifier.lower().strip()

        for key, member in prefs.team_members.items():
            if (identifier_lower == key or
                identifier_lower == member.name.lower() or
                identifier_lower == member.username.lower() or
                identifier_lower == member.email.lower() or
                identifier_lower == member.discord_username.lower().lstrip('@')):
                return member

        return None

    async def add_trigger(
        self,
        user_id: str,
        pattern: str,
        action: str,
        value: Any
    ) -> bool:
        """Add a custom trigger."""
        prefs = await self.get_preferences(user_id)

        trigger = Trigger(
            pattern=pattern,
            action=action,
            value=value
        )

        prefs.triggers.append(trigger)
        return await self.save_preferences(prefs)

    async def remove_trigger(self, user_id: str, pattern: str) -> bool:
        """Remove a trigger by pattern."""
        prefs = await self.get_preferences(user_id)

        prefs.triggers = [t for t in prefs.triggers if t.pattern.lower() != pattern.lower()]
        return await self.save_preferences(prefs)

    async def set_always_ask(self, user_id: str, fields: List[str]) -> bool:
        """Set fields to always ask about."""
        prefs = await self.get_preferences(user_id)
        prefs.always_ask = fields
        return await self.save_preferences(prefs)

    async def set_skip_questions(self, user_id: str, fields: List[str]) -> bool:
        """Set fields to skip questions for."""
        prefs = await self.get_preferences(user_id)
        prefs.skip_questions_for = fields
        return await self.save_preferences(prefs)

    def clear_cache(self, user_id: Optional[str] = None):
        """Clear the preferences cache."""
        if user_id:
            self._cache.pop(user_id, None)
        else:
            self._cache.clear()


# Singleton instance
preferences_manager = PreferencesManager()


def get_preferences_manager() -> PreferencesManager:
    """Get the preferences manager instance."""
    return preferences_manager
