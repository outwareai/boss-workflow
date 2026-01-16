"""
Conversation manager for multi-turn task creation.

Handles the state machine for conversational task creation with the boss.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum

from ..models.conversation import ConversationState, ConversationStage
from ..models.task import Task, TaskPriority, TaskStatus, AcceptanceCriteria
from ..memory.context import ConversationContext, get_conversation_context
from ..memory.preferences import PreferencesManager, get_preferences_manager
from ..ai.clarifier import TaskClarifier
from ..ai.deepseek import get_deepseek_client
from ..integrations.discord import get_discord_integration
from ..integrations.sheets import get_sheets_integration
from ..integrations.calendar import get_calendar_integration

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Manages the conversational flow for task creation.

    Flow:
    1. User sends task request
    2. AI analyzes and decides if clarification needed
    3. If needed, ask questions
    4. User answers (can /skip or /done)
    5. Generate spec and show preview
    6. User confirms or requests changes
    7. Create task and post to integrations
    """

    def __init__(self):
        self.context = get_conversation_context()
        self.prefs = get_preferences_manager()
        self.clarifier = TaskClarifier()
        self.discord = get_discord_integration()
        self.sheets = get_sheets_integration()
        self.calendar = get_calendar_integration()

    async def start_conversation(
        self,
        user_id: str,
        chat_id: str,
        message: str,
        is_urgent: bool = False
    ) -> Tuple[str, ConversationState]:
        """
        Start a new task creation conversation.

        Returns the response message and the conversation state.
        """
        # Create conversation
        conversation = await self.context.create_conversation(
            user_id=user_id,
            chat_id=chat_id,
            original_message=message,
            is_urgent=is_urgent
        )

        # Get user preferences
        preferences = await self.prefs.get_preferences(user_id)

        # Apply any triggers from preferences
        trigger = preferences.find_trigger(message)
        if trigger:
            if trigger.action == "set_priority":
                conversation.extracted_info["priority"] = trigger.value
            elif trigger.action == "set_deadline":
                conversation.extracted_info["deadline_hint"] = trigger.value
            elif trigger.action == "set_assignee":
                conversation.extracted_info["assignee"] = trigger.value

        # Analyze the message
        conversation.stage = ConversationStage.ANALYZING
        await self.context.save_conversation(conversation)

        should_ask, analysis = await self.clarifier.analyze_and_decide(
            conversation=conversation,
            preferences=preferences.to_dict(),
            team_info=preferences.get_team_info()
        )

        if should_ask and not is_urgent:
            # Need to ask clarifying questions
            conversation.stage = ConversationStage.CLARIFYING

            question_msg, questions = await self.clarifier.generate_question_message(
                analysis=analysis,
                preferences=preferences.to_dict()
            )

            # Store questions in conversation
            for q in questions:
                conversation.add_question(q.question, q.options)
            conversation.total_questions_planned = len(questions)

            conversation.add_assistant_message(question_msg)
            conversation.stage = ConversationStage.AWAITING_ANSWER
            await self.context.save_conversation(conversation)

            return question_msg, conversation

        else:
            # Can proceed directly to spec generation
            return await self._generate_and_preview(conversation, preferences.to_dict())

    async def process_message(
        self,
        user_id: str,
        message: str,
        message_id: Optional[str] = None
    ) -> Tuple[str, Optional[ConversationState]]:
        """
        Process a message in an ongoing conversation.

        Returns the response message and updated conversation state.
        """
        # Get active conversation
        conversation = await self.context.get_active_conversation(user_id)

        if not conversation:
            # No active conversation - start a new one
            return await self.start_conversation(
                user_id=user_id,
                chat_id=user_id,  # Assuming chat_id same as user_id for DMs
                message=message
            )

        # Add user message to conversation
        conversation.add_user_message(message, message_id)

        # Get preferences
        preferences = await self.prefs.get_preferences(user_id)

        # Handle based on current stage
        if conversation.stage == ConversationStage.AWAITING_ANSWER:
            return await self._handle_answer(conversation, message, preferences.to_dict())

        elif conversation.stage == ConversationStage.PREVIEW:
            return await self._handle_preview_response(conversation, message, preferences.to_dict())

        else:
            # Unexpected state - treat as new conversation
            logger.warning(f"Unexpected conversation stage: {conversation.stage}")
            return await self.start_conversation(
                user_id=user_id,
                chat_id=conversation.chat_id,
                message=message
            )

    async def _handle_answer(
        self,
        conversation: ConversationState,
        answer: str,
        preferences: Dict[str, Any]
    ) -> Tuple[str, ConversationState]:
        """Handle user's answer to clarifying questions."""

        # Process the answers
        await self.clarifier.process_user_answers(conversation, answer)

        # Check if we have more questions
        pending_questions = [
            q for q in conversation.questions_asked
            if q.answer is None and not q.skipped
        ]

        if pending_questions:
            # More questions to ask
            next_question = pending_questions[0]
            response = f"Got it! Next question:\n\n{next_question.question}"

            if next_question.options:
                response += "\n"
                for i, opt in enumerate(next_question.options, 1):
                    response += f"\n   {chr(64+i)}) {opt}"

            conversation.add_assistant_message(response)
            await self.context.save_conversation(conversation)

            return response, conversation

        else:
            # All questions answered - generate spec
            return await self._generate_and_preview(conversation, preferences)

    async def _generate_and_preview(
        self,
        conversation: ConversationState,
        preferences: Dict[str, Any]
    ) -> Tuple[str, ConversationState]:
        """Generate the task spec and show preview."""
        conversation.stage = ConversationStage.GENERATING

        preview, spec = await self.clarifier.generate_spec_preview(
            conversation=conversation,
            preferences=preferences
        )

        conversation.generated_spec = spec
        conversation.stage = ConversationStage.PREVIEW
        conversation.add_assistant_message(preview)

        await self.context.save_conversation(conversation)

        return preview, conversation

    async def _handle_preview_response(
        self,
        conversation: ConversationState,
        response: str,
        preferences: Dict[str, Any]
    ) -> Tuple[str, ConversationState]:
        """Handle user's response to the preview."""

        response_lower = response.lower().strip()

        # Check for confirmation
        if response_lower in ['✅', 'yes', 'y', 'confirm', 'ok', 'looks good', 'lgtm', 'approved', '👍']:
            return await self._create_task(conversation, preferences)

        # Check for cancellation
        elif response_lower in ['cancel', 'abort', 'stop', 'no', 'nevermind', '❌']:
            conversation.stage = ConversationStage.ABANDONED
            await self.context.save_conversation(conversation)
            return "Task creation cancelled. Send a new message anytime to start again.", conversation

        # User wants changes - process feedback and regenerate
        else:
            # Add the feedback to extracted info
            conversation.extracted_info["user_feedback"] = response

            # Regenerate with feedback
            conversation.stage = ConversationStage.GENERATING
            preview, spec = await self.clarifier.generate_spec_preview(
                conversation=conversation,
                preferences=preferences
            )

            conversation.generated_spec = spec
            conversation.stage = ConversationStage.PREVIEW
            conversation.add_assistant_message(f"Updated based on your feedback:\n\n{preview}")

            await self.context.save_conversation(conversation)

            return f"Updated based on your feedback:\n\n{preview}", conversation

    async def _create_task(
        self,
        conversation: ConversationState,
        preferences: Dict[str, Any]
    ) -> Tuple[str, ConversationState]:
        """Create the task and post to all integrations."""
        conversation.stage = ConversationStage.CONFIRMED

        spec = conversation.generated_spec
        if not spec:
            return "Error: No task specification found. Please try again.", conversation

        # Build the task
        task = Task(
            title=spec.get("title", "Untitled Task"),
            description=spec.get("description", conversation.original_message),
            assignee=spec.get("assignee"),
            priority=TaskPriority(spec.get("priority", "medium")),
            task_type=spec.get("task_type", "task"),
            estimated_effort=spec.get("estimated_effort"),
            tags=spec.get("tags", []),
            created_by=conversation.user_id,
            original_message=conversation.original_message,
            conversation_id=conversation.conversation_id,
        )

        # Parse deadline
        deadline_str = spec.get("deadline")
        if deadline_str:
            try:
                task.deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
            except ValueError:
                logger.warning(f"Could not parse deadline: {deadline_str}")

        # Add acceptance criteria
        criteria_list = spec.get("acceptance_criteria", [])
        for criterion in criteria_list:
            task.acceptance_criteria.append(AcceptanceCriteria(description=criterion))

        # Post to Discord
        discord_msg_id = await self.discord.post_task(task)
        if discord_msg_id:
            task.discord_message_id = discord_msg_id

        # Add to Google Sheets
        sheets_row = await self.sheets.add_task(task)
        if sheets_row:
            task.sheets_row_id = sheets_row

        # Add to Google Calendar (if deadline set)
        if task.deadline:
            calendar_event_id = await self.calendar.create_task_event(task)
            if calendar_event_id:
                task.google_calendar_event_id = calendar_event_id

        # Update conversation
        conversation.task_id = task.id
        conversation.stage = ConversationStage.COMPLETED
        await self.context.save_conversation(conversation)

        # Build success message
        success_msg = f"""✅ **Task Created!**

**{task.id}**: {task.title}

"""
        if discord_msg_id:
            success_msg += "→ Posted to Discord #tasks-daily\n"
        if sheets_row:
            success_msg += "→ Added to Google Sheet\n"
        if task.google_calendar_event_id:
            success_msg += "→ Added to Google Calendar\n"
        if task.assignee:
            success_msg += f"→ Assigned to {task.assignee}\n"

        success_msg += "\nSend another message anytime to create a new task!"

        return success_msg, conversation

    async def handle_skip(self, user_id: str) -> Tuple[str, Optional[ConversationState]]:
        """Handle /skip command - use defaults for remaining questions."""
        conversation = await self.context.get_active_conversation(user_id)

        if not conversation:
            return "No active task creation. Send a message to start.", None

        if conversation.stage not in [ConversationStage.AWAITING_ANSWER, ConversationStage.CLARIFYING]:
            return "Nothing to skip right now.", conversation

        # Mark remaining questions as skipped
        for q in conversation.questions_asked:
            if q.answer is None:
                q.skipped = True

        conversation.skip_requested = True

        # Get preferences and apply defaults
        preferences = await self.prefs.get_preferences(user_id)
        self.clarifier.apply_defaults(conversation, preferences.to_dict())

        # Generate spec with defaults
        return await self._generate_and_preview(conversation, preferences.to_dict())

    async def handle_done(self, user_id: str) -> Tuple[str, Optional[ConversationState]]:
        """Handle /done command - finalize immediately with current info."""
        conversation = await self.context.get_active_conversation(user_id)

        if not conversation:
            return "No active task creation. Send a message to start.", None

        # Get preferences
        preferences = await self.prefs.get_preferences(user_id)

        # Apply defaults for any missing info
        self.clarifier.apply_defaults(conversation, preferences.to_dict())

        # Generate and show preview, then auto-confirm
        preview, spec = await self.clarifier.generate_spec_preview(
            conversation=conversation,
            preferences=preferences.to_dict()
        )

        # Auto-confirm and create
        conversation.generated_spec = spec
        return await self._create_task(conversation, preferences.to_dict())

    async def handle_cancel(self, user_id: str) -> Tuple[str, Optional[ConversationState]]:
        """Handle conversation cancellation."""
        conversation = await self.context.get_active_conversation(user_id)

        if not conversation:
            return "No active task creation to cancel.", None

        conversation.stage = ConversationStage.ABANDONED
        await self.context.save_conversation(conversation)
        await self.context.clear_active_conversation(user_id)

        return "Task creation cancelled. Send a new message anytime to start again.", conversation

    async def get_status(self, user_id: str) -> str:
        """Get current conversation/task status."""
        conversation = await self.context.get_active_conversation(user_id)

        if not conversation:
            return "No active task creation. Send a message to start a new task."

        stage_messages = {
            ConversationStage.INITIAL: "Starting to analyze your request...",
            ConversationStage.ANALYZING: "Analyzing your task request...",
            ConversationStage.CLARIFYING: "Preparing clarifying questions...",
            ConversationStage.AWAITING_ANSWER: f"Waiting for your answer to question {conversation.current_question_index + 1}",
            ConversationStage.GENERATING: "Generating task specification...",
            ConversationStage.PREVIEW: "Waiting for your confirmation of the task preview",
            ConversationStage.CONFIRMED: "Creating your task...",
            ConversationStage.COMPLETED: f"Task {conversation.task_id} has been created!",
            ConversationStage.ABANDONED: "Previous task was cancelled",
            ConversationStage.ERROR: f"An error occurred: {conversation.error_message}",
        }

        status = stage_messages.get(conversation.stage, "Unknown status")

        if conversation.stage == ConversationStage.AWAITING_ANSWER:
            pending = len([q for q in conversation.questions_asked if q.answer is None and not q.skipped])
            status += f"\n{pending} question(s) remaining"
            status += "\n\nYou can /skip to use defaults or /done to finalize now"

        return status


# Singleton instance
conversation_manager = ConversationManager()


def get_conversation_manager() -> ConversationManager:
    """Get the conversation manager instance."""
    return conversation_manager
