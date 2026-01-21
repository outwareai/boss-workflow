"""
Task Processor - Clean architecture for parsing and creating tasks.

Architecture:
1. PARSE: Deterministically split message into individual task strings (no AI)
2. EXTRACT: AI extracts structured fields from each task string (no generation)
3. VALIDATE: Ensure extracted fields match the original input
4. CONFIRM: Show each task for confirmation with self-healing options

This replaces the previous approach where AI had too much creative freedom.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class ParsedTask:
    """A task parsed from user input."""
    original_text: str
    assignee: Optional[str] = None
    deadline_text: Optional[str] = None
    deadline_iso: Optional[str] = None
    priority: str = "medium"
    title: Optional[str] = None
    description: Optional[str] = None

    # Validation
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)


class TaskParser:
    """
    STEP 1: Deterministic parsing - NO AI involved.

    Splits a multi-task message into individual task strings and extracts
    basic information like assignee and deadline using regex patterns.
    """

    # Team members for assignee detection
    TEAM_NAMES = ["mayank", "sarah", "john", "minty", "mike", "david", "alex", "emma", "james", "zea"]

    # Ordinal patterns
    ORDINAL_WORDS = r'(?:first|second|third|fourth|forth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)'
    ORDINAL_NOUNS = r'(?:one|task|item|thing)'

    def parse_message(self, message: str) -> Tuple[List[ParsedTask], Dict[str, Any]]:
        """
        Parse a message into individual tasks.

        Returns:
            Tuple of (list of ParsedTask, metadata dict with preamble info)
        """
        message = message.strip()
        metadata = {
            "original_message": message,
            "preamble_assignee": None,
            "no_questions": False,
            "task_count": 0
        }

        # Step 1: Extract preamble info (assignee, "no questions")
        message, metadata = self._extract_preamble(message, metadata)

        # Step 2: Split into individual task strings
        task_strings = self._split_into_tasks(message)

        # Step 3: Parse each task string
        tasks = []
        for task_str in task_strings:
            parsed = self._parse_single_task(task_str, metadata.get("preamble_assignee"))
            if parsed.original_text.strip():  # Only add non-empty tasks
                tasks.append(parsed)

        metadata["task_count"] = len(tasks)
        logger.info(f"Parsed {len(tasks)} tasks from message")

        return tasks, metadata

    def _extract_preamble(self, message: str, metadata: Dict) -> Tuple[str, Dict]:
        """Extract preamble information like assignee and 'no questions'."""

        # Check for "no questions" phrase
        no_question_phrases = [
            "no questions", "no need to ask", "don't ask", "dont ask",
            "skip questions", "just create", "just do"
        ]
        for phrase in no_question_phrases:
            if phrase in message.lower():
                metadata["no_questions"] = True
                break

        # Extract "Tasks for [Name]" or "For [Name]" preamble
        # Pattern: Match "for [name]" followed by ANY text until we hit an ordinal pattern
        # Use .*? (non-greedy any char) with lookahead to stop at ordinal
        preamble_pattern = (
            r'^(?:tasks?\s+)?for\s+(' + '|'.join(self.TEAM_NAMES) + r')\b'
            r'.*?'  # Any characters (non-greedy) including "no questions pleased"
            r'(?=' + self.ORDINAL_WORDS + r'\s+' + self.ORDINAL_NOUNS + r')'
        )

        match = re.match(preamble_pattern, message, re.IGNORECASE | re.DOTALL)
        if match:
            metadata["preamble_assignee"] = match.group(1).capitalize()
            # Remove preamble from message
            message = message[match.end():].strip()
            logger.info(f"Extracted preamble assignee: {metadata['preamble_assignee']}")
        else:
            # Fallback: Try simpler pattern - just "for [name]" at start
            simple_pattern = r'^(?:tasks?\s+)?for\s+(' + '|'.join(self.TEAM_NAMES) + r')\b\s*'
            simple_match = re.match(simple_pattern, message, re.IGNORECASE)
            if simple_match:
                metadata["preamble_assignee"] = simple_match.group(1).capitalize()
                logger.info(f"Extracted preamble assignee (simple): {metadata['preamble_assignee']}")
                # Don't remove from message in simple case - let ordinal split handle it

        return message, metadata

    def _split_into_tasks(self, message: str) -> List[str]:
        """Split message into individual task strings."""

        # Pattern 1: Ordinal patterns (First one, Second task, etc.)
        ordinal_split = self.ORDINAL_WORDS + r'\s+' + self.ORDINAL_NOUNS + r'(?:\s*(?:will\s+be(?:\s+to)?|is(?:\s+to)?|:))?\s*'

        ordinal_count = len(re.findall(self.ORDINAL_WORDS + r'\s+' + self.ORDINAL_NOUNS, message, re.IGNORECASE))
        if ordinal_count >= 2:
            parts = re.split(ordinal_split, message, flags=re.IGNORECASE)
            tasks = [p.strip() for p in parts if p and p.strip() and len(p.strip()) > 5]
            if len(tasks) >= 2:
                logger.info(f"Split into {len(tasks)} tasks using ordinal pattern")
                return tasks

        # Pattern 2: Numbered list (1. 2. 3.)
        if re.search(r'\d+[\.\)]\s*\S', message):
            parts = re.split(r'\s*\d+[\.\)]\s*', message)
            tasks = [p.strip() for p in parts if p and p.strip() and len(p.strip()) > 5]
            if len(tasks) >= 2:
                logger.info(f"Split into {len(tasks)} tasks using numbered list")
                return tasks

        # Pattern 3: Action verb comma separation with "and"
        # Detects: "Finish X, engage Y, and enroll Z" - multiple distinct actions
        # Look for pattern: "verb1 stuff, verb2 stuff, and verb3 stuff"
        action_verbs = r'(?:finish|complete|add|create|fix|update|build|implement|design|review|check|test|deploy|enroll|engage|send|write|prepare|setup|configure|install|remove|delete|change|modify|upload|download|contact|call|email|message|schedule|plan|organize|clean|improve|optimize|analyze|research|find|get|make|do|start|begin|launch|publish|submit|approve|reject|assign|notify|remind|follow|track|monitor|verify|validate|confirm|cancel|close|open|enable|disable|run|stop|pause|resume|restart)'

        # Check if message has comma-separated action items ending with "and"
        # Pattern: action, action, and action OR action, action, action
        comma_and_pattern = re.compile(
            rf'({action_verbs}\s+[^,]+),\s*({action_verbs}\s+[^,]+),?\s*(?:and\s+)?({action_verbs}\s+[^,]+)',
            re.IGNORECASE
        )

        match = comma_and_pattern.search(message)
        if match:
            # Extract the three action items
            tasks = [match.group(1).strip(), match.group(2).strip(), match.group(3).strip()]
            tasks = [t for t in tasks if t and len(t) > 5]
            if len(tasks) >= 2:
                logger.info(f"Split into {len(tasks)} tasks using action verb comma pattern")
                return tasks

        # Pattern 3b: Two action items with "and"
        # "Finish X and engage Y"
        two_action_pattern = re.compile(
            rf'({action_verbs}\s+[^,]+?)\s+and\s+({action_verbs}\s+.+)',
            re.IGNORECASE
        )

        match = two_action_pattern.search(message)
        if match:
            task1 = match.group(1).strip()
            task2 = match.group(2).strip()
            # Only split if both parts are substantial (not just "and do it")
            if len(task1) > 10 and len(task2) > 10:
                logger.info(f"Split into 2 tasks using action verb 'and' pattern")
                return [task1, task2]

        # Pattern 4: "And another task is to" / "Another task is" separation
        # Handles: "Give Zea X And another task is to Y And another task is to Z"
        another_task_pattern = re.compile(
            r'\s+[Aa]nd\s+another\s+task\s+(?:is\s+(?:to\s+)?)?',
            re.IGNORECASE
        )
        if another_task_pattern.search(message):
            parts = another_task_pattern.split(message)
            tasks = [p.strip() for p in parts if p and p.strip() and len(p.strip()) > 5]
            if len(tasks) >= 2:
                logger.info(f"Split into {len(tasks)} tasks using 'another task' pattern")
                return tasks

        # No splitting needed - single task
        return [message] if message.strip() else []

    def _parse_single_task(self, task_str: str, preamble_assignee: Optional[str] = None) -> ParsedTask:
        """Parse a single task string into structured data."""

        task = ParsedTask(original_text=task_str)

        # Set assignee from preamble if available
        if preamble_assignee:
            task.assignee = preamble_assignee

        # Try to extract assignee from task text if not set
        if not task.assignee:
            for name in self.TEAM_NAMES:
                if re.search(rf'\b{name}\b', task_str, re.IGNORECASE):
                    task.assignee = name.capitalize()
                    break

        # Extract deadline from common phrases
        task.deadline_text, task.deadline_iso = self._extract_deadline(task_str)

        # Extract priority from keywords
        task.priority = self._extract_priority(task_str)

        # Clean up title (remove time references, assignee mentions for cleaner title)
        task.title = self._clean_title(task_str)
        task.description = task_str  # Keep original as description

        return task

    def _extract_deadline(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract deadline from text."""
        text_lower = text.lower()
        now = datetime.now()

        # Specific time patterns (more specific first)
        time_patterns = [
            # "tonight at 10PM", "tonight at 10 PM", "tonight at 10pm"
            (r'tonight\s+at\s+(\d{1,2})\s*(?:pm|PM|p\.m\.?)', lambda m: now.replace(hour=int(m.group(1)) + (12 if int(m.group(1)) < 12 else 0), minute=0, second=0, microsecond=0)),
            (r'tonight\s+at\s+(\d{1,2})\s*(?:am|AM|a\.m\.?)', lambda m: now.replace(hour=int(m.group(1)), minute=0, second=0, microsecond=0)),
            # "at 10PM tonight"
            (r'at\s+(\d{1,2})\s*(?:pm|PM|p\.m\.?)\s+tonight', lambda m: now.replace(hour=int(m.group(1)) + (12 if int(m.group(1)) < 12 else 0), minute=0, second=0, microsecond=0)),
            # "10PM tonight"
            (r'(\d{1,2})\s*(?:pm|PM|p\.m\.?)\s+tonight', lambda m: now.replace(hour=int(m.group(1)) + (12 if int(m.group(1)) < 12 else 0), minute=0, second=0, microsecond=0)),
            # "by 5pm", "before 6PM"
            (r'(?:by|before)\s+(\d{1,2})\s*(?:pm|PM|p\.m\.?)', lambda m: now.replace(hour=int(m.group(1)) + (12 if int(m.group(1)) < 12 else 0), minute=0, second=0, microsecond=0)),
        ]

        for pattern, converter in time_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    dt = converter(match)
                    return match.group(0), dt.isoformat()
                except Exception as e:
                    logger.warning(f"Failed to parse time pattern: {e}")
                    pass

        # Date patterns (check these after specific times)
        if "for today" in text_lower or text_lower.startswith("today"):
            return "today", now.replace(hour=23, minute=59, second=0, microsecond=0).isoformat()

        # "is tonight" without specific time
        if "tonight" in text_lower:
            return "tonight", now.replace(hour=23, minute=59, second=0, microsecond=0).isoformat()

        # "today" anywhere in text
        if "today" in text_lower:
            return "today", now.replace(hour=23, minute=59, second=0, microsecond=0).isoformat()

        # "after tomorrow" = day after tomorrow
        if "after tomorrow" in text_lower:
            day_after = now + timedelta(days=2)
            return "after tomorrow", day_after.replace(hour=23, minute=59, second=0, microsecond=0).isoformat()

        # "tomorrow"
        if "tomorrow" in text_lower:
            tomorrow = now + timedelta(days=1)
            return "tomorrow", tomorrow.replace(hour=23, minute=59, second=0, microsecond=0).isoformat()

        return None, None

    def _extract_priority(self, text: str) -> str:
        """Extract priority from text."""
        text_lower = text.lower()

        if any(kw in text_lower for kw in ["urgent", "asap", "critical", "emergency", "immediately"]):
            return "urgent"
        if any(kw in text_lower for kw in ["high priority", "important", "high"]):
            return "high"
        if any(kw in text_lower for kw in ["low priority", "when you can", "no rush", "low"]):
            return "low"

        return "medium"

    def _clean_title(self, text: str) -> str:
        """Clean up text to create a title."""
        title = text

        # Remove time references at the start
        title = re.sub(r'^(?:for\s+)?today\s+', '', title, flags=re.IGNORECASE)
        title = re.sub(r'^tonight\s+(?:at\s+\d+\s*(?:am|pm)\s+)?', '', title, flags=re.IGNORECASE)
        title = re.sub(r'^tomorrow\s+', '', title, flags=re.IGNORECASE)
        title = re.sub(r'^after\s+tomorrow\s+', '', title, flags=re.IGNORECASE)

        # Capitalize first letter
        title = title.strip()
        if title:
            title = title[0].upper() + title[1:]

        # Truncate if too long
        if len(title) > 100:
            title = title[:97] + "..."

        return title


class TaskExtractor:
    """
    STEP 2: AI-assisted field extraction.

    Uses AI to extract structured fields, but with STRICT instructions
    to only extract what's in the input, not generate new content.
    """

    def __init__(self, ai_client):
        self.ai = ai_client

    async def extract_fields(self, parsed_task: ParsedTask) -> Dict[str, Any]:
        """
        Use AI to extract/enhance fields from a parsed task.

        The AI is instructed to ONLY extract what's there, not invent.
        """
        prompt = f"""EXTRACT task information from this text. PRESERVE ALL DETAILS - do not oversimplify!

TEXT: "{parsed_task.original_text}"

ALREADY EXTRACTED (use these if correct):
- Assignee: {parsed_task.assignee or "Not found"}
- Deadline: {parsed_task.deadline_text or "Not found"} → {parsed_task.deadline_iso or "Not found"}
- Priority: {parsed_task.priority}

YOUR JOB:
1. Create a TITLE that captures the FULL task (preserve details, up to 120 chars)
2. Verify the assignee is correct
3. Verify the deadline is correct (use the ISO format provided)
4. Create acceptance criteria that capture EVERY detail mentioned

⚠️ CRITICAL RULES:
- PRESERVE ALL DETAILS from the original text
- If user says "test payment recurring, retrial, what data is passed" → ALL THREE should be in criteria
- If user mentions specific things like "Digital Ocean to Ionos" → keep those exact names
- DO NOT simplify "extensive REAL LIVE test" to just "test"
- Keep technical terms: "Stripe", "subscription", "retrial", etc.
- If deadline was extracted, USE IT (don't return null)

BAD (oversimplified):
- "run test for stripe" ❌
- "Email is fixed" ❌

GOOD (preserves detail):
- "Run extensive real live test for Stripe: payment recurring, retrial on failed subscription, verify data passed" ✓
- "Fix email functionality and deploy to production" ✓

Return JSON:
{{
    "title": "Detailed title preserving user's words (up to 120 chars)",
    "assignee": "{parsed_task.assignee or 'null'}",
    "deadline": "{parsed_task.deadline_iso or 'null'}",
    "priority": "{parsed_task.priority}",
    "task_type": "task/bug/feature/research",
    "acceptance_criteria": ["Specific criterion from user's text", "Another specific detail mentioned"],
    "estimated_effort": "Reasonable estimate"
}}"""

        try:
            response = await self.ai._call_api(
                messages=[
                    {"role": "system", "content": "You extract task fields from text. Never invent content."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for consistency
                max_tokens=500,
                response_format={"type": "json_object"}
            )

            import json
            result = json.loads(response)

            # Ensure result is a dict (AI sometimes returns unexpected types)
            if not isinstance(result, dict):
                logger.warning(f"AI extraction returned non-dict: {type(result)} - using fallback")
                return {
                    "title": parsed_task.title or parsed_task.original_text[:100],
                    "assignee": parsed_task.assignee,
                    "deadline": parsed_task.deadline_iso,
                    "priority": parsed_task.priority,
                    "task_type": "task",
                    "acceptance_criteria": [],
                    "estimated_effort": "TBD"
                }

            # Validate the result
            result = self._validate_extraction(result, parsed_task)

            return result

        except Exception as e:
            logger.error(f"AI extraction failed: {e}")
            # Return basic extraction without AI
            return {
                "title": parsed_task.title,
                "assignee": parsed_task.assignee,
                "deadline": parsed_task.deadline_iso,
                "priority": parsed_task.priority,
                "task_type": "task",
                "acceptance_criteria": [],
                "estimated_effort": "TBD"
            }

    def _validate_extraction(self, result: Dict, parsed_task: ParsedTask) -> Dict:
        """Validate that AI extraction matches the input."""

        # Check title uses words from original
        title = result.get("title", "")
        original_words = set(w.lower() for w in re.findall(r'\b\w{3,}\b', parsed_task.original_text))
        title_words = set(w.lower() for w in re.findall(r'\b\w{3,}\b', title))

        # Common words to ignore
        stop_words = {'the', 'and', 'for', 'with', 'this', 'that', 'from', 'will', 'can', 'should'}
        original_words -= stop_words
        title_words -= stop_words

        overlap = original_words & title_words
        if len(overlap) < 2 and len(original_words) > 3:
            logger.warning(f"AI title doesn't match input. Using fallback.")
            result["title"] = parsed_task.title

        # Ensure assignee wasn't changed incorrectly
        if parsed_task.assignee and result.get("assignee") != parsed_task.assignee:
            result["assignee"] = parsed_task.assignee

        # Ensure deadline wasn't changed incorrectly
        if parsed_task.deadline_iso and result.get("deadline") != parsed_task.deadline_iso:
            result["deadline"] = parsed_task.deadline_iso

        return result


class TaskProcessor:
    """
    Main processor that orchestrates the clean task creation flow.

    Flow:
    1. Parse message into individual tasks (deterministic)
    2. Extract fields for each task (AI with strict rules)
    3. Validate extractions match input
    4. Return tasks for confirmation
    """

    def __init__(self, ai_client=None):
        self.parser = TaskParser()
        self.extractor = TaskExtractor(ai_client) if ai_client else None

    async def process_message(self, message: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Process a message and return structured tasks ready for confirmation.

        Returns:
            Tuple of (list of task specs, metadata)
        """
        # Step 1: Parse (deterministic)
        parsed_tasks, metadata = self.parser.parse_message(message)

        if not parsed_tasks:
            return [], metadata

        # Step 2 & 3: Extract and validate
        task_specs = []
        for parsed in parsed_tasks:
            if self.extractor:
                spec = await self.extractor.extract_fields(parsed)
            else:
                # No AI available - use parsed data directly
                spec = {
                    "title": parsed.title,
                    "assignee": parsed.assignee,
                    "deadline": parsed.deadline_iso,
                    "priority": parsed.priority,
                    "task_type": "task",
                    "acceptance_criteria": [],
                    "estimated_effort": "TBD",
                    "description": parsed.description
                }

            # Add original text for reference
            spec["_original_text"] = parsed.original_text
            task_specs.append(spec)

        logger.info(f"Processed {len(task_specs)} tasks")
        return task_specs, metadata


# Singleton instance
_task_processor = None

def get_task_processor(ai_client=None) -> TaskProcessor:
    """Get or create the task processor instance."""
    global _task_processor
    if _task_processor is None:
        _task_processor = TaskProcessor(ai_client)
    return _task_processor
