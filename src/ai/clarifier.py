"""
Task Clarifier - Smart question generation and conversation management.

Decides what questions to ask based on:
- Missing information from the initial message
- User's saved preferences
- Task type detection
- Urgency signals
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from .deepseek import DeepSeekClient, get_deepseek_client
from ..models.conversation import ConversationState, ConversationStage, ClarifyingQuestion

logger = logging.getLogger(__name__)


class TaskClarifier:
    """
    Manages the clarification process for task creation.

    Handles the logic of deciding when to ask questions,
    what to ask, and when to proceed directly to spec generation.
    Also handles template detection and smart dependency suggestions.
    """

    def __init__(self, deepseek_client: Optional[DeepSeekClient] = None):
        self.ai = deepseek_client or get_deepseek_client()

        # Fields that typically need clarification
        self.important_fields = ["assignee", "priority", "deadline"]

        # Confidence threshold below which we ask questions
        self.confidence_threshold = 0.7

        # Maximum questions to ask in one round
        self.max_questions_per_round = 3

    def detect_and_apply_template(
        self,
        conversation: ConversationState,
        preferences: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Detect if message matches a task template and apply its defaults.

        Returns the matched template info or None.
        """
        from ..memory.preferences import UserPreferences, TaskTemplate, DEFAULT_TEMPLATES

        message = conversation.original_message.lower()

        # Check user templates first, then defaults
        matched_template = None
        template_name = None

        # Check defaults
        for template_data in DEFAULT_TEMPLATES:
            for keyword in template_data["keywords"]:
                if keyword.lower() in message:
                    matched_template = template_data
                    template_name = template_data["name"]
                    break
            if matched_template:
                break

        if not matched_template:
            return None

        # Apply template defaults to extracted_info
        defaults = matched_template.get("defaults", {})

        if "task_type" in defaults and "task_type" not in conversation.extracted_info:
            conversation.extracted_info["task_type"] = defaults["task_type"]

        if "priority" in defaults and "priority" not in conversation.extracted_info:
            conversation.extracted_info["priority"] = defaults["priority"]

        if "tags" in defaults:
            existing_tags = conversation.extracted_info.get("tags", [])
            conversation.extracted_info["tags"] = list(set(existing_tags + defaults["tags"]))

        if "effort" in defaults and "estimated_effort" not in conversation.extracted_info:
            conversation.extracted_info["estimated_effort"] = defaults["effort"]

        if "deadline_hours" in defaults and "deadline" not in conversation.extracted_info:
            from datetime import datetime, timedelta
            deadline = datetime.now() + timedelta(hours=defaults["deadline_hours"])
            conversation.extracted_info["deadline"] = deadline.isoformat()

        # Store template info
        conversation.extracted_info["_template_applied"] = template_name

        logger.info(f"Applied template '{template_name}' with defaults: {defaults}")

        return {
            "template_name": template_name,
            "applied_defaults": defaults,
            "description": matched_template.get("description", "")
        }

    async def find_potential_dependencies(
        self,
        task_description: str,
        assignee: str = None
    ) -> List[Dict[str, Any]]:
        """
        Find pending/in-progress tasks that might be dependencies.

        Uses AI to detect if the new task relates to existing tasks.
        Returns list of potential blocking tasks.
        """
        from ..integrations.sheets import get_sheets_integration

        sheets = get_sheets_integration()
        all_tasks = await sheets.get_all_tasks()

        # Filter to only pending/in-progress/blocked tasks
        active_tasks = [
            t for t in all_tasks
            if t.get('Status') in ['pending', 'in_progress', 'blocked', 'in_review']
        ]

        if not active_tasks:
            return []

        # Use AI to find related tasks
        try:
            prompt = f"""Analyze if this new task might depend on any existing tasks.

NEW TASK: "{task_description}"
{f"ASSIGNEE: {assignee}" if assignee else ""}

EXISTING ACTIVE TASKS:
"""
            for task in active_tasks[:15]:  # Limit to 15 tasks
                prompt += f"- {task.get('ID', 'N/A')}: {task.get('Title', '')} (Status: {task.get('Status', '')}, Assignee: {task.get('Assignee', 'Unassigned')})\n"

            prompt += """
Return JSON with tasks that the new task might need to wait for:
{
    "potential_dependencies": [
        {"task_id": "TASK-XXX", "reason": "Brief explanation why this might be a dependency"}
    ],
    "explanation": "Overall assessment"
}

Only include tasks that are clearly related. Return empty array if no dependencies found.
"""

            response = await self.ai.client.chat.completions.create(
                model=self.ai.model,
                messages=[
                    {"role": "system", "content": "You identify task dependencies. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )

            import json
            result = json.loads(response.choices[0].message.content)
            dependencies = result.get("potential_dependencies", [])

            logger.info(f"Found {len(dependencies)} potential dependencies for new task")
            return dependencies

        except Exception as e:
            logger.error(f"Error finding dependencies: {e}")
            return []

    async def analyze_and_decide(
        self,
        conversation: ConversationState,
        preferences: Dict[str, Any],
        team_info: Dict[str, str]
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Analyze the task request and decide whether to ask questions.

        Returns:
            Tuple of (should_ask_questions, analysis_result)
        """
        # First, detect and apply templates
        template_info = self.detect_and_apply_template(conversation, preferences)
        if template_info:
            logger.info(f"Template detected: {template_info['template_name']}")

        # Get analysis from AI
        analysis = await self.ai.analyze_task_request(
            user_message=conversation.original_message,
            preferences=preferences,
            team_info=team_info,
            conversation_history=conversation.get_conversation_context()
        )

        # Add template info to analysis
        if template_info:
            analysis["template_applied"] = template_info

        # Store extracted info in conversation
        if "understood" in analysis:
            conversation.extracted_info.update(analysis["understood"])

        # Check if we have enough information
        can_proceed = analysis.get("can_proceed_without_questions", False)

        # Normalize suggested_questions to dict format early
        # AI may return strings or dicts, we need dicts for filtering
        raw_questions = analysis.get("suggested_questions", [])
        normalized_questions = []
        for q in raw_questions:
            if isinstance(q, str):
                normalized_questions.append({"question": q, "field": "general"})
            elif isinstance(q, dict):
                normalized_questions.append(q)
        analysis["suggested_questions"] = normalized_questions

        # Apply preference overrides
        can_proceed = self._apply_preference_logic(analysis, preferences, can_proceed)

        # Check urgency - if very urgent, minimize questions
        if conversation.is_urgent or self._detect_high_urgency(analysis):
            # For urgent tasks, only ask critical questions
            analysis["suggested_questions"] = self._filter_critical_questions(
                analysis.get("suggested_questions", [])
            )
            if not analysis["suggested_questions"]:
                can_proceed = True

        return not can_proceed, analysis

    def _apply_preference_logic(
        self,
        analysis: Dict[str, Any],
        preferences: Dict[str, Any],
        can_proceed: bool
    ) -> bool:
        """Apply user preferences to modify question logic."""

        # Check if user has set "always ask about X"
        always_ask = preferences.get("always_ask", [])
        skip_questions_for = preferences.get("skip_questions_for", [])

        confidence = analysis.get("confidence", {})
        suggested_questions = analysis.get("suggested_questions", [])  # Already normalized

        # Remove questions for fields user wants to skip
        filtered_questions = [
            q for q in suggested_questions
            if q.get("field") not in skip_questions_for
        ]

        # Add questions for fields user always wants asked (if not already high confidence)
        for field in always_ask:
            if confidence.get(field, 0) < 0.9:
                # Check if question for this field already exists
                existing = any(q.get("field") == field for q in filtered_questions)
                if not existing:
                    filtered_questions.append({
                        "field": field,
                        "question": f"What should the {field} be?",
                        "options": self._get_default_options(field)
                    })

        analysis["suggested_questions"] = filtered_questions

        # If we have questions to ask, we shouldn't proceed
        if filtered_questions:
            return False

        return can_proceed

    def _get_default_options(self, field: str) -> List[str]:
        """Get default options for common fields."""
        defaults = {
            "priority": ["High - needed urgently", "Medium - this week", "Low - when available"],
            "deadline": ["Today EOD", "Tomorrow", "End of week", "No deadline"],
            "task_type": ["Bug fix", "New feature", "Research/Investigation", "General task"]
        }
        return defaults.get(field, [])

    def _detect_high_urgency(self, analysis: Dict[str, Any]) -> bool:
        """Detect if the task has high urgency signals."""
        urgency_signals = analysis.get("urgency_signals", [])
        high_urgency_keywords = ["asap", "urgent", "immediately", "critical", "blocker", "emergency"]

        return any(
            keyword in signal.lower()
            for signal in urgency_signals
            for keyword in high_urgency_keywords
        )

    def _filter_critical_questions(
        self,
        questions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter to only the most critical questions for urgent tasks."""
        critical_fields = ["assignee", "deadline"]  # Priority is implied by urgency
        return [q for q in questions if q.get("field") in critical_fields][:2]

    async def generate_question_message(
        self,
        analysis: Dict[str, Any],
        preferences: Dict[str, Any]
    ) -> Tuple[str, List[ClarifyingQuestion]]:
        """
        Generate a natural question message for the user.

        Returns:
            Tuple of (message_text, list_of_questions)
        """
        questions_data = await self.ai.generate_clarifying_questions(
            analysis=analysis,
            preferences=preferences,
            max_questions=self.max_questions_per_round
        )

        intro = questions_data.get("intro_message", "A few quick questions:")
        questions = questions_data.get("questions", [])

        if not questions:
            return "I think I have everything I need. Let me generate the task spec.", []

        # Build the message
        message_parts = [intro, ""]

        clarifying_questions = []
        for i, q in enumerate(questions, 1):
            question_text = q.get("text", "")
            options = q.get("options", [])

            message_parts.append(f"{i}. {question_text}")

            if options:
                for j, opt in enumerate(options, 1):
                    message_parts.append(f"   {chr(64+j)}) {opt}")

            if q.get("allow_custom", True):
                message_parts.append("   (or type your own answer)")

            message_parts.append("")

            clarifying_questions.append(ClarifyingQuestion(
                question=question_text,
                options=options
            ))

        message_parts.append("Reply with your answers, or /skip to use defaults, or /done to finish.")

        return "\n".join(message_parts), clarifying_questions

    async def process_user_answers(
        self,
        conversation: ConversationState,
        user_response: str
    ) -> Dict[str, Any]:
        """
        Process user's answers to clarifying questions.

        Handles:
        - Multiple answers in one message
        - Option selections (A, B, C)
        - Custom text answers
        - Partial answers
        """
        updates = {}

        # Get pending questions
        pending_questions = [
            q for q in conversation.questions_asked
            if q.answer is None and not q.skipped
        ]

        if not pending_questions:
            return updates

        # Try to parse answers
        lines = user_response.strip().split("\n")
        answers = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for option selection (A, B, C, etc.)
            if len(line) == 1 and line.upper() in "ABCDEFGH":
                option_index = ord(line.upper()) - ord("A")
                answers.append(("option", option_index))
            # Check for numbered answer (1. answer, 2. answer)
            elif line[0].isdigit() and "." in line[:3]:
                answer_text = line.split(".", 1)[1].strip()
                answers.append(("text", answer_text))
            else:
                # Plain text answer
                answers.append(("text", line))

        # Match answers to questions
        for i, (answer_type, answer_value) in enumerate(answers):
            if i >= len(pending_questions):
                break

            question = pending_questions[i]

            if answer_type == "option" and answer_value < len(question.options):
                actual_answer = question.options[answer_value]
            else:
                actual_answer = str(answer_value)

            # Process the answer through AI to extract structured info
            result = await self.ai.process_answer(
                question=question.question,
                answer=actual_answer,
                current_info=conversation.extracted_info,
                field=self._infer_field_from_question(question.question)
            )

            # Update conversation
            question.answer = actual_answer
            question.answered_at = datetime.now()

            # Store extracted value
            if result.get("extracted_value"):
                field = result.get("field", "unknown")
                conversation.extracted_info[field] = result["extracted_value"]
                updates[field] = result["extracted_value"]

        return updates

    def _infer_field_from_question(self, question: str) -> str:
        """Infer which field a question is about."""
        question_lower = question.lower()

        field_keywords = {
            "priority": ["priority", "urgent", "important"],
            "deadline": ["deadline", "when", "due", "by when", "timeframe"],
            "assignee": ["who", "assign", "person", "team member"],
            "description": ["describe", "details", "what", "scope"],
            "acceptance_criteria": ["criteria", "done when", "requirements"],
        }

        for field, keywords in field_keywords.items():
            if any(kw in question_lower for kw in keywords):
                return field

        return "other"

    async def generate_spec_preview(
        self,
        conversation: ConversationState,
        preferences: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate the task specification and format it as a preview.

        Returns:
            Tuple of (preview_message, spec_dict)
        """
        # Generate the spec
        spec = await self.ai.generate_task_spec(
            original_message=conversation.original_message,
            qa_pairs=conversation.get_qa_summary(),
            preferences=preferences,
            extracted_info=conversation.extracted_info
        )

        # Store in conversation
        conversation.generated_spec = spec

        # Format as preview message
        preview = await self._format_preview_message(spec)

        return preview, spec

    async def _format_preview_message(self, spec: Dict[str, Any]) -> str:
        """Format spec as a readable preview message."""
        priority_emoji = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "urgent": "🔴"
        }

        lines = [
            "📋 **Task Preview**",
            "",
            f"**Title:** {spec.get('title', 'Untitled')}",
            f"**Assignee:** {spec.get('assignee', 'Unassigned')}",
            f"**Priority:** {priority_emoji.get(spec.get('priority', 'medium'), '🟡')} {spec.get('priority', 'medium').upper()}",
        ]

        if spec.get("deadline"):
            lines.append(f"**Deadline:** {spec.get('deadline')}")

        if spec.get("estimated_effort"):
            lines.append(f"**Estimated Effort:** {spec.get('estimated_effort')}")

        lines.extend(["", f"**Description:**", spec.get("description", "No description"), ""])

        # Show subtasks if present
        subtasks = spec.get("subtasks", [])
        if subtasks:
            lines.append(f"**Subtasks ({len(subtasks)}):**")
            for i, st in enumerate(subtasks, 1):
                title = st.get("title", f"Subtask {i}") if isinstance(st, dict) else str(st)
                lines.append(f"  {i}. {title}")
            lines.append("")

        criteria = spec.get("acceptance_criteria", [])
        if criteria:
            lines.append("**Acceptance Criteria:**")
            for c in criteria:
                lines.append(f"☐ {c}")
            lines.append("")

        # Show notes if present
        notes = spec.get("notes")
        if notes and notes != "null":
            lines.append(f"**Notes:** {notes}")
            lines.append("")

        lines.extend([
            "---",
            "Reply ✅ to confirm and create this task",
            "Or tell me what to change"
        ])

        return "\n".join(lines)

    def should_finalize_with_defaults(
        self,
        conversation: ConversationState,
        preferences: Dict[str, Any]
    ) -> bool:
        """Check if we should auto-finalize with defaults."""
        # Check timeout
        if conversation.should_auto_finalize():
            return True

        # Check if skip was requested
        if conversation.skip_requested:
            return True

        return False

    def apply_defaults(
        self,
        conversation: ConversationState,
        preferences: Dict[str, Any]
    ) -> None:
        """Apply default values from preferences to missing fields."""
        defaults = preferences.get("defaults", {})

        if "priority" not in conversation.extracted_info:
            conversation.extracted_info["priority"] = defaults.get("priority", "medium")

        if "deadline" not in conversation.extracted_info:
            default_deadline = defaults.get("deadline_behavior", "next_business_day")
            # Would calculate actual deadline based on this
            conversation.extracted_info["deadline_behavior"] = default_deadline

        # Mark unanswered questions as skipped
        for q in conversation.questions_asked:
            if q.answer is None:
                q.skipped = True
