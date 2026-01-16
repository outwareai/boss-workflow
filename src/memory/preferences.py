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

logger = logging.getLogger(__name__)


class TeamMember(BaseModel):
    """Team member information."""
    name: str
    username: str  # Discord/Telegram username
    role: str = ""  # e.g., "backend specialist", "frontend developer"
    skills: List[str] = Field(default_factory=list)
    default_task_types: List[str] = Field(default_factory=list)  # Task types usually assigned


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
    """

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self._cache: Dict[str, UserPreferences] = {}

    async def connect(self):
        """Connect to Redis."""
        if not self.redis:
            self.redis = await redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info("Connected to Redis for preferences")

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            self.redis = None

    def _get_key(self, user_id: str) -> str:
        """Get Redis key for user preferences."""
        return f"preferences:{user_id}"

    async def get_preferences(self, user_id: str) -> UserPreferences:
        """
        Get user preferences, creating defaults if not exists.

        Checks cache first, then Redis.
        """
        # Check cache
        if user_id in self._cache:
            return self._cache[user_id]

        await self.connect()

        # Check Redis
        key = self._get_key(user_id)
        data = await self.redis.get(key)

        if data:
            try:
                prefs = UserPreferences.from_dict(json.loads(data))
                self._cache[user_id] = prefs
                return prefs
            except Exception as e:
                logger.error(f"Error loading preferences for {user_id}: {e}")

        # Create default preferences
        prefs = UserPreferences(user_id=user_id)
        await self.save_preferences(prefs)
        return prefs

    async def save_preferences(self, prefs: UserPreferences) -> bool:
        """Save user preferences to Redis."""
        await self.connect()

        try:
            key = self._get_key(prefs.user_id)
            prefs.updated_at = datetime.now()
            await self.redis.set(key, json.dumps(prefs.to_dict()))
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
        skills: List[str] = None
    ) -> bool:
        """Add a team member to user's knowledge."""
        prefs = await self.get_preferences(user_id)

        member = TeamMember(
            name=name,
            username=username,
            role=role,
            skills=skills or []
        )

        prefs.team_members[name.lower()] = member
        return await self.save_preferences(prefs)

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
