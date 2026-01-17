"""
Intent detection for natural language processing.

Interprets what the user wants from their message without commands.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


class UserIntent(str, Enum):
    """Possible user intents detected from messages."""

    # Task creation
    CREATE_TASK = "create_task"              # "john needs to fix the login bug"

    # Task completion/submission
    TASK_DONE = "task_done"                  # "I finished the landing page"
    SUBMIT_PROOF = "submit_proof"            # [sends screenshot or link]
    DONE_ADDING_PROOF = "done_adding_proof"  # "that's all", "done"
    ADD_NOTES = "add_notes"                  # "tested on chrome and safari"
    CONFIRM_SUBMISSION = "confirm_submit"    # "yes", "send it"

    # Validation responses (boss)
    APPROVE_TASK = "approve_task"            # "looks good", "approved", "yes"
    REJECT_TASK = "reject_task"              # "no - fix the footer", "needs work"

    # Status/info requests
    CHECK_STATUS = "check_status"            # "what's pending?", "status"
    LIST_TASKS = "list_tasks"                # "what tasks are there?"
    CHECK_OVERDUE = "check_overdue"          # "anything overdue?"
    EMAIL_RECAP = "email_recap"              # "recap my emails", "summarize my inbox"

    # Search and bulk operations
    SEARCH_TASKS = "search_tasks"            # "what's John working on?", "find bug tasks"
    BULK_COMPLETE = "bulk_complete"          # "mark these 3 as done"
    BULK_UPDATE = "bulk_update"              # "block TASK-001 TASK-002"

    # Task updates
    DELAY_TASK = "delay_task"                # "delay the landing page to tomorrow"
    ADD_NOTE = "add_note"                    # "note on TASK-001: talked to client"
    CANCEL_TASK = "cancel_task"              # "cancel that task"
    CLEAR_TASKS = "clear_tasks"              # "clear all tasks", "delete all tasks"
    ARCHIVE_TASKS = "archive_tasks"          # "archive completed tasks"

    # Team management
    ADD_TEAM_MEMBER = "add_team"             # "john is our backend dev"

    # Learning/preferences
    TEACH_PREFERENCE = "teach"               # "when I say urgent, deadline is today"

    # Templates
    LIST_TEMPLATES = "list_templates"        # "/templates", "what templates are there?"

    # Spec generation
    GENERATE_SPEC = "generate_spec"          # "/spec TASK-001", "generate spec for task"

    # Conversation control
    SKIP = "skip"                            # "skip", "whatever", "default"
    CANCEL = "cancel"                        # "cancel", "nevermind", "stop"
    HELP = "help"                            # "help", "what can you do?"
    GREETING = "greeting"                    # "hi", "hello"

    # Unknown - needs clarification
    UNKNOWN = "unknown"


class IntentDetector:
    """
    Detects user intent from natural language messages.

    Uses a combination of:
    1. Quick pattern matching for obvious intents
    2. AI inference for ambiguous messages
    """

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )
        self.model = settings.deepseek_model

    async def detect_intent(
        self,
        message: str,
        context: Dict[str, Any] = None
    ) -> Tuple[UserIntent, Dict[str, Any]]:
        """
        Detect the user's intent from their message.

        Args:
            message: The user's message
            context: Current conversation context (stage, pending items, etc.)

        Returns:
            Tuple of (intent, extracted_data)
        """
        message_lower = message.lower().strip()
        context = context or {}

        # Quick pattern matching first (fast path)
        intent, data = self._quick_match(message_lower, context)
        if intent != UserIntent.UNKNOWN:
            return intent, data

        # Use AI for complex intent detection
        return await self._ai_detect(message, context)

    def _quick_match(
        self,
        message: str,
        context: Dict[str, Any]
    ) -> Tuple[UserIntent, Dict[str, Any]]:
        """Fast pattern matching for obvious intents."""

        current_stage = context.get("stage", "")
        is_boss = context.get("is_boss", False)
        awaiting_validation = context.get("awaiting_validation", False)
        collecting_proof = context.get("collecting_proof", False)
        awaiting_notes = context.get("awaiting_notes", False)
        awaiting_confirm = context.get("awaiting_confirm", False)

        # === SLASH COMMAND HANDLING ===
        if message.startswith("/"):
            cmd_parts = message[1:].split(None, 1)  # Remove / and split
            cmd = cmd_parts[0].lower() if cmd_parts else ""
            args = cmd_parts[1] if len(cmd_parts) > 1 else ""

            # Map slash commands to intents
            slash_commands = {
                "help": (UserIntent.HELP, {}),
                "start": (UserIntent.GREETING, {}),
                "status": (UserIntent.CHECK_STATUS, {}),
                "daily": (UserIntent.CHECK_STATUS, {"filter": "today"}),
                "weekly": (UserIntent.CHECK_STATUS, {"filter": "week"}),
                "overdue": (UserIntent.CHECK_OVERDUE, {}),
                "pending": (UserIntent.CHECK_STATUS, {"filter": "pending"}),
                "cancel": (UserIntent.CANCEL, {}),
                "skip": (UserIntent.SKIP, {}),
                "done": (UserIntent.SKIP, {}),  # Finalize with current info
                "templates": (UserIntent.LIST_TEMPLATES, {}),
                "team": (UserIntent.CHECK_STATUS, {"filter": "team"}),
            }

            if cmd in slash_commands:
                return slash_commands[cmd]

            # Commands with arguments
            if cmd == "task" and args:
                return UserIntent.CREATE_TASK, {"message": args}
            if cmd == "urgent" and args:
                return UserIntent.CREATE_TASK, {"message": args, "priority": "urgent"}
            if cmd == "search" and args:
                return UserIntent.SEARCH_TASKS, {"query": args}
            if cmd in ["complete", "finish"] and args:
                task_ids = [t.strip() for t in args.replace(",", " ").split()]
                return UserIntent.BULK_COMPLETE, {"task_ids": task_ids}
            if cmd == "clear" and args:
                task_ids = [t.strip() for t in args.replace(",", " ").split()]
                return UserIntent.CLEAR_TASKS, {"task_ids": task_ids}
            if cmd == "archive":
                return UserIntent.ARCHIVE_TASKS, {}
            if cmd == "spec" and args:
                # Extract task ID from args
                task_id = args.strip().upper()
                return UserIntent.GENERATE_SPEC, {"task_id": task_id}

            # If command not recognized, let it fall through to AI detection

        # === CONTEXT-AWARE MATCHING ===

        # Boss responding to validation
        if is_boss and awaiting_validation:
            if any(w in message for w in ["yes", "approved", "looks good", "lgtm", "great", "perfect", "nice", "good job", "well done", "ship it", "✅", "👍"]):
                return UserIntent.APPROVE_TASK, {"approval_message": message}
            if any(w in message for w in ["no", "reject", "needs", "fix", "change", "wrong", "issue", "problem", "❌", "👎"]):
                return UserIntent.REJECT_TASK, {"feedback": message}

        # Collecting proof stage
        if collecting_proof:
            if any(w in message for w in ["done", "that's all", "thats all", "that is all", "finish", "send it", "submit", "no more"]):
                return UserIntent.DONE_ADDING_PROOF, {}
            if message.startswith("http"):
                return UserIntent.SUBMIT_PROOF, {"proof_type": "link", "content": message}
            # Assume any text during proof collection is a note/proof
            return UserIntent.SUBMIT_PROOF, {"proof_type": "note", "content": message}

        # Awaiting notes
        if awaiting_notes:
            if any(w in message for w in ["skip", "no", "none", "nope", "nothing"]):
                return UserIntent.ADD_NOTES, {"notes": None}
            return UserIntent.ADD_NOTES, {"notes": message}

        # Awaiting confirmation
        if awaiting_confirm:
            if any(w in message for w in ["yes", "y", "confirm", "ok", "send", "submit", "do it", "go", "yep", "yeah"]):
                return UserIntent.CONFIRM_SUBMISSION, {}
            if any(w in message for w in ["no", "cancel", "stop", "wait", "hold"]):
                return UserIntent.CANCEL, {}

        # === BOSS ON TELEGRAM = TASK CREATION ===
        # Boss on Telegram is ALWAYS creating/managing tasks, never submitting proof

        if is_boss:
            # Detect formatted task specs (from copy-pasted previews or manual entry)
            if "title:" in message and any(field in message for field in ["assignee:", "priority:", "deadline:", "description:"]):
                return UserIntent.CREATE_TASK, {"message": message, "is_formatted_spec": True}

            # "Submit new task" or "create new task" = task creation for boss
            if any(phrase in message for phrase in ["submit new task", "create new task", "new task:", "add new task", "submit task"]):
                return UserIntent.CREATE_TASK, {"message": message}

            # Boss saying "submit" with task details = creating a task, NOT proof
            if "submit" in message and any(w in message for w in ["task", "title", "assignee", "mayank", "sarah", "john"]):
                return UserIntent.CREATE_TASK, {"message": message}

        # Greetings
        if message in ["hi", "hello", "hey", "yo", "sup", "morning", "evening"]:
            return UserIntent.GREETING, {}

        # Help
        if message in ["help", "?", "what can you do", "commands", "how does this work"]:
            return UserIntent.HELP, {}

        # Cancel/skip
        if message in ["cancel", "nevermind", "never mind", "stop", "abort", "forget it"]:
            return UserIntent.CANCEL, {}
        if message in ["skip", "whatever", "default", "idk", "don't care", "dont care"]:
            return UserIntent.SKIP, {}

        # Task completion signals
        done_phrases = ["i finished", "i'm done", "im done", "completed", "done with",
                       "finished the", "i did", "task done", "all done", "wrapped up"]
        if any(phrase in message for phrase in done_phrases):
            return UserIntent.TASK_DONE, {"message": message}

        # Status checks
        if any(w in message for w in ["status", "what's pending", "whats pending", "pending tasks", "overview"]):
            return UserIntent.CHECK_STATUS, {}
        if any(w in message for w in ["overdue", "late", "past due", "missed deadline"]):
            return UserIntent.CHECK_OVERDUE, {}

        # Search - natural language patterns
        search_patterns = [
            "what's", "whats", "what is", "show me", "find", "search",
            "working on", "assigned to", "tasks for", "list tasks"
        ]
        if any(pattern in message for pattern in search_patterns):
            # Check if asking about a person
            if "@" in message or any(w in message for w in ["working on", "assigned to", "tasks for"]):
                return UserIntent.SEARCH_TASKS, {"query": message}

        # Templates
        if any(w in message for w in ["templates", "what templates", "show templates", "list templates"]):
            return UserIntent.LIST_TEMPLATES, {}

        # Spec generation - natural language
        spec_phrases = ["generate spec", "create spec", "spec sheet", "make spec", "spec for"]
        if any(phrase in message for phrase in spec_phrases):
            # Try to extract task ID
            import re
            task_id_match = re.search(r'TASK-[\w\-]+', message, re.IGNORECASE)
            task_id = task_id_match.group(0).upper() if task_id_match else None
            return UserIntent.GENERATE_SPEC, {"task_id": task_id, "message": message}

        # Bulk operations - natural language
        bulk_complete_phrases = [
            "mark these", "mark all", "complete these", "finish these",
            "mark as done", "these are done", "all done", "mark done"
        ]
        if any(phrase in message for phrase in bulk_complete_phrases):
            # Extract task IDs if present
            import re
            task_ids = re.findall(r'TASK-[\w\-]+', message, re.IGNORECASE)
            return UserIntent.BULK_COMPLETE, {"task_ids": task_ids, "message": message}

        # Email recap - prioritize this for email-related personal requests
        if any(w in message for w in ["email", "emails", "inbox", "mail", "gmail"]):
            # Any request to see/get/check emails is a recap, not a task
            if any(w in message for w in ["recap", "summary", "summarize", "check", "show", "what",
                                           "any", "unread", "fetch", "get", "read", "see", "my",
                                           "last", "recent", "latest", "new", "today"]):
                return UserIntent.EMAIL_RECAP, {}

        # Delay
        if any(w in message for w in ["delay", "postpone", "push back", "move to", "reschedule"]):
            return UserIntent.DELAY_TASK, {"message": message}

        # Team
        if " is our " in message or " is the " in message or " handles " in message:
            return UserIntent.ADD_TEAM_MEMBER, {"message": message}

        # Teaching/preferences
        if message.startswith("when i say") or message.startswith("when i mention") or "always ask" in message or "default" in message:
            return UserIntent.TEACH_PREFERENCE, {"message": message}

        # Clear/delete/archive tasks - BEFORE general task creation matching
        # Check for specific task IDs first
        import re
        task_ids = re.findall(r'TASK-[\w\-]+', message, re.IGNORECASE)

        clear_keywords = ["clear", "delete", "remove", "wipe", "reset"]

        # Check if message starts with or prominently features clear intent
        clear_first = message.split()[0] if message.split() else ""
        is_clear_intent = clear_first in clear_keywords

        if task_ids and any(kw in message for kw in clear_keywords):
            # Clearing specific tasks
            return UserIntent.CLEAR_TASKS, {"task_ids": task_ids, "message": message}

        # Clear all tasks - more comprehensive detection
        clear_patterns = [
            # Exact phrases
            "clear all", "clear the", "clear tasks", "clear existing", "clear every",
            "delete all", "delete the tasks", "delete tasks", "delete existing", "delete every",
            "remove all tasks", "remove all the tasks", "remove existing", "remove every",
            "wipe all", "wipe tasks", "wipe everything",
            "reset tasks", "reset all",
            # Natural patterns
            "get rid of all", "get rid of the tasks", "clean up tasks", "clean tasks",
            "start fresh", "fresh start", "empty the tasks", "empty tasks"
        ]
        if any(phrase in message for phrase in clear_patterns):
            return UserIntent.CLEAR_TASKS, {"task_ids": [], "message": message}

        # Also catch "clear" at start of message followed by task-related words
        if is_clear_intent and any(w in message for w in ["task", "all", "everything", "existing"]):
            return UserIntent.CLEAR_TASKS, {"task_ids": [], "message": message}

        archive_phrases = ["archive completed", "archive done", "archive old", "archive tasks"]
        if any(phrase in message for phrase in archive_phrases):
            return UserIntent.ARCHIVE_TASKS, {"message": message}

        # If message mentions a person and an action, likely a task
        action_words = ["needs to", "should", "must", "has to", "can you",
                       "fix", "build", "create", "make", "update", "add", "check"]
        if any(word in message for word in action_words):
            # But not if it's about clearing/deleting
            if not any(w in message for w in ["clear", "delete", "remove", "wipe", "reset"]):
                return UserIntent.CREATE_TASK, {"message": message}

        return UserIntent.UNKNOWN, {}

    async def _ai_detect(
        self,
        message: str,
        context: Dict[str, Any]
    ) -> Tuple[UserIntent, Dict[str, Any]]:
        """Use AI for complex intent detection."""

        prompt = f"""Analyze this message and determine the user's intent.

MESSAGE: "{message}"

CONTEXT:
- Current stage: {context.get('stage', 'none')}
- Is boss: {context.get('is_boss', False)}
- Awaiting validation response: {context.get('awaiting_validation', False)}
- Collecting proof: {context.get('collecting_proof', False)}

POSSIBLE INTENTS:
- create_task: User wants to create/assign a task TO SOMEONE ELSE
- task_done: User is saying they finished a task
- submit_proof: User is providing proof of work
- approve_task: Boss is approving submitted work
- reject_task: Boss is rejecting with feedback
- check_status: User wants status overview
- email_recap: User wants to see/read/check their OWN emails (not delegate)
- delay_task: User wants to delay/postpone a task
- add_team: User is telling about a team member
- teach: User wants bot to learn something
- greeting: Just saying hello
- help: Asking for help
- cancel: Wants to cancel current action
- unknown: Can't determine intent

IMPORTANT: If user asks about their OWN emails (fetch, recap, check, see emails), use email_recap NOT create_task.
Only use create_task when user wants to DELEGATE something to another person.

Respond with JSON:
{{
    "intent": "the_intent",
    "confidence": 0.9,
    "extracted_data": {{
        "task_description": "if creating task",
        "person_mentioned": "name if any",
        "feedback": "if rejecting",
        "other_relevant_data": "..."
    }}
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You detect user intent from messages. Respond only with JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )

            import json
            result = json.loads(response.choices[0].message.content)

            intent_str = result.get("intent", "unknown")
            try:
                intent = UserIntent(intent_str)
            except ValueError:
                intent = UserIntent.UNKNOWN

            return intent, result.get("extracted_data", {})

        except Exception as e:
            logger.error(f"AI intent detection failed: {e}")
            return UserIntent.UNKNOWN, {}

    def is_photo_proof(self, has_photo: bool, context: Dict[str, Any]) -> bool:
        """Check if a photo should be treated as proof."""
        return has_photo and context.get("collecting_proof", False)

    def is_link(self, message: str) -> bool:
        """Check if message is a URL."""
        return message.startswith("http://") or message.startswith("https://")


# Singleton
intent_detector = IntentDetector()

def get_intent_detector() -> IntentDetector:
    return intent_detector
