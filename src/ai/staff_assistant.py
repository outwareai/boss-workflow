"""
Staff AI Assistant - Smart assistant for team members.

This module provides an AI-powered assistant that helps staff with their tasks:
- Answers questions about task requirements, acceptance criteria, deadlines
- Validates work submissions against acceptance criteria
- Provides guidance on what's missing or needs fixing
- Escalates to boss only when necessary
"""

import logging
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


class StaffAssistant:
    """
    AI-powered assistant for staff members.

    Capabilities:
    - Answer questions about tasks (specs, criteria, deadlines)
    - Validate submissions against acceptance criteria
    - Guide staff on what's missing
    - Escalate to boss when AI can't answer
    """

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )
        self.model = settings.deepseek_model

    async def process_staff_message(
        self,
        staff_name: str,
        message: str,
        task_context: Dict[str, Any],
        conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Process a message from a staff member and generate a response.

        Args:
            staff_name: Name of the staff member
            message: The staff's message
            task_context: The task details (title, description, criteria, etc.)
            conversation_history: Previous messages in this conversation

        Returns:
            Dict with:
            - response: The AI's response to show the staff
            - action: What to do next (respond, escalate, submit_for_review)
            - escalation_reason: Why escalating to boss (if applicable)
            - validation_result: Results of criteria check (if submission)
        """
        conversation_history = conversation_history or []

        # Detect intent of staff message
        intent = await self._detect_staff_intent(message, task_context)

        if intent == "question":
            return await self._handle_question(staff_name, message, task_context, conversation_history)
        elif intent == "submission":
            return await self._handle_submission(staff_name, message, task_context, conversation_history)
        elif intent == "update":
            return await self._handle_status_update(staff_name, message, task_context)
        elif intent == "help":
            return await self._handle_help_request(staff_name, task_context)
        elif intent == "escalate":
            return await self._handle_escalation(staff_name, message, task_context)
        else:
            return await self._handle_general(staff_name, message, task_context, conversation_history)

    async def _detect_staff_intent(self, message: str, task_context: Dict) -> str:
        """Detect what the staff member wants to do."""

        message_lower = message.lower()

        # Submission indicators
        submission_words = ["done", "finished", "completed", "here's my work", "here is my work",
                          "i'm done", "im done", "submitted", "ready for review", "please review",
                          "check my work", "take a look", "proof", "screenshot", "link"]
        if any(word in message_lower for word in submission_words):
            return "submission"

        # Question indicators
        question_words = ["what", "how", "when", "where", "why", "can you", "could you",
                        "tell me", "explain", "?", "criteria", "requirements", "deadline",
                        "supposed to", "should i", "do i need"]
        if any(word in message_lower for word in question_words):
            return "question"

        # Status update indicators
        update_words = ["working on", "started", "in progress", "halfway", "almost done",
                       "update:", "status:", "blocked", "stuck", "issue", "problem"]
        if any(word in message_lower for word in update_words):
            return "update"

        # Help request
        help_words = ["help", "confused", "don't understand", "unclear", "not sure"]
        if any(word in message_lower for word in help_words):
            return "help"

        # Escalation request
        escalate_words = ["talk to boss", "need boss", "ask mat", "escalate", "manager"]
        if any(word in message_lower for word in escalate_words):
            return "escalate"

        return "general"

    async def _handle_question(
        self,
        staff_name: str,
        message: str,
        task_context: Dict,
        history: List[Dict]
    ) -> Dict[str, Any]:
        """Handle a question from staff about their task."""

        task_id = task_context.get("task_id", "Unknown")
        title = task_context.get("title", "Untitled Task")
        description = task_context.get("description", "No description")
        criteria = task_context.get("acceptance_criteria", [])
        deadline = task_context.get("deadline", "Not set")
        priority = task_context.get("priority", "medium")
        notes = task_context.get("notes", "")

        # Format criteria for the prompt
        criteria_text = "\n".join([f"  {i+1}. {c}" for i, c in enumerate(criteria)]) if criteria else "None specified"

        # Build conversation history for context
        history_text = ""
        if history:
            history_text = "\n\nPrevious conversation:\n"
            for msg in history[-5:]:  # Last 5 messages for context
                role = "Staff" if msg.get("role") == "staff" else "Assistant"
                history_text += f"{role}: {msg.get('content', '')}\n"

        prompt = f"""You are a helpful AI assistant for {staff_name} who is working on a task.
Answer their question based on the task information below. Be concise and helpful.

TASK INFORMATION:
- Task ID: {task_id}
- Title: {title}
- Description: {description}
- Acceptance Criteria:
{criteria_text}
- Deadline: {deadline}
- Priority: {priority}
- Additional Notes: {notes or "None"}
{history_text}

STAFF'S QUESTION: "{message}"

RULES:
1. Answer based ONLY on the task information above
2. If you don't have enough information to answer, say so and offer to escalate to the boss
3. Be friendly but professional
4. If asking about acceptance criteria, list them clearly
5. If asking about deadline, include the exact date/time
6. Keep responses concise (2-4 sentences unless listing criteria)

Respond naturally as if chatting with a colleague."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful task assistant. Be concise and friendly."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )

            ai_response = response.choices[0].message.content.strip()

            # Check if AI couldn't answer and needs escalation
            needs_escalation = any(phrase in ai_response.lower() for phrase in [
                "don't have that information", "not sure about that",
                "need to ask", "escalate", "check with", "don't know"
            ])

            return {
                "response": ai_response,
                "action": "escalate" if needs_escalation else "respond",
                "escalation_reason": "AI couldn't answer staff's question" if needs_escalation else None
            }

        except Exception as e:
            logger.error(f"Error handling staff question: {e}")
            return {
                "response": f"Sorry {staff_name}, I encountered an error. Let me escalate this to the boss.",
                "action": "escalate",
                "escalation_reason": f"AI error: {str(e)}"
            }

    async def _handle_submission(
        self,
        staff_name: str,
        message: str,
        task_context: Dict,
        history: List[Dict]
    ) -> Dict[str, Any]:
        """Handle a work submission from staff - validate against criteria."""

        task_id = task_context.get("task_id", "Unknown")
        title = task_context.get("title", "Untitled Task")
        criteria = task_context.get("acceptance_criteria", [])

        if not criteria:
            # No criteria to validate against
            return {
                "response": f"Thanks {staff_name}! I've received your submission for **{task_id}**. Sending it to the boss for review since there are no specific acceptance criteria to check against.",
                "action": "submit_for_review",
                "validation_result": {"status": "no_criteria", "passed": True}
            }

        # Format criteria for validation
        criteria_text = "\n".join([f"{i+1}. {c}" for i, c in enumerate(criteria)])

        prompt = f"""You are validating a work submission against acceptance criteria.

TASK: {title} ({task_id})

ACCEPTANCE CRITERIA:
{criteria_text}

STAFF'S SUBMISSION MESSAGE:
"{message}"

PREVIOUS CONTEXT (if any):
{json.dumps(history[-3:]) if history else "None"}

Analyze the submission and check each criterion. For each criterion, determine:
- ✅ PASS: Evidence shows this is completed
- ❌ FAIL: This is clearly not done or missing
- ⚠️ UNCLEAR: Can't verify from the submission, needs manual review

Respond with this JSON format:
{{
    "overall_status": "pass" | "fail" | "needs_review",
    "criteria_results": [
        {{"criterion": "the criterion text", "status": "pass|fail|unclear", "reason": "brief explanation"}}
    ],
    "missing_items": ["list of things clearly missing"],
    "feedback": "friendly summary for the staff member"
}}

Be fair but thorough. If they mention completing something, give benefit of doubt unless clearly wrong."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You validate work submissions. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=800
            )

            response_text = response.choices[0].message.content.strip()

            # Clean up JSON response
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            validation = json.loads(response_text)

            overall_status = validation.get("overall_status", "needs_review")
            criteria_results = validation.get("criteria_results", [])
            missing_items = validation.get("missing_items", [])
            feedback = validation.get("feedback", "")

            # Build response message for staff
            response_lines = [f"**Submission Review for {task_id}**\n"]

            for result in criteria_results:
                status_emoji = {"pass": "✅", "fail": "❌", "unclear": "⚠️"}.get(result.get("status"), "⚠️")
                response_lines.append(f"{status_emoji} {result.get('criterion', 'Unknown')}")
                if result.get("reason"):
                    response_lines.append(f"   _{result.get('reason')}_")

            response_lines.append("")

            if overall_status == "pass":
                response_lines.append(f"🎉 **Great job, {staff_name}!** All criteria met. Submitting for boss approval...")
                action = "submit_for_review"
            elif overall_status == "fail":
                response_lines.append(f"**Missing items:**")
                for item in missing_items:
                    response_lines.append(f"• {item}")
                response_lines.append(f"\nPlease address these items and resubmit, {staff_name}.")
                action = "respond"
            else:
                response_lines.append(f"Some items need manual verification. Sending to boss for review...")
                action = "submit_for_review"

            return {
                "response": "\n".join(response_lines),
                "action": action,
                "validation_result": validation
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse validation JSON: {e}")
            return {
                "response": f"Thanks {staff_name}! I couldn't automatically validate your submission. Sending to the boss for manual review.",
                "action": "submit_for_review",
                "validation_result": {"status": "error", "error": str(e)}
            }
        except Exception as e:
            logger.error(f"Error handling submission: {e}")
            return {
                "response": f"Thanks {staff_name}! Sending your submission to the boss for review.",
                "action": "submit_for_review",
                "validation_result": {"status": "error", "error": str(e)}
            }

    async def _handle_status_update(
        self,
        staff_name: str,
        message: str,
        task_context: Dict
    ) -> Dict[str, Any]:
        """Handle a status update from staff."""

        task_id = task_context.get("task_id", "Unknown")

        # Detect if blocked or has issues
        is_blocked = any(word in message.lower() for word in ["blocked", "stuck", "can't", "cannot", "issue", "problem", "help"])

        if is_blocked:
            return {
                "response": f"Thanks for the update, {staff_name}. I see you're facing some challenges. Let me notify the boss so they can help unblock you.",
                "action": "escalate",
                "escalation_reason": f"Staff {staff_name} is blocked on {task_id}: {message}"
            }
        else:
            return {
                "response": f"Thanks for the update on {task_id}, {staff_name}! Keep up the good work. Let me know when you're ready to submit or if you have any questions.",
                "action": "respond"
            }

    async def _handle_help_request(
        self,
        staff_name: str,
        task_context: Dict
    ) -> Dict[str, Any]:
        """Handle a help request from staff."""

        task_id = task_context.get("task_id", "Unknown")
        title = task_context.get("title", "")
        criteria = task_context.get("acceptance_criteria", [])

        criteria_text = "\n".join([f"  {i+1}. {c}" for i, c in enumerate(criteria)]) if criteria else "  None specified"

        response = f"""Hey {staff_name}! Here's what I can help you with for **{task_id}** ({title}):

**Your acceptance criteria:**
{criteria_text}

**I can help you with:**
• Answer questions about the task requirements
• Explain acceptance criteria
• Check your deadline
• Validate your work when you submit
• Escalate to the boss if needed

Just ask me anything about the task, or say "I'm done" when you're ready to submit your work!"""

        return {
            "response": response,
            "action": "respond"
        }

    async def _handle_escalation(
        self,
        staff_name: str,
        message: str,
        task_context: Dict
    ) -> Dict[str, Any]:
        """Handle explicit escalation request."""

        task_id = task_context.get("task_id", "Unknown")

        return {
            "response": f"Got it, {staff_name}. I'm escalating this to the boss right now. They'll get back to you soon.",
            "action": "escalate",
            "escalation_reason": f"Staff {staff_name} requested escalation for {task_id}: {message}"
        }

    async def _handle_general(
        self,
        staff_name: str,
        message: str,
        task_context: Dict,
        history: List[Dict]
    ) -> Dict[str, Any]:
        """Handle general conversation."""

        task_id = task_context.get("task_id", "Unknown")
        title = task_context.get("title", "")

        prompt = f"""You are a helpful AI assistant for {staff_name} working on task "{title}" ({task_id}).

The staff sent: "{message}"

Respond helpfully and briefly. If they seem to need help with the task, offer to:
- Explain the acceptance criteria
- Answer questions about requirements
- Help them submit when ready

Keep it friendly and concise (1-2 sentences)."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful, friendly task assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=200
            )

            return {
                "response": response.choices[0].message.content.strip(),
                "action": "respond"
            }
        except Exception as e:
            logger.error(f"Error in general handler: {e}")
            return {
                "response": f"I'm here to help with your task, {staff_name}! Ask me about the requirements or let me know when you're done.",
                "action": "respond"
            }


# Singleton
_staff_assistant = None

def get_staff_assistant() -> StaffAssistant:
    global _staff_assistant
    if _staff_assistant is None:
        _staff_assistant = StaffAssistant()
    return _staff_assistant
