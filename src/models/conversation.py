"""Conversation state model for tracking multi-turn interactions."""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


class ConversationStage(str, Enum):
    """Stages of the task creation conversation."""
    INITIAL = "initial"              # Just received initial message
    ANALYZING = "analyzing"          # AI is analyzing the message
    CLARIFYING = "clarifying"        # Asking clarification questions
    AWAITING_ANSWER = "awaiting_answer"  # Waiting for user response
    GENERATING = "generating"        # Generating the spec
    PREVIEW = "preview"              # Showing preview, awaiting confirmation
    CONFIRMED = "confirmed"          # User confirmed, creating task
    COMPLETED = "completed"          # Task created successfully
    ABANDONED = "abandoned"          # Conversation timed out or cancelled
    ERROR = "error"                  # Error occurred
    # Spec sheet generation stages
    SPEC_ANALYZING = "spec_analyzing"      # Analyzing if we have enough for a spec
    SPEC_CLARIFYING = "spec_clarifying"    # Asking questions to build the spec
    SPEC_GENERATING = "spec_generating"    # Generating the detailed spec


class ClarifyingQuestion(BaseModel):
    """A clarifying question asked during conversation."""
    question: str
    options: List[str] = Field(default_factory=list)  # Optional predefined options
    answer: Optional[str] = None
    skipped: bool = False
    asked_at: datetime = Field(default_factory=datetime.now)
    answered_at: Optional[datetime] = None


class ConversationMessage(BaseModel):
    """A message in the conversation history."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    message_id: Optional[str] = None


class ConversationState(BaseModel):
    """
    Tracks the state of a conversation for task creation.
    Stored in Redis for fast access and persistence.
    """

    # Identification
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # Telegram user ID
    chat_id: str  # Telegram chat ID

    # Stage tracking
    stage: ConversationStage = ConversationStage.INITIAL

    # Message content
    original_message: str = ""
    voice_transcription: Optional[str] = None
    attachments: List[str] = Field(default_factory=list)  # File paths or URLs

    # Conversation history
    messages: List[ConversationMessage] = Field(default_factory=list)

    # Clarification tracking
    questions_asked: List[ClarifyingQuestion] = Field(default_factory=list)
    current_question_index: int = 0
    total_questions_planned: int = 0

    # Extracted/gathered information
    extracted_info: Dict[str, Any] = Field(default_factory=dict)
    # Example: {
    #   "title": "Fix login bug",
    #   "assignee": "john",
    #   "priority": "high",
    #   "deadline": "2026-01-16T18:00:00",
    #   "description": "...",
    #   "acceptance_criteria": [...]
    # }

    # Generated spec (preview)
    generated_spec: Optional[Dict[str, Any]] = None

    # Timing
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_activity_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # Result
    task_id: Optional[str] = None  # Created task ID
    error_message: Optional[str] = None

    # Flags
    is_urgent: bool = False
    skip_requested: bool = False

    def add_user_message(self, content: str, message_id: Optional[str] = None) -> None:
        """Add a user message to the conversation."""
        self.messages.append(ConversationMessage(
            role="user",
            content=content,
            message_id=message_id
        ))
        self.last_activity_at = datetime.now()
        self.updated_at = datetime.now()

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the conversation."""
        self.messages.append(ConversationMessage(
            role="assistant",
            content=content
        ))
        self.updated_at = datetime.now()

    def add_question(self, question: str, options: List[str] = None) -> None:
        """Add a clarifying question."""
        self.questions_asked.append(ClarifyingQuestion(
            question=question,
            options=options or []
        ))
        self.updated_at = datetime.now()

    def answer_current_question(self, answer: str, skipped: bool = False) -> None:
        """Record the answer to the current question."""
        if self.current_question_index < len(self.questions_asked):
            q = self.questions_asked[self.current_question_index]
            q.answer = answer
            q.skipped = skipped
            q.answered_at = datetime.now()
            self.current_question_index += 1
            self.updated_at = datetime.now()

    def get_conversation_context(self) -> str:
        """Get formatted conversation history for AI context."""
        lines = []
        for msg in self.messages:
            role = "User" if msg.role == "user" else "Assistant"
            lines.append(f"{role}: {msg.content}")
        return "\n".join(lines)

    def get_qa_summary(self) -> Dict[str, Any]:
        """Get a summary of questions and answers."""
        return {
            q.question: q.answer or "(skipped)"
            for q in self.questions_asked
            if q.answer or q.skipped
        }

    def is_timed_out(self, timeout_minutes: int = 30) -> bool:
        """Check if conversation has timed out."""
        elapsed = (datetime.now() - self.last_activity_at).total_seconds()
        return elapsed > (timeout_minutes * 60)

    def should_auto_finalize(self, auto_finalize_hours: int = 2) -> bool:
        """Check if conversation should be auto-finalized."""
        elapsed = (datetime.now() - self.last_activity_at).total_seconds()
        return elapsed > (auto_finalize_hours * 3600)

    def to_redis_key(self) -> str:
        """Generate Redis key for this conversation."""
        return f"conversation:{self.user_id}:{self.conversation_id}"

    @classmethod
    def active_conversation_key(cls, user_id: str) -> str:
        """Generate Redis key for user's active conversation lookup."""
        return f"active_conversation:{user_id}"
