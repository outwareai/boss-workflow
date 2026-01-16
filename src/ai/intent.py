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

    # Task updates
    DELAY_TASK = "delay_task"                # "delay the landing page to tomorrow"
    ADD_NOTE = "add_note"                    # "note on TASK-001: talked to client"
    CANCEL_TASK = "cancel_task"              # "cancel that task"

    # Team management
    ADD_TEAM_MEMBER = "add_team"             # "john is our backend dev"

    # Learning/preferences
    TEACH_PREFERENCE = "teach"               # "when I say urgent, deadline is today"

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

        # === GENERAL MATCHING ===

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

        # Email recap
        if any(w in message for w in ["email", "emails", "inbox", "mail", "gmail"]):
            if any(w in message for w in ["recap", "summary", "summarize", "check", "show", "what", "any", "unread"]):
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

        # If message mentions a person and an action, likely a task
        action_words = ["needs to", "should", "must", "has to", "can you", "please",
                       "fix", "build", "create", "make", "update", "add", "remove", "check"]
        if any(word in message for word in action_words):
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
- create_task: User wants to create/assign a task
- task_done: User is saying they finished a task
- submit_proof: User is providing proof of work
- approve_task: Boss is approving submitted work
- reject_task: Boss is rejecting with feedback
- check_status: User wants status overview
- delay_task: User wants to delay/postpone a task
- add_team: User is telling about a team member
- teach: User wants bot to learn something
- greeting: Just saying hello
- help: Asking for help
- cancel: Wants to cancel current action
- unknown: Can't determine intent

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
