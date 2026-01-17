"""
AI Memory repository for persistent user context.

Stores:
- User preferences (from /teach)
- Team knowledge
- Custom triggers (ASAP -> 4 hours)
- Learned patterns
- Recent context for continuity
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from ..connection import get_database
from ..models import AIMemoryDB

logger = logging.getLogger(__name__)


class AIMemoryRepository:
    """Repository for AI memory operations."""

    def __init__(self):
        self.db = get_database()

    async def get_or_create(self, user_id: str) -> AIMemoryDB:
        """Get user memory or create if doesn't exist."""
        async with self.db.session() as session:
            result = await session.execute(
                select(AIMemoryDB).where(AIMemoryDB.user_id == user_id)
            )
            memory = result.scalar_one_or_none()

            if not memory:
                memory = AIMemoryDB(
                    user_id=user_id,
                    preferences={},
                    team_knowledge={},
                    custom_triggers={},
                    learned_patterns={},
                    recent_context={},
                )
                session.add(memory)
                await session.flush()
                logger.info(f"Created AI memory for user {user_id}")

            return memory

    async def get(self, user_id: str) -> Optional[AIMemoryDB]:
        """Get user memory."""
        async with self.db.session() as session:
            result = await session.execute(
                select(AIMemoryDB).where(AIMemoryDB.user_id == user_id)
            )
            return result.scalar_one_or_none()

    # ==================== PREFERENCES ====================

    async def get_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get user preferences."""
        memory = await self.get_or_create(user_id)
        return memory.preferences or {}

    async def update_preferences(
        self,
        user_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update user preferences (merge with existing)."""
        async with self.db.session() as session:
            memory = await self.get_or_create(user_id)

            current_prefs = memory.preferences or {}
            current_prefs.update(updates)

            await session.execute(
                update(AIMemoryDB)
                .where(AIMemoryDB.user_id == user_id)
                .values(preferences=current_prefs, updated_at=datetime.now())
            )

            logger.info(f"Updated preferences for user {user_id}: {list(updates.keys())}")
            return current_prefs

    async def set_preference(
        self,
        user_id: str,
        key: str,
        value: Any
    ) -> Dict[str, Any]:
        """Set a single preference."""
        return await self.update_preferences(user_id, {key: value})

    # ==================== TEAM KNOWLEDGE ====================

    async def get_team_knowledge(self, user_id: str) -> Dict[str, Any]:
        """Get team knowledge for a user."""
        memory = await self.get_or_create(user_id)
        return memory.team_knowledge or {}

    async def add_team_member(
        self,
        user_id: str,
        member_name: str,
        member_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Add or update a team member in knowledge base."""
        async with self.db.session() as session:
            memory = await self.get_or_create(user_id)

            team = memory.team_knowledge or {}
            team[member_name.lower()] = {
                "name": member_name,
                **member_info,
                "added_at": datetime.now().isoformat(),
            }

            await session.execute(
                update(AIMemoryDB)
                .where(AIMemoryDB.user_id == user_id)
                .values(team_knowledge=team, updated_at=datetime.now())
            )

            logger.info(f"Added team member {member_name} to {user_id}'s knowledge")
            return team

    async def find_team_member(
        self,
        user_id: str,
        search: str
    ) -> Optional[Dict[str, Any]]:
        """Find a team member by name (fuzzy match)."""
        team = await self.get_team_knowledge(user_id)
        search_lower = search.lower()

        # Exact match
        if search_lower in team:
            return team[search_lower]

        # Partial match
        for name, info in team.items():
            if search_lower in name or name in search_lower:
                return info
            if info.get("name", "").lower() in search_lower:
                return info

        return None

    # ==================== CUSTOM TRIGGERS ====================

    async def get_triggers(self, user_id: str) -> Dict[str, Any]:
        """Get custom triggers for a user."""
        memory = await self.get_or_create(user_id)
        return memory.custom_triggers or {}

    async def add_trigger(
        self,
        user_id: str,
        trigger_pattern: str,
        action: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Add a custom trigger."""
        async with self.db.session() as session:
            memory = await self.get_or_create(user_id)

            triggers = memory.custom_triggers or {}
            triggers[trigger_pattern.lower()] = {
                "pattern": trigger_pattern,
                "action": action,
                "created_at": datetime.now().isoformat(),
            }

            await session.execute(
                update(AIMemoryDB)
                .where(AIMemoryDB.user_id == user_id)
                .values(custom_triggers=triggers, updated_at=datetime.now())
            )

            logger.info(f"Added trigger '{trigger_pattern}' for user {user_id}")
            return triggers

    async def match_trigger(
        self,
        user_id: str,
        text: str
    ) -> Optional[Dict[str, Any]]:
        """Check if text matches any triggers."""
        triggers = await self.get_triggers(user_id)
        text_lower = text.lower()

        for pattern, trigger_info in triggers.items():
            if pattern in text_lower:
                return trigger_info.get("action")

        return None

    # ==================== LEARNED PATTERNS ====================

    async def get_patterns(self, user_id: str) -> Dict[str, Any]:
        """Get learned patterns for a user."""
        memory = await self.get_or_create(user_id)
        return memory.learned_patterns or {}

    async def record_pattern(
        self,
        user_id: str,
        pattern_type: str,
        pattern_data: Dict[str, Any]
    ):
        """Record a learned pattern."""
        async with self.db.session() as session:
            memory = await self.get_or_create(user_id)

            patterns = memory.learned_patterns or {}
            if pattern_type not in patterns:
                patterns[pattern_type] = []

            patterns[pattern_type].append({
                **pattern_data,
                "recorded_at": datetime.now().isoformat(),
            })

            # Keep only last 100 patterns per type
            patterns[pattern_type] = patterns[pattern_type][-100:]

            await session.execute(
                update(AIMemoryDB)
                .where(AIMemoryDB.user_id == user_id)
                .values(learned_patterns=patterns, updated_at=datetime.now())
            )

    async def get_common_default(
        self,
        user_id: str,
        field: str
    ) -> Optional[str]:
        """Get the most common value for a field based on patterns."""
        patterns = await self.get_patterns(user_id)

        field_patterns = patterns.get(f"{field}_choices", [])
        if not field_patterns:
            return None

        # Count occurrences
        counts = {}
        for p in field_patterns[-20:]:  # Last 20 choices
            value = p.get("value")
            if value:
                counts[value] = counts.get(value, 0) + 1

        if not counts:
            return None

        # Return most common
        return max(counts, key=counts.get)

    # ==================== RECENT CONTEXT ====================

    async def get_context(self, user_id: str) -> Dict[str, Any]:
        """Get recent context for a user."""
        memory = await self.get_or_create(user_id)
        return memory.recent_context or {}

    async def update_context(
        self,
        user_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update recent context."""
        async with self.db.session() as session:
            memory = await self.get_or_create(user_id)

            current_context = memory.recent_context or {}
            current_context.update(context)
            current_context["last_updated"] = datetime.now().isoformat()

            await session.execute(
                update(AIMemoryDB)
                .where(AIMemoryDB.user_id == user_id)
                .values(recent_context=current_context, updated_at=datetime.now())
            )

            return current_context

    async def clear_context(self, user_id: str):
        """Clear recent context."""
        async with self.db.session() as session:
            await session.execute(
                update(AIMemoryDB)
                .where(AIMemoryDB.user_id == user_id)
                .values(recent_context={}, updated_at=datetime.now())
            )

    # ==================== STATS ====================

    async def increment_stats(
        self,
        user_id: str,
        tasks_created: int = 0,
        conversations: int = 0
    ):
        """Increment user stats."""
        async with self.db.session() as session:
            result = await session.execute(
                select(AIMemoryDB).where(AIMemoryDB.user_id == user_id)
            )
            memory = result.scalar_one_or_none()

            if memory:
                await session.execute(
                    update(AIMemoryDB)
                    .where(AIMemoryDB.user_id == user_id)
                    .values(
                        total_tasks_created=AIMemoryDB.total_tasks_created + tasks_created,
                        total_conversations=AIMemoryDB.total_conversations + conversations,
                        updated_at=datetime.now(),
                    )
                )

    async def get_full_context_for_ai(self, user_id: str) -> Dict[str, Any]:
        """Get all context needed for AI prompt."""
        memory = await self.get_or_create(user_id)

        return {
            "preferences": memory.preferences or {},
            "team_knowledge": memory.team_knowledge or {},
            "custom_triggers": memory.custom_triggers or {},
            "recent_context": memory.recent_context or {},
            "stats": {
                "total_tasks": memory.total_tasks_created,
                "total_conversations": memory.total_conversations,
            },
        }


# Singleton
_ai_memory_repository: Optional[AIMemoryRepository] = None


def get_ai_memory_repository() -> AIMemoryRepository:
    """Get the AI memory repository singleton."""
    global _ai_memory_repository
    if _ai_memory_repository is None:
        _ai_memory_repository = AIMemoryRepository()
    return _ai_memory_repository
