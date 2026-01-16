"""
Learning system for the bot to improve over time.

Handles the /teach command and tracks patterns in user behavior.
"""

import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from .preferences import PreferencesManager, get_preferences_manager, Trigger

logger = logging.getLogger(__name__)


class LearningManager:
    """
    Manages the bot's learning capabilities.

    Handles:
    - /teach command parsing
    - Pattern recognition in user behavior
    - Automatic preference suggestions
    """

    def __init__(self, preferences_manager: Optional[PreferencesManager] = None):
        self.prefs_manager = preferences_manager or get_preferences_manager()

        # Teaching patterns and their parsers
        self.teaching_patterns = [
            (r"when (?:i|I) (?:say|mention|write) ['\"]?(.+?)['\"]?,?\s*(?:set |make |)?(.+)", self._parse_trigger_teaching),
            (r"(.+?) is (?:our|the|a) (.+)", self._parse_team_teaching),
            (r"always ask (?:me )?about (.+)", self._parse_always_ask),
            (r"(?:don't|never|stop) ask(?:ing)? (?:me )?about (.+)", self._parse_skip_question),
            (r"my (?:default )?(.+) (?:is|should be) (.+)", self._parse_default),
            (r"my timezone is (.+)", self._parse_timezone),
        ]

    async def process_teach_command(
        self,
        user_id: str,
        teaching_text: str
    ) -> Tuple[bool, str]:
        """
        Process a /teach command from the user.

        Returns:
            Tuple of (success, response_message)
        """
        teaching_text = teaching_text.strip()

        if not teaching_text:
            return False, self._get_teach_help()

        # Try each pattern
        for pattern, handler in self.teaching_patterns:
            match = re.match(pattern, teaching_text, re.IGNORECASE)
            if match:
                return await handler(user_id, match)

        # If no pattern matched, try to infer intent
        return await self._infer_teaching_intent(user_id, teaching_text)

    def _get_teach_help(self) -> str:
        """Get help text for the /teach command."""
        return """What would you like me to learn? Examples:

**Triggers:**
• "When I say ASAP, set deadline to 4 hours"
• "When I mention 'client X', set priority to high"

**Team Knowledge:**
• "John is our backend expert"
• "Sarah is the frontend developer"

**Question Preferences:**
• "Always ask about deadline"
• "Don't ask about priority"

**Defaults:**
• "My default priority is medium"
• "My timezone is EST"

Just type what you want me to learn!"""

    async def _parse_trigger_teaching(
        self,
        user_id: str,
        match: re.Match
    ) -> Tuple[bool, str]:
        """Parse trigger-style teaching (when I say X, do Y)."""
        trigger_phrase = match.group(1).strip()
        action_text = match.group(2).strip().lower()

        # Parse the action
        action, value = self._parse_action(action_text)

        if not action:
            return False, f"I couldn't understand what to do when you say '{trigger_phrase}'. Can you rephrase?"

        # Save the trigger
        success = await self.prefs_manager.add_trigger(
            user_id=user_id,
            pattern=trigger_phrase,
            action=action,
            value=value
        )

        if success:
            return True, f"""Got it! I'll remember:
**Trigger:** '{trigger_phrase}'
**Action:** {action.replace('_', ' ')} to {value}

Saved ✅"""
        else:
            return False, "There was an error saving this. Please try again."

    def _parse_action(self, action_text: str) -> Tuple[Optional[str], Any]:
        """Parse an action from text."""
        # Priority patterns
        priority_match = re.search(r"priority (?:to |is |= )?(\w+)", action_text)
        if priority_match:
            priority = priority_match.group(1).lower()
            if priority in ["low", "medium", "high", "urgent"]:
                return "set_priority", priority

        # Deadline patterns
        deadline_match = re.search(r"deadline (?:to |is |= )?(.+)", action_text)
        if deadline_match:
            return "set_deadline", deadline_match.group(1).strip()

        # Assignee patterns
        assignee_match = re.search(r"assign(?:ee)? (?:to |is |= )?(\w+)", action_text)
        if assignee_match:
            return "set_assignee", assignee_match.group(1).strip()

        # Flag as urgent
        if "urgent" in action_text and "priority" not in action_text:
            return "set_priority", "urgent"

        return None, None

    async def _parse_team_teaching(
        self,
        user_id: str,
        match: re.Match
    ) -> Tuple[bool, str]:
        """Parse team member teaching (X is our Y)."""
        name = match.group(1).strip()
        role = match.group(2).strip()

        # Extract username if provided
        username_match = re.search(r"@(\w+)", name)
        username = username_match.group(1) if username_match else name.lower().replace(" ", "")
        clean_name = re.sub(r"@\w+", "", name).strip()

        success = await self.prefs_manager.add_team_member(
            user_id=user_id,
            name=clean_name or name,
            username=username,
            role=role
        )

        if success:
            return True, f"""Got it! I'll remember:
**{clean_name or name}** ({username}) - {role}

Saved ✅"""
        else:
            return False, "There was an error saving this. Please try again."

    async def _parse_always_ask(
        self,
        user_id: str,
        match: re.Match
    ) -> Tuple[bool, str]:
        """Parse 'always ask about X' teaching."""
        fields_text = match.group(1).strip()
        fields = [f.strip().lower() for f in re.split(r"[,&]| and ", fields_text)]

        # Map common terms to field names
        field_map = {
            "deadline": "deadline",
            "due date": "deadline",
            "priority": "priority",
            "urgency": "priority",
            "assignee": "assignee",
            "who": "assignee",
            "description": "description",
            "scope": "description",
            "criteria": "acceptance_criteria",
            "acceptance criteria": "acceptance_criteria",
        }

        mapped_fields = []
        for f in fields:
            if f in field_map:
                mapped_fields.append(field_map[f])
            elif f in field_map.values():
                mapped_fields.append(f)

        if not mapped_fields:
            return False, f"I don't recognize these fields: {fields_text}. Try: deadline, priority, assignee, description"

        prefs = await self.prefs_manager.get_preferences(user_id)
        prefs.always_ask = list(set(prefs.always_ask + mapped_fields))
        success = await self.prefs_manager.save_preferences(prefs)

        if success:
            return True, f"Got it! I'll always ask about: {', '.join(mapped_fields)} ✅"
        else:
            return False, "There was an error saving this. Please try again."

    async def _parse_skip_question(
        self,
        user_id: str,
        match: re.Match
    ) -> Tuple[bool, str]:
        """Parse 'don't ask about X' teaching."""
        fields_text = match.group(1).strip()
        fields = [f.strip().lower() for f in re.split(r"[,&]| and ", fields_text)]

        field_map = {
            "deadline": "deadline",
            "due date": "deadline",
            "priority": "priority",
            "urgency": "priority",
            "assignee": "assignee",
            "who": "assignee",
        }

        mapped_fields = []
        for f in fields:
            if f in field_map:
                mapped_fields.append(field_map[f])
            elif f in field_map.values():
                mapped_fields.append(f)

        if not mapped_fields:
            return False, f"I don't recognize these fields: {fields_text}. Try: deadline, priority, assignee"

        prefs = await self.prefs_manager.get_preferences(user_id)
        prefs.skip_questions_for = list(set(prefs.skip_questions_for + mapped_fields))
        success = await self.prefs_manager.save_preferences(prefs)

        if success:
            return True, f"Got it! I won't ask about: {', '.join(mapped_fields)} ✅"
        else:
            return False, "There was an error saving this. Please try again."

    async def _parse_default(
        self,
        user_id: str,
        match: re.Match
    ) -> Tuple[bool, str]:
        """Parse default value teaching."""
        field = match.group(1).strip().lower()
        value = match.group(2).strip().lower()

        field_map = {
            "priority": "priority",
            "deadline": "deadline_behavior",
        }

        if field not in field_map:
            return False, f"I can set defaults for: priority, deadline"

        actual_field = field_map[field]
        success = await self.prefs_manager.update_preference(
            user_id=user_id,
            key=f"defaults.{actual_field}",
            value=value
        )

        if success:
            return True, f"Got it! Your default {field} is now: {value} ✅"
        else:
            return False, "There was an error saving this. Please try again."

    async def _parse_timezone(
        self,
        user_id: str,
        match: re.Match
    ) -> Tuple[bool, str]:
        """Parse timezone teaching."""
        tz = match.group(1).strip()

        # Common timezone mappings
        tz_map = {
            "est": "America/New_York",
            "eastern": "America/New_York",
            "cst": "America/Chicago",
            "central": "America/Chicago",
            "mst": "America/Denver",
            "mountain": "America/Denver",
            "pst": "America/Los_Angeles",
            "pacific": "America/Los_Angeles",
            "utc": "UTC",
            "gmt": "UTC",
        }

        actual_tz = tz_map.get(tz.lower(), tz)

        success = await self.prefs_manager.update_preference(
            user_id=user_id,
            key="timezone",
            value=actual_tz
        )

        if success:
            return True, f"Got it! Your timezone is now: {actual_tz} ✅"
        else:
            return False, "There was an error saving this. Please try again."

    async def _infer_teaching_intent(
        self,
        user_id: str,
        text: str
    ) -> Tuple[bool, str]:
        """Try to infer what the user wants to teach."""
        text_lower = text.lower()

        # Check for common patterns
        if "priority" in text_lower and any(p in text_lower for p in ["low", "medium", "high", "urgent"]):
            # Probably a default priority
            for p in ["low", "medium", "high", "urgent"]:
                if p in text_lower:
                    return await self._parse_default(
                        user_id,
                        re.match(r"(priority).*(low|medium|high|urgent)", text_lower)
                    )

        # Couldn't infer
        return False, """I'm not sure what you want me to learn. Try being more specific:

• "When I say X, set priority to high"
• "John is our backend developer"
• "Always ask about deadlines"
• "My default priority is medium"

What would you like me to learn?"""

    async def get_preferences_summary(self, user_id: str) -> str:
        """Get a formatted summary of user preferences."""
        prefs = await self.prefs_manager.get_preferences(user_id)

        lines = ["📋 **Your Preferences**", ""]

        # Defaults
        lines.append("**Defaults:**")
        for key, value in prefs.defaults.items():
            lines.append(f"  • {key.replace('_', ' ').title()}: {value}")
        lines.append("")

        # Question preferences
        if prefs.always_ask:
            lines.append(f"**Always ask about:** {', '.join(prefs.always_ask)}")
        if prefs.skip_questions_for:
            lines.append(f"**Skip questions for:** {', '.join(prefs.skip_questions_for)}")
        lines.append("")

        # Team members
        if prefs.team_members:
            lines.append("**Team Members:**")
            for name, member in prefs.team_members.items():
                lines.append(f"  • {member.name} (@{member.username}): {member.role}")
            lines.append("")

        # Triggers
        if prefs.triggers:
            lines.append("**Custom Triggers:**")
            for trigger in prefs.triggers:
                lines.append(f"  • '{trigger.pattern}' → {trigger.action}: {trigger.value}")
            lines.append("")

        lines.append(f"**Timezone:** {prefs.timezone}")

        return "\n".join(lines)


# Singleton instance
learning_manager = LearningManager()


def get_learning_manager() -> LearningManager:
    """Get the learning manager instance."""
    return learning_manager
