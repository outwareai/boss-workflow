"""
Validation workflow handler for task completion proof of work.

Manages the complete validation flow:
1. Team member submits "done" with proof
2. Bot collects screenshots/proof
3. Validation request sent to boss
4. Boss approves or rejects with feedback
5. Notifications sent to all parties
"""

import logging
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum
import redis.asyncio as redis

from config import settings
from ..models.task import Task, TaskStatus
from ..models.validation import (
    TaskValidation,
    ValidationStatus,
    ValidationAttempt,
    ValidationRequest,
    ValidationFeedback,
    ProofItem,
    ProofType
)
from ..integrations.discord import get_discord_integration
from ..integrations.sheets import get_sheets_integration

logger = logging.getLogger(__name__)


class ValidationStage(str, Enum):
    """Stages of the validation submission process."""
    IDLE = "idle"
    COLLECTING_PROOF = "collecting_proof"
    COLLECTING_NOTES = "collecting_notes"
    CONFIRMING = "confirming"
    SUBMITTED = "submitted"


class ValidationSession(Dict):
    """Active validation session for a team member."""
    pass


class ValidationWorkflow:
    """
    Manages the complete validation workflow.

    Handles:
    - Team members submitting proof of completion
    - Boss receiving validation requests
    - Approval/rejection flow
    - Notifications and feedback
    """

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.discord = get_discord_integration()
        self.sheets = get_sheets_integration()
        self._validations: Dict[str, TaskValidation] = {}  # In-memory cache
        self._sessions: Dict[str, Dict] = {}  # Active submission sessions

    async def connect(self):
        """Connect to Redis."""
        if not self.redis:
            self.redis = await redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            self.redis = None

    # ==================== TEAM MEMBER SIDE ====================

    async def start_submission(
        self,
        user_id: str,
        task_id: str,
        task_title: str,
        assignee_name: str
    ) -> str:
        """
        Start a validation submission process.

        Called when team member says task is done.
        """
        await self.connect()

        # Create or get validation record
        validation = await self._get_or_create_validation(task_id)

        # Check if already approved
        if validation.current_status == ValidationStatus.APPROVED:
            return f"✅ Task {task_id} is already approved!"

        # Create submission session
        session = {
            "stage": ValidationStage.COLLECTING_PROOF.value,
            "task_id": task_id,
            "task_title": task_title,
            "user_id": user_id,
            "assignee_name": assignee_name,
            "proof_items": [],
            "notes": None,
            "started_at": datetime.now().isoformat()
        }

        self._sessions[user_id] = session
        await self._save_session(user_id, session)

        return f"""📸 **Submitting: {task_title}**

Great! Now I need proof of completion.

**Send me:**
• Screenshots of the completed work
• Links to live demos or PRs
• Any other evidence

You can send multiple items. When done, type `/submitproof` or just say "done".

Type `/cancel` to abort submission."""

    async def add_proof_item(
        self,
        user_id: str,
        proof_type: ProofType,
        content: str,
        caption: Optional[str] = None,
        file_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Add a proof item to the current submission."""
        session = await self._get_session(user_id)

        if not session or session.get("stage") != ValidationStage.COLLECTING_PROOF.value:
            return False, "No active submission. Use `/done [task-id]` to start."

        proof = ProofItem(
            proof_type=proof_type,
            content=content,
            caption=caption,
            file_id=file_id
        )

        session["proof_items"].append(proof.model_dump(mode="json"))
        await self._save_session(user_id, session)

        count = len(session["proof_items"])
        proof_emoji = {
            ProofType.SCREENSHOT: "🖼️",
            ProofType.VIDEO: "🎬",
            ProofType.LINK: "🔗",
            ProofType.DOCUMENT: "📄",
            ProofType.NOTE: "📝",
            ProofType.CODE_COMMIT: "💻",
        }

        emoji = proof_emoji.get(proof_type, "📎")
        return True, f"{emoji} Proof #{count} added! Send more or type 'done' when finished."

    async def finish_collecting_proof(self, user_id: str) -> str:
        """Move to notes collection after proof is gathered."""
        session = await self._get_session(user_id)

        if not session:
            return "No active submission."

        if not session.get("proof_items"):
            return "⚠️ Please add at least one proof item (screenshot, link, etc.)"

        session["stage"] = ValidationStage.COLLECTING_NOTES.value
        await self._save_session(user_id, session)

        return f"""✅ **{len(session['proof_items'])} proof item(s) collected!**

Would you like to add any notes for the boss?
(Explain what was done, any issues encountered, etc.)

Type your notes or say "skip" to submit without notes."""

    async def add_submission_notes(self, user_id: str, notes: str) -> str:
        """Add notes to the submission."""
        session = await self._get_session(user_id)

        if not session:
            return "No active submission."

        if notes.lower() in ["skip", "no", "none"]:
            notes = None

        session["notes"] = notes
        session["stage"] = ValidationStage.CONFIRMING.value
        await self._save_session(user_id, session)

        # Build confirmation message
        return await self._build_confirmation_message(session)

    async def confirm_submission(self, user_id: str) -> Tuple[bool, str, Optional[ValidationRequest]]:
        """Confirm and submit the validation request."""
        session = await self._get_session(user_id)

        if not session or session.get("stage") != ValidationStage.CONFIRMING.value:
            return False, "Nothing to confirm. Start with `/done [task-id]`", None

        task_id = session["task_id"]
        validation = await self._get_or_create_validation(task_id)

        # Build proof items
        proof_items = [
            ProofItem(**p) for p in session.get("proof_items", [])
        ]

        # Submit for validation
        attempt = validation.submit_for_validation(
            submitted_by=user_id,
            proof_items=proof_items,
            notes=session.get("notes")
        )

        # Save validation
        await self._save_validation(validation)

        # Create validation request for boss
        request = ValidationRequest(
            task_id=task_id,
            task_title=session["task_title"],
            assignee_name=session["assignee_name"],
            assignee_id=user_id,
            attempt=attempt
        )

        # Clear session
        await self._clear_session(user_id)

        return True, f"""✅ **Submitted for Review!**

**Task:** {task_id}
**Proof Items:** {len(proof_items)}

The boss will be notified. You'll receive feedback once reviewed.

_Attempt #{attempt.attempt_number}_""", request

    async def cancel_submission(self, user_id: str) -> str:
        """Cancel the current submission."""
        session = await self._get_session(user_id)

        if not session:
            return "No active submission to cancel."

        task_id = session.get("task_id", "Unknown")
        await self._clear_session(user_id)

        return f"❌ Submission cancelled for {task_id}"

    # ==================== BOSS SIDE ====================

    async def process_boss_response(
        self,
        boss_id: str,
        message: str,
        reply_to_request_id: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[ValidationFeedback], Optional[str]]:
        """
        Process boss's response to a validation request.

        Returns: (response_message, feedback, assignee_id)
        """
        message_lower = message.lower().strip()

        # Parse the response
        if message_lower.startswith("approve"):
            # Extract optional message
            approve_msg = message[7:].strip() if len(message) > 7 else "Great work! Task approved."
            return await self._handle_approval(reply_to_request_id, boss_id, approve_msg)

        elif message_lower.startswith("reject"):
            # Extract feedback
            feedback_text = message[6:].strip()
            if not feedback_text:
                return "❌ Please provide feedback: `reject [what needs to be changed]`", None, None
            return await self._handle_rejection(reply_to_request_id, boss_id, feedback_text)

        return None, None, None

    async def _handle_approval(
        self,
        request_id: str,
        boss_id: str,
        message: str
    ) -> Tuple[str, ValidationFeedback, str]:
        """Handle task approval."""
        # Find the validation by request_id
        validation, request = await self._find_validation_by_request(request_id)

        if not validation or not request:
            return "❌ Could not find the validation request.", None, None

        # Approve
        feedback = validation.approve(boss_id, message)
        await self._save_validation(validation)

        # Update task status
        # (This would integrate with the task storage)

        response = f"""✅ **APPROVED**

**Task:** {request.task_id}
**Assignee:** {request.assignee_name}
**Message:** {message}

The assignee has been notified."""

        return response, feedback, request.assignee_id

    async def _handle_rejection(
        self,
        request_id: str,
        boss_id: str,
        feedback_text: str
    ) -> Tuple[str, ValidationFeedback, str]:
        """Handle task rejection."""
        validation, request = await self._find_validation_by_request(request_id)

        if not validation or not request:
            return "❌ Could not find the validation request.", None, None

        # Parse required changes (split by newlines or semicolons)
        required_changes = []
        if '\n' in feedback_text:
            required_changes = [c.strip() for c in feedback_text.split('\n') if c.strip()]
        elif ';' in feedback_text:
            required_changes = [c.strip() for c in feedback_text.split(';') if c.strip()]

        # Reject
        feedback = validation.reject(boss_id, feedback_text, required_changes)
        await self._save_validation(validation)

        response = f"""❌ **REVISION REQUESTED**

**Task:** {request.task_id}
**Assignee:** {request.assignee_name}
**Feedback:** {feedback_text}

The assignee has been notified to make changes."""

        return response, feedback, request.assignee_id

    async def build_assignee_notification(
        self,
        feedback: ValidationFeedback,
        task_id: str,
        task_title: str
    ) -> str:
        """Build notification message for assignee after boss review."""
        if feedback.status == ValidationStatus.APPROVED:
            return f"""🎉 **TASK APPROVED!**

**{task_id}**: {task_title}

✅ {feedback.message}

Great job! The task is now marked as complete."""

        else:  # Rejected
            lines = [
                f"🔄 **REVISION NEEDED**",
                "",
                f"**{task_id}**: {task_title}",
                "",
                f"**Feedback from boss:**",
                f"_{feedback.message}_",
                ""
            ]

            if feedback.requires_changes:
                lines.append("**Required changes:**")
                for i, change in enumerate(feedback.requires_changes, 1):
                    lines.append(f"  {i}. {change}")
                lines.append("")

            lines.extend([
                "Please make the requested changes and resubmit.",
                "Use `/done {task_id}` when ready."
            ])

            return "\n".join(lines)

    # ==================== STORAGE HELPERS ====================

    async def _get_or_create_validation(self, task_id: str) -> TaskValidation:
        """Get or create a validation record for a task."""
        await self.connect()

        # Check cache
        if task_id in self._validations:
            return self._validations[task_id]

        # Check Redis
        key = f"validation:{task_id}"
        data = await self.redis.get(key)

        if data:
            validation = TaskValidation(**json.loads(data))
        else:
            validation = TaskValidation(task_id=task_id)

        self._validations[task_id] = validation
        return validation

    async def _save_validation(self, validation: TaskValidation) -> None:
        """Save validation to Redis."""
        await self.connect()

        key = f"validation:{validation.task_id}"
        await self.redis.set(key, json.dumps(validation.model_dump(mode="json")))
        self._validations[validation.task_id] = validation

    async def _get_session(self, user_id: str) -> Optional[Dict]:
        """Get active submission session."""
        if user_id in self._sessions:
            return self._sessions[user_id]

        await self.connect()
        key = f"validation_session:{user_id}"
        data = await self.redis.get(key)

        if data:
            session = json.loads(data)
            self._sessions[user_id] = session
            return session

        return None

    async def _save_session(self, user_id: str, session: Dict) -> None:
        """Save submission session."""
        await self.connect()

        key = f"validation_session:{user_id}"
        await self.redis.setex(key, 3600, json.dumps(session))  # 1 hour TTL
        self._sessions[user_id] = session

    async def _clear_session(self, user_id: str) -> None:
        """Clear submission session."""
        await self.connect()

        key = f"validation_session:{user_id}"
        await self.redis.delete(key)
        self._sessions.pop(user_id, None)

    async def _find_validation_by_request(
        self,
        request_id: str
    ) -> Tuple[Optional[TaskValidation], Optional[ValidationRequest]]:
        """Find validation and request by request ID."""
        # This would need a proper index in production
        # For now, scan recent validations
        await self.connect()

        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor=cursor,
                match="validation:*",
                count=100
            )

            for key in keys:
                data = await self.redis.get(key)
                if data:
                    validation = TaskValidation(**json.loads(data))
                    # Check if any request matches
                    # (In production, we'd store requests separately with index)

            if cursor == 0:
                break

        return None, None

    async def _build_confirmation_message(self, session: Dict) -> str:
        """Build confirmation message for submission."""
        lines = [
            "📋 **Submission Summary**",
            "",
            f"**Task:** {session['task_id']}",
            f"**Title:** {session['task_title']}",
            "",
            f"**Proof Items:** {len(session.get('proof_items', []))}",
        ]

        for i, proof in enumerate(session.get("proof_items", [])[:5], 1):
            proof_type = proof.get("proof_type", "unknown")
            caption = proof.get("caption", "")[:30]
            lines.append(f"  {i}. {proof_type}: {caption or '(no caption)'}")

        if len(session.get("proof_items", [])) > 5:
            lines.append(f"  ... and {len(session['proof_items']) - 5} more")

        if session.get("notes"):
            lines.extend([
                "",
                "**Notes:**",
                f"_{session['notes'][:200]}_"
            ])

        lines.extend([
            "",
            "─────────────────────",
            "Reply **yes** to submit or **cancel** to abort."
        ])

        return "\n".join(lines)

    async def get_pending_validations(self) -> List[Dict[str, Any]]:
        """Get all pending validation requests (for boss overview)."""
        await self.connect()

        pending = []
        cursor = 0

        while True:
            cursor, keys = await self.redis.scan(
                cursor=cursor,
                match="validation:*",
                count=100
            )

            for key in keys:
                data = await self.redis.get(key)
                if data:
                    validation = TaskValidation(**json.loads(data))
                    if validation.current_status == ValidationStatus.PENDING_REVIEW:
                        pending.append({
                            "task_id": validation.task_id,
                            "attempts": validation.total_attempts,
                            "submitted_at": validation.last_submitted_at.isoformat() if validation.last_submitted_at else None
                        })

            if cursor == 0:
                break

        return pending


# Singleton instance
validation_workflow = ValidationWorkflow()


def get_validation_workflow() -> ValidationWorkflow:
    """Get the validation workflow instance."""
    return validation_workflow
