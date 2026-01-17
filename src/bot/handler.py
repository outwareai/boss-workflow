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
        if " and another " in second_part:
            task_parts = second_part.split(" and another ")
        elif " another one " in second_part:
            idx = second_part.find(" another one ")
            task_parts = [second_part[:idx], second_part[idx + 13:]]

        for task_desc in task_parts:
            task_desc = task_desc.strip()
            if not task_desc:
                continue

            # Reconstruct full message for task creation
            create_response, _ = await self._handle_create_task(
                user_id, task_desc, {"message": task_desc}, context, user_name
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
        # Boss doesn't submit proof - they review it
        if context.get("is_boss"):
            return """As the boss, you review task completions rather than submit them.

To create a new task, just describe it:
• "Mayank needs to fix the login bug"
• "Assign Sarah to update the docs"

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
        - "1. Task one 2. Task two 3. Task three"
        - "Task one, also task two, and task three"
        - "Task one. Another task is two. And three"
        """
        import re

        message = message.strip()

        # Pattern 1: Numbered list (1. 2. 3. or 1) 2) 3))
        numbered_pattern = r'(?:^|\s)(\d+[\.\)]\s*)'
        if re.search(numbered_pattern, message):
            # Split by numbers
            parts = re.split(r'\s*\d+[\.\)]\s*', message)
            tasks = [p.strip() for p in parts if p.strip() and len(p.strip()) > 10]
            if len(tasks) >= 2:
                return tasks

        # Pattern 2: "Also" / "And also" / "Another" separators
        separators = [
            r'\.\s+also\s+',
            r',\s+also\s+',
            r'\s+and\s+also\s+',
            r'\.\s+another\s+(?:task|one)\s+(?:is\s+)?',
            r',\s+another\s+(?:task|one)\s+(?:is\s+)?',
            r'\.\s+plus\s+',
            r',\s+plus\s+',
        ]

        for sep in separators:
            if re.search(sep, message, re.IGNORECASE):
                parts = re.split(sep, message, flags=re.IGNORECASE)
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

        # If no questions needed, create all tasks directly
        if not all_questions:
            responses = []
            for task_entry in batch["tasks"]:
                preview, spec = await self.clarifier.generate_spec_preview(
                    conversation=task_entry["conversation"],
                    preferences=prefs.to_dict()
                )
                task_entry["conversation"].generated_spec = spec
                task_entry["conversation"].stage = ConversationStage.PREVIEW
                responses.append(f"**Task {task_entry['index']}:**\n{preview[:200]}...")

            batch["awaiting_confirm"] = True
            self._batch_tasks[user_id] = batch

            return f"""📋 **{len(batch['tasks'])} Tasks Ready**

{chr(10).join(responses)}

Reply **yes** to create all, or specify changes.""", None

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

        return f"""📋 **{len(batch['tasks'])} Tasks Ready:**

{chr(10).join(previews)}

Reply **yes** to create all, or **cancel** to abort.""", None

    async def _handle_batch_confirm(
        self, user_id: str, message: str, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle confirmation to create all batch tasks."""
        batch = self._batch_tasks.get(user_id)
        if not batch:
            return "No pending batch tasks.", None

        message_lower = message.lower().strip()

        # Check for cancel
        if any(w in message_lower for w in ["cancel", "no", "stop", "abort"]):
            del self._batch_tasks[user_id]
            return "Batch cancelled. No tasks created.", None

        # Check for confirmation
        if any(w in message_lower for w in ["yes", "ok", "confirm", "create", "go", "do it"]):
            created_tasks = []
            errors = []

            for task_entry in batch["tasks"]:
                try:
                    conv = task_entry["conversation"]
                    if not conv.generated_spec:
                        continue

                    # Create the task
                    response, action = await self._finalize_task(conv, user_id)

                    if "Created" in response or "✅" in response:
                        # Extract task ID from response
                        import re
                        match = re.search(r'(TASK-[\w-]+)', response)
                        if match:
                            created_tasks.append(match.group(1))
                    else:
                        errors.append(f"Task {task_entry['index']}: {response[:50]}")

                except Exception as e:
                    logger.error(f"Error creating batch task {task_entry['index']}: {e}")
                    errors.append(f"Task {task_entry['index']}: Error")

            # Clean up batch session
            del self._batch_tasks[user_id]

            # Build response
            if created_tasks and not errors:
                return f"✅ **Created {len(created_tasks)} tasks:**\n• " + "\n• ".join(created_tasks), None
            elif created_tasks and errors:
                return f"""✅ **Created {len(created_tasks)} tasks:**
• {chr(10).join(created_tasks)}

⚠️ **Issues:**
• {chr(10).join(errors)}""", None
            else:
                return "❌ Failed to create tasks. Please try again.", None

        return "Reply **yes** to create all tasks, or **cancel** to abort.", None


# Singleton
unified_handler = UnifiedHandler()

def get_unified_handler() -> UnifiedHandler:
    return unified_handler
