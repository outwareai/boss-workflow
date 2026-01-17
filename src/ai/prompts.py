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

CRITICAL - DETECT AND PRESERVE SUBTASKS:
If the user lists subtasks or items (after "subtasks:", "in it:", "-", "•", numbered items, etc.),
you MUST extract them as separate subtasks. DON'T oversimplify or lose details!

SUBTASK RULES - VERY IMPORTANT:
1. PRESERVE the user's original wording and details - don't summarize too much
2. If user gives a detailed subtask, keep ALL that detail in the title
3. Complex subtasks should have LONGER, more descriptive titles (up to 150 chars)
4. Simple subtasks can have short titles

BAD Example (oversimplified - DON'T DO THIS):
User: "change design and colors same for affiliate page in the console side also add the tiers and more info"
❌ "Update affiliate page" (TOO SHORT - lost all the detail!)
✅ "Update affiliate page design/colors in console, add commission tiers and additional info sections"

BAD Example:
User: "Third page needs to change design and colors to white for hybrid and flat fee and red for commission only"
❌ "Update third page colors" (TOO SHORT!)
✅ "Update third page design: white theme for hybrid/flat fee options, red theme for commission only"

GOOD Examples:
User: "Fix header" → "Fix header" (simple task, short title is fine)
User: "Set up rate limiter in Digital Ocean to limit monthly billing" → "Set up rate limiter in Digital Ocean for monthly cost control"

Generate a complete task specification as JSON:
{{
    "title": "Clear, actionable title for MAIN task (under 100 chars)",
    "description": "Description of the main task - NOT the subtasks",
    "assignee": "team member name or null",
    "priority": "low/medium/high/urgent",
    "deadline": "ISO datetime or null",
    "task_type": "bug/feature/task/research",
    "estimated_effort": "time estimate (e.g., '2 hours', '1 day')",
    "acceptance_criteria": [
        "Clear, testable criterion 1",
        "Clear, testable criterion 2"
    ],
    "subtasks": [
        {{
            "title": "DETAILED subtask title preserving user's original wording (up to 150 chars)",
            "description": "Additional context if the title can't fit everything",
            "order": 1
        }}
    ],
    "tags": ["relevant", "tags"],
    "notes": "Any notes mentioned by user (e.g., 'make sure phone is working')"
}}

RULES:
- If user lists items with "-", numbers, or keywords like "subtasks", "in it", "including" → MUST extract as subtasks
- PRESERVE user's original detail in subtask titles - DON'T over-summarize!
- Complex requests need LONGER subtask titles (up to 150 chars) - keep the detail!
- Simple subtasks can have short titles
- If NO subtasks mentioned → "subtasks": []
- NEVER lose user's listed items or details
- Keep notes separate from description"""

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
    def analyze_spec_readiness_prompt(
        task_id: str,
        title: str,
        description: str,
        assignee: Optional[str],
        priority: str,
        deadline: Optional[str],
        task_type: str,
        existing_notes: Optional[str] = None,
        additional_context: Optional[str] = None
    ) -> str:
        """Analyze if we have enough information to create a detailed spec sheet."""

        return f"""You are a senior technical lead reviewing a task before writing a spec for your team.

TASK:
- ID: {task_id}
- Title: {title}
- Description: {description or "(empty)"}
- Assignee: {assignee or "TBD"}
- Priority: {priority}
- Deadline: {deadline or "Not set"}
- Type: {task_type}
{f"- Notes: {existing_notes}" if existing_notes else ""}
{f"- Context: {additional_context}" if additional_context else ""}

YOUR JOB: Decide if you can write a useful spec, or if you need specific clarification.

THINK LIKE A DEVELOPER WHO WILL IMPLEMENT THIS:
- For a BUG: Do I know what's broken? What should happen instead? Can I reproduce it?
- For a FEATURE: Do I know the user flow? What screens/components are involved? Edge cases?
- For a TASK: Is the scope clear? What's the definition of done?

BE SMART - DON'T ASK GENERIC QUESTIONS:
❌ BAD: "What's the priority?" (already provided)
❌ BAD: "Who should work on this?" (already assigned)
❌ BAD: "What are the acceptance criteria?" (that's YOUR job to derive)
❌ BAD: "Is there a deadline?" (already provided or not relevant)

✅ GOOD: Specific questions about THIS task that a developer would need answered
✅ GOOD: Questions that unlock understanding of the actual work

EXAMPLES OF SMART QUESTIONS:

For "Fix login bug":
- "What error do users see? (or does the page just hang?)"
- "Does this happen on all browsers or specific ones?"

For "Add dark mode":
- "Should it sync with system settings or be a manual toggle?"
- "Any specific colors/brand guidelines to follow?"

For "Update pricing page":
- "What specifically needs to change - prices, layout, or copy?"
- "Are there new pricing tiers or changes to existing ones?"

For "Improve performance":
- "Which part is slow? (page load, specific action, API calls?)"
- "Is there a target load time we're aiming for?"

Respond with JSON:
{{
    "has_enough_info": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of your assessment",
    "questions_to_ask": [
        {{
            "question": "Specific question about THIS task",
            "options": ["Option A", "Option B"] or null,
            "why_needed": "What this unlocks for the spec"
        }}
    ]
}}

RULES:
- Max 2 questions - ask only what's CRITICAL
- If title + description give you enough to work with, set has_enough_info=true
- Questions must be specific to THIS task, not generic templates
- Offer options only when there are clear choices (not open-ended)
- If you can make reasonable assumptions, do it - don't ask"""

    @staticmethod
    def generate_spec_questions_prompt(
        task_info: Dict[str, Any],
        missing_info: List[str],
        conversation_history: str = ""
    ) -> str:
        """Generate natural clarifying questions for spec generation."""

        return f"""Based on this task information and what's missing, generate clarifying questions.

TASK INFO:
{task_info}

MISSING CRITICAL INFO:
{missing_info}

CONVERSATION SO FAR:
{conversation_history if conversation_history else "None yet"}

Generate 1-3 natural, conversational questions that will help create a detailed spec.

Rules:
1. Be conversational, not formal
2. Offer options where possible (faster to answer)
3. Focus on the MOST important missing pieces
4. Don't ask about things you can reasonably assume

Respond with JSON:
{{
    "intro_message": "Brief context before questions",
    "questions": [
        {{
            "text": "The question to ask",
            "options": ["Option A", "Option B", "Option C"],
            "field": "what this clarifies (e.g., 'scope', 'flow', 'requirements')"
        }}
    ]
}}"""

    @staticmethod
    def process_spec_answer_prompt(
        question: str,
        answer: str,
        current_info: Dict[str, Any]
    ) -> str:
        """Process user's answer to a spec clarifying question."""

        return f"""The boss answered a clarifying question. Extract the useful info.

QUESTION ASKED: {question}
BOSS'S ANSWER: {answer}
TASK SO FAR: {current_info}

Your job: Take their answer and turn it into spec-ready information.

BE SMART:
- If they said "mobile only" → derive: "Bug is specific to mobile browsers"
- If they said "redirect to dashboard" → derive: "Success flow: redirect user to dashboard"
- If they said "users see 500 error" → derive: "Current behavior: Server returns 500 error"

Respond with JSON:
{{
    "should_add_to_description": "Clear description text derived from their answer (or null)",
    "acceptance_criteria": ["Testable criteria derived from answer"] or [],
    "technical_notes": "Any technical implications (or null)",
    "needs_followup": false,
    "followup_question": null
}}

ONLY set needs_followup=true if their answer was unclear or incomplete.
Most answers should just add to the spec directly."""

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

        return f"""You're a senior dev writing a spec that a developer can pick up and start working immediately.

TASK: {title}
TYPE: {task_type}
DESCRIPTION: {description or "(see title)"}
ASSIGNEE: {assignee or "TBD"}
PRIORITY: {priority} | DEADLINE: {deadline or "Not set"}
{f"NOTES: {existing_notes}" if existing_notes else ""}
{f"EXTRA CONTEXT: {team_context}" if team_context else ""}

WRITE A SPEC THAT'S ACTUALLY USEFUL:

For BUGS:
- Current behavior (what's broken)
- Expected behavior (what should happen)
- Reproduction steps if known
- Acceptance: "Bug is fixed when X works correctly"

For FEATURES:
- What the user can do after this is done
- The flow/interaction
- Edge cases to handle
- Acceptance: specific user scenarios that work

For TASKS:
- Clear scope of what's included
- What "done" looks like
- Any constraints

DON'T BE GENERIC:
❌ "Implement the feature as described"
❌ "Ensure quality and testing"
❌ "Follow best practices"

✅ Specific, actionable items for THIS task
✅ Criteria a dev can actually verify
✅ Real technical considerations if relevant

Respond with JSON:
{{
    "expanded_description": "2-4 sentences explaining the task clearly. Include the WHY if it adds context.",
    "acceptance_criteria": [
        "Specific testable thing 1",
        "Specific testable thing 2",
        "Specific testable thing 3"
    ],
    "technical_details": "Only if there are real technical considerations. null otherwise.",
    "dependencies": ["Only real dependencies"] or null,
    "estimated_effort": "Realistic estimate based on scope",
    "additional_notes": "Only if genuinely useful. null otherwise."
}}

Keep it concise. A dev should read this in 30 seconds and know exactly what to do."""

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
