"""
Validation model for task completion proof of work.

Handles the workflow:
1. Team member marks task as "ready for review"
2. Submits proof (screenshots, links, notes)
3. Boss receives validation request
4. Boss approves or rejects with feedback
5. If rejected, assignee gets feedback and can resubmit
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


class ValidationStatus(str, Enum):
    """Status of the validation process."""
    NOT_SUBMITTED = "not_submitted"      # No proof submitted yet
    PENDING_REVIEW = "pending_review"    # Waiting for boss review
    APPROVED = "approved"                # Boss approved
    REJECTED = "rejected"                # Boss rejected, needs rework
    RESUBMITTED = "resubmitted"          # Resubmitted after rejection


class ProofType(str, Enum):
    """Types of proof that can be submitted."""
    SCREENSHOT = "screenshot"
    VIDEO = "video"
    LINK = "link"
    DOCUMENT = "document"
    NOTE = "note"
    CODE_COMMIT = "code_commit"


class ProofItem(BaseModel):
    """A single piece of proof submitted for validation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    proof_type: ProofType
    content: str  # URL, file_id, or text content
    caption: Optional[str] = None
    submitted_at: datetime = Field(default_factory=datetime.now)
    file_id: Optional[str] = None  # Telegram file ID for media


class ValidationFeedback(BaseModel):
    """Feedback from boss on a validation attempt."""
    feedback_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: ValidationStatus
    message: str
    given_by: str  # Boss user ID
    given_at: datetime = Field(default_factory=datetime.now)
    requires_changes: List[str] = Field(default_factory=list)  # Specific items to fix


class ValidationAttempt(BaseModel):
    """A single validation attempt (submission + review)."""
    attempt_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    attempt_number: int = 1

    # Submission
    submitted_by: str  # Assignee user ID
    submitted_at: datetime = Field(default_factory=datetime.now)
    proof_items: List[ProofItem] = Field(default_factory=list)
    submission_notes: Optional[str] = None

    # Review
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    status: ValidationStatus = ValidationStatus.PENDING_REVIEW
    feedback: Optional[ValidationFeedback] = None


class TaskValidation(BaseModel):
    """
    Complete validation record for a task.

    Tracks all submission attempts and their outcomes.
    """
    task_id: str

    # Current state
    current_status: ValidationStatus = ValidationStatus.NOT_SUBMITTED
    total_attempts: int = 0

    # Validation history
    attempts: List[ValidationAttempt] = Field(default_factory=list)

    # Final approval
    final_approved_at: Optional[datetime] = None
    final_approved_by: Optional[str] = None

    # Timing
    first_submitted_at: Optional[datetime] = None
    last_submitted_at: Optional[datetime] = None

    # Telegram message tracking
    validation_request_message_id: Optional[str] = None

    def submit_for_validation(
        self,
        submitted_by: str,
        proof_items: List[ProofItem],
        notes: Optional[str] = None
    ) -> ValidationAttempt:
        """Submit task for validation with proof."""
        self.total_attempts += 1

        attempt = ValidationAttempt(
            attempt_number=self.total_attempts,
            submitted_by=submitted_by,
            proof_items=proof_items,
            submission_notes=notes,
            status=ValidationStatus.PENDING_REVIEW
        )

        self.attempts.append(attempt)
        self.current_status = ValidationStatus.PENDING_REVIEW
        self.last_submitted_at = datetime.now()

        if not self.first_submitted_at:
            self.first_submitted_at = datetime.now()

        return attempt

    def approve(self, approved_by: str, message: str = "Great work!") -> ValidationFeedback:
        """Approve the current validation attempt."""
        if not self.attempts:
            raise ValueError("No validation attempt to approve")

        current_attempt = self.attempts[-1]

        feedback = ValidationFeedback(
            status=ValidationStatus.APPROVED,
            message=message,
            given_by=approved_by
        )

        current_attempt.status = ValidationStatus.APPROVED
        current_attempt.reviewed_at = datetime.now()
        current_attempt.reviewed_by = approved_by
        current_attempt.feedback = feedback

        self.current_status = ValidationStatus.APPROVED
        self.final_approved_at = datetime.now()
        self.final_approved_by = approved_by

        return feedback

    def reject(
        self,
        rejected_by: str,
        message: str,
        required_changes: List[str] = None
    ) -> ValidationFeedback:
        """Reject the current validation attempt with feedback."""
        if not self.attempts:
            raise ValueError("No validation attempt to reject")

        current_attempt = self.attempts[-1]

        feedback = ValidationFeedback(
            status=ValidationStatus.REJECTED,
            message=message,
            given_by=rejected_by,
            requires_changes=required_changes or []
        )

        current_attempt.status = ValidationStatus.REJECTED
        current_attempt.reviewed_at = datetime.now()
        current_attempt.reviewed_by = rejected_by
        current_attempt.feedback = feedback

        self.current_status = ValidationStatus.REJECTED

        return feedback

    def get_current_attempt(self) -> Optional[ValidationAttempt]:
        """Get the current/latest validation attempt."""
        return self.attempts[-1] if self.attempts else None

    def get_rejection_history(self) -> List[ValidationFeedback]:
        """Get all rejection feedback for learning."""
        return [
            a.feedback for a in self.attempts
            if a.feedback and a.status == ValidationStatus.REJECTED
        ]

    def to_summary(self) -> str:
        """Generate a summary of the validation status."""
        status_emoji = {
            ValidationStatus.NOT_SUBMITTED: "⬜",
            ValidationStatus.PENDING_REVIEW: "🔄",
            ValidationStatus.APPROVED: "✅",
            ValidationStatus.REJECTED: "❌",
            ValidationStatus.RESUBMITTED: "🔁",
        }

        lines = [
            f"**Validation Status:** {status_emoji.get(self.current_status, '')} {self.current_status.value.replace('_', ' ').title()}",
            f"**Attempts:** {self.total_attempts}"
        ]

        if self.attempts:
            current = self.attempts[-1]
            lines.append(f"**Proof Items:** {len(current.proof_items)}")

            if current.feedback:
                lines.append(f"**Last Feedback:** {current.feedback.message[:100]}")

        if self.final_approved_at:
            lines.append(f"**Approved:** {self.final_approved_at.strftime('%Y-%m-%d %H:%M')}")

        return "\n".join(lines)


class ValidationRequest(BaseModel):
    """
    A validation request sent to the boss.

    This is what appears in the boss's Telegram when
    someone submits work for review.
    """
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id: str
    task_title: str
    assignee_name: str
    assignee_id: str

    # The validation attempt
    attempt: ValidationAttempt

    # Request details
    requested_at: datetime = Field(default_factory=datetime.now)

    # Telegram tracking
    boss_message_id: Optional[str] = None

    def to_telegram_message(self) -> str:
        """Format as a Telegram message for the boss."""
        lines = [
            "📋 **VALIDATION REQUEST**",
            "",
            f"**Task:** {self.task_id}",
            f"**Title:** {self.task_title}",
            f"**Submitted by:** {self.assignee_name}",
            f"**Attempt:** #{self.attempt.attempt_number}",
            "",
        ]

        if self.attempt.submission_notes:
            lines.extend([
                "**Notes from assignee:**",
                f"_{self.attempt.submission_notes}_",
                ""
            ])

        lines.extend([
            f"**Proof Items:** {len(self.attempt.proof_items)}",
        ])

        for i, proof in enumerate(self.attempt.proof_items, 1):
            proof_emoji = {
                ProofType.SCREENSHOT: "🖼️",
                ProofType.VIDEO: "🎬",
                ProofType.LINK: "🔗",
                ProofType.DOCUMENT: "📄",
                ProofType.NOTE: "📝",
                ProofType.CODE_COMMIT: "💻",
            }
            emoji = proof_emoji.get(proof.proof_type, "📎")
            caption = f" - {proof.caption}" if proof.caption else ""
            lines.append(f"  {i}. {emoji} {proof.proof_type.value}{caption}")

        lines.extend([
            "",
            "─────────────────────",
            "**Reply with:**",
            "✅ `approve` - Accept this work",
            "❌ `reject [feedback]` - Request changes",
            "",
            f"_Request ID: {self.request_id}_"
        ])

        return "\n".join(lines)

    def to_discord_embed(self) -> Dict[str, Any]:
        """Convert to Discord embed format."""
        fields = [
            {"name": "Task ID", "value": self.task_id, "inline": True},
            {"name": "Assignee", "value": self.assignee_name, "inline": True},
            {"name": "Attempt #", "value": str(self.attempt.attempt_number), "inline": True},
        ]

        if self.attempt.submission_notes:
            fields.append({
                "name": "Submission Notes",
                "value": self.attempt.submission_notes[:256],
                "inline": False
            })

        proof_text = "\n".join([
            f"• {p.proof_type.value}: {p.caption or p.content[:50]}"
            for p in self.attempt.proof_items[:5]
        ])

        fields.append({
            "name": f"Proof Items ({len(self.attempt.proof_items)})",
            "value": proof_text or "No proof attached",
            "inline": False
        })

        return {
            "title": f"🔍 Validation Request: {self.task_title}",
            "description": f"**{self.assignee_name}** has submitted work for review",
            "color": 0x3498DB,  # Blue
            "fields": fields,
            "footer": {"text": f"Request ID: {self.request_id}"},
            "timestamp": self.requested_at.isoformat()
        }
