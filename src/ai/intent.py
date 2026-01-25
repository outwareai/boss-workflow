"""
AI-First Intent Detection System (v2.0)

The AI is the brain - it handles ALL intent detection.
No more brittle regex patterns that miss edge cases.

Architecture:
1. Slash commands → Direct mapping (unambiguous)
2. Context states → Direct mapping (awaiting confirmation, etc.)
3. Everything else → AI classifies with full context
"""

import logging
import json
import re
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

    # Batch operations (Q1 2026)
    BATCH_COMPLETE_TASKS = "batch_complete_tasks"      # "complete all tasks for John"
    BATCH_REASSIGN = "batch_reassign"                  # "reassign all from John to Sarah"
    BATCH_STATUS_CHANGE = "batch_status_change"        # "block all frontend tasks"
    BATCH_DELETE = "batch_delete"                      # "delete all cancelled tasks"
    BATCH_ADD_TAGS = "batch_add_tags"                  # "tag all John's tasks as urgent"
    BATCH_DRY_RUN = "batch_dry_run"                    # "preview changes", "dry run"

    # Task updates
    DELAY_TASK = "delay_task"                # "delay the landing page to tomorrow"
    ADD_NOTE = "add_note"                    # "note on TASK-001: talked to client"
    CANCEL_TASK = "cancel_task"              # "cancel that task"
    CLEAR_TASKS = "clear_tasks"              # "clear all tasks", "delete all tasks"
    ARCHIVE_TASKS = "archive_tasks"          # "archive completed tasks"

    # Task modification operations (v2.2)
    MODIFY_TASK = "modify_task"              # "change the title", "update description"
    REASSIGN_TASK = "reassign_task"          # "reassign to Sarah", "give TASK-001 to John"
    CHANGE_PRIORITY = "change_priority"      # "make this urgent", "lower priority"
    CHANGE_DEADLINE = "change_deadline"      # "extend deadline to tomorrow"
    CHANGE_STATUS = "change_status"          # "move to in_progress", "mark as blocked"
    ADD_TAGS = "add_tags"                    # "tag this as frontend"
    REMOVE_TAGS = "remove_tags"              # "remove urgent tag"
    ADD_SUBTASK = "add_subtask"              # "add subtask to design mockup"
    COMPLETE_SUBTASK = "complete_subtask"    # "mark subtask 1 done"
    ADD_DEPENDENCY = "add_dependency"        # "TASK-001 depends on TASK-002"
    REMOVE_DEPENDENCY = "remove_dependency"  # "remove dependency"
    DUPLICATE_TASK = "duplicate_task"        # "duplicate this task for Sarah"
    SPLIT_TASK = "split_task"                # "split this into 2 tasks"

    # Team management
    ADD_TEAM_MEMBER = "add_team"             # "john is our backend dev"

    # Boss attendance reporting
    REPORT_ABSENCE = "report_absence"        # "Mayank didn't come today", "Sarah was late"

    # Direct team communication (NOT task creation)
    ASK_TEAM_MEMBER = "ask_team_member"      # "ask Mayank what tasks are left", "tell Sarah to update me"

    # Learning/preferences
    TEACH_PREFERENCE = "teach"               # "when I say urgent, deadline is today"

    # Templates
    LIST_TEMPLATES = "list_templates"        # "/templates", "what templates are there?"
    CREATE_FROM_TEMPLATE = "create_from_template"  # "/template bug login crashes"

    # Spec generation
    GENERATE_SPEC = "generate_spec"          # "/spec TASK-001", "generate spec for task"

    # Conversation control
    SKIP = "skip"                            # "skip", "whatever", "default"
    CANCEL = "cancel"                        # "cancel", "nevermind", "stop"
    HELP = "help"                            # "help", "what can you do?"
    GREETING = "greeting"                    # "hi", "hello"

    # Unknown - needs clarification
    UNKNOWN = "unknown"


# Team names for extraction (can be extended)
TEAM_NAMES = ["mayank", "sarah", "john", "minty", "mike", "david", "alex", "emma", "james", "zea"]


class IntentDetector:
    """
    AI-First Intent Detection System.

    The AI is the brain - it classifies ALL messages (except slash commands
    and context-aware states which are unambiguous).

    Benefits:
    - Handles ANY phrasing naturally
    - Understands context and nuance
    - No more regex maintenance
    - Self-healing through examples in prompt
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

        Flow:
        1. Slash commands → Direct mapping (unambiguous)
        2. Context states → Direct mapping (awaiting confirmation, etc.)
        3. Everything else → AI classifies

        Args:
            message: The user's message
            context: Current conversation context

        Returns:
            Tuple of (intent, extracted_data)
        """
        message_lower = message.lower().strip()
        context = context or {}

        # === STEP 1: SLASH COMMANDS (unambiguous, no AI needed) ===
        if message_lower.startswith("/"):
            intent, data = self._handle_slash_command(message_lower)
            if intent != UserIntent.UNKNOWN:
                logger.info(f"Slash command detected: {intent.value}")
                return intent, data

        # === STEP 2: CONTEXT-AWARE STATES (unambiguous responses) ===
        intent, data = self._handle_context_state(message_lower, context)
        if intent != UserIntent.UNKNOWN:
            logger.info(f"Context state handled: {intent.value}")
            return intent, data

        # === STEP 2.5: TASK MODIFICATION PATTERNS (pre-AI check) ===
        intent, data = self._handle_modification_patterns(message, message_lower)
        if intent != UserIntent.UNKNOWN:
            logger.info(f"Task modification pattern detected: {intent.value}")
            return intent, data

        # === STEP 3: AI CLASSIFICATION (the brain) ===
        logger.info(f"Sending to AI for classification: {message[:100]}...")
        return await self._ai_classify(message, context)

    def _handle_slash_command(self, message: str) -> Tuple[UserIntent, Dict[str, Any]]:
        """Handle explicit slash commands - these are unambiguous."""

        if not message.startswith("/"):
            return UserIntent.UNKNOWN, {}

        cmd_parts = message[1:].split(None, 1)
        cmd = cmd_parts[0].lower() if cmd_parts else ""
        args = cmd_parts[1] if len(cmd_parts) > 1 else ""

        # Direct command mappings
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
            "done": (UserIntent.SKIP, {}),
            "templates": (UserIntent.LIST_TEMPLATES, {}),
            "team": (UserIntent.CHECK_STATUS, {"filter": "team"}),
            "archive": (UserIntent.ARCHIVE_TASKS, {}),
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
        if cmd == "spec" and args:
            task_id = args.strip().upper()
            return UserIntent.GENERATE_SPEC, {"task_id": task_id}

        return UserIntent.UNKNOWN, {}

    def _handle_context_state(
        self,
        message: str,
        context: Dict[str, Any]
    ) -> Tuple[UserIntent, Dict[str, Any]]:
        """
        Handle context-aware states where the expected response is clear.
        These don't need AI because the conversation flow is predefined.
        """

        is_boss = context.get("is_boss", False)
        awaiting_validation = context.get("awaiting_validation", False)
        collecting_proof = context.get("collecting_proof", False)
        awaiting_notes = context.get("awaiting_notes", False)
        awaiting_confirm = context.get("awaiting_confirm", False)

        # Boss responding to task validation
        if is_boss and awaiting_validation:
            positive = ["yes", "approved", "looks good", "lgtm", "great", "perfect",
                       "nice", "good job", "well done", "ship it", "✅", "👍", "ok", "okay"]
            negative = ["no", "reject", "needs", "fix", "change", "wrong",
                       "issue", "problem", "❌", "👎", "redo"]

            if any(w in message for w in positive):
                return UserIntent.APPROVE_TASK, {"approval_message": message}
            if any(w in message for w in negative):
                return UserIntent.REJECT_TASK, {"feedback": message}

        # Staff collecting proof
        if collecting_proof:
            done_words = ["done", "that's all", "thats all", "that is all",
                         "finish", "send it", "submit", "no more"]
            if any(w in message for w in done_words):
                return UserIntent.DONE_ADDING_PROOF, {}
            if message.startswith("http"):
                return UserIntent.SUBMIT_PROOF, {"proof_type": "link", "content": message}
            # Any text during proof collection is proof/notes
            return UserIntent.SUBMIT_PROOF, {"proof_type": "note", "content": message}

        # Awaiting notes
        if awaiting_notes:
            skip_words = ["skip", "no", "none", "nope", "nothing"]
            if any(w in message for w in skip_words):
                return UserIntent.ADD_NOTES, {"notes": None}
            return UserIntent.ADD_NOTES, {"notes": message}

        # Awaiting confirmation
        if awaiting_confirm:
            yes_words = ["yes", "y", "confirm", "ok", "send", "submit", "do it", "go", "yep", "yeah"]
            no_words = ["no", "cancel", "stop", "wait", "hold"]
            if any(w in message for w in yes_words):
                return UserIntent.CONFIRM_SUBMISSION, {}
            if any(w in message for w in no_words):
                return UserIntent.CANCEL, {}

        return UserIntent.UNKNOWN, {}

    def _handle_modification_patterns(
        self,
        message: str,
        message_lower: str
    ) -> Tuple[UserIntent, Dict[str, Any]]:
        """
        Handle obvious task modification patterns before AI classification.

        If message contains TASK-ID and modification keywords, directly classify
        without needing AI (these are unambiguous).
        """

        # Extract task IDs from message
        task_ids = re.findall(r'TASK-[\w\-]+', message, re.IGNORECASE)

        if not task_ids:
            return UserIntent.UNKNOWN, {}

        task_id = task_ids[0].upper()
        data = {"task_id": task_id, "task_ids": [t.upper() for t in task_ids], "message": message}

        # Check for modification keywords
        # MODIFY_TASK: change/update/rename title/description
        if any(k in message_lower for k in ["change", "update", "rename", "edit"]):
            if any(k in message_lower for k in ["title", "description"]):
                return UserIntent.MODIFY_TASK, data

        # REASSIGN_TASK: reassign/give/assign to [name]
        if any(k in message_lower for k in ["reassign", "give", "assign", "transfer"]):
            if any(k in message_lower for k in [" to ", " for "]):
                # Extract person name
                for name in TEAM_NAMES:
                    if name.lower() in message_lower:
                        data["new_assignee"] = name.capitalize()
                        break
                return UserIntent.REASSIGN_TASK, data

        # CHANGE_PRIORITY: make urgent/high/low priority
        if any(k in message_lower for k in ["make", "set", "change", "priority"]):
            priority_map = {
                "urgent": "urgent",
                "high": "high",
                "medium": "medium",
                "low": "low",
                "normal": "medium",
            }
            for key, value in priority_map.items():
                if key in message_lower:
                    data["new_priority"] = value
                    return UserIntent.CHANGE_PRIORITY, data

        # CHANGE_DEADLINE: extend/push deadline, due [date]
        if any(k in message_lower for k in ["deadline", "due"]):
            if any(k in message_lower for k in ["extend", "push", "change", "move", "tomorrow", "friday", "monday", "week"]):
                return UserIntent.CHANGE_DEADLINE, data

        # CHANGE_STATUS: move to/mark as [status]
        if any(k in message_lower for k in ["move to", "mark as", "status"]):
            return UserIntent.CHANGE_STATUS, data

        # ADD_TAGS: tag as/label/add tag
        if any(k in message_lower for k in ["tag", "label"]):
            if not any(k in message_lower for k in ["remove", "delete", "untag"]):
                return UserIntent.ADD_TAGS, data

        # REMOVE_TAGS: remove tag/untag
        if any(k in message_lower for k in ["remove tag", "delete tag", "untag"]):
            return UserIntent.REMOVE_TAGS, data

        # ADD_SUBTASK: add subtask
        if "add subtask" in message_lower or "subtask" in message_lower:
            if "add" in message_lower or "create" in message_lower:
                return UserIntent.ADD_SUBTASK, data

        # COMPLETE_SUBTASK: complete/finish/done subtask
        if "subtask" in message_lower:
            if any(k in message_lower for k in ["complete", "finish", "done", "mark"]):
                # Extract subtask number
                match = re.search(r'subtask\s+#?(\d+)', message_lower)
                if match:
                    data["subtask_number"] = int(match.group(1))
                return UserIntent.COMPLETE_SUBTASK, data

        # ADD_DEPENDENCY: depends on/blocked by
        if len(task_ids) >= 2:
            if any(k in message_lower for k in ["depends on", "blocked by", "after"]):
                return UserIntent.ADD_DEPENDENCY, data

        # REMOVE_DEPENDENCY: remove dependency
        if len(task_ids) >= 2:
            if any(k in message_lower for k in ["remove dependency", "unblock"]):
                return UserIntent.REMOVE_DEPENDENCY, data

        # DUPLICATE_TASK: duplicate/copy
        if any(k in message_lower for k in ["duplicate", "copy"]):
            return UserIntent.DUPLICATE_TASK, data

        # SPLIT_TASK: split/break into
        if any(k in message_lower for k in ["split", "break into"]):
            return UserIntent.SPLIT_TASK, data

        # If has task ID but no clear modification pattern, let AI handle it
        return UserIntent.UNKNOWN, {}

    async def _ai_classify(
        self,
        message: str,
        context: Dict[str, Any]
    ) -> Tuple[UserIntent, Dict[str, Any]]:
        """
        AI-powered intent classification - the brain of the system.

        The AI analyzes the message and returns:
        - intent: The classified intent
        - confidence: How sure the AI is (0-1)
        - extracted_data: Relevant data extracted from the message
        """

        is_boss = context.get("is_boss", False)
        team_names_str = ", ".join(TEAM_NAMES)

        prompt = f"""You are an intent classification system for a task management bot.
Analyze the message and determine what the user wants.

MESSAGE: "{message}"

CONTEXT:
- Is boss (can create tasks, approve work): {is_boss}
- Known team members: {team_names_str}

AVAILABLE INTENTS (pick exactly one):

**TASK MANAGEMENT:**
- create_task: Boss wants to ASSIGN WORK to someone. Keywords: "needs to", "should", "fix", "build", "create", "implement", "add feature", "deploy", task descriptions with assignee names.
- clear_tasks: Delete/remove tasks. Keywords: "clear", "delete", "remove", "wipe" + tasks.
- archive_tasks: Archive completed tasks.
- delay_task: Postpone a task. Keywords: "delay", "postpone", "push back", "reschedule".
- bulk_complete: Mark multiple tasks done. Keywords: "mark done", "complete these".

**TASK MODIFICATION (if message contains TASK-XXXXXX-XXX pattern, likely modification):**
- modify_task: Change task title or description. Keywords: "change TASK-X title", "update TASK-X description", "rename TASK-X", "edit TASK-X". Pattern: "change/update/rename TASK-ID title/description to X". REQUIRES task ID.
- reassign_task: Change who's assigned. Keywords: "reassign TASK-X", "give TASK-X to [name]", "assign TASK-X to", "transfer TASK-X to". Pattern: "reassign/give/assign TASK-ID to [name]". REQUIRES task ID.
- change_priority: Update priority level. Keywords: "make TASK-X urgent", "TASK-X high priority", "lower priority of TASK-X", "priority to medium for TASK-X". Pattern: "make TASK-ID urgent/high/medium/low" or "TASK-ID priority to X". REQUIRES task ID.
- change_deadline: Update deadline. Keywords: "extend TASK-X deadline", "push TASK-X deadline", "TASK-X due tomorrow", "deadline Friday for TASK-X". Pattern: "extend/push TASK-ID deadline to X" or "TASK-ID due X". REQUIRES task ID.
- change_status: Directly update status. Keywords: "move TASK-X to in_progress", "mark TASK-X as blocked", "status to review for TASK-X". Pattern: "move/mark TASK-ID to/as STATUS". REQUIRES task ID.
- add_tags: Add tags/labels. Keywords: "tag TASK-X as", "label TASK-X", "add tag to TASK-X". Pattern: "tag/label TASK-ID as X". REQUIRES task ID.
- remove_tags: Remove tags. Keywords: "remove tag from TASK-X", "untag TASK-X", "delete tag from TASK-X". Pattern: "remove/delete tag from TASK-ID". REQUIRES task ID.

**CRITICAL: When message contains TASK-XXXXXX-XXX format AND action verbs (change, update, reassign, etc.), it's MODIFICATION not task creation!**

**TASK STRUCTURE:**
- add_subtask: Add subtask to task. Keywords: "add subtask", "break down into", "add step". REQUIRES task ID.
- complete_subtask: Mark subtask done. Keywords: "subtask done", "finish subtask #1". REQUIRES task ID.
- add_dependency: Link tasks as dependencies. Keywords: "depends on", "blocked by", "after TASK-X". REQUIRES 2 task IDs.
- remove_dependency: Remove dependency link. Keywords: "remove dependency", "unblock". REQUIRES 2 task IDs.
- duplicate_task: Clone a task. Keywords: "duplicate", "copy task", "create similar". REQUIRES task ID.
- split_task: Break into multiple tasks. Keywords: "split into", "break into 2 tasks". REQUIRES task ID.

**DIRECT COMMUNICATION (NOT task creation):**
- ask_team_member: Boss wants to COMMUNICATE with team member (ask question, send message, request update). This is NOT assigning work - it's asking/telling/messaging. Keywords: "ask [name]", "tell [name]", "message [name]", "check with [name]", "ping [name]".

**STATUS & INFO:**
- check_status: Want overview of tasks. Keywords: "status", "pending", "what's happening", "overview".
- check_overdue: Check overdue tasks. Keywords: "overdue", "late", "past due".
- search_tasks: Find specific tasks. Keywords: "what's [name] working on", "find", "search".
- list_templates: Show available templates.
- email_recap: Check own emails (not delegate). Keywords: "my emails", "inbox", "check mail".

**TEAM & ATTENDANCE:**
- add_team: Registering team member info. Pattern: "[name] is our [role]".
- report_absence: Boss reporting attendance (absence, late, sick). Keywords: "didn't come", "was late", "sick leave", "absent".

**TASK COMPLETION (usually staff, not boss):**
- task_done: Saying they finished a task. Keywords: "I finished", "done with", "completed".
- submit_proof: Providing proof of work (screenshots, links).
- approve_task: Boss approving submitted work.
- reject_task: Boss rejecting with feedback.

**CONVERSATION:**
- greeting: Just saying hello ("hi", "hello", "hey").
- help: Asking for help ("help", "what can you do").
- cancel: Cancel current action ("cancel", "nevermind").
- skip: Skip/use defaults ("skip", "whatever").
- teach: Teaching bot preferences ("when I say X, do Y").
- generate_spec: Generate spec for existing task.

**CRITICAL DISTINCTIONS:**

1. **ask_team_member vs create_task:**
   - "ask Mayank what tasks are left" → ask_team_member (QUESTION/COMMUNICATION)
   - "Mayank needs to finish the tasks" → create_task (ASSIGNING WORK)
   - "tell Sarah to update me on progress" → ask_team_member (REQUEST FOR INFO)
   - "Sarah update the homepage" → create_task (ASSIGNING WORK)
   - "message John about the API status" → ask_team_member (COMMUNICATION)
   - "John fix the API bug" → create_task (ASSIGNING WORK)

2. **The key difference:**
   - ask_team_member = COMMUNICATE (ask, tell, message, ping, check with)
   - create_task = ASSIGN WORK (needs to, should, fix, build, create)

3. **Spec sheets / detailed tasks:**
   - If message contains "specsheets", "spec sheet", "detailed spec", "PRD" → create_task with detailed_mode: true

4. **Task modification vs task creation:**
   - "change TASK-001 title to X" → modify_task (MODIFICATION of existing task)
   - "create task titled X" → create_task (NEW task)
   - "reassign TASK-001 to Sarah" → reassign_task (MODIFICATION)
   - "Sarah needs to work on X" → create_task (NEW task)
   - "make TASK-001 urgent" → change_priority (MODIFICATION)
   - "urgent task for John" → create_task (NEW task)
   - **KEY: If message references existing TASK-ID format (TASK-XXXXXX-XXX), it's likely MODIFICATION not creation!**

RESPOND WITH ONLY THIS JSON (no other text):
{{
    "intent": "intent_name",
    "confidence": 0.95,
    "reasoning": "Brief explanation of why this intent",
    "extracted_data": {{
        "message": "original message",
        "task_id": "TASK-001 if single task mentioned",
        "task_ids": ["TASK-001", "TASK-002"] if multiple tasks mentioned,
        "target_name": "person name if ask_team_member",
        "original_request": "what to send if ask_team_member",
        "query": "search query if searching",
        "detailed_mode": true/false for spec sheets,
        "priority": "urgent/high/medium/low if mentioned",
        "new_priority": "new priority for change_priority",
        "new_assignee": "person name for reassignment",
        "new_status": "status name for change_status",
        "new_deadline": "deadline for change_deadline",
        "tags": ["tag1", "tag2"] for add_tags/remove_tags,
        "subtask_title": "subtask title for add_subtask",
        "subtask_number": 1 for complete_subtask,
        "filter": "today/week/pending if status filter"
    }}
}}

Only include relevant fields in extracted_data. Remove null/empty fields."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise intent classifier. Return ONLY valid JSON, no markdown, no explanation outside JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )

            # Parse the response
            response_text = response.choices[0].message.content.strip()

            # Clean up response if it has markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)

            intent_str = result.get("intent", "unknown")
            confidence = result.get("confidence", 0.5)
            reasoning = result.get("reasoning", "")
            extracted_data = result.get("extracted_data", {})

            # Ensure extracted_data is a dict (AI sometimes returns string)
            if not isinstance(extracted_data, dict):
                logger.warning(f"AI returned non-dict extracted_data: {type(extracted_data)} - {extracted_data}")
                extracted_data = {"message": message}

            # Clean up extracted_data - remove None/empty values
            extracted_data = {k: v for k, v in extracted_data.items() if v is not None and v != "" and v != []}

            # Log the AI's decision
            logger.info(f"AI classified: {intent_str} (confidence: {confidence})")
            logger.debug(f"AI reasoning: {reasoning}")

            # Validate intent
            try:
                intent = UserIntent(intent_str)
            except ValueError:
                logger.warning(f"AI returned invalid intent: {intent_str}")
                intent = UserIntent.UNKNOWN

            # Low confidence fallback
            if confidence < 0.5:
                logger.warning(f"Low confidence ({confidence}) - treating as unknown")
                return UserIntent.UNKNOWN, {"message": message, "ai_suggested": intent_str}

            # Post-processing for specific intents
            extracted_data = self._post_process_data(intent, message, extracted_data)

            return intent, extracted_data

        except json.JSONDecodeError as e:
            logger.error(f"AI returned invalid JSON: {e}")
            logger.error(f"Response was: {response_text[:500] if 'response_text' in locals() else 'N/A'}")
            return UserIntent.UNKNOWN, {"message": message}
        except Exception as e:
            logger.error(f"AI intent detection failed: {e}")
            return UserIntent.UNKNOWN, {"message": message}

    def _post_process_data(
        self,
        intent: UserIntent,
        message: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Post-process extracted data for specific intents."""

        # Ensure message is always included for task creation
        if intent == UserIntent.CREATE_TASK:
            data["message"] = message

        # Extract task IDs if present
        task_ids = re.findall(r'TASK-[\w\-]+', message, re.IGNORECASE)
        if task_ids and "task_ids" not in data:
            data["task_ids"] = [t.upper() for t in task_ids]

        # For ask_team_member, ensure we have the target and request
        if intent == UserIntent.ASK_TEAM_MEMBER:
            if "target_name" not in data:
                # Try to extract from message
                for name in TEAM_NAMES:
                    if name.lower() in message.lower():
                        data["target_name"] = name.capitalize()
                        break
            if "original_request" not in data:
                data["original_request"] = message
            data["message"] = message

        # For clear_tasks, ensure task_ids is a list
        if intent == UserIntent.CLEAR_TASKS:
            if "task_ids" not in data:
                data["task_ids"] = task_ids if task_ids else []
            data["message"] = message

        # For search, ensure query exists
        if intent == UserIntent.SEARCH_TASKS:
            if "query" not in data:
                data["query"] = message

        # For modification operations, ensure task_id is present
        modification_intents = [
            UserIntent.MODIFY_TASK,
            UserIntent.REASSIGN_TASK,
            UserIntent.CHANGE_PRIORITY,
            UserIntent.CHANGE_DEADLINE,
            UserIntent.CHANGE_STATUS,
            UserIntent.ADD_TAGS,
            UserIntent.REMOVE_TAGS,
            UserIntent.ADD_SUBTASK,
            UserIntent.COMPLETE_SUBTASK,
            UserIntent.ADD_DEPENDENCY,
            UserIntent.REMOVE_DEPENDENCY,
            UserIntent.DUPLICATE_TASK,
            UserIntent.SPLIT_TASK,
        ]

        if intent in modification_intents:
            # Extract task IDs if not already present
            if not data.get("task_id") and task_ids:
                data["task_id"] = task_ids[0].upper()
            if not data.get("task_ids") and task_ids:
                data["task_ids"] = [t.upper() for t in task_ids]

            # Extract values based on intent type
            if intent == UserIntent.REASSIGN_TASK:
                # Extract target person name if not already present
                if not data.get("new_assignee"):
                    for name in TEAM_NAMES:
                        if name.lower() in message.lower():
                            data["new_assignee"] = name.capitalize()
                            break

            elif intent == UserIntent.CHANGE_PRIORITY:
                # Extract priority level if not already present
                if not data.get("new_priority"):
                    priority_map = {
                        "urgent": "urgent",
                        "high": "high",
                        "medium": "medium",
                        "low": "low",
                        "normal": "medium",
                    }
                    for key, value in priority_map.items():
                        if key in message.lower():
                            data["new_priority"] = value
                            break

            elif intent == UserIntent.CHANGE_STATUS:
                # Extract status if not already present
                if not data.get("new_status"):
                    valid_statuses = [
                        "pending", "in_progress", "in_review", "awaiting_validation",
                        "needs_revision", "completed", "cancelled", "blocked",
                        "delayed", "undone", "on_hold", "waiting", "needs_info", "overdue"
                    ]
                    for status in valid_statuses:
                        if status.replace("_", " ") in message.lower():
                            data["new_status"] = status
                            break

            elif intent in [UserIntent.ADD_TAGS, UserIntent.REMOVE_TAGS]:
                # Extract tags if not already present
                if not data.get("tags"):
                    tags = re.findall(r'tag(?:ged)? (?:as |with )?(\w+)', message.lower())
                    if tags:
                        data["tags"] = tags

            elif intent == UserIntent.COMPLETE_SUBTASK:
                # Extract subtask number if not already present
                if not data.get("subtask_number"):
                    match = re.search(r'subtask\s+#?(\d+)', message, re.IGNORECASE)
                    if match:
                        data["subtask_number"] = int(match.group(1))

            data["message"] = message

        return data

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
