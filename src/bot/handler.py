"""
Unified message handler - fully conversational, no commands needed.

Interprets natural language and routes to appropriate actions.
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

from config import settings, get_settings
from ..ai.intent import IntentDetector, UserIntent, get_intent_detector
from ..ai.deepseek import get_deepseek_client
from ..ai.clarifier import TaskClarifier
from ..memory.preferences import get_preferences_manager
from ..memory.context import get_conversation_context
from ..memory.learning import get_learning_manager
from ..models.task import Task, TaskStatus, TaskPriority, AcceptanceCriteria
from ..models.conversation import ConversationState, ConversationStage
from ..models.validation import ProofItem, ProofType, TaskValidation, ValidationStatus
from ..integrations.discord import get_discord_integration, register_review_callback, get_review_callback, clear_review_callback, ReviewAction
from ..integrations.sheets import get_sheets_integration
from ..integrations.calendar import get_calendar_integration
from ..integrations.gmail import get_gmail_integration
from ..ai.email_summarizer import get_email_summarizer
from ..ai.reviewer import get_submission_reviewer, ReviewResult

logger = logging.getLogger(__name__)


class UnifiedHandler:
    """
    Handles all messages conversationally without commands.

    The flow is natural:
    - User talks naturally
    - AI interprets intent
    - Bot responds and takes action
    """

    def __init__(self):
        self.intent = get_intent_detector()
        self.ai = get_deepseek_client()
        self.clarifier = TaskClarifier()
        self.prefs = get_preferences_manager()
        self.context = get_conversation_context()
        self.learning = get_learning_manager()
        self.discord = get_discord_integration()
        self.sheets = get_sheets_integration()
        self.calendar = get_calendar_integration()
        self.reviewer = get_submission_reviewer()

        # Track active sessions
        self._validation_sessions: Dict[str, Dict] = {}
        self._pending_validations: Dict[str, Dict] = {}  # task_id -> validation info
        self._pending_reviews: Dict[str, Dict] = {}  # user_id -> review session
        self._pending_actions: Dict[str, Dict] = {}  # user_id -> pending dangerous action
        self._batch_tasks: Dict[str, Dict] = {}  # user_id -> batch task session
        self._spec_sessions: Dict[str, Dict] = {}  # user_id -> spec generation session

    async def handle_message(
        self,
        user_id: str,
        message: str,
        photo_file_id: Optional[str] = None,
        photo_caption: Optional[str] = None,
        photo_analysis: Optional[str] = None,
        user_name: str = "User",
        is_boss: bool = False,
        source: str = "telegram"  # "telegram" or "discord"
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Handle any incoming message.

        Architecture:
        - Telegram = Boss only (create tasks, approve, check status)
        - Discord = Staff (see tasks, react to update status)

        Returns:
            Tuple of (response_text, optional_action_data)
            action_data might contain: send_to_boss, notify_user, etc.
        """
        # IMPORTANT: Telegram is boss-only interface
        # All Telegram messages are from the boss - force is_boss=True
        if source == "telegram":
            is_boss = True

        # Clear any stuck sessions for boss
        if is_boss and user_id in self._validation_sessions:
            del self._validation_sessions[user_id]
            logger.info(f"Cleared validation session for boss {user_id}")

        if is_boss and user_id in self._pending_reviews:
            del self._pending_reviews[user_id]
            logger.info(f"Cleared review session for boss {user_id}")

        # Build context for intent detection
        context = await self._build_context(user_id, is_boss)

        # Check for multi-action message (e.g., "clear all tasks then create...")
        multi_action_result = await self._handle_multi_action(user_id, message, user_name, context)
        if multi_action_result:
            return multi_action_result

        # Handle photos
        if photo_file_id:
            if context.get("collecting_proof"):
                return await self._handle_proof_photo(user_id, photo_file_id, photo_caption, photo_analysis)
            else:
                # Photo outside of proof collection - just acknowledge
                if photo_caption:
                    message = f"[Photo] {photo_caption}"
                else:
                    return "Got the photo! What's this for?", None

        # Check for pending dangerous actions first (like clear tasks confirmation)
        pending_action = self._pending_actions.get(user_id)
        if pending_action:
            action_type = pending_action.get("type")
            if action_type == "clear_tasks":
                return await self._handle_clear_tasks(user_id, message, {}, context, user_name)

        # Check for batch task session (answering numbered questions or confirming)
        batch_session = self._batch_tasks.get(user_id)
        if batch_session:
            if batch_session.get("awaiting_answers"):
                return await self._handle_batch_answers(user_id, message, user_name)
            elif batch_session.get("awaiting_confirm"):
                return await self._handle_batch_confirm(user_id, message, user_name)

        # Check for spec generation session (answering clarifying questions)
        spec_session = self._spec_sessions.get(user_id)
        if spec_session and spec_session.get("awaiting_answers"):
            return await self._handle_spec_answer(user_id, message, user_name)

        # Check for active task preview - user may be providing corrections
        active_conv = await self.context.get_active_conversation(user_id)
        if active_conv and active_conv.stage == ConversationStage.PREVIEW:
            msg_lower = message.lower().strip()

            # User says "no" followed by correction = edit the task
            if msg_lower.startswith("no ") or msg_lower.startswith("no,"):
                correction = message[3:].strip() if msg_lower.startswith("no ") else message[3:].strip()
                if correction:
                    return await self._handle_task_correction(user_id, active_conv, correction, user_name)

            # User says "edit" or "change" followed by what to change
            if msg_lower.startswith("edit ") or msg_lower.startswith("change "):
                correction = message[5:].strip() if msg_lower.startswith("edit ") else message[7:].strip()
                if correction:
                    return await self._handle_task_correction(user_id, active_conv, correction, user_name)

            # User says "add" something to the task
            if msg_lower.startswith("add "):
                correction = message  # Keep full message for context
                return await self._handle_task_correction(user_id, active_conv, correction, user_name)

            # User says "make it" something
            if msg_lower.startswith("make it ") or msg_lower.startswith("make this "):
                return await self._handle_task_correction(user_id, active_conv, message, user_name)

            # User just says "no" = cancel
            elif msg_lower == "no":
                await self.context.clear_conversation(user_id)
                return "Task cancelled. What would you like to do?", None

            # User says "yes" = confirm and create
            elif msg_lower in ["yes", "y", "ok", "confirm", "create", "looks good", "lgtm", "good", "perfect"]:
                return await self._finalize_task(active_conv, user_id)

        # Detect intent
        intent, data = await self.intent.detect_intent(message, context)
        logger.info(f"Detected intent: {intent} for user {user_id}")

        # Route to handler
        handlers = {
            UserIntent.GREETING: self._handle_greeting,
            UserIntent.HELP: self._handle_help,
            UserIntent.CREATE_TASK: self._handle_create_task,
            UserIntent.TASK_DONE: self._handle_task_done,
            UserIntent.SUBMIT_PROOF: self._handle_submit_proof,
            UserIntent.DONE_ADDING_PROOF: self._handle_done_proof,
            UserIntent.ADD_NOTES: self._handle_add_notes,
            UserIntent.CONFIRM_SUBMISSION: self._handle_confirm_submission,
            UserIntent.APPROVE_TASK: self._handle_approve,
            UserIntent.REJECT_TASK: self._handle_reject,
            UserIntent.CHECK_STATUS: self._handle_status,
            UserIntent.CHECK_OVERDUE: self._handle_overdue,
            UserIntent.EMAIL_RECAP: self._handle_email_recap,
            UserIntent.SEARCH_TASKS: self._handle_search,
            UserIntent.BULK_COMPLETE: self._handle_bulk_complete,
            UserIntent.LIST_TEMPLATES: self._handle_templates,
            UserIntent.DELAY_TASK: self._handle_delay,
            UserIntent.ADD_TEAM_MEMBER: self._handle_add_team,
            UserIntent.TEACH_PREFERENCE: self._handle_teach,
            UserIntent.CLEAR_TASKS: self._handle_clear_tasks,
            UserIntent.ARCHIVE_TASKS: self._handle_archive_tasks,
            UserIntent.GENERATE_SPEC: self._handle_generate_spec,
            UserIntent.CANCEL: self._handle_cancel,
            UserIntent.SKIP: self._handle_skip,
            UserIntent.UNKNOWN: self._handle_unknown,
        }

        handler = handlers.get(intent, self._handle_unknown)
        return await handler(user_id, message, data, context, user_name)

    async def _build_context(self, user_id: str, is_boss: bool) -> Dict[str, Any]:
        """Build context for intent detection."""
        context = {
            "is_boss": is_boss,
            "stage": "none",
            "collecting_proof": False,
            "awaiting_notes": False,
            "awaiting_confirm": False,
            "awaiting_validation": False,
            "awaiting_review_response": False,
        }

        # Check for active validation session
        session = self._validation_sessions.get(user_id)
        if session:
            stage = session.get("stage", "")
            context["stage"] = stage
            context["collecting_proof"] = stage == "collecting_proof"
            context["awaiting_notes"] = stage == "awaiting_notes"
            context["awaiting_confirm"] = stage == "awaiting_confirm"
            context["awaiting_review_response"] = stage == "awaiting_review_response"

        # Check for pending review
        if user_id in self._pending_reviews:
            context["awaiting_review_response"] = True

        # Check if boss has pending validations to respond to
        if is_boss and self._pending_validations:
            context["awaiting_validation"] = True

        # Check for active task creation conversation
        conv = await self.context.get_active_conversation(user_id)
        if conv:
            context["stage"] = conv.stage.value
            context["has_active_conversation"] = True

        return context

    async def _handle_multi_action(
        self, user_id: str, message: str, user_name: str, context: Dict
    ) -> Optional[Tuple[str, Optional[Dict]]]:
        """
        Detect and handle messages with multiple actions.

        E.g., "Clear all tasks then create a new task for Mayank..."

        Returns None if not a multi-action message.
        """
        message_lower = message.lower()

        # Check for action separators
        separators = [" then ", " and then ", " after that ", " also ", " and also "]

        found_separator = None
        for sep in separators:
            if sep in message_lower:
                found_separator = sep
                break

        if not found_separator:
            return None

        # Split into parts
        parts = message_lower.split(found_separator, 1)
        if len(parts) < 2:
            return None

        first_part = parts[0].strip()
        second_part = parts[1].strip()

        # Check if first part is a clear/delete action
        clear_keywords = ["clear", "delete", "remove", "wipe", "reset"]
        is_clear_first = any(kw in first_part for kw in clear_keywords)

        # Check if second part is a create action
        create_keywords = ["create", "make", "add", "new task", "assign"]
        is_create_second = any(kw in second_part for kw in create_keywords)

        if not (is_clear_first and is_create_second):
            # Not a recognized multi-action pattern, let normal flow handle
            return None

        logger.info(f"Detected multi-action: CLEAR then CREATE")

        responses = []

        # Step 1: Handle clear action
        clear_response, _ = await self._handle_clear_tasks(
            user_id, first_part, {"task_ids": []}, context, user_name
        )

        # Check if clear needs confirmation
        if "confirm" in clear_response.lower() or "yes" in clear_response.lower():
            # Auto-confirm the clear for multi-action
            confirm_response, _ = await self._handle_clear_tasks(
                user_id, "yes", {"task_ids": []}, context, user_name
            )
            responses.append(confirm_response)
        else:
            responses.append(clear_response)

        # Step 2: Handle create action(s)
        # The second part might contain multiple tasks separated by "and another"
        task_parts = [second_part]
        second_lower = second_part.lower()
        if " and another " in second_lower:
            # Split while preserving original case
            import re
            task_parts = re.split(r'\s+and\s+another\s+', second_part, flags=re.IGNORECASE)
        elif " another one " in second_lower:
            idx = second_lower.find(" another one ")
            task_parts = [second_part[:idx], second_part[idx + 13:]]

        # Clean up task parts
        task_parts = [t.strip() for t in task_parts if t.strip()]

        if len(task_parts) > 1:
            # Multiple tasks - use batch system to ensure all get created on "yes"
            prefs = await self.prefs.get_preferences(user_id)
            batch_response, _ = await self._handle_batch_tasks(user_id, task_parts, prefs, user_name)
            responses.append(batch_response)
        elif task_parts:
            # Single task - normal flow
            create_response, _ = await self._handle_create_task(
                user_id, task_parts[0], {"message": task_parts[0]}, context, user_name
            )
            responses.append(create_response)

        # Combine responses
        combined = "\n\n---\n\n".join(responses)
        return combined, None

    # ==================== INTENT HANDLERS ====================

    async def _handle_greeting(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle greetings."""
        return f"""Hey {user_name}! 👋

**Your Command Center:**
• Create tasks: "Mayank needs to fix the login bug"
• Check status: "What's pending?"
• Email recap: "Check my emails"

Staff will see tasks on Discord and update their status there.

What would you like to do?""", None

    async def _handle_help(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle help requests."""
        return """📖 **Boss Command Center**

**Just Chat Naturally:**
• "John needs to fix the login bug by tomorrow"
• "What's pending?" / "Show overdue"
• "Mark TASK-001 as done"
• "What's Sarah working on?"

**Task Creation:**
• `/task` or `/urgent` - Start task
• Templates: "bug: crash" auto-applies defaults
• `/templates` - View templates

**Task Management:**
• `/status` - Overview
• `/search @John` or `/search #urgent`
• `/complete ID ID` - Bulk complete
• `/note TASK-001 notes`
• `/delay TASK-001 tomorrow`

**Subtasks:**
• `/subtask TASK-001 "Design mockup"`
• `/subtasks TASK-001` - List
• `/subdone TASK-001 1,2` - Complete

**Time Tracking:**
• `/start TASK-001` / `/stop`
• `/log TASK-001 2h30m`
• `/timesheet` or `/timesheet team`

**Recurring:**
• `/recurring "Standup" every:monday 9am`
• `/recurring list`

**Reports:**
• `/daily` / `/weekly` / `/overdue`

**Team:**
• `/team` / `/addteam Name Role`
• `/pending` - Review submissions
• `/approve ID` / `/reject ID`

**Voice:** Send audio message - I'll transcribe it!""", None

    async def _handle_create_task(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle task creation - supports multiple tasks in one message."""
        # Get preferences
        prefs = await self.prefs.get_preferences(user_id)

        # Detect multiple tasks in message
        task_messages = self._split_multiple_tasks(message)

        if len(task_messages) > 1:
            # Multiple tasks - handle as batch
            return await self._handle_batch_tasks(user_id, task_messages, prefs, user_name)

        # Single task - normal flow
        conversation = await self.context.create_conversation(
            user_id=user_id,
            chat_id=user_id,
            original_message=message
        )

        # Analyze with AI
        should_ask, analysis = await self.clarifier.analyze_and_decide(
            conversation=conversation,
            preferences=prefs.to_dict(),
            team_info=prefs.get_team_info()
        )

        if should_ask:
            # Generate questions
            question_msg, questions = await self.clarifier.generate_question_message(
                analysis=analysis,
                preferences=prefs.to_dict()
            )
            for q in questions:
                conversation.add_question(q.question, q.options)

            conversation.stage = ConversationStage.AWAITING_ANSWER
            await self.context.save_conversation(conversation)

            return f"Got it! Quick questions:\n\n{question_msg}", None
        else:
            # Can create directly
            return await self._create_task_directly(conversation, prefs.to_dict())

    async def _handle_task_correction(
        self, user_id: str, conversation: ConversationState, correction: str, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle user correction after task preview (they said 'no, [changes]' or 'edit X')."""
        import json

        # Get current spec - if None, rebuild from extracted_info
        current_spec = conversation.generated_spec
        if not current_spec:
            current_spec = conversation.extracted_info.copy() if conversation.extracted_info else {}
            logger.warning(f"generated_spec was None for conversation {conversation.conversation_id}, using extracted_info")

        # If still empty, we can't correct - need to regenerate
        if not current_spec or not current_spec.get('title'):
            logger.error(f"No spec to correct for conversation {conversation.conversation_id}")
            # Try to regenerate from original message + correction
            prefs = await self.prefs.get_preferences(user_id)
            conversation.original_message = f"{conversation.original_message}. Also: {correction}"
            return await self._create_task_directly(conversation, prefs.to_dict())

        # Use AI to apply the correction - more robust prompt
        prompt = f"""You are updating a task specification based on user feedback.

CURRENT TASK:
- Title: {current_spec.get('title', 'Untitled')}
- Assignee: {current_spec.get('assignee', 'Unassigned')}
- Priority: {current_spec.get('priority', 'medium')}
- Deadline: {current_spec.get('deadline', 'Not set')}
- Description: {current_spec.get('description', 'No description')}
- Acceptance Criteria: {current_spec.get('acceptance_criteria', [])}

USER'S CORRECTION/ADDITION: "{correction}"

The user wants to modify the task. Understand what they mean:
- "add favicon" = add to description/acceptance criteria
- "make it urgent" = change priority to urgent
- "assign to X" = change assignee
- "also X" or "don't forget X" = add X to description/criteria
- "change title to X" = update title
- etc.

Return the COMPLETE updated task as JSON (include all fields, even unchanged ones):
{{
    "title": "Task title",
    "assignee": "person name or null",
    "priority": "urgent/high/medium/low",
    "deadline": "ISO datetime or keep existing",
    "description": "Full description including any additions",
    "estimated_effort": "time estimate",
    "acceptance_criteria": ["criterion 1", "criterion 2"]
}}

IMPORTANT: Merge the user's request INTO the existing task. Don't remove information, add to it."""

        try:
            response = await self.ai.chat(
                messages=[
                    {"role": "system", "content": "You update task specifications based on user feedback. Always return valid JSON. Be smart about understanding what users want to change or add."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )

            content = response.choices[0].message.content
            logger.info(f"AI correction response: {content[:200]}...")

            # Extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            updated_spec = json.loads(content.strip())

            # Merge with existing spec (keep fields AI didn't return)
            for key, value in current_spec.items():
                if key not in updated_spec or updated_spec[key] is None:
                    updated_spec[key] = value

            # Update conversation
            conversation.generated_spec = updated_spec
            await self.context.save_conversation(conversation)

            # Show new preview
            preview = self._format_task_preview(updated_spec)

            return f"""📋 **Updated Task:**

{preview}

Look good now? (yes/no)""", None

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in correction: {e}, content: {content[:200] if 'content' in dir() else 'N/A'}")
            # Fallback: just append correction to description
            if current_spec.get('description'):
                current_spec['description'] += f"\n\nAdditional: {correction}"
            else:
                current_spec['description'] = correction

            conversation.generated_spec = current_spec
            await self.context.save_conversation(conversation)

            preview = self._format_task_preview(current_spec)
            return f"""📋 **Updated Task** (added your note):

{preview}

Look good now? (yes/no)""", None

        except Exception as e:
            logger.error(f"Error applying correction: {type(e).__name__}: {e}")
            # Last resort: ask for clearer instruction
            return f"I had trouble applying that change. Could you be more specific?\n\nFor example:\n• \"change title to X\"\n• \"add X to the description\"\n• \"make it urgent\"\n• \"assign to John\"", None

    def _format_task_preview(self, spec: Dict) -> str:
        """Format a task spec as a preview string."""
        priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
            spec.get("priority", "medium"), "⚪"
        )

        lines = [
            f"**Title:** {spec.get('title', 'Untitled')}",
            f"**Assignee:** {spec.get('assignee') or 'Unassigned'}",
            f"**Priority:** {priority_emoji} {spec.get('priority', 'medium').upper()}",
        ]

        if spec.get("deadline"):
            lines.append(f"**Deadline:** {spec.get('deadline')}")

        if spec.get("estimated_effort"):
            lines.append(f"**Effort:** {spec.get('estimated_effort')}")

        if spec.get("description"):
            desc = spec.get("description", "")[:200]
            if len(spec.get("description", "")) > 200:
                desc += "..."
            lines.append(f"\n**Description:**\n{desc}")

        return "\n".join(lines)

    async def _create_task_directly(
        self, conversation: ConversationState, preferences: Dict
    ) -> Tuple[str, Optional[Dict]]:
        """Create task without questions, with smart dependency check."""
        preview, spec = await self.clarifier.generate_spec_preview(
            conversation=conversation,
            preferences=preferences
        )

        conversation.generated_spec = spec
        conversation.stage = ConversationStage.PREVIEW
        await self.context.save_conversation(conversation)

        # Build response with template info if applied
        response_parts = []

        # Check if template was applied
        template_name = conversation.extracted_info.get("_template_applied")
        if template_name:
            response_parts.append(f"📋 *Template applied: {template_name.upper()}*\n")

        response_parts.append(preview)

        # Smart dependency check
        try:
            dependencies = await self.clarifier.find_potential_dependencies(
                task_description=spec.get("title", "") + " " + spec.get("description", ""),
                assignee=spec.get("assignee")
            )

            if dependencies:
                dep_msg = "\n\n⚠️ **Potential Dependencies:**"
                for dep in dependencies[:3]:  # Limit to 3
                    dep_msg += f"\n• {dep['task_id']}: {dep['reason'][:50]}"
                dep_msg += "\n\n_Add as blocked_by? Reply 'yes' to create, 'block:TASK-ID' to add dependency_"
                response_parts.append(dep_msg)

                # Store potential dependencies in conversation
                conversation.extracted_info["_potential_deps"] = [d["task_id"] for d in dependencies]
                await self.context.save_conversation(conversation)
            else:
                response_parts.append("\n\nLook good? (yes/no)")
        except Exception as e:
            logger.warning(f"Dependency check failed: {e}")
            response_parts.append("\n\nLook good? (yes/no)")

        return "".join(response_parts), None

    async def _handle_task_done(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle when someone says they finished a task."""
        # Boss on Telegram = might be trying to create a task, not submit proof
        if context.get("is_boss"):
            # Check if this looks like task creation
            msg_lower = message.lower()
            if any(w in msg_lower for w in ["title:", "assignee:", "submit new", "create", "task for", "needs to"]):
                # Redirect to task creation
                return await self._handle_create_task(user_id, message, {"message": message}, context, user_name)

            return """To create a task, just describe it:
• "Mayank needs to fix the login bug"
• "Sarah should update the docs by Friday"

Or ask "what's pending?" to see current tasks.""", None

        # Start proof collection session for team member
        self._validation_sessions[user_id] = {
            "stage": "collecting_proof",
            "user_id": user_id,
            "user_name": user_name,
            "message": message,
            "proof_items": [],
            "started_at": datetime.now().isoformat()
        }

        return f"""Nice work! 🎉

Send me proof of what you did:
• Screenshots
• Links to live site/PR
• Whatever shows it's done

When you're done sending, just say "that's all\"""", None

    async def _handle_submit_proof(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle proof submission (text/link)."""
        session = self._validation_sessions.get(user_id)
        if not session:
            return "What task did you finish? Tell me about it!", None

        proof_type = data.get("proof_type", "note")
        content = data.get("content", message)

        proof = {
            "type": proof_type,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        session["proof_items"].append(proof)

        count = len(session["proof_items"])
        emoji = "🔗" if proof_type == "link" else "📝"

        return f"{emoji} Got it! ({count} item{'s' if count > 1 else ''} so far)\n\nMore proof, or say \"that's all\"", None

    async def _handle_proof_photo(
        self, user_id: str, file_id: str, caption: Optional[str], analysis: Optional[str] = None
    ) -> Tuple[str, None]:
        """Handle photo as proof with AI vision analysis."""
        session = self._validation_sessions.get(user_id)
        if not session:
            return "What's this screenshot for?", None

        proof = {
            "type": "screenshot",
            "file_id": file_id,
            "caption": caption,
            "analysis": analysis,  # Store vision analysis
            "timestamp": datetime.now().isoformat()
        }
        session["proof_items"].append(proof)

        count = len(session["proof_items"])

        # Include analysis summary in response if available
        if analysis:
            analysis_preview = analysis[:100] + "..." if len(analysis) > 100 else analysis
            return f"📸 Screenshot received! ({count} item{'s' if count > 1 else ''})\n\n🔍 _AI Analysis: {analysis_preview}_\n\nMore, or \"that's all\"", None

        return f"📸 Screenshot received! ({count} item{'s' if count > 1 else ''})\n\nMore, or \"that's all\"", None

    async def _handle_done_proof(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle when user is done adding proof."""
        session = self._validation_sessions.get(user_id)
        if not session:
            return "Nothing to submit. Tell me what task you finished!", None

        if not session.get("proof_items"):
            return "Send at least one piece of proof first (screenshot, link, etc.)", None

        session["stage"] = "awaiting_notes"

        return f"""Got {len(session['proof_items'])} proof item(s)!

Any notes for the boss? (what you did, issues, etc.)
Or say "no" to skip.""", None

    async def _handle_add_notes(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle notes for submission - triggers auto-review."""
        session = self._validation_sessions.get(user_id)
        if not session:
            return "No active submission.", None

        notes = data.get("notes")
        session["notes"] = notes

        # === AUTO-REVIEW ===
        if settings.enable_auto_review:
            feedback = await self.reviewer.review_submission(
                task_description=session.get("message", ""),
                proof_items=session.get("proof_items", []),
                notes=notes,
                user_name=user_name
            )

            if feedback.passes_threshold:
                # Quality is good - proceed to confirm
                session["stage"] = "awaiting_confirm"
                proof_count = len(session.get("proof_items", []))
                summary = f"""✅ **Looks good!** (Score: {feedback.score}/100)

📋 Task: {session.get('message', 'Task completion')[:50]}...
📎 Proof: {proof_count} item(s)
📝 Notes: {notes if notes else '(none)'}

Send to boss for review? (yes/no)"""
                return summary, None
            else:
                # Quality needs improvement - show feedback
                session["stage"] = "awaiting_review_response"
                session["review_feedback"] = feedback.to_dict()

                # Store review session for response handling
                self._pending_reviews[user_id] = {
                    "session": session,
                    "feedback": feedback,
                    "submission_id": f"SUB-{datetime.now().strftime('%m%d%H%M')}-{user_id[-3:]}"
                }

                # Generate feedback message
                review_msg = await self.reviewer.generate_improvement_message(feedback, user_name)

                # Post to Discord with buttons
                submission_id = self._pending_reviews[user_id]["submission_id"]
                await self.discord.post_review_feedback(
                    user_id=user_id,
                    user_name=user_name,
                    review_message=review_msg,
                    submission_id=submission_id,
                    has_suggestions=bool(feedback.improved_notes)
                )

                # Return Telegram message with options
                options_msg = f"""{review_msg}

─────────────────
**Reply with:**
• **"yes"** - Apply suggestions and send
• **"no"** - Send to boss as-is anyway
• **"edit"** - Let me fix it myself (then type your new notes)"""

                return options_msg, None
        else:
            # No auto-review - direct confirm
            session["stage"] = "awaiting_confirm"
            proof_count = len(session.get("proof_items", []))
            summary = f"""**Ready to submit:**

📋 Task: {session.get('message', 'Task completion')[:50]}...
📎 Proof: {proof_count} item(s)
📝 Notes: {notes if notes else '(none)'}

Send to boss for review? (yes/no)"""
            return summary, None

    async def _handle_confirm_submission(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle confirmation - send to boss."""
        session = self._validation_sessions.get(user_id)
        if not session:
            return "Nothing to confirm.", None

        # Generate a task reference
        task_ref = f"TASK-{datetime.now().strftime('%m%d')}-{user_id[-3:]}"

        # Store as pending validation
        self._pending_validations[task_ref] = {
            "task_id": task_ref,
            "user_id": user_id,
            "user_name": user_name,
            "description": session.get("message", ""),
            "proof_items": session.get("proof_items", []),
            "notes": session.get("notes"),
            "submitted_at": datetime.now().isoformat()
        }

        # Clear session
        del self._validation_sessions[user_id]

        # Build message for boss
        boss_message = self._build_boss_notification(task_ref, user_name, session)

        return "✅ Sent to boss for review! I'll let you know when they respond.", {
            "send_to_boss": True,
            "boss_message": boss_message,
            "proof_items": session.get("proof_items", []),
            "task_ref": task_ref
        }

    def _build_boss_notification(self, task_ref: str, user_name: str, session: Dict) -> str:
        """Build the notification message for boss."""
        lines = [
            f"📋 **{user_name}** finished a task!",
            "",
            f"**{session.get('message', 'Task')[:100]}**",
            "",
            f"📎 **Proof:** {len(session.get('proof_items', []))} item(s)",
        ]

        # List proof items with AI analysis
        for i, proof in enumerate(session.get("proof_items", [])[:5], 1):
            ptype = proof.get("type", "item")
            emoji = {"screenshot": "🖼️", "link": "🔗", "note": "📝"}.get(ptype, "📎")
            if ptype == "link":
                lines.append(f"  {emoji} {proof.get('content', '')[:50]}")
            elif ptype == "screenshot":
                lines.append(f"  {emoji} Screenshot {i}")
                # Include AI analysis if available
                if proof.get("analysis"):
                    analysis_preview = proof["analysis"][:80]
                    lines.append(f"     🔍 _{analysis_preview}..._")
            else:
                lines.append(f"  {emoji} {proof.get('content', '')[:30]}...")

        if session.get("notes"):
            lines.extend(["", f"📝 **Notes:** {session['notes']}"])

        lines.extend([
            "",
            "─────────────────",
            f"_Ref: {task_ref}_",
            "",
            "**Reply:** yes (approve) or no + feedback"
        ])

        return "\n".join(lines)

    async def _handle_approve(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle boss approval."""
        if not self._pending_validations:
            return "Nothing pending approval.", None

        # Get the most recent pending validation
        # In production, would match to specific task from reply context
        task_ref = list(self._pending_validations.keys())[-1]
        validation = self._pending_validations.pop(task_ref)

        approval_msg = data.get("approval_message", message)

        # Post to Discord
        await self.discord.post_alert(
            title="Task Approved ✅",
            message=f"**{validation['user_name']}** - {validation['description'][:50]}",
            alert_type="success"
        )

        # Notify assignee
        assignee_notification = f"""🎉 **APPROVED!**

Your work on "{validation['description'][:50]}..." was approved!

Boss said: "{approval_msg}"

Great job! ✅"""

        return f"✅ Approved! Notified {validation['user_name']}.", {
            "notify_user": validation["user_id"],
            "notification": assignee_notification
        }

    async def _handle_reject(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle boss rejection with feedback."""
        if not self._pending_validations:
            return "Nothing pending review.", None

        task_ref = list(self._pending_validations.keys())[-1]
        validation = self._pending_validations.pop(task_ref)

        feedback = data.get("feedback", message)
        # Clean up the feedback (remove "no" prefix if present)
        if feedback.lower().startswith("no"):
            feedback = feedback[2:].strip(" -:,")

        # Post to Discord
        await self.discord.post_alert(
            title="Revision Requested",
            message=f"**{validation['user_name']}** - {feedback[:100]}",
            alert_type="warning"
        )

        # Notify assignee
        assignee_notification = f"""🔄 **Changes Requested**

Your submission needs some work.

**Feedback:**
{feedback}

Make the changes and submit again when ready!"""

        return f"Sent feedback to {validation['user_name']}.", {
            "notify_user": validation["user_id"],
            "notification": assignee_notification
        }

    async def _handle_status(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle status check."""
        daily_tasks = await self.sheets.get_daily_tasks()
        overdue = await self.sheets.get_overdue_tasks()

        lines = ["📊 **Status Overview**", ""]

        if daily_tasks:
            completed = sum(1 for t in daily_tasks if t.get("Status") == "completed")
            lines.append(f"Today: {completed}/{len(daily_tasks)} tasks done")
        else:
            lines.append("No tasks for today")

        if overdue:
            lines.append(f"⚠️ {len(overdue)} overdue")

        if self._pending_validations:
            lines.append(f"📋 {len(self._pending_validations)} awaiting review")

        return "\n".join(lines), None

    async def _handle_overdue(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle overdue check."""
        overdue = await self.sheets.get_overdue_tasks()

        if not overdue:
            return "✅ Nothing overdue!", None

        lines = ["🚨 **Overdue Tasks**", ""]
        for task in overdue[:5]:
            lines.append(f"• {task.get('Title', 'Task')[:40]} - {task.get('Assignee', '?')}")

        return "\n".join(lines), None

    async def _handle_search(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle natural language search."""
        import re

        query = data.get("query", message)

        # Parse natural language search patterns
        assignee = None
        status = None
        priority = None

        # "What's John working on?" -> search by assignee
        working_on_match = re.search(r"what'?s?\s+(\w+)\s+working\s+on", query, re.IGNORECASE)
        if working_on_match:
            assignee = working_on_match.group(1)

        # "tasks for Sarah" -> search by assignee
        tasks_for_match = re.search(r"tasks?\s+(?:for|assigned\s+to)\s+@?(\w+)", query, re.IGNORECASE)
        if tasks_for_match:
            assignee = tasks_for_match.group(1)

        # Extract @mentions
        mention_match = re.search(r'@(\w+)', query)
        if mention_match:
            assignee = mention_match.group(1)

        # "urgent tasks" or "high priority"
        if any(w in query.lower() for w in ["urgent", "critical"]):
            priority = "urgent"
        elif "high priority" in query.lower():
            priority = "high"

        # "blocked tasks"
        if "blocked" in query.lower():
            status = "blocked"
        elif "pending" in query.lower():
            status = "pending"
        elif "in progress" in query.lower() or "in_progress" in query.lower():
            status = "in_progress"

        # Text search terms (remove special patterns)
        text_query = query
        for pattern in [r"what'?s?\s+\w+\s+working\s+on", r"tasks?\s+(?:for|assigned\s+to)\s+@?\w+", r"@\w+"]:
            text_query = re.sub(pattern, "", text_query, flags=re.IGNORECASE).strip()

        results = await self.sheets.search_tasks(
            query=text_query if len(text_query) > 2 else None,
            assignee=assignee,
            status=status,
            priority=priority,
            limit=10
        )

        if not results:
            search_desc = []
            if assignee:
                search_desc.append(f"assignee: {assignee}")
            if status:
                search_desc.append(f"status: {status}")
            if priority:
                search_desc.append(f"priority: {priority}")
            return f"No tasks found{' (' + ', '.join(search_desc) + ')' if search_desc else ''}", None

        lines = [f"🔍 **Found {len(results)} task(s)**", ""]

        for task in results:
            priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                task.get('Priority', '').lower(), "⚪"
            )
            status_val = task.get('Status', 'pending')
            lines.append(f"{priority_emoji} **{task.get('ID', 'N/A')}**: {task.get('Title', '')[:35]}")
            lines.append(f"   {task.get('Assignee', 'Unassigned')} | {status_val}")

        return "\n".join(lines), None

    async def _handle_bulk_complete(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle bulk task completion via natural language."""
        task_ids = data.get("task_ids", [])

        if not task_ids:
            return "Which tasks do you want to mark as done? List their IDs.", None

        success_count, failed = await self.sheets.bulk_update_status(
            task_ids=task_ids,
            new_status="completed"
        )

        # Post to Discord
        if success_count > 0:
            await self.discord.post_alert(
                title="Tasks Completed",
                message=f"{success_count} task(s) marked as completed by {user_name}",
                alert_type="success"
            )

        if failed:
            return f"✅ Completed {success_count} task(s)\n❌ Not found: {', '.join(failed)}", None
        return f"✅ Marked {success_count} task(s) as done!", None

    async def _handle_clear_tasks(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle request to clear/delete tasks (specific or all)."""
        task_ids = data.get("task_ids", [])

        # If specific task IDs provided, cancel them directly
        if task_ids:
            return await self._clear_specific_tasks(task_ids, user_name)

        # For "clear all" - this is dangerous, confirm with the user
        pending_action = self._pending_actions.get(user_id)

        if pending_action and pending_action.get("type") == "clear_tasks":
            # User is confirming
            if any(w in message.lower() for w in ["yes", "confirm", "do it", "proceed"]):
                # Actually clear the tasks
                try:
                    # Get all tasks and mark as cancelled
                    tasks = await self.sheets.get_all_tasks()
                    count = 0

                    for task in tasks:
                        status = task.get("Status", task.get("status", ""))
                        task_id = task.get("ID", task.get("id", ""))
                        if status.lower() not in ["completed", "cancelled"] and task_id:
                            success = await self.sheets.update_task(
                                task_id=task_id,
                                updates={"Status": "cancelled"}
                            )
                            if success:
                                count += 1

                    del self._pending_actions[user_id]

                    await self.discord.post_alert(
                        title="Tasks Cleared",
                        message=f"{count} task(s) marked as cancelled by {user_name}",
                        alert_type="warning"
                    )

                    return f"✅ Cleared {count} task(s). They've been marked as cancelled.", None

                except Exception as e:
                    logger.error(f"Error clearing tasks: {e}", exc_info=True)
                    del self._pending_actions[user_id]
                    return "❌ Error clearing tasks. Please try again.", None
            else:
                del self._pending_actions[user_id]
                return "Cancelled. No tasks were cleared.", None

        # First time - ask for confirmation
        try:
            tasks = await self.sheets.get_all_tasks()
            active_count = sum(1 for t in tasks if t.get("Status", t.get("status", "")).lower() not in ["completed", "cancelled"])
        except Exception:
            active_count = "unknown number of"

        self._pending_actions[user_id] = {"type": "clear_tasks"}

        return f"""⚠️ **Clear All Tasks?**

This will mark {active_count} active task(s) as cancelled.

**This action cannot be undone.**

Reply **yes** to confirm or **no** to cancel.""", None

    async def _clear_specific_tasks(
        self, task_ids: list, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Clear/cancel specific tasks by ID."""
        cancelled = []
        not_found = []

        for task_id in task_ids:
            task_id = task_id.upper()
            try:
                success = await self.sheets.update_task(
                    task_id=task_id,
                    updates={"Status": "cancelled"}
                )
                if success:
                    cancelled.append(task_id)
                else:
                    not_found.append(task_id)
            except Exception as e:
                logger.error(f"Error cancelling task {task_id}: {e}")
                not_found.append(task_id)

        # Post to Discord
        if cancelled:
            await self.discord.post_alert(
                title="Tasks Cancelled",
                message=f"{len(cancelled)} task(s) cancelled by {user_name}: {', '.join(cancelled)}",
                alert_type="warning"
            )

        # Build response
        if cancelled and not_found:
            return f"✅ Cancelled: {', '.join(cancelled)}\n❌ Not found: {', '.join(not_found)}", None
        elif cancelled:
            return f"✅ Cancelled {len(cancelled)} task(s): {', '.join(cancelled)}", None
        else:
            return f"❌ Could not find: {', '.join(not_found)}", None

    async def _handle_archive_tasks(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle request to archive completed tasks."""
        try:
            count = await self.sheets.archive_completed_tasks(days_old=0)  # Archive all completed

            if count > 0:
                await self.discord.post_alert(
                    title="Tasks Archived",
                    message=f"{count} completed task(s) archived by {user_name}",
                    alert_type="info"
                )
                return f"✅ Archived {count} completed task(s).", None
            else:
                return "No completed tasks to archive.", None

        except Exception as e:
            logger.error(f"Error archiving tasks: {e}")
            return "❌ Error archiving tasks. Please try again.", None

    async def _handle_generate_spec(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle request to generate a detailed spec sheet for a task."""
        from ..ai.prompts import PromptTemplates
        import json

        task_id = data.get("task_id")

        # If no task ID provided, ask for one
        if not task_id:
            return "Please specify a task ID. Usage: `/spec TASK-001` or \"generate spec for TASK-001\"", None

        try:
            # Find the task in Google Sheets
            task_data = await self.sheets.get_task(task_id)

            if not task_data:
                return f"❌ Task `{task_id}` not found. Check the ID and try again.", None

            # Extract task info
            title = task_data.get("Title", task_data.get("title", "Unknown"))
            description = task_data.get("Description", task_data.get("description", ""))
            assignee = task_data.get("Assignee", task_data.get("assignee", ""))
            priority = task_data.get("Priority", task_data.get("priority", "medium"))
            deadline = task_data.get("Deadline", task_data.get("deadline", ""))
            task_type = task_data.get("Type", task_data.get("type", "task"))
            notes = task_data.get("Notes", task_data.get("notes", ""))

            # Store task info for the session
            task_info = {
                "task_id": task_id,
                "title": title,
                "description": description,
                "assignee": assignee,
                "priority": priority,
                "deadline": deadline,
                "task_type": task_type,
                "notes": notes,
            }

            # Step 1: Analyze if we have enough info for a good spec
            analysis_prompt = PromptTemplates.analyze_spec_readiness_prompt(
                task_id=task_id,
                title=title,
                description=description,
                assignee=assignee,
                priority=priority,
                deadline=deadline,
                task_type=task_type,
                existing_notes=notes if notes else None
            )

            response = await self.ai.chat(
                messages=[
                    {"role": "system", "content": "You analyze task information to determine if there's enough detail for a comprehensive spec. Respond only with JSON."},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.2
            )

            try:
                content = response.choices[0].message.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                analysis = json.loads(content.strip())
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse analysis JSON: {e}")
                # Proceed anyway with generation
                analysis = {"has_enough_info": True}

            # If we have enough info, generate the spec directly
            if analysis.get("has_enough_info", False) and analysis.get("confidence", 0) >= 0.7:
                return await self._generate_and_post_spec(task_info, user_name)

            # Not enough info - start a conversation
            questions = analysis.get("questions_to_ask", [])
            if not questions:
                # No questions but not confident - generate anyway with assumptions
                return await self._generate_and_post_spec(task_info, user_name)

            # Start spec session
            self._spec_sessions[user_id] = {
                "task_info": task_info,
                "questions": questions,
                "current_question": 0,
                "answers": [],
                "additional_context": "",
                "awaiting_answers": True,
                "conversation_history": []
            }

            # Format questions naturally
            response_lines = [f"📋 **{title}** ({task_id})", ""]

            # If there's reasoning, show it briefly
            reasoning = analysis.get("reasoning", "")
            if reasoning:
                response_lines.append(f"_{reasoning}_")
                response_lines.append("")

            # Show questions conversationally
            if len(questions) == 1:
                q = questions[0]
                question_text = q.get("question", q) if isinstance(q, dict) else q
                response_lines.append(f"Quick question: {question_text}")

                options = q.get("options", []) if isinstance(q, dict) else []
                if options:
                    response_lines.append("")
                    for j, opt in enumerate(options, 1):
                        response_lines.append(f"  {j}) {opt}")
            else:
                response_lines.append("A couple things I need to know:")
                response_lines.append("")
                for i, q in enumerate(questions[:2], 1):
                    question_text = q.get("question", q) if isinstance(q, dict) else q
                    response_lines.append(f"{i}. {question_text}")

                    options = q.get("options", []) if isinstance(q, dict) else []
                    if options:
                        opts_str = " / ".join(options)
                        response_lines.append(f"   ({opts_str})")
                    response_lines.append("")

            response_lines.append("")
            response_lines.append("_Or say 'skip' to generate with reasonable assumptions_")

            return "\n".join(response_lines), None

        except Exception as e:
            logger.error(f"Error starting spec generation for {task_id}: {e}")
            return f"❌ Error: {str(e)}", None

    async def _handle_spec_answer(
        self, user_id: str, message: str, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle user's answers to spec clarifying questions."""
        import json
        from ..ai.prompts import PromptTemplates

        session = self._spec_sessions.get(user_id)
        if not session:
            return "No active spec session. Use `/spec TASK-ID` to start.", None

        # Check for skip/cancel
        msg_lower = message.lower().strip()
        if msg_lower in ["skip", "/skip", "generate", "just generate", "done"]:
            # Generate with what we have
            del self._spec_sessions[user_id]
            return await self._generate_and_post_spec(session["task_info"], user_name, session.get("additional_context"))

        if msg_lower in ["cancel", "/cancel", "nevermind", "stop"]:
            del self._spec_sessions[user_id]
            return "Spec generation cancelled.", None

        # Parse answers - support formats like "1. answer1  2. answer2" or just a single answer
        questions = session.get("questions", [])

        # Add the user's message to additional context
        session["additional_context"] = session.get("additional_context", "") + f"\nUser said: {message}"
        session["conversation_history"].append({"role": "user", "content": message})

        # Process the answer using AI
        try:
            task_info = session["task_info"]
            process_prompt = PromptTemplates.process_spec_answer_prompt(
                question=str(questions),
                answer=message,
                current_info=task_info
            )

            response = await self.ai.chat(
                messages=[
                    {"role": "system", "content": "Extract useful information from user answers for spec generation. Respond with JSON."},
                    {"role": "user", "content": process_prompt}
                ],
                temperature=0.2
            )

            content = response.choices[0].message.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            try:
                processed = json.loads(content.strip())

                # Update task info with extracted details
                if processed.get("should_add_to_description"):
                    task_info["description"] = task_info.get("description", "") + "\n" + processed["should_add_to_description"]

                if processed.get("acceptance_criteria"):
                    task_info["extra_criteria"] = task_info.get("extra_criteria", []) + processed["acceptance_criteria"]

                if processed.get("technical_notes"):
                    task_info["technical_notes"] = processed["technical_notes"]

                # Check if we need followup
                if processed.get("needs_followup") and processed.get("followup_question"):
                    session["questions"] = [{"question": processed["followup_question"]}]
                    return f"Got it! One more thing: {processed['followup_question']}", None

            except json.JSONDecodeError:
                pass  # Continue anyway

        except Exception as e:
            logger.error(f"Error processing spec answer: {e}")

        # We have the answers - generate the spec
        del self._spec_sessions[user_id]
        return await self._generate_and_post_spec(
            session["task_info"],
            user_name,
            session.get("additional_context")
        )

    async def _generate_and_post_spec(
        self,
        task_info: Dict[str, Any],
        user_name: str,
        additional_context: str = None
    ) -> Tuple[str, Optional[Dict]]:
        """Generate and post the spec sheet to Discord."""
        from ..ai.prompts import PromptTemplates
        import json

        task_id = task_info["task_id"]
        title = task_info["title"]
        description = task_info["description"]
        assignee = task_info["assignee"]
        priority = task_info["priority"]
        deadline = task_info["deadline"]
        task_type = task_info["task_type"]
        notes = task_info.get("notes", "")

        # Combine notes with additional context
        full_context = notes
        if additional_context:
            full_context = f"{notes}\n\nAdditional context from conversation:\n{additional_context}"

        # Generate detailed spec using AI
        prompt = PromptTemplates.generate_detailed_spec_prompt(
            task_id=task_id,
            title=title,
            description=description,
            assignee=assignee,
            priority=priority,
            deadline=deadline,
            task_type=task_type,
            existing_notes=full_context if full_context else None,
            team_context=str(task_info.get("extra_criteria", []))
        )

        try:
            response = await self.ai.chat(
                messages=[
                    {"role": "system", "content": "You create detailed, practical task specifications. Respond only with JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )

            content = response.choices[0].message.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            spec_data = json.loads(content.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse spec JSON: {e}")
            return "❌ Failed to generate spec. AI response format error.", None
        except Exception as e:
            logger.error(f"Error generating spec: {e}")
            return f"❌ Error generating spec: {str(e)}", None

        # Merge any extra criteria from conversation
        all_criteria = spec_data.get("acceptance_criteria", [])
        if task_info.get("extra_criteria"):
            all_criteria.extend(task_info["extra_criteria"])

        # Post spec to Discord
        discord_msg_id = await self.discord.post_spec_sheet(
            task_id=task_id,
            title=title,
            assignee=assignee or "Unassigned",
            priority=priority,
            deadline=deadline if deadline else None,
            description=spec_data.get("expanded_description", description),
            acceptance_criteria=all_criteria,
            technical_details=spec_data.get("technical_details") or task_info.get("technical_notes"),
            dependencies=spec_data.get("dependencies"),
            notes=spec_data.get("additional_notes"),
            estimated_effort=spec_data.get("estimated_effort")
        )

        if discord_msg_id:
            response_lines = [
                f"✅ **Spec sheet posted for {task_id}**",
                "",
                f"📋 **{title}**",
                f"👤 {assignee or 'Unassigned'} | ⏱️ {spec_data.get('estimated_effort', 'Unknown')}",
                "",
                "**Acceptance Criteria:**"
            ]
            for i, criterion in enumerate(all_criteria[:3], 1):
                response_lines.append(f"  {i}. {criterion}")
            if len(all_criteria) > 3:
                response_lines.append(f"  ... and {len(all_criteria) - 3} more")

            response_lines.append("")
            response_lines.append("📤 Posted to #specs channel")

            return "\n".join(response_lines), None
        else:
            return "⚠️ Spec generated but failed to post to Discord. Check webhook configuration.", None

    async def _handle_templates(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle template list request."""
        from ..memory.preferences import DEFAULT_TEMPLATES

        lines = ["📝 **Task Templates**", ""]
        lines.append("Say these keywords and I'll auto-apply defaults:")
        lines.append("")

        for template in DEFAULT_TEMPLATES:
            name = template["name"]
            defaults = template["defaults"]
            priority = defaults.get("priority", "medium")
            priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")

            keywords_str = ", ".join(template["keywords"][:2])
            lines.append(f"{priority_emoji} **{name}**: {keywords_str}")

        lines.append("")
        lines.append("Example: \"bug: login crashes\" → High priority bug")

        return "\n".join(lines), None

    async def _handle_email_recap(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle email recap request."""
        try:
            gmail = get_gmail_integration()
            summarizer = get_email_summarizer()

            # Check if Gmail is available
            if not await gmail.is_available():
                return "Email integration not configured. Contact admin to set up Gmail OAuth.", None

            # Get recent emails (last 12 hours)
            emails = await gmail.get_emails_since(hours=12, max_results=20)

            if not emails:
                return "No new emails in the last 12 hours.", None

            # Count unread
            unread_count = sum(1 for e in emails if e.is_unread)

            # Convert to dict format for summarizer
            email_dicts = [
                {
                    "subject": e.subject,
                    "from": e.sender,
                    "snippet": e.snippet,
                    "body": e.body_text[:500] if e.body_text else e.snippet,
                    "date": e.date.isoformat() if e.date else "",
                    "is_important": e.is_important
                }
                for e in emails
            ]

            # Get user preferences for context
            user_prefs = await self.prefs.get_preferences(user_id)

            # Summarize
            result = await summarizer.summarize_emails(email_dicts, "on-demand", user_prefs.to_dict())

            # Use the proper digest formatter
            formatted = await summarizer.generate_digest_message(
                summary_result=result,
                period="now",
                total_emails=len(emails),
                unread_count=unread_count
            )

            return formatted, None

        except Exception as e:
            logger.error(f"Email recap error: {e}", exc_info=True)
            return f"Sorry, couldn't fetch emails: {str(e)[:100]}", None

    async def _handle_delay(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle delay request."""
        # Would parse the task and new deadline from message
        return "Which task do you want to delay, and to when?", None

    async def _handle_add_team(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle team member addition."""
        success, response = await self.learning.process_teach_command(user_id, message)
        return response, None

    async def _handle_teach(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle teaching preferences."""
        success, response = await self.learning.process_teach_command(user_id, message)
        return response, None

    async def _handle_cancel(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle cancellation."""
        # Clear any active sessions
        if user_id in self._validation_sessions:
            del self._validation_sessions[user_id]

        await self.context.clear_active_conversation(user_id)

        return "Cancelled. What else can I help with?", None

    async def _handle_skip(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle skip request."""
        # Check what stage we're in
        conv = await self.context.get_active_conversation(user_id)
        if conv and conv.stage == ConversationStage.AWAITING_ANSWER:
            # Skip questions, use defaults
            prefs = await self.prefs.get_preferences(user_id)
            self.clarifier.apply_defaults(conv, prefs.to_dict())
            return await self._create_task_directly(conv, prefs.to_dict())

        return "Nothing to skip right now.", None

    async def _handle_unknown(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle unknown intent - try to help."""

        # Check for pending review response
        if context.get("awaiting_review_response") or user_id in self._pending_reviews:
            return await self._handle_review_response(user_id, message, user_name)

        # Check if there's an active conversation that needs a response
        conv = await self.context.get_active_conversation(user_id)
        if conv:
            if conv.stage == ConversationStage.AWAITING_ANSWER:
                # They're answering a question
                prefs = await self.prefs.get_preferences(user_id)
                await self.clarifier.process_user_answers(conv, message)
                return await self._create_task_directly(conv, prefs.to_dict())

            elif conv.stage == ConversationStage.PREVIEW:
                # They're responding to preview
                if any(w in message.lower() for w in ["yes", "ok", "good", "confirm", "create"]):
                    return await self._finalize_task(conv, user_id)
                elif any(w in message.lower() for w in ["no", "change", "edit"]):
                    return "What would you like to change?", None

        return "I'm not sure what you mean. Try:\n• Describe a task to create\n• Say \"I finished [task]\" with proof\n• Ask \"what's pending?\"", None

    async def _handle_review_response(
        self, user_id: str, message: str, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle user response to auto-review feedback."""
        pending = self._pending_reviews.get(user_id)
        if not pending:
            return "No pending review to respond to.", None

        session = pending["session"]
        feedback = pending["feedback"]
        submission_id = pending["submission_id"]
        message_lower = message.lower().strip()

        # Option 1: Apply suggestions
        if any(w in message_lower for w in ["yes", "apply", "accept", "sure", "ok"]):
            # Apply AI suggestions
            if feedback.improved_notes:
                session["notes"] = feedback.improved_notes
            if feedback.improved_description:
                session["message"] = feedback.improved_description

            # Clean up
            del self._pending_reviews[user_id]
            session["stage"] = "awaiting_confirm"

            # Post to Discord
            await self.discord.post_submission_approved(
                user_name=user_name,
                task_description=session.get("message", ""),
                submission_id=submission_id,
                applied_suggestions=True
            )

            return f"""✨ **Suggestions applied!**

Updated notes: "{session.get('notes', '')[:100]}..."

Ready to send to boss? (yes/no)""", None

        # Option 2: Send anyway despite issues
        elif any(w in message_lower for w in ["no", "send anyway", "anyway", "as is", "skip"]):
            # Clean up
            del self._pending_reviews[user_id]
            session["stage"] = "awaiting_confirm"

            return f"""📤 **Got it.** Keeping your original submission.

Ready to send to boss? (yes/no)""", None

        # Option 3: Edit manually
        elif any(w in message_lower for w in ["edit", "manual", "fix", "change", "let me"]):
            session["stage"] = "awaiting_manual_edit"

            return """✏️ **No problem!** Type your updated notes below.

Just send your new text and I'll use that instead.""", None

        # Option 4: They're providing the manual edit
        elif session.get("stage") == "awaiting_manual_edit":
            # They're typing their new notes
            session["notes"] = message
            session["stage"] = "awaiting_confirm"

            # Clean up review session
            if user_id in self._pending_reviews:
                del self._pending_reviews[user_id]

            # Re-run review with new notes
            new_feedback = await self.reviewer.review_submission(
                task_description=session.get("message", ""),
                proof_items=session.get("proof_items", []),
                notes=message,
                user_name=user_name
            )

            if new_feedback.passes_threshold:
                return f"""✅ **Much better!** (Score: {new_feedback.score}/100)

New notes: "{message[:100]}..."

Ready to send to boss? (yes/no)""", None
            else:
                # Still not great but let them proceed
                return f"""📝 **Updated!** (Score: {new_feedback.score}/100)

Some issues remain, but you can send if you want.

Ready to send to boss? (yes/no)""", None

        else:
            return """I didn't catch that. Reply with:
• **"yes"** - Apply my suggestions
• **"no"** - Send as-is anyway
• **"edit"** - Type new notes yourself""", None

    async def _finalize_task(
        self, conv: ConversationState, user_id: str
    ) -> Tuple[str, Optional[Dict]]:
        """Finalize and create the task."""
        spec = conv.generated_spec
        if not spec:
            return "Something went wrong. Try describing the task again.", None

        # Get user preferences for team member lookup
        user_prefs = await self.prefs.get_preferences(user_id)
        assignee_name = spec.get("assignee")
        assignee_discord_id = None
        assignee_email = None
        assignee_telegram_id = None

        # Look up team member info if assignee specified
        if assignee_name:
            team_member = self.prefs.find_team_member(user_prefs, assignee_name)
            if team_member:
                assignee_name = team_member.name  # Use canonical name
                assignee_discord_id = team_member.discord_username or team_member.discord_id
                assignee_email = team_member.email
                assignee_telegram_id = team_member.telegram_id

        task = Task(
            title=spec.get("title", "Untitled"),
            description=spec.get("description", conv.original_message),
            assignee=assignee_name,
            assignee_discord_id=assignee_discord_id,
            assignee_email=assignee_email,
            assignee_telegram_id=assignee_telegram_id,
            priority=TaskPriority(spec.get("priority", "medium")),
            task_type=spec.get("task_type", "task"),
            estimated_effort=spec.get("estimated_effort"),
            created_by=user_id,
            original_message=conv.original_message,
        )

        # Parse deadline
        if spec.get("deadline"):
            try:
                task.deadline = datetime.fromisoformat(spec["deadline"].replace('Z', '+00:00'))
            except:
                pass

        # Add criteria
        for c in spec.get("acceptance_criteria", []):
            task.acceptance_criteria.append(AcceptanceCriteria(description=c))

        # Post to integrations and capture Discord message ID
        discord_message_id = await self.discord.post_task(task)

        # Convert task to dict for sheets
        task_dict = {
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'assignee': task.assignee or '',
            'priority': task.priority.value,
            'status': task.status.value,
            'task_type': task.task_type,
            'deadline': task.deadline.strftime('%Y-%m-%d %H:%M') if task.deadline else '',
            'created_at': task.created_at.strftime('%Y-%m-%d %H:%M'),
            'updated_at': task.updated_at.strftime('%Y-%m-%d %H:%M'),
            'effort': task.estimated_effort or '',
            'tags': ', '.join(task.tags) if task.tags else '',
            'created_by': task.created_by or 'Boss',
            'discord_message_id': discord_message_id or '',
        }
        await self.sheets.add_task(task_dict)

        # Save to PostgreSQL with discord_message_id
        subtask_ids = []
        try:
            from ..database.repositories import get_task_repository
            task_repo = get_task_repository()
            db_task_data = {
                'task_id': task.id,
                'title': task.title,
                'description': task.description,
                'assignee': task.assignee,
                'priority': task.priority.value,
                'status': task.status.value,
                'task_type': task.task_type,
                'deadline': task.deadline,
                'discord_message_id': discord_message_id,
            }
            await task_repo.create(db_task_data)
            logger.info(f"Task {task.id} saved to PostgreSQL")

            # Create subtasks if present in spec
            subtasks_data = spec.get("subtasks", [])
            if subtasks_data:
                for st in subtasks_data:
                    if isinstance(st, dict):
                        subtask_title = st.get("title", "Untitled subtask")
                        subtask_desc = st.get("description", "")
                    else:
                        subtask_title = str(st)
                        subtask_desc = ""

                    try:
                        subtask = await task_repo.add_subtask(
                            task.id,
                            subtask_title,
                            subtask_desc
                        )
                        if subtask:
                            subtask_ids.append(subtask.title)
                            logger.info(f"Created subtask '{subtask_title}' for {task.id}")
                    except Exception as se:
                        logger.warning(f"Failed to create subtask '{subtask_title}': {se}")

                if subtask_ids:
                    logger.info(f"Created {len(subtask_ids)} subtasks for {task.id}")

        except Exception as e:
            logger.warning(f"Failed to save task to PostgreSQL: {e}")

        if task.deadline:
            await self.calendar.create_task_event(task)

        conv.stage = ConversationStage.COMPLETED
        conv.task_id = task.id
        await self.context.save_conversation(conv)

        # Clear conversation after successful creation
        await self.context.clear_active_conversation(user_id)

        assignee_text = f" for {task.assignee}" if task.assignee else ""
        response = f"✅ Created{assignee_text}!\n\n**{task.id}**: {task.title}"

        # Add subtask info to response
        if subtask_ids:
            response += f"\n📝 + {len(subtask_ids)} subtasks"

        # Prepare notification for assignee if they have Telegram ID
        action = None
        if task.assignee_telegram_id:
            deadline_text = f"\n📅 Deadline: {task.deadline.strftime('%b %d, %I:%M %p')}" if task.deadline else ""
            assignee_notification = f"""📋 **New Task Assigned**

**{task.title}**

{task.description[:200]}{'...' if len(task.description) > 200 else ''}
{deadline_text}
Priority: {task.priority.value.upper()}

_Task ID: {task.id}_

When done, tell me "I finished {task.id}" and show me proof!"""

            action = {
                "notify_user": task.assignee_telegram_id,
                "notification": assignee_notification
            }
            response += f"\n📨 Notifying {task.assignee} on Telegram"

        return response, action

    # ==================== BATCH TASK HANDLING ====================

    def _split_multiple_tasks(self, message: str) -> List[str]:
        """
        Detect and split multiple tasks in a single message.

        Handles patterns like:
        - "Mayank fix login, Sarah update docs, John test API"
        - "1. Task one 2. Task two 3. Task three"
        - "Task one, also task two, and task three"
        """
        import re

        message = message.strip()

        # Pattern 1: Numbered list (1. 2. 3. or 1) 2) 3))
        numbered_pattern = r'(?:^|\s)(\d+[\.\)]\s*)'
        if re.search(numbered_pattern, message):
            parts = re.split(r'\s*\d+[\.\)]\s*', message)
            tasks = [p.strip() for p in parts if p.strip() and len(p.strip()) > 10]
            if len(tasks) >= 2:
                return tasks

        # Pattern 2: Explicit separators
        separators = [
            r'\.\s+also\s+',
            r',\s+also\s+',
            r'\s+and\s+also\s+',
            r'\.\s+another\s+(?:task|one)?\s*(?:is\s+)?',
            r',\s+another\s+(?:task|one)?\s*(?:is\s+)?',
            r'\.\s+plus\s+',
            r',\s+plus\s+',
            r'\s+then\s+',
        ]

        for sep in separators:
            if re.search(sep, message, re.IGNORECASE):
                parts = re.split(sep, message, flags=re.IGNORECASE)
                tasks = [p.strip() for p in parts if p.strip() and len(p.strip()) > 10]
                if len(tasks) >= 2:
                    return tasks

        # Pattern 3: Multiple names with actions - "Name1 action1, Name2 action2"
        # Look for pattern: CapitalName + verb/action, repeated
        name_action_pattern = r'([A-Z][a-z]+)\s+(?:needs?\s+to\s+|should\s+|must\s+|has\s+to\s+|will\s+)?(\w+)'
        matches = re.findall(name_action_pattern, message)

        if len(matches) >= 2:
            # Try to split by comma or "and" between name-action pairs
            # Split by comma first
            comma_parts = re.split(r',\s*', message)
            if len(comma_parts) >= 2:
                tasks = []
                for part in comma_parts:
                    part = part.strip()
                    # Remove leading "and"
                    part = re.sub(r'^and\s+', '', part, flags=re.IGNORECASE)
                    if part and len(part) > 5:
                        tasks.append(part)
                if len(tasks) >= 2:
                    return tasks

            # Try splitting by " and " if commas didn't work
            and_parts = re.split(r'\s+and\s+', message, flags=re.IGNORECASE)
            if len(and_parts) >= 2:
                tasks = [p.strip() for p in and_parts if p.strip() and len(p.strip()) > 5]
                if len(tasks) >= 2:
                    return tasks

        # Pattern 4: Semicolon separated
        if ';' in message:
            parts = message.split(';')
            tasks = [p.strip() for p in parts if p.strip() and len(p.strip()) > 10]
            if len(tasks) >= 2:
                return tasks

        # No multiple tasks detected
        return [message]

    async def _handle_batch_tasks(
        self, user_id: str, task_messages: List[str], prefs, user_name: str
    ) -> Tuple[str, None]:
        """Handle multiple tasks with numbered questions."""
        batch = {
            "tasks": [],
            "questions": [],
            "awaiting_answers": False,
            "created_at": datetime.now().isoformat()
        }

        all_questions = []
        tasks_needing_questions = []
        tasks_ready = []

        for idx, task_msg in enumerate(task_messages, 1):
            # Create conversation for each task
            conversation = await self.context.create_conversation(
                user_id=f"{user_id}_batch_{idx}",
                chat_id=user_id,
                original_message=task_msg
            )

            # Analyze
            should_ask, analysis = await self.clarifier.analyze_and_decide(
                conversation=conversation,
                preferences=prefs.to_dict(),
                team_info=prefs.get_team_info()
            )

            task_entry = {
                "index": idx,
                "message": task_msg,
                "conversation": conversation,
                "analysis": analysis,
                "needs_questions": should_ask
            }

            if should_ask and analysis.get("suggested_questions"):
                tasks_needing_questions.append(task_entry)
                # Add numbered questions
                for q in analysis.get("suggested_questions", [])[:2]:  # Max 2 questions per task
                    all_questions.append({
                        "task_idx": idx,
                        "question": q.get("question", q.get("text", "")),
                        "field": q.get("field", ""),
                        "options": q.get("options", [])
                    })
            else:
                tasks_ready.append(task_entry)

            batch["tasks"].append(task_entry)

        batch["questions"] = all_questions

        # If no questions needed, show clean previews
        if not all_questions:
            responses = []
            for task_entry in batch["tasks"]:
                preview, spec = await self.clarifier.generate_spec_preview(
                    conversation=task_entry["conversation"],
                    preferences=prefs.to_dict()
                )
                task_entry["conversation"].generated_spec = spec
                task_entry["conversation"].stage = ConversationStage.PREVIEW
                task_entry["spec"] = spec

                # Create detailed summary with subtasks
                title = spec.get("title", "Untitled")
                assignee = spec.get("assignee") or "Unassigned"
                priority = spec.get("priority", "medium")
                p_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                deadline = spec.get("deadline", "")
                deadline_str = f" | Due: {deadline[:10]}" if deadline else ""

                # Build response with subtasks if present
                task_lines = [f"**{task_entry['index']}.** {p_emoji} **{title}**", f"   → {assignee}{deadline_str}"]

                # Show subtasks
                subtasks = spec.get("subtasks", [])
                if subtasks:
                    task_lines.append(f"   📝 **Subtasks ({len(subtasks)}):**")
                    for i, st in enumerate(subtasks[:5], 1):  # Show max 5 subtasks
                        st_title = st.get("title", str(st)) if isinstance(st, dict) else str(st)
                        task_lines.append(f"      {i}. {st_title[:60]}{'...' if len(st_title) > 60 else ''}")
                    if len(subtasks) > 5:
                        task_lines.append(f"      ... and {len(subtasks) - 5} more")

                # Show notes if present
                notes = spec.get("notes")
                if notes and notes != "null" and str(notes).strip():
                    task_lines.append(f"   📌 Note: {str(notes)[:80]}{'...' if len(str(notes)) > 80 else ''}")

                responses.append("\n".join(task_lines))

            batch["awaiting_confirm"] = True
            self._batch_tasks[user_id] = batch

            num = len(batch['tasks'])
            return f"""📋 **{num} Tasks Ready**

{chr(10).join(responses)}

**yes** = create all | **no** = cancel all
Or per task: **1 yes 2 no** / **1 yes 2 edit**""", None

        # Questions needed - format them with numbers
        batch["awaiting_answers"] = True
        self._batch_tasks[user_id] = batch

        lines = [f"📋 **{len(task_messages)} Tasks** - Quick questions:\n"]

        for q in all_questions:
            q_num = len([x for x in all_questions if all_questions.index(x) < all_questions.index(q)]) + 1
            lines.append(f"**{q_num}.** [Task {q['task_idx']}] {q['question']}")
            if q['options']:
                opts = " / ".join(q['options'][:3])
                lines.append(f"   _Options: {opts}_")
            lines.append("")

        lines.append("**Answer format:** `1yes 2tomorrow 3skip`")
        lines.append("Or just type answers in order, one per line.")

        return "\n".join(lines), None

    async def _handle_batch_answers(
        self, user_id: str, message: str, user_name: str
    ) -> Tuple[str, None]:
        """Handle numbered answers for batch tasks."""
        import re

        batch = self._batch_tasks.get(user_id)
        if not batch:
            return "No pending batch tasks.", None

        questions = batch.get("questions", [])
        message_lower = message.lower().strip()

        # Check for cancel
        if message_lower in ["cancel", "stop", "nevermind"]:
            del self._batch_tasks[user_id]
            return "Batch cancelled.", None

        # Check for skip all
        if message_lower in ["skip", "skip all", "defaults"]:
            # Use defaults for all
            for task_entry in batch["tasks"]:
                prefs = await self.prefs.get_preferences(user_id)
                self.clarifier.apply_defaults(task_entry["conversation"], prefs.to_dict())
            batch["awaiting_answers"] = False
            batch["awaiting_confirm"] = True
            return await self._finalize_batch_preview(user_id, batch)

        # Parse answers - support formats:
        # "1yes 2tomorrow 3skip" or "1. yes 2. tomorrow" or line by line
        answers = {}

        # Pattern: number followed by answer (1yes, 1. yes, 1: yes)
        pattern = r'(\d+)[\.\:\s]*([^\d]+?)(?=\d+[\.\:\s]|$)'
        matches = re.findall(pattern, message_lower + " ")

        if matches:
            for num_str, answer in matches:
                num = int(num_str)
                answers[num] = answer.strip()
        else:
            # Try line by line
            lines = message.strip().split('\n')
            for i, line in enumerate(lines, 1):
                if line.strip():
                    answers[i] = line.strip()

        # Apply answers to questions
        for q_idx, q in enumerate(questions, 1):
            if q_idx in answers:
                answer = answers[q_idx]
                task_idx = q["task_idx"]

                # Find the task
                for task_entry in batch["tasks"]:
                    if task_entry["index"] == task_idx:
                        # Apply answer
                        field = q["field"]
                        if answer.lower() in ["skip", "default", "idk"]:
                            continue

                        # Map common answers
                        if field == "priority":
                            if "high" in answer or "urgent" in answer:
                                task_entry["conversation"].extracted_info["priority"] = "high"
                            elif "low" in answer:
                                task_entry["conversation"].extracted_info["priority"] = "low"
                            else:
                                task_entry["conversation"].extracted_info["priority"] = "medium"
                        elif field == "deadline":
                            task_entry["conversation"].extracted_info["deadline_text"] = answer
                        elif field == "assignee":
                            task_entry["conversation"].extracted_info["assignee"] = answer
                        else:
                            task_entry["conversation"].extracted_info[field] = answer

        # Move to confirmation
        batch["awaiting_answers"] = False
        batch["awaiting_confirm"] = True

        return await self._finalize_batch_preview(user_id, batch)

    async def _finalize_batch_preview(
        self, user_id: str, batch: Dict
    ) -> Tuple[str, None]:
        """Generate preview for all batch tasks."""
        prefs = await self.prefs.get_preferences(user_id)
        previews = []

        for task_entry in batch["tasks"]:
            preview, spec = await self.clarifier.generate_spec_preview(
                conversation=task_entry["conversation"],
                preferences=prefs.to_dict()
            )
            task_entry["conversation"].generated_spec = spec
            task_entry["spec"] = spec

            title = spec.get("title", "Untitled")[:50]
            assignee = spec.get("assignee", "Unassigned")
            priority = spec.get("priority", "medium")
            priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")

            previews.append(f"{task_entry['index']}. {priority_emoji} **{title}** → {assignee}")

        self._batch_tasks[user_id] = batch

        num_tasks = len(batch['tasks'])
        return f"""📋 **{num_tasks} Tasks Ready:**

{chr(10).join(previews)}

**yes** = create all | **no** = cancel all
Or respond per task: **1 yes 2 no** / **1 yes 2 edit**""", None

    async def _handle_batch_confirm(
        self, user_id: str, message: str, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle confirmation to create batch tasks - supports numbered responses."""
        import re

        batch = self._batch_tasks.get(user_id)
        if not batch:
            return "No pending batch tasks.", None

        message_lower = message.lower().strip()
        num_tasks = len(batch["tasks"])

        # Check for cancel all
        if message_lower in ["cancel", "cancel all", "stop", "abort", "nevermind"]:
            del self._batch_tasks[user_id]
            return "Batch cancelled. No tasks created.", None

        # Check for numbered responses: "1 yes 2 no" or "1yes 2edit" etc.
        numbered_pattern = r'(\d+)\s*(yes|no|cancel|edit|skip|ok|confirm)'
        numbered_matches = re.findall(numbered_pattern, message_lower)

        if numbered_matches:
            # Process numbered responses
            created_tasks = []
            cancelled = []
            needs_edit = []
            errors = []

            # Build action map from matches
            actions = {}
            for num_str, action in numbered_matches:
                idx = int(num_str)
                if 1 <= idx <= num_tasks:
                    actions[idx] = action

            for task_entry in batch["tasks"]:
                idx = task_entry["index"]
                action = actions.get(idx, None)

                if action in ["yes", "ok", "confirm"]:
                    # Create this task
                    try:
                        conv = task_entry["conversation"]
                        if conv.generated_spec:
                            response, _ = await self._finalize_task(conv, user_id)
                            match = re.search(r'(TASK-[\w-]+)', response)
                            if match:
                                created_tasks.append(match.group(1))
                            else:
                                errors.append(f"Task {idx}: {response[:50]}")
                    except Exception as e:
                        errors.append(f"Task {idx}: Error - {str(e)[:30]}")

                elif action in ["no", "cancel", "skip"]:
                    cancelled.append(idx)

                elif action == "edit":
                    needs_edit.append(task_entry)

            # Handle tasks needing edit - keep them in session
            if needs_edit and not created_tasks and not cancelled:
                # Only edits requested - ask what to change
                edit_nums = [t["index"] for t in needs_edit]
                return f"What would you like to change for task {', '.join(map(str, edit_nums))}?", None

            # Clean up or keep for remaining edits
            if needs_edit:
                # Keep only tasks that need editing
                batch["tasks"] = needs_edit
                for i, t in enumerate(batch["tasks"], 1):
                    t["index"] = i  # Renumber
            else:
                del self._batch_tasks[user_id]

            # Build response
            response_parts = []
            if created_tasks:
                response_parts.append(f"✅ Created: {', '.join(created_tasks)}")
            if cancelled:
                response_parts.append(f"❌ Cancelled: Task {', '.join(map(str, cancelled))}")
            if needs_edit:
                response_parts.append(f"✏️ Editing: Task {', '.join(map(str, [t['index'] for t in needs_edit]))}")
                response_parts.append("\nWhat would you like to change?")
            if errors:
                response_parts.append(f"⚠️ Errors: {', '.join(errors)}")

            return "\n".join(response_parts), None

        # Check for simple "yes" = confirm all
        if any(w in message_lower for w in ["yes", "yes all", "ok", "confirm", "create all", "go", "do it"]):
            created_tasks = []
            errors = []

            for task_entry in batch["tasks"]:
                try:
                    conv = task_entry["conversation"]
                    if not conv.generated_spec:
                        continue

                    response, action = await self._finalize_task(conv, user_id)

                    if "Created" in response or "✅" in response:
                        match = re.search(r'(TASK-[\w-]+)', response)
                        if match:
                            created_tasks.append(match.group(1))
                    else:
                        errors.append(f"Task {task_entry['index']}: {response[:50]}")

                except Exception as e:
                    logger.error(f"Error creating batch task {task_entry['index']}: {e}")
                    errors.append(f"Task {task_entry['index']}: Error")

            del self._batch_tasks[user_id]

            if created_tasks and not errors:
                return f"✅ **Created {len(created_tasks)} tasks:**\n• " + "\n• ".join(created_tasks), None
            elif created_tasks and errors:
                return f"✅ Created: {', '.join(created_tasks)}\n⚠️ Errors: {', '.join(errors)}", None
            else:
                return "❌ Failed to create tasks. Please try again.", None

        # Check for simple "no" = cancel all
        if message_lower == "no":
            del self._batch_tasks[user_id]
            return "Batch cancelled. No tasks created.", None

        return f"Reply **yes** to create all {num_tasks} tasks, or use numbers: **1 yes 2 no** / **1 edit**", None


# Singleton
unified_handler = UnifiedHandler()

def get_unified_handler() -> UnifiedHandler:
    return unified_handler
