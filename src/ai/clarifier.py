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

        # v2.2: Role-based defaults for smarter self-answering
        self.role_defaults = {
            "developer": {
                "task_type": "feature",
                "priority": "medium",
                "effort": "4h",
                "tags": ["dev", "code"],
            },
            "admin": {
                "task_type": "task",
                "priority": "medium",
                "effort": "2h",
                "tags": ["admin", "process"],
            },
            "marketing": {
                "task_type": "task",
                "priority": "medium",
                "effort": "3h",
                "tags": ["marketing", "content"],
            },
            "design": {
                "task_type": "design",
                "priority": "medium",
                "effort": "6h",
                "tags": ["design", "ui"],
            }
        }

    def _calculate_task_complexity(self, message: str, analysis: Dict[str, Any]) -> int:
        """
        v2.2: Calculate task complexity score (1-10).

        1-3: Simple (fix typo, small change) → No questions
        4-6: Medium (feature, refactor) → 1-2 critical questions only
        7-10: Complex (new system, integration) → Full clarification
        """
        score = 3  # Base score
        message_lower = message.lower()

        # Increase for complexity signals
        complex_keywords = ['system', 'architecture', 'integration', 'design', 'build', 'create', 'implement']
        if any(word in message_lower for word in complex_keywords):
            score += 2

        scope_keywords = ['multiple', 'several', 'complex', 'comprehensive', 'complete', 'full']
        if any(word in message_lower for word in scope_keywords):
            score += 2

        # Long messages indicate more complexity
        if len(message) > 300:
            score += 2
        elif len(message) > 150:
            score += 1

        # Multiple items/subtasks
        if 'subtask' in message_lower or message.count(',') > 4:
            score += 2
        elif message.count(',') > 2:
            score += 1

        # Technical terms
        tech_keywords = ['api', 'database', 'migration', 'authentication', 'payment', 'notification']
        if any(word in message_lower for word in tech_keywords):
            score += 1

        # Decrease for simplicity signals
        simple_keywords = ['fix', 'typo', 'small', 'quick', 'simple', 'minor', 'update', 'change']
        if any(word in message_lower for word in simple_keywords):
            score -= 2

        skip_keywords = ['no questions', 'just do', 'straightforward', 'no need to ask', 'dont ask']
        if any(phrase in message_lower for phrase in skip_keywords):
            score -= 3

        # If "no questions" is explicitly said, force simple
        if 'no question' in message_lower:
            score = min(score, 3)

        # Clamp to 1-10
        return max(1, min(10, score))

    def _get_role_defaults(self, assignee: str) -> Dict[str, Any]:
        """v2.2: Get smart defaults based on assignee's role."""
        # Try to look up role from team data
        role = self._lookup_assignee_role(assignee)
        if not role:
            return self.role_defaults["developer"]  # Default

        role_lower = role.lower()
        if any(k in role_lower for k in ["dev", "engineer", "backend", "frontend", "programmer"]):
            return self.role_defaults["developer"]
        elif any(k in role_lower for k in ["admin", "manager", "lead", "director", "coordinator"]):
            return self.role_defaults["admin"]
        elif any(k in role_lower for k in ["market", "content", "social", "growth", "seo"]):
            return self.role_defaults["marketing"]
        elif any(k in role_lower for k in ["design", "ui", "ux", "graphic", "creative"]):
            return self.role_defaults["design"]

        return self.role_defaults["developer"]

    def _lookup_assignee_role(self, assignee: str) -> Optional[str]:
        """Look up assignee's role from team configuration."""
        if not assignee:
            return None

        try:
            # Try to get from team config
            from ..config.team import TEAM_MEMBERS
            assignee_lower = assignee.lower()
            for member in TEAM_MEMBERS:
                if member.get("name", "").lower() == assignee_lower:
                    return member.get("role", "")
        except Exception:
            pass

        return None

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
        team_info: Dict[str, str],
        detailed_mode: bool = False
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Analyze the task request and decide whether to ask questions.

        INTELLIGENT LOOP: AI tries to answer its own questions first using
        context and best practices. Only asks user for truly ambiguous things.

        Args:
            detailed_mode: If True (SPECSHEETS), generate comprehensive PRD

        Returns:
            Tuple of (should_ask_questions, analysis_result)
        """
        message = conversation.original_message

        # EARLY EXIT: Check if user explicitly says "no questions"
        no_question_phrases = [
            "no need to ask", "don't ask", "dont ask", "no questions",
            "just use what", "use what i'm giving", "use what im giving",
            "already gave you", "i've given you", "ive given you",
            "don't need questions", "skip questions", "no need for questions"
        ]
        message_lower = message.lower()
        user_said_no_questions = any(phrase in message_lower for phrase in no_question_phrases)

        if user_said_no_questions:
            logger.info("User explicitly said no questions - will skip ALL questions")

        # First, detect and apply templates
        template_info = self.detect_and_apply_template(conversation, preferences)
        if template_info:
            logger.info(f"Template detected: {template_info['template_name']}")

        # Get initial analysis from AI
        analysis = await self.ai.analyze_task_request(
            user_message=message,
            preferences=preferences,
            team_info=team_info,
            conversation_history=conversation.get_conversation_context()
        )

        # Add template info to analysis
        if template_info:
            analysis["template_applied"] = template_info

        # Store extracted info in conversation
        if "understood" in analysis:
            understood = analysis["understood"]
            # Ensure understood is a dict (AI sometimes returns string)
            if isinstance(understood, dict):
                conversation.extracted_info.update(understood)
            else:
                logger.warning(f"AI returned non-dict 'understood': {type(understood)} - {understood}")

        # Mark detailed mode in analysis
        analysis["detailed_mode"] = detailed_mode

        # ==================== INTELLIGENT SELF-ANSWERING LOOP ====================
        # Instead of asking user, try to answer questions ourselves first
        # using context, best practices, and intelligent inference

        suggested_questions = analysis.get("suggested_questions", [])
        missing_info = analysis.get("missing_info", [])

        if suggested_questions or missing_info:
            logger.info(f"AI identified {len(suggested_questions)} questions, {len(missing_info)} missing fields")

            # Try to self-answer using AI intelligence
            self_answered, remaining_questions = await self._intelligent_self_answer(
                original_message=message,
                analysis=analysis,
                preferences=preferences,
                team_info=team_info,
                detailed_mode=detailed_mode
            )

            if self_answered and isinstance(self_answered, dict):
                # Merge self-answered info into analysis
                if "understood" not in analysis or not isinstance(analysis["understood"], dict):
                    analysis["understood"] = {}
                analysis["understood"].update(self_answered)
                conversation.extracted_info.update(self_answered)
                logger.info(f"AI self-answered {len(self_answered)} fields: {list(self_answered.keys())}")

            # Update questions to only what AI couldn't answer
            analysis["suggested_questions"] = remaining_questions
            analysis["missing_info"] = [m for m in missing_info if m not in self_answered]

        # ==================== END INTELLIGENT LOOP ====================

        # Check if we can proceed now
        can_proceed = analysis.get("can_proceed_without_questions", False)

        # Normalize remaining questions
        raw_questions = analysis.get("suggested_questions", [])
        normalized_questions = []
        for q in raw_questions:
            if isinstance(q, str):
                normalized_questions.append({"question": q, "field": "general"})
            elif isinstance(q, dict):
                normalized_questions.append(q)
        analysis["suggested_questions"] = normalized_questions

        # v2.2: SMART COMPLEXITY-BASED QUESTION LOGIC
        # Simple tasks → No questions (self-answer)
        # Medium tasks → 1-2 critical questions only
        # Complex tasks → Full clarification
        complexity = self._calculate_task_complexity(
            conversation.original_message,
            analysis
        )
        analysis["complexity"] = complexity
        analysis["complexity_level"] = "simple" if complexity <= 3 else "medium" if complexity <= 6 else "complex"

        if complexity <= 3:
            # Simple task - self-answer everything, no questions
            can_proceed = True
            analysis["suggested_questions"] = []
            logger.info(f"Simple task (complexity={complexity}) - skipping all questions")
        elif complexity <= 6:
            # Medium task - ask only critical questions (max 2)
            critical_questions = self._filter_critical_questions(normalized_questions)[:2]
            if critical_questions:
                can_proceed = False
                analysis["suggested_questions"] = critical_questions
                logger.info(f"Medium task (complexity={complexity}) - asking {len(critical_questions)} critical questions")
            else:
                can_proceed = True
                analysis["suggested_questions"] = []
                logger.info(f"Medium task (complexity={complexity}) - no critical questions, proceeding")
        else:
            # Complex task - full clarification (max 4 questions)
            if normalized_questions:
                can_proceed = False
                analysis["suggested_questions"] = normalized_questions[:4]
                logger.info(f"Complex task (complexity={complexity}) - asking {len(analysis['suggested_questions'])} questions")
            else:
                can_proceed = True
                analysis["suggested_questions"] = []
                logger.info(f"Complex task (complexity={complexity}) - no questions available, proceeding")

        # Apply preference overrides (only for non-detailed mode)
        if not detailed_mode:
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

    def _is_comprehensive_message(self, message: str) -> bool:
        """
        Detect if a message is comprehensive enough to skip questions.

        A message is comprehensive if it contains:
        - Detailed description (multiple sentences or long text)
        - Feature specifications
        - User flows or technical details
        """
        # Check word count - detailed messages have more words
        word_count = len(message.split())
        if word_count > 30:
            logger.debug(f"Message is comprehensive: {word_count} words")
            return True

        # Check for multiple sentences (indicates detailed description)
        sentence_count = len([s for s in message.replace("...", ".").split(".") if s.strip()])
        if sentence_count >= 3:
            logger.debug(f"Message is comprehensive: {sentence_count} sentences")
            return True

        # Check for feature-like keywords indicating detailed spec
        feature_keywords = [
            "users can", "user can", "should be able to", "must be able to",
            "when the user", "the system should", "feature", "functionality",
            "integration", "connect to", "api", "database", "the flow",
            "step 1", "step 2", "first,", "then,", "finally,",
            "requirements:", "acceptance criteria", "spec:"
        ]
        message_lower = message.lower()
        if any(kw in message_lower for kw in feature_keywords):
            logger.debug("Message is comprehensive: contains feature keywords")
            return True

        return False

    async def _intelligent_self_answer(
        self,
        original_message: str,
        analysis: Dict[str, Any],
        preferences: Dict[str, Any],
        team_info: Dict[str, str],
        detailed_mode: bool = False
    ) -> Tuple[Dict[str, Any], List[Dict]]:
        """
        INTELLIGENT SELF-ANSWERING LOOP

        AI tries to answer its own questions using:
        1. Context from the original message
        2. Best practices for the task type
        3. Industry standards
        4. Logical inference

        Returns:
            Tuple of (self_answered_fields, remaining_questions_for_user)
        """
        questions = analysis.get("suggested_questions", [])
        missing_info = analysis.get("missing_info", [])

        if not questions and not missing_info:
            return {}, []

        # Build prompt for AI to self-answer EVERYTHING - NEVER ask user
        prompt = f"""You are a DECISIVE AI assistant. Your job is to ANSWER ALL QUESTIONS YOURSELF.
NEVER return questions for the user. Fill in ALL missing information using best practices.

ORIGINAL TASK REQUEST:
"{original_message}"

CURRENT ANALYSIS:
{analysis.get("understood", {})}

QUESTIONS THAT NEED TO BE SELF-ANSWERED (DO NOT ASK USER):
{questions}

MISSING INFORMATION TO FILL IN:
{missing_info}

MANDATORY SELF-ANSWERING RULES:
- Priority: Default "medium". Use "high" if urgent/ASAP/critical mentioned. Use "low" if "when you can"
- Deadline: Extract from message. If none, leave null (don't guess)
- Effort: Simple task=2-4 hours, Medium feature=1-2 days, Complex system=1-2 weeks
- Architecture: ALWAYS pick industry-standard, flexible approach
- Scope: Include core features for v1. Edge cases are "nice to have"
- Technical: Pick proven, maintainable solutions
- UI/UX: Modern, clean, user-friendly defaults
- Integration: Standard REST APIs, webhooks where needed
- Testing: Include basic happy path tests

YOU MUST ANSWER EVERYTHING. The boss is busy and WILL NOT answer questions.
Use your best judgment based on context + best practices.

Respond with JSON:
{{
    "self_answered": {{
        "priority": "medium/high/low based on context",
        "estimated_effort": "realistic time estimate",
        "technical_approach": "your recommended approach",
        "architecture": "system design decisions",
        "scope": "what's included in v1",
        "acceptance_criteria_additions": ["any criteria you'd add"],
        "implementation_notes": "helpful notes for developer"
    }},
    "remaining_questions": [],
    "reasoning": "Brief explanation of your decisions"
}}

CRITICAL: remaining_questions MUST be empty array []. Answer EVERYTHING yourself."""

        try:
            response = await self.ai._call_api(
                messages=[
                    {"role": "system", "content": "You are a decisive AI that makes smart decisions based on context and best practices."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            import json
            result = json.loads(response)

            self_answered = result.get("self_answered", {})
            remaining = result.get("remaining_questions", [])
            reasoning = result.get("reasoning", "")

            if reasoning:
                logger.info(f"AI self-answer reasoning: {reasoning[:200]}...")

            return self_answered, remaining

        except Exception as e:
            logger.error(f"Error in intelligent self-answer: {e}")
            # On error, don't ask questions - just proceed with what we have
            return {}, []

    async def generate_question_message(
        self,
        analysis: Dict[str, Any],
        preferences: Dict[str, Any],
        detailed_mode: bool = False
    ) -> Tuple[str, List[ClarifyingQuestion]]:
        """
        Generate a natural question message for the user.

        Args:
            detailed_mode: If True, generate PRD-focused questions for spec sheets

        Returns:
            Tuple of (message_text, list_of_questions)
        """
        # For detailed mode, generate PRD-specific questions
        if detailed_mode or analysis.get("detailed_mode") or analysis.get("force_prd_questions"):
            questions_data = await self._generate_prd_questions(analysis, preferences)
        else:
            questions_data = await self.ai.generate_clarifying_questions(
                analysis=analysis,
                preferences=preferences,
                max_questions=self.max_questions_per_round
            )

        intro = questions_data.get("intro_message", "A few quick questions:")
        questions = questions_data.get("questions", [])

        if not questions:
            if detailed_mode:
                return "I have enough context. Let me generate a comprehensive spec sheet.", []
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

        if detailed_mode:
            message_parts.append("Answer these questions, or /skip to let me make assumptions, or /done to generate the PRD now.")
        else:
            message_parts.append("Reply with your answers, or /skip to use defaults, or /done to finish.")

        return "\n".join(message_parts), clarifying_questions

    async def _generate_prd_questions(
        self,
        analysis: Dict[str, Any],
        preferences: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate PRD-focused questions for comprehensive spec sheets.

        These questions focus on:
        - Technical architecture and approach
        - User flows and interactions
        - Data models and APIs
        - Integration points
        - Success criteria
        """
        understood = analysis.get("understood", {})

        # Use AI to generate smart PRD questions
        prompt = f"""You are helping create a comprehensive PRD (Product Requirements Document).

TASK REQUEST: {understood.get('task_description', 'Unknown task')}
ASSIGNEE: {understood.get('assignee', 'Not specified')}
CONTEXT: {analysis}

Generate 3-5 intelligent questions to gather requirements for a detailed spec sheet.
Focus on:
1. **Technical Approach**: How should this be built? What's the architecture?
2. **User Experience**: What's the user flow? What should users see/do?
3. **Data & Integration**: What data is needed? What systems does this connect to?
4. **Scope & Priorities**: What's must-have vs nice-to-have? Any constraints?
5. **Success Criteria**: How do we know it's done right? What metrics matter?

DON'T ask about basic things like priority or deadline - focus on REQUIREMENTS.

Return JSON:
{{
    "intro_message": "Let me understand the requirements better for this spec sheet:",
    "questions": [
        {{
            "text": "Smart, specific question about requirements",
            "options": ["Option A", "Option B", "Option C"],
            "allow_custom": true
        }}
    ]
}}

Make questions conversational and intelligent, like a senior developer or product manager would ask."""

        try:
            response = await self.ai._call_api(
                messages=[
                    {"role": "system", "content": "You generate intelligent PRD questions. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )

            import json
            return json.loads(response)
        except Exception as e:
            logger.error(f"Error generating PRD questions: {e}")
            # Fallback questions
            return {
                "intro_message": "Let me understand the requirements better:",
                "questions": [
                    {
                        "text": "What's the main user flow or workflow you envision?",
                        "options": [],
                        "allow_custom": True
                    },
                    {
                        "text": "Are there specific technical requirements or constraints?",
                        "options": ["Use existing stack", "New technology needed", "No constraints"],
                        "allow_custom": True
                    },
                    {
                        "text": "What systems or services does this need to integrate with?",
                        "options": [],
                        "allow_custom": True
                    }
                ]
            }

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
        # Check if detailed mode was set by handler (from intent detection)
        detailed_mode = conversation.extracted_info.get("_detailed_mode", False)

        # Also detect SPECSHEETS keyword in message as fallback
        if not detailed_mode:
            message_lower = conversation.original_message.lower()
            detailed_mode = any(kw in message_lower for kw in [
                "specsheet", "spec sheet", "detailed spec", "detailed for:",
                "full spec", "comprehensive", "with details", "more developed", "more detailed"
            ])

        # Generate the spec
        spec = await self.ai.generate_task_spec(
            original_message=conversation.original_message,
            qa_pairs=conversation.get_qa_summary(),
            preferences=preferences,
            extracted_info=conversation.extracted_info,
            detailed_mode=detailed_mode  # Pass flag for detailed generation
        )

        # VALIDATION: Ensure spec actually uses content from user's message
        # This catches AI hallucination where it generates completely unrelated content
        spec = self._validate_and_fix_spec(spec, conversation.original_message)

        # Store in conversation
        conversation.generated_spec = spec

        # Format as preview message (pass detailed_mode for different formatting)
        preview = await self._format_preview_message(spec, detailed_mode)

        return preview, spec

    def _validate_and_fix_spec(self, spec: Dict[str, Any], original_message: str) -> Dict[str, Any]:
        """
        Validate that the generated spec actually relates to the user's input.
        If AI hallucinated completely unrelated content, fix it using deterministic extraction.
        Also ensures assignee is extracted from [For Name] prefix if present.
        """
        import re

        # Extract assignee from [For Name] prefix if present
        assignee_match = re.match(r'^\[For (\w+)\]', original_message, re.IGNORECASE)
        if assignee_match:
            extracted_assignee = assignee_match.group(1).capitalize()
            if not spec.get('assignee') or spec.get('assignee') == 'Unassigned':
                spec['assignee'] = extracted_assignee
                logger.info(f"Extracted assignee from prefix: {extracted_assignee}")

        # Extract significant words from original message (ignore common words)
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
            'during', 'before', 'after', 'above', 'below', 'between', 'under',
            'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where',
            'why', 'how', 'all', 'each', 'few', 'more', 'most', 'other', 'some',
            'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
            'too', 'very', 'just', 'and', 'but', 'or', 'if', 'because', 'until',
            'while', 'about', 'against', 'this', 'that', 'these', 'those', 'am',
            'it', 'its', 'he', 'she', 'they', 'them', 'his', 'her', 'their',
            'what', 'which', 'who', 'whom', 'i', 'me', 'my', 'we', 'our', 'you',
            'your', 'one', 'two', 'first', 'second', 'third', 'fourth', 'fifth',
            'sixth', 'task', 'tasks', 'please', 'pleased', 'today', 'tonight',
            'tomorrow', 'questions', 'question', 'mayank', 'sarah', 'john', 'minty'
        }

        # Clean the "[For Name]" prefix if present
        clean_message = re.sub(r'^\[For \w+\]\s*', '', original_message, flags=re.IGNORECASE)

        # Get significant words from original message
        original_words = set(
            word.lower() for word in re.findall(r'\b\w+\b', clean_message)
            if len(word) > 2 and word.lower() not in stop_words
        )

        # Get words from generated title
        title = spec.get('title', '')
        title_words = set(
            word.lower() for word in re.findall(r'\b\w+\b', title)
            if len(word) > 2 and word.lower() not in stop_words
        )

        # Check overlap - at least some significant words should match
        overlap = original_words & title_words
        overlap_ratio = len(overlap) / max(len(original_words), 1)

        logger.debug(f"Spec validation: original_words={original_words}, title_words={title_words}, overlap={overlap}, ratio={overlap_ratio:.2f}")

        # If very low overlap, AI probably hallucinated - use deterministic extraction
        if overlap_ratio < 0.1 and len(original_words) > 3:
            logger.warning(f"AI hallucination detected! Title '{title}' doesn't match input. Using fallback extraction.")

            # Create a simple, direct title from the original message
            # Remove common prefixes and clean up
            fallback_title = clean_message

            # Remove time references at the start
            fallback_title = re.sub(r'^(for today|today|tonight at \d+\s*(?:am|pm)?|tonight)\s*', '', fallback_title, flags=re.IGNORECASE)

            # Capitalize first letter and limit length
            fallback_title = fallback_title.strip()
            if fallback_title:
                fallback_title = fallback_title[0].upper() + fallback_title[1:]

            # Truncate if too long
            if len(fallback_title) > 100:
                fallback_title = fallback_title[:97] + "..."

            spec['title'] = fallback_title
            spec['description'] = clean_message  # Use original as description too
            spec['_fallback_extraction'] = True

            logger.info(f"Fallback title: '{fallback_title}'")

        return spec

    async def _format_preview_message(self, spec: Dict[str, Any], detailed_mode: bool = False) -> str:
        """Format spec as a readable preview message."""
        priority_emoji = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "urgent": "🔴"
        }

        if detailed_mode:
            # AI Assistant style for SPECSHEETS - more conversational
            lines = [
                "📋 **Spec Sheet Ready**",
                "",
                f"I've prepared a comprehensive specification for **{spec.get('assignee', 'the assignee')}**:",
                "",
                f"**{spec.get('title', 'Untitled')}**",
                f"Priority: {priority_emoji.get(spec.get('priority', 'medium'), '🟡')} {spec.get('priority', 'medium').upper()} | Effort: {spec.get('estimated_effort', 'TBD')}",
            ]

            if spec.get("deadline"):
                lines.append(f"Deadline: {spec.get('deadline')}")

            lines.extend(["", "**Overview:**", spec.get("description", "No description")[:500] + "..." if len(spec.get("description", "")) > 500 else spec.get("description", "No description"), ""])

            # Show subtasks count
            subtasks = spec.get("subtasks", [])
            criteria = spec.get("acceptance_criteria", [])
            if subtasks or criteria:
                summary = []
                if subtasks:
                    summary.append(f"{len(subtasks)} implementation tasks")
                if criteria:
                    summary.append(f"{len(criteria)} acceptance criteria")
                lines.append(f"📊 Includes: {' and '.join(summary)}")
                lines.append("")

            lines.extend([
                "---",
                "When confirmed, this will be posted to Discord as a **forum thread spec sheet** with full details.",
                "",
                "Reply **yes** to create | Or tell me what to change"
            ])
        else:
            # Standard task preview (non-detailed)
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
