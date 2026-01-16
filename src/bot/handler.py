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

    async def handle_message(
        self,
        user_id: str,
        message: str,
        photo_file_id: Optional[str] = None,
        photo_caption: Optional[str] = None,
        user_name: str = "User",
        is_boss: bool = False
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Handle any incoming message.

        Returns:
            Tuple of (response_text, optional_action_data)
            action_data might contain: send_to_boss, notify_user, etc.
        """
        # Build context for intent detection
        context = await self._build_context(user_id, is_boss)

        # Handle photos
        if photo_file_id:
            if context.get("collecting_proof"):
                return await self._handle_proof_photo(user_id, photo_file_id, photo_caption)
            else:
                # Photo outside of proof collection - just acknowledge
                if photo_caption:
                    message = f"[Photo] {photo_caption}"
                else:
                    return "Got the photo! What's this for?", None

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
            UserIntent.DELAY_TASK: self._handle_delay,
            UserIntent.ADD_TEAM_MEMBER: self._handle_add_team,
            UserIntent.TEACH_PREFERENCE: self._handle_teach,
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

    # ==================== INTENT HANDLERS ====================

    async def _handle_greeting(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle greetings."""
        return f"""Hey {user_name}! 👋

Just tell me what you need:
• Assign a task: "John needs to fix the login bug"
• Mark done: "I finished the landing page"
• Check status: "What's pending?"

What's up?""", None

    async def _handle_help(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle help requests."""
        return """**How I work:**

Just talk to me naturally!

**Create tasks:**
"Sarah needs to build the checkout page by Friday"
"Fix the mobile menu bug - urgent"

**Mark done:**
"I finished the landing page"
Then send screenshots/links as proof

**Check things:**
"What's pending?"
"Anything overdue?"

**Teach me:**
"John is our backend dev"
"When I say ASAP, deadline is 4 hours"

No commands needed - just chat!""", None

    async def _handle_create_task(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, Optional[Dict]]:
        """Handle task creation."""
        # Get preferences
        prefs = await self.prefs.get_preferences(user_id)

        # Create conversation
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
        """Create task without questions."""
        preview, spec = await self.clarifier.generate_spec_preview(
            conversation=conversation,
            preferences=preferences
        )

        conversation.generated_spec = spec
        conversation.stage = ConversationStage.PREVIEW
        await self.context.save_conversation(conversation)

        return f"{preview}\n\nLook good? (yes/no)", None

    async def _handle_task_done(
        self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
    ) -> Tuple[str, None]:
        """Handle when someone says they finished a task."""
        # Start proof collection session
        self._validation_sessions[user_id] = {
            "stage": "collecting_proof",
            "user_id": user_id,
            "user_name": user_name,
            "message": message,
            "proof_items": [],
            "started_at": datetime.now().isoformat()
        }

        # Try to extract task reference from message
        # AI could help identify which task they're referring to

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
        self, user_id: str, file_id: str, caption: Optional[str]
    ) -> Tuple[str, None]:
        """Handle photo as proof."""
        session = self._validation_sessions.get(user_id)
        if not session:
            return "What's this screenshot for?", None

        proof = {
            "type": "screenshot",
            "file_id": file_id,
            "caption": caption,
            "timestamp": datetime.now().isoformat()
        }
        session["proof_items"].append(proof)

        count = len(session["proof_items"])
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

        # List proof items
        for i, proof in enumerate(session.get("proof_items", [])[:5], 1):
            ptype = proof.get("type", "item")
            emoji = {"screenshot": "🖼️", "link": "🔗", "note": "📝"}.get(ptype, "📎")
            if ptype == "link":
                lines.append(f"  {emoji} {proof.get('content', '')[:50]}")
            elif ptype == "screenshot":
                lines.append(f"  {emoji} Screenshot {i}")
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

            # Convert to dict format for summarizer
            email_dicts = [
                {
                    "subject": e.subject,
                    "sender": e.sender,
                    "snippet": e.snippet,
                    "date": e.date.isoformat() if e.date else ""
                }
                for e in emails
            ]

            # Get user preferences for context
            user_prefs = await self.prefs.get_preferences(user_id)

            # Summarize
            result = await summarizer.summarize_emails(email_dicts, "on-demand", user_prefs.to_dict())

            # Format response
            lines = ["📧 **Email Recap**", ""]
            lines.append(result.summary)

            if result.action_items:
                lines.append("")
                lines.append("**Action Items:**")
                for item in result.action_items[:5]:
                    lines.append(f"• {item}")

            if result.priority_subjects:
                lines.append("")
                lines.append("**Priority Emails:**")
                for subj in result.priority_subjects[:3]:
                    lines.append(f"• {subj}")

            lines.append(f"\n_({len(emails)} emails analyzed)_")

            return "\n".join(lines), None

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

        task = Task(
            title=spec.get("title", "Untitled"),
            description=spec.get("description", conv.original_message),
            assignee=spec.get("assignee"),
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

        # Post to integrations
        await self.discord.post_task(task)
        await self.sheets.add_task(task)
        if task.deadline:
            await self.calendar.create_task_event(task)

        conv.stage = ConversationStage.COMPLETED
        conv.task_id = task.id
        await self.context.save_conversation(conv)

        assignee_text = f" for {task.assignee}" if task.assignee else ""
        return f"✅ Created{assignee_text}!\n\n**{task.id}**: {task.title}", None


# Singleton
unified_handler = UnifiedHandler()

def get_unified_handler() -> UnifiedHandler:
    return unified_handler
