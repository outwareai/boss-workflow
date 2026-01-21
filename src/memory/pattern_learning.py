"""
Pattern Learning Module - Learns from past interactions to improve future responses.

Tracks:
- Successful task patterns (what works well for which staff/task types)
- Common issues and their resolutions
- Boss preferences and feedback patterns
- Staff working styles and common questions

v2.0.5: Initial implementation
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from collections import defaultdict
import json

from config import settings

logger = logging.getLogger(__name__)


class PatternLearner:
    """
    Learns patterns from past interactions to provide better context.

    Stores patterns in memory and database for persistence.
    """

    def __init__(self):
        # Pattern storage
        self._staff_patterns: Dict[str, Dict[str, Any]] = {}
        self._task_type_patterns: Dict[str, Dict[str, Any]] = {}
        self._common_issues: Dict[str, List[Dict]] = {}
        self._boss_preferences: Dict[str, Any] = {}
        self._successful_resolutions: List[Dict] = []

        # Database repository (lazy loaded)
        self._repo = None
        self._db_available = None

    def _get_repo(self):
        """Lazy load the AI memory repository."""
        if self._repo is None:
            try:
                from ..database.repositories.ai_memory import get_ai_memory_repository
                self._repo = get_ai_memory_repository()
                self._db_available = True
            except Exception as e:
                logger.warning(f"Database not available for pattern learning: {e}")
                self._db_available = False
        return self._repo

    # ==================== STAFF PATTERNS ====================

    async def learn_staff_pattern(
        self,
        staff_id: str,
        staff_name: str,
        pattern_type: str,  # "working_style", "common_question", "issue_type"
        pattern_data: Dict[str, Any]
    ) -> None:
        """Learn a pattern from staff interactions."""
        if staff_id not in self._staff_patterns:
            self._staff_patterns[staff_id] = {
                "name": staff_name,
                "patterns": defaultdict(list),
                "learned_at": datetime.now().isoformat(),
            }

        self._staff_patterns[staff_id]["patterns"][pattern_type].append({
            "data": pattern_data,
            "timestamp": datetime.now().isoformat(),
        })

        # Keep only last 20 patterns per type
        if len(self._staff_patterns[staff_id]["patterns"][pattern_type]) > 20:
            self._staff_patterns[staff_id]["patterns"][pattern_type] = \
                self._staff_patterns[staff_id]["patterns"][pattern_type][-20:]

        # Persist to database
        await self._save_staff_patterns_to_db(staff_id)

        logger.debug(f"Learned {pattern_type} pattern for staff {staff_name}")

    async def get_staff_context(self, staff_id: str) -> Dict[str, Any]:
        """Get learned context for a staff member to enhance AI responses."""
        if staff_id in self._staff_patterns:
            patterns = self._staff_patterns[staff_id]["patterns"]

            # Summarize patterns
            context = {
                "working_style": self._summarize_patterns(patterns.get("working_style", [])),
                "common_questions": self._summarize_patterns(patterns.get("common_question", [])),
                "typical_issues": self._summarize_patterns(patterns.get("issue_type", [])),
            }

            return context

        # Try loading from database
        repo = self._get_repo()
        if repo and self._db_available:
            try:
                db_patterns = await repo.get_user_patterns(staff_id)
                if db_patterns:
                    return db_patterns
            except Exception as e:
                logger.error(f"Error loading staff patterns from database: {e}")

        return {}

    def _summarize_patterns(self, patterns: List[Dict]) -> str:
        """Summarize a list of patterns into a brief description."""
        if not patterns:
            return ""

        # Take last 5 patterns
        recent = patterns[-5:]
        summaries = []

        for p in recent:
            data = p.get("data", {})
            if isinstance(data, dict):
                summary = data.get("summary", data.get("description", str(data)))
            else:
                summary = str(data)
            if summary:
                summaries.append(summary[:100])

        if summaries:
            return "; ".join(summaries)
        return ""

    # ==================== TASK TYPE PATTERNS ====================

    async def learn_task_type_pattern(
        self,
        task_type: str,
        outcome: str,  # "success", "revision_needed", "escalated"
        details: Dict[str, Any]
    ) -> None:
        """Learn patterns for different task types."""
        if task_type not in self._task_type_patterns:
            self._task_type_patterns[task_type] = {
                "success_count": 0,
                "revision_count": 0,
                "escalation_count": 0,
                "common_issues": [],
                "best_practices": [],
            }

        pattern = self._task_type_patterns[task_type]

        if outcome == "success":
            pattern["success_count"] += 1
            if details.get("what_worked"):
                pattern["best_practices"].append(details["what_worked"])
        elif outcome == "revision_needed":
            pattern["revision_count"] += 1
            if details.get("issue"):
                pattern["common_issues"].append(details["issue"])
        elif outcome == "escalated":
            pattern["escalation_count"] += 1

        # Keep lists manageable
        pattern["best_practices"] = pattern["best_practices"][-10:]
        pattern["common_issues"] = pattern["common_issues"][-10:]

        logger.debug(f"Learned {outcome} pattern for task type {task_type}")

    def get_task_type_advice(self, task_type: str) -> Optional[str]:
        """Get advice based on learned patterns for a task type."""
        if task_type not in self._task_type_patterns:
            return None

        pattern = self._task_type_patterns[task_type]
        advice_lines = []

        # Add best practices
        if pattern["best_practices"]:
            practices = pattern["best_practices"][-3:]
            advice_lines.append("**What typically works:**")
            for p in practices:
                advice_lines.append(f"• {p}")

        # Add common issues to watch
        if pattern["common_issues"]:
            issues = pattern["common_issues"][-3:]
            advice_lines.append("\n**Watch out for:**")
            for issue in issues:
                advice_lines.append(f"• {issue}")

        if advice_lines:
            return "\n".join(advice_lines)
        return None

    # ==================== ISSUE RESOLUTION PATTERNS ====================

    async def learn_issue_resolution(
        self,
        issue_type: str,
        issue_description: str,
        resolution: str,
        worked: bool
    ) -> None:
        """Learn from issue resolutions."""
        if issue_type not in self._common_issues:
            self._common_issues[issue_type] = []

        self._common_issues[issue_type].append({
            "description": issue_description,
            "resolution": resolution,
            "worked": worked,
            "timestamp": datetime.now().isoformat(),
        })

        # Keep only resolutions that worked
        if worked:
            self._successful_resolutions.append({
                "issue_type": issue_type,
                "description": issue_description,
                "resolution": resolution,
                "timestamp": datetime.now().isoformat(),
            })

            # Keep last 50 successful resolutions
            self._successful_resolutions = self._successful_resolutions[-50:]

        logger.debug(f"Learned resolution for {issue_type}: worked={worked}")

    def get_similar_resolution(self, issue_description: str) -> Optional[str]:
        """Find a similar past resolution for an issue."""
        if not self._successful_resolutions:
            return None

        # Simple keyword matching
        issue_words = set(issue_description.lower().split())

        best_match = None
        best_score = 0

        for resolution in self._successful_resolutions:
            res_words = set(resolution.get("description", "").lower().split())
            overlap = len(issue_words & res_words)
            if overlap > best_score and overlap >= 2:
                best_score = overlap
                best_match = resolution

        if best_match:
            return f"**Similar issue resolved before:**\n{best_match.get('resolution', '')}"
        return None

    # ==================== BOSS PREFERENCES ====================

    async def learn_boss_preference(
        self,
        preference_type: str,  # "communication_style", "priority", "approval_pattern"
        preference_value: Any
    ) -> None:
        """Learn from boss interactions and preferences."""
        self._boss_preferences[preference_type] = {
            "value": preference_value,
            "learned_at": datetime.now().isoformat(),
        }

        # Persist to database
        await self._save_boss_preferences_to_db()

        logger.debug(f"Learned boss preference: {preference_type}={preference_value}")

    def get_boss_context(self) -> Dict[str, Any]:
        """Get context about boss preferences for AI responses."""
        context = {}
        for pref_type, pref_data in self._boss_preferences.items():
            context[pref_type] = pref_data.get("value")
        return context

    # ==================== CONVERSATION LEARNING ====================

    async def learn_from_conversation(
        self,
        task_id: str,
        staff_id: str,
        conversation_summary: str,
        outcome: str,
        key_points: List[str] = None
    ) -> None:
        """Learn from a completed conversation."""
        learning = {
            "task_id": task_id,
            "staff_id": staff_id,
            "summary": conversation_summary,
            "outcome": outcome,
            "key_points": key_points or [],
            "timestamp": datetime.now().isoformat(),
        }

        # Extract patterns
        if outcome == "success":
            await self.learn_staff_pattern(
                staff_id=staff_id,
                staff_name="",  # Will be filled in
                pattern_type="working_style",
                pattern_data={"summary": f"Successful completion: {conversation_summary[:100]}"}
            )
        elif outcome == "escalated":
            await self.learn_staff_pattern(
                staff_id=staff_id,
                staff_name="",
                pattern_type="issue_type",
                pattern_data={"summary": f"Needed escalation: {conversation_summary[:100]}"}
            )

        logger.debug(f"Learned from conversation for task {task_id}")

    # ==================== CONTEXT ENRICHMENT ====================

    async def get_enriched_context(
        self,
        staff_id: str = None,
        task_type: str = None,
        current_issue: str = None
    ) -> Dict[str, Any]:
        """
        Get enriched context for AI responses based on learned patterns.

        This is used to provide better AI assistant responses.
        """
        context = {}

        # Add staff context
        if staff_id:
            staff_context = await self.get_staff_context(staff_id)
            if staff_context:
                context["staff_patterns"] = staff_context

        # Add task type advice
        if task_type:
            advice = self.get_task_type_advice(task_type)
            if advice:
                context["task_type_advice"] = advice

        # Add similar resolution
        if current_issue:
            resolution = self.get_similar_resolution(current_issue)
            if resolution:
                context["similar_resolution"] = resolution

        # Add boss preferences
        boss_context = self.get_boss_context()
        if boss_context:
            context["boss_preferences"] = boss_context

        return context

    # ==================== DATABASE PERSISTENCE ====================

    async def _save_staff_patterns_to_db(self, staff_id: str) -> None:
        """Save staff patterns to database."""
        repo = self._get_repo()
        if not repo or not self._db_available:
            return

        try:
            patterns = self._staff_patterns.get(staff_id, {})
            await repo.save_user_memory(
                user_id=staff_id,
                memory_type="staff_patterns",
                data=patterns
            )
        except Exception as e:
            logger.error(f"Error saving staff patterns: {e}")

    async def _save_boss_preferences_to_db(self) -> None:
        """Save boss preferences to database."""
        repo = self._get_repo()
        if not repo or not self._db_available:
            return

        try:
            await repo.save_user_memory(
                user_id="boss",
                memory_type="preferences",
                data=self._boss_preferences
            )
        except Exception as e:
            logger.error(f"Error saving boss preferences: {e}")

    async def load_from_database(self) -> None:
        """Load all patterns from database on startup."""
        repo = self._get_repo()
        if not repo or not self._db_available:
            return

        try:
            # Load boss preferences
            boss_prefs = await repo.get_user_memory("boss", "preferences")
            if boss_prefs:
                self._boss_preferences = boss_prefs

            # Other patterns loaded on-demand

            logger.info("Pattern learning data loaded from database")
        except Exception as e:
            logger.error(f"Error loading pattern learning data: {e}")


# Singleton
_pattern_learner = None


def get_pattern_learner() -> PatternLearner:
    global _pattern_learner
    if _pattern_learner is None:
        _pattern_learner = PatternLearner()
    return _pattern_learner
