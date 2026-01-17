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

        return f"""Analyze this task request and identify what information is missing or unclear.

USER'S MESSAGE:
"{user_message}"

USER'S PREFERENCES:
{pref_str}

TEAM MEMBERS:
{team_str}

{f"CONVERSATION HISTORY:{chr(10)}{conversation_history}" if conversation_history else ""}

Analyze the message and respond with a JSON object containing:
{{
    "understood": {{
        "title": "extracted or inferred title",
        "assignee": "extracted or inferred assignee (or null)",
        "priority": "extracted or inferred priority (low/medium/high/urgent or null)",
        "deadline": "extracted deadline in ISO format (or null)",
        "description": "extracted description",
        "task_type": "bug/feature/task/research",
        "acceptance_criteria": ["inferred criteria..."]
    }},
    "missing_info": ["list of missing important fields"],
    "confidence": {{
        "title": 0.9,
        "assignee": 0.5,
        "priority": 0.7,
        "deadline": 0.3
    }},
    "can_proceed_without_questions": true/false,
    "urgency_signals": ["any urgency indicators found"],
    "suggested_questions": [
        {{
            "field": "priority",
            "question": "What priority should this have?",
            "options": ["High - needed today", "Medium - this week", "Low - when possible"]
        }}
    ]
}}

Only include questions for fields with confidence < 0.7 that are important.
Prioritize questions that significantly impact the task scope or deadline."""

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
