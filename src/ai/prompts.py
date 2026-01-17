"""Prompt templates for DeepSeek AI interactions."""

from typing import Dict, Any, List, Optional


class PromptTemplates:
    """Collection of prompt templates for the task workflow system."""

    SYSTEM_PROMPT = """You are a smart task management assistant helping a boss delegate work to their team.
Your job is to:
1. Analyze task requests and identify missing information
2. Ask smart, concise clarifying questions when needed
3. Generate detailed, actionable task specifications

IMPORTANT GUIDELINES:
- Be concise and professional
- Ask only necessary questions (1-3 max per round)
- Offer multiple-choice options when appropriate
- Use the user's preferences to minimize questions
- Detect urgency signals and task types automatically
- Generate specs with clear acceptance criteria

You have access to the user's preferences and team information to help fill in gaps."""

    @staticmethod
    def analyze_task_prompt(
        user_message: str,
        preferences: Dict[str, Any],
        team_info: Dict[str, str],
        conversation_history: str = ""
    ) -> str:
        """Generate prompt to analyze a task request and identify missing info."""

        pref_str = "\n".join([f"- {k}: {v}" for k, v in preferences.items()]) if preferences else "None set"
        team_str = "\n".join([f"- {name}: {role}" for name, role in team_info.items()]) if team_info else "None defined"

        return f"""Analyze this task request and extract all information. BE DECISIVE - proceed without questions when possible.

USER'S MESSAGE:
"{user_message}"

USER'S PREFERENCES:
{pref_str}

TEAM MEMBERS:
{team_str}

{f"CONVERSATION HISTORY:{chr(10)}{conversation_history}" if conversation_history else ""}

CRITICAL RULES:
1. If an assignee is mentioned (name like "Mayank", "John", etc.), EXTRACT IT - don't ask about it
2. If a deadline is mentioned ("by tomorrow", "today", "next week"), EXTRACT IT - don't ask about it
3. If priority signals exist ("urgent", "ASAP", "when you can"), INFER IT - don't ask about it
4. DEFAULT priority to "medium" if not specified - don't ask unless truly ambiguous
5. ONLY ask questions if something is TRULY UNCLEAR, not just unspecified

SET can_proceed_without_questions=TRUE when:
- Assignee is identified (even partially - match against team members)
- Task action is clear (what needs to be done)
- Priority can be inferred or defaulted

SET can_proceed_without_questions=FALSE ONLY when:
- No assignee can be determined AND it's not a general task
- The action itself is ambiguous (what exactly needs to be done?)

Respond with JSON:
{{
    "understood": {{
        "title": "extracted or inferred title",
        "assignee": "extracted assignee (match against team members, or null if truly unknown)",
        "priority": "low/medium/high/urgent (DEFAULT to medium if not explicit)",
        "deadline": "extracted deadline in ISO format (or null)",
        "description": "extracted description",
        "task_type": "bug/feature/task/research",
        "acceptance_criteria": ["inferred criteria..."]
    }},
    "missing_info": ["ONLY truly missing critical fields"],
    "confidence": {{
        "title": 0.9,
        "assignee": 0.8,
        "priority": 0.8,
        "deadline": 0.5
    }},
    "can_proceed_without_questions": true,
    "urgency_signals": ["any urgency indicators found"],
    "suggested_questions": []
}}

REMEMBER: The boss is busy. Only ask questions if ABSOLUTELY necessary. Default to proceeding."""

    @staticmethod
    def generate_questions_prompt(
        analysis: Dict[str, Any],
        preferences: Dict[str, Any],
        max_questions: int = 3
    ) -> str:
        """Generate natural clarifying questions based on analysis."""

        return f"""Based on this task analysis, generate {max_questions} or fewer clarifying questions.

ANALYSIS:
{analysis}

USER PREFERENCES:
{preferences}

Generate questions that:
1. Are concise and conversational
2. Offer multiple choice options where possible
3. Can be answered quickly
4. Focus on the most impactful missing information

Respond with a JSON object in this exact format:
{{
    "questions": [
        {{
            "text": "The question to ask",
            "options": ["Option A", "Option B", "Option C"],
            "field": "which field this clarifies",
            "allow_custom": true
        }}
    ],
    "intro_message": "Brief friendly intro before questions"
}}"""

    @staticmethod
    def generate_spec_prompt(
        original_message: str,
        qa_pairs: Dict[str, str],
        preferences: Dict[str, Any],
        extracted_info: Dict[str, Any]
    ) -> str:
        """Generate the final task specification."""

        qa_str = "\n".join([f"Q: {q}\nA: {a}" for q, a in qa_pairs.items()]) if qa_pairs else "No additional Q&A"

        return f"""Generate a complete task specification based on all gathered information.

ORIGINAL REQUEST:
"{original_message}"

CLARIFICATION Q&A:
{qa_str}

EXTRACTED INFORMATION:
{extracted_info}

USER PREFERENCES:
{preferences}

Generate a complete task specification as JSON:
{{
    "title": "Clear, actionable title (under 100 chars)",
    "description": "Detailed description of the task, including context and any specific requirements",
    "assignee": "team member name or null",
    "priority": "low/medium/high/urgent",
    "deadline": "ISO datetime or null",
    "task_type": "bug/feature/task/research",
    "estimated_effort": "time estimate (e.g., '2 hours', '1 day')",
    "acceptance_criteria": [
        "Clear, testable criterion 1",
        "Clear, testable criterion 2"
    ],
    "tags": ["relevant", "tags"],
    "notes": "Any additional notes or considerations"
}}

Ensure the spec is:
- Actionable and clear
- Has specific, testable acceptance criteria
- Includes all gathered information
- Uses sensible defaults where information is missing"""

    @staticmethod
    def format_preview_prompt(spec: Dict[str, Any]) -> str:
        """Format spec for preview message to user."""

        return f"""Format this task specification as a concise preview message for Telegram.

SPECIFICATION:
{spec}

Create a formatted message that:
1. Shows all key fields clearly
2. Uses emoji for visual clarity
3. Is easy to read at a glance
4. Ends with confirmation instructions

Format it nicely for Telegram (use markdown sparingly, mainly for bold)."""

    @staticmethod
    def process_answer_prompt(
        question: str,
        answer: str,
        current_info: Dict[str, Any],
        field: str
    ) -> str:
        """Process a user's answer to a clarifying question."""

        return f"""Process this answer to a clarifying question.

QUESTION: {question}
ANSWER: {answer}
FIELD BEING CLARIFIED: {field}
CURRENT INFORMATION: {current_info}

Extract the relevant information from the answer and return a JSON object:
{{
    "field": "{field}",
    "extracted_value": "the value extracted from the answer",
    "confidence": 0.95,
    "needs_followup": false,
    "followup_question": null
}}"""

    @staticmethod
    def daily_standup_prompt(tasks: List[Dict[str, Any]], completed_yesterday: List[Dict[str, Any]]) -> str:
        """Generate daily standup summary."""

        return f"""Generate a daily standup summary for the team.

TODAY'S TASKS:
{tasks}

COMPLETED YESTERDAY:
{completed_yesterday}

Create a concise, motivating daily standup message that:
1. Summarizes yesterday's accomplishments
2. Lists today's priorities by assignee
3. Highlights any urgent or overdue items
4. Is formatted for Discord (markdown supported)

Keep it brief but informative."""

    @staticmethod
    def weekly_summary_prompt(
        weekly_stats: Dict[str, Any],
        tasks_by_status: Dict[str, List],
        team_performance: Dict[str, Any]
    ) -> str:
        """Generate weekly summary report."""

        return f"""Generate a weekly summary report.

WEEKLY STATISTICS:
{weekly_stats}

TASKS BY STATUS:
{tasks_by_status}

TEAM PERFORMANCE:
{team_performance}

Create a comprehensive but readable weekly report that:
1. Highlights key metrics (completion rate, velocity)
2. Lists major accomplishments
3. Notes any blockers or concerns
4. Provides brief recommendations
5. Is formatted for Discord/Telegram

Make it insightful and actionable."""

    @staticmethod
    def generate_detailed_spec_prompt(
        task_id: str,
        title: str,
        description: str,
        assignee: Optional[str],
        priority: str,
        deadline: Optional[str],
        task_type: str,
        existing_notes: Optional[str] = None,
        team_context: Optional[str] = None
    ) -> str:
        """Generate prompt to create a detailed spec sheet for team members."""

        return f"""Create a detailed specification sheet for this task that team members can use as their guide.

TASK INFORMATION:
- Task ID: {task_id}
- Title: {title}
- Description: {description}
- Assignee: {assignee or "Not assigned"}
- Priority: {priority}
- Deadline: {deadline or "Not set"}
- Type: {task_type}
{f"- Existing Notes: {existing_notes}" if existing_notes else ""}
{f"- Team Context: {team_context}" if team_context else ""}

Generate a comprehensive spec with the following sections:

1. EXPANDED DESCRIPTION: Rewrite the description to be clearer and more detailed. Include:
   - What exactly needs to be done
   - Why this task matters (business context)
   - Any constraints or limitations

2. ACCEPTANCE CRITERIA: List 3-7 specific, testable criteria. Each should be:
   - Clear and unambiguous
   - Measurable or verifiable
   - Written as "The system should..." or "User can..."

3. TECHNICAL DETAILS (if applicable): Include:
   - Files/components likely affected
   - Suggested approach (if obvious)
   - Potential edge cases to handle

4. DEPENDENCIES: List any:
   - Tasks that must be completed first
   - External resources needed
   - People to consult

5. ESTIMATED EFFORT: Provide a time estimate

Respond with JSON:
{{
    "expanded_description": "Detailed description...",
    "acceptance_criteria": [
        "Criterion 1",
        "Criterion 2",
        "Criterion 3"
    ],
    "technical_details": "Technical implementation notes or null if not applicable",
    "dependencies": ["Dependency 1"] or null if none,
    "estimated_effort": "2 hours" or "1 day" etc.,
    "additional_notes": "Any other relevant notes or null"
}}

Be specific and practical. This spec will be read by developers/team members who need to understand exactly what to do."""

    @staticmethod
    def breakdown_task_prompt(
        title: str,
        description: str,
        task_type: str,
        priority: str,
        estimated_effort: Optional[str] = None,
        acceptance_criteria: Optional[List[str]] = None
    ) -> str:
        """Generate prompt to break down a task into subtasks."""

        criteria_str = "\n".join([f"- {c}" for c in acceptance_criteria]) if acceptance_criteria else "None specified"

        return f"""Analyze this task and break it down into smaller, actionable subtasks.

TASK DETAILS:
Title: {title}
Description: {description}
Type: {task_type}
Priority: {priority}
Estimated Effort: {estimated_effort or "Not specified"}

Acceptance Criteria:
{criteria_str}

Break this task into 3-8 logical subtasks that:
1. Are specific and actionable
2. Can be completed independently (where possible)
3. Follow a logical sequence
4. Cover all aspects of the task
5. Each takes roughly equal effort

Respond with a JSON object:
{{
    "analysis": "Brief explanation of why this breakdown makes sense",
    "is_complex_enough": true/false,
    "subtasks": [
        {{
            "title": "Subtask title (clear and actionable)",
            "description": "Brief description of what this involves",
            "order": 1,
            "estimated_effort": "30 minutes",
            "depends_on": null
        }},
        {{
            "title": "Second subtask",
            "description": "Description",
            "order": 2,
            "estimated_effort": "1 hour",
            "depends_on": 1
        }}
    ],
    "total_estimated_effort": "4 hours",
    "recommended": true/false,
    "reason": "Why this breakdown is or isn't recommended"
}}

Rules:
- If the task is simple (can be done in under 30 minutes), set is_complex_enough=false
- Order subtasks logically (dependencies first)
- Use depends_on to indicate which subtask must be done first (by order number)
- Keep subtask titles under 80 characters
- Be specific, not generic (avoid "Research", "Plan" unless truly needed)"""
