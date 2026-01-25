"""
Planning handler for conversational project planning.

Implements CONVERSATIONAL PLANNING MODE:
1. Detect planning intent
2. Gather information iteratively
3. AI-powered task breakdown
4. Interactive refinement
5. Create project + tasks

v3.0 Planning System (Q1 2026)
"""

import logging
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from datetime import datetime

from src.database.connection import get_session
from src.database.repositories import (
    get_planning_repository,
    get_task_draft_repository,
    get_conversation_repository,
    get_project_repository,
    get_task_repository,
    get_template_repository
)
from src.database.models import PlanningStateEnum, ProjectComplexityEnum
from src.ai.deepseek import DeepSeekClient
from src.ai.memory_retrieval import memory_retrieval  # GROUP 2: Memory System
from src.ai.memory_extractor import memory_extractor  # GROUP 2: Memory System
from src.integrations.sheets import GoogleSheetsIntegration as GoogleSheetsClient
from src.bot.planning_enhancements import PlanningEnhancer
from src.bot.planning_session_manager import get_planning_session_manager  # GROUP 3 Phase 7
from src.bot.planning_session_timeout import get_timeout_handler  # GROUP 3 Phase 7
from config.settings import settings

if TYPE_CHECKING:
    from src.bot.telegram_simple import TelegramBotSimple as TelegramClient
else:
    TelegramClient = Any

logger = logging.getLogger(__name__)

class PlanningHandler:
    """
    Handles conversational planning flow.

    State machine:
    INITIATED → GATHERING_INFO → AI_ANALYZING → REVIEWING_BREAKDOWN → REFINING → FINALIZING → COMPLETED
    """

    def __init__(
        self,
        telegram_client: TelegramClient,
        ai_client: DeepSeekClient,
        sheets_client: GoogleSheetsClient
    ):
        self.telegram = telegram_client
        self.ai = ai_client
        self.sheets = sheets_client
        # GROUP 1: Conversational Planning Engine enhancements
        self.enhancer = PlanningEnhancer(ai_client)
        # GROUP 3 Phase 7: Enhanced session management
        self.session_manager = get_planning_session_manager(ai_client)
        self.timeout_handler = get_timeout_handler(telegram_client, timeout_minutes=30)

    async def detect_planning_intent(
        self,
        message: str,
        conversation_id: str
    ) -> bool:
        """
        Detect if user wants to plan a project

        Patterns:
        - "plan [project]"
        - "I want to build..."
        - "Let's create a project for..."
        - "Help me organize [project]"

        Args:
            message: User message
            conversation_id: Conversation ID

        Returns:
            True if planning intent detected
        """
        planning_keywords = [
            "plan",
            "let's plan",
            "help me plan",
            "organize",
            "break down",
            "build",
            "create project",
            "new project",
            "project for",
            "i want to build",
            "we should build",
            "let's build"
        ]

        message_lower = message.lower()

        # Direct keyword match
        for keyword in planning_keywords:
            if keyword in message_lower:
                logger.info(f"Planning intent detected: '{keyword}' in message")
                return True

        # AI-based intent detection for edge cases
        if len(message.split()) > 20:  # Longer messages
            try:
                prompt = f"""Determine if this message expresses intent to PLAN or ORGANIZE a project (not just create a single task).

Message: "{message}"

Answer with ONLY: YES or NO

YES = User wants to plan/organize a multi-step project
NO = User wants to create a simple task or other action"""

                response = await self.ai.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )

                # Extract text from response

                text = response.choices[0].message.content

                answer = text.strip().upper()

                if answer == "YES":
                    logger.info("Planning intent detected via AI")
                    return True

            except Exception as e:
                logger.error(f"AI intent detection failed: {e}", exc_info=True)

        return False

    async def start_planning_session(
        self,
        user_id: str,
        raw_input: str,
        conversation_id: Optional[str] = None,
        chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start new planning session

        Args:
            user_id: User ID
            raw_input: Initial planning request
            conversation_id: Optional conversation ID
            chat_id: Telegram chat ID for responses

        Returns:
            Dict with session info and next_action
        """
        try:
            # GROUP 3 Phase 7: Use session manager to check for active/stale sessions
            session_check = await self.session_manager.get_or_create_session(
                user_id,
                raw_input
            )

            if session_check["status"] == "active":
                # User has active session
                active_session = session_check["session"]

                if chat_id:
                    await self.telegram.send_message(
                        chat_id,
                        f"⚠️ You have an active planning session: {active_session.project_name or 'Unnamed Project'}\n\n"
                        f"Please complete or cancel it first.\n\n"
                        f"Session ID: `{active_session.session_id}`\n"
                        f"State: {active_session.state}",
                        parse_mode="Markdown"
                    )

                return {
                    "success": False,
                    "error": "active_session_exists",
                    "session_id": active_session.session_id
                }

            if session_check["status"] == "has_saved":
                # User has saved sessions
                if chat_id:
                    await self.telegram.send_message(
                        chat_id,
                        session_check["message"],
                        parse_mode="Markdown"
                    )

            async with get_session() as db:
                planning_repo = get_planning_repository(db)

                # Create new session
                session = await planning_repo.create(
                    user_id=user_id,
                    raw_input=raw_input,
                    conversation_id=conversation_id
                )

                logger.info(f"Created planning session {session.session_id} for user {user_id}")

                # GROUP 2: Get relevant context from memory system
                context = await self._get_planning_context(raw_input, session.session_id)

                # Store context in session
                if context.get("has_context"):
                    await planning_repo.update_session(
                        session.session_id,
                        similar_projects_context=context.get("similar_projects"),
                        predicted_challenges=context.get("predicted_challenges"),
                        recommended_templates=context.get("recommended_templates")
                    )

                # Send welcome message with context
                if chat_id:
                    welcome_msg = f"🎯 **Planning Mode Activated**\n\n"
                    welcome_msg += f"Let's break down your project into actionable tasks!\n\n"
                    welcome_msg += f"**Your request:** {raw_input}\n\n"

                    # Include context if available
                    if context.get("has_context"):
                        welcome_msg += f"\n{context['context_summary']}\n\n"

                    welcome_msg += f"I'll ask a few questions to understand the scope..."

                    await self.telegram.send_message(
                        chat_id,
                        welcome_msg,
                        parse_mode="Markdown"
                    )

                # GROUP 3 Phase 7: Start timeout timer
                if chat_id:
                    self.timeout_handler.start_timeout_timer(
                        session.session_id,
                        user_id,
                        chat_id
                    )

                # Move to information gathering
                return {
                    "success": True,
                    "session_id": session.session_id,
                    "next_action": "gather_info",
                    "state": PlanningStateEnum.GATHERING_INFO.value
                }

        except Exception as e:
            logger.error(f"Failed to start planning session: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def gather_information(
        self,
        session_id: str,
        chat_id: str
    ) -> Dict[str, Any]:
        """
        Ask clarifying questions to gather information

        Args:
            session_id: Planning session ID
            chat_id: Telegram chat ID

        Returns:
            Dict with questions and state
        """
        try:
            async with get_session() as db:
                planning_repo = get_planning_repository(db)
                session = await planning_repo.get_by_id_or_fail(session_id)

                # Generate questions using AI
                questions = await self._generate_clarifying_questions(session.raw_input)

                # Save questions to session
                await planning_repo.update_state(
                    session_id,
                    PlanningStateEnum.GATHERING_INFO,
                    clarifying_questions=questions
                )

                # Send questions to user
                question_text = "**Let me ask a few questions:**\n\n"
                for idx, q in enumerate(questions, 1):
                    question_text += f"{idx}. {q}\n\n"

                question_text += "*Reply with your answers, one per message or all at once.*"

                await self.telegram.send_message(
                    chat_id,
                    question_text,
                    parse_mode="Markdown"
                )

                logger.info(f"Sent {len(questions)} clarifying questions for session {session_id}")

                return {
                    "success": True,
                    "questions": questions,
                    "state": PlanningStateEnum.GATHERING_INFO.value
                }

        except Exception as e:
            logger.error(f"Failed to gather information: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _generate_clarifying_questions(
        self,
        raw_input: str,
        max_questions: int = 3
    ) -> List[str]:
        """
        Use AI to generate clarifying questions

        ALWAYS asks baseline questions:
        1. Project name (if not mentioned)
        2. Deadline/timeline
        3. Who is assigned

        Then adds context-specific questions.

        Args:
            raw_input: Original planning request
            max_questions: Maximum questions to generate

        Returns:
            List of questions (minimum 3)
        """
        try:
            # Baseline questions to ALWAYS consider
            baseline_questions = []

            # Check if project name mentioned
            if not any(word in raw_input.lower() for word in ["project", "called", "named"]):
                baseline_questions.append("What should we name this project (or leave unnamed)?")

            # Check if timeline mentioned
            if not any(word in raw_input.lower() for word in ["deadline", "by", "timeline", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]):
                baseline_questions.append("When do you need this completed?")

            # Check if assignee mentioned
            if not any(word in raw_input.lower() for word in ["mayank", "zea", "team", "assign", "for"]):
                baseline_questions.append("Who should work on this?")

            # Generate additional context-specific questions via AI
            prompt = f"""You are helping a boss plan a project. Based on their request, generate {max_questions - len(baseline_questions)} SHORT clarifying questions.

Request: "{raw_input}"

DO NOT ask about:
- Project name (already asking)
- Timeline/deadline (already asking)
- Who will work on it (already asking)

Focus on:
- Scope (what's included/excluded)
- Priority (what's most important)
- Dependencies (what's needed first)
- Constraints (budget, tech stack, etc.)

Keep questions SHORT and SPECIFIC. Format as numbered list.

Example:
1. Are there any existing systems this needs to integrate with?
2. What's the most critical feature to deliver first?"""

            response = await self.ai.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )

            # Parse numbered list
            ai_questions = []
            for line in text.strip().split("\n"):
                line = line.strip()
                if line and line[0].isdigit():
                    # Remove number prefix
                    question = line.split(".", 1)[1].strip() if "." in line else line
                    ai_questions.append(question)

            # Combine baseline + AI questions
            all_questions = baseline_questions + ai_questions

            logger.info(f"Generated {len(all_questions)} clarifying questions ({len(baseline_questions)} baseline + {len(ai_questions)} context)")
            return all_questions[:max_questions]

        except Exception as e:
            logger.error(f"Failed to generate questions: {e}", exc_info=True)
            # Fallback questions - comprehensive baseline
            return [
                "What should we name this project (or leave unnamed)?",
                "When do you need this completed?",
                "Who should work on this?"
            ]

    async def process_answer(
        self,
        session_id: str,
        answer: str,
        chat_id: str
    ) -> Dict[str, Any]:
        """
        Process user's answer to questions

        Args:
            session_id: Planning session ID
            answer: User's answer
            chat_id: Telegram chat ID

        Returns:
            Dict with next action
        """
        try:
            # GROUP 3 Phase 7: Reset timeout on user activity
            async with get_session() as db:
                planning_repo = get_planning_repository(db)
                session = await planning_repo.get_by_id_or_fail(session_id)

                # Reset timeout timer
                self.timeout_handler.reset_timeout_timer(
                    session_id,
                    session.user_id,
                    chat_id
                )

                # Store answer in raw_input (append)
                updated_input = f"{session.raw_input}\n\nAdditional Info: {answer}"

                # Check if we have enough info
                questions = session.clarifying_questions or []
                answers_collected = updated_input.count("Additional Info:")

                if answers_collected >= len(questions):
                    # Move to AI analysis
                    await planning_repo.update_state(
                        session_id,
                        PlanningStateEnum.AI_ANALYZING,
                        raw_input=updated_input
                    )

                    await self.telegram.send_message(
                        chat_id,
                        "✅ Got it! Analyzing your project and breaking it down into tasks...\n\n"
                        "This will take a moment... ⏳",
                        parse_mode="Markdown"
                    )

                    # Trigger AI breakdown
                    breakdown_result = await self.ai_breakdown(session_id, chat_id)

                    return {
                        "success": True,
                        "next_action": "review_breakdown",
                        "breakdown": breakdown_result
                    }
                else:
                    # Still gathering info
                    await planning_repo.update_state(
                        session_id,
                        PlanningStateEnum.GATHERING_INFO,
                        raw_input=updated_input
                    )

                    remaining = len(questions) - answers_collected
                    await self.telegram.send_message(
                        chat_id,
                        f"👍 Got it! {remaining} more question(s) to go...",
                        parse_mode="Markdown"
                    )

                    return {
                        "success": True,
                        "next_action": "continue_gathering",
                        "remaining_questions": remaining
                    }

        except Exception as e:
            logger.error(f"Failed to process answer: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def ai_breakdown(
        self,
        session_id: str,
        chat_id: str
    ) -> Dict[str, Any]:
        """
        Use AI to break down project into tasks

        Args:
            session_id: Planning session ID
            chat_id: Telegram chat ID

        Returns:
            Dict with task breakdown
        """
        try:
            async with get_session() as db:
                planning_repo = get_planning_repository(db)
                draft_repo = get_task_draft_repository(db)

                session = await planning_repo.get_by_id_or_fail(session_id)
                template_repo = get_template_repository(db)

                # GROUP 2.2: Context-Aware AI - Gather context
                context_data = await self._gather_planning_context(
                    session.raw_input,
                    session.user_id,
                    db
                )

                # GROUP 3.3: Template System - Match templates
                matched_template = await self._match_template(
                    session.raw_input,
                    template_repo
                )

                # GROUP 3.1 & 3.2: Smart Breakdown with Learning
                # Generate task breakdown with context
                prompt = f"""You are an expert project manager. Break down this project into specific, actionable tasks.

PROJECT REQUEST:
{session.raw_input}

{context_data.get("context_prompt", "")}

{matched_template.get("template_prompt", "")}

INSTRUCTIONS:
1. Create 4-10 discrete tasks (not too many, not too few)
2. Each task should be SPECIFIC and ACTIONABLE
3. Order tasks logically (dependencies first)
4. Estimate hours for each task (be realistic)
5. Suggest team members if mentioned
6. Identify dependencies between tasks
7. Learn from past project patterns if provided

OUTPUT FORMAT (JSON):
{{
  "project_name": "Short project name",
  "complexity": "simple|moderate|complex|very_complex",
  "total_hours": <estimated total>,
  "tasks": [
    {{
      "title": "Task title",
      "description": "What needs to be done",
      "category": "development|design|testing|deployment",
      "priority": "high|medium|low",
      "estimated_hours": <hours>,
      "assigned_to": "Name or null",
      "depends_on": [<indices of tasks this depends on>],
      "reasoning": "Why this task is needed"
    }}
  ]
}}

Generate the JSON now:"""

                # Track template usage
                if matched_template.get("template_id"):
                    await template_repo.increment_usage(matched_template["template_id"])
                    session.applied_template_id = matched_template["template_id"]
                    await db.commit()

                response = await self.ai.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    response_format={"type": "json_object"}
                )

                import json
                breakdown = json.loads(response.choices[0].message.content)

                # Determine complexity
                complexity_map = {
                    "simple": ProjectComplexityEnum.SIMPLE,
                    "moderate": ProjectComplexityEnum.MODERATE,
                    "complex": ProjectComplexityEnum.COMPLEX,
                    "very_complex": ProjectComplexityEnum.VERY_COMPLEX
                }

                complexity = complexity_map.get(
                    breakdown.get("complexity", "moderate"),
                    ProjectComplexityEnum.MODERATE
                )

                # Save breakdown to session
                await planning_repo.save_ai_breakdown(
                    session_id,
                    breakdown,
                    complexity,
                    breakdown.get("total_hours", 0)
                )

                # GROUP 1 Phase 2: Enhance tasks with historical data and assignee suggestions
                tasks = breakdown.get("tasks", [])
                enhanced_tasks = await self.enhancer.enhance_task_drafts(
                    session_id,
                    tasks,
                    session.detected_project_id or "NEW",
                    db
                )

                # Create task drafts
                await draft_repo.bulk_create_from_ai(session_id, enhanced_tasks)

                # GROUP 1 Phase 3: Validate dependencies
                validation = await self.enhancer.validate_plan(session_id, enhanced_tasks)

                # Present to user
                await self._present_breakdown(chat_id, session_id, breakdown)

                # Show validation results
                if not validation["is_valid"]:
                    validation_msg = self.enhancer.format_validation_message(validation)
                    await self.telegram.send_message(
                        chat_id,
                        f"\n{validation_msg}",
                        parse_mode="Markdown"
                    )

                logger.info(f"Generated breakdown for session {session_id}: {len(tasks)} tasks")

                return {
                    "success": True,
                    "breakdown": breakdown,
                    "task_count": len(tasks)
                }

        except Exception as e:
            logger.error(f"AI breakdown failed: {e}", exc_info=True)

            if chat_id:
                # Use None parse_mode to avoid Markdown errors with exception text
                await self.telegram.send_message(
                    chat_id,
                    f"❌ Failed to generate task breakdown: {str(e)}\n\n"
                    "Please try rephrasing your project description.",
                    parse_mode=None
                )

            return {
                "success": False,
                "error": str(e)
            }

    async def _present_breakdown(
        self,
        chat_id: str,
        session_id: str,
        breakdown: Dict[str, Any]
    ):
        """
        Present task breakdown to user

        Args:
            chat_id: Telegram chat ID
            session_id: Planning session ID
            breakdown: AI-generated breakdown
        """
        try:
            project_name = breakdown.get("project_name", "Your Project")
            complexity = breakdown.get("complexity", "moderate")
            total_hours = breakdown.get("total_hours", 0)
            tasks = breakdown.get("tasks", [])

            # Build message
            message = f"✨ **Project Plan: {project_name}**\n\n"
            message += f"**Complexity:** {complexity.title()}\n"
            message += f"**Estimated Time:** {total_hours} hours\n"
            message += f"**Tasks:** {len(tasks)}\n\n"
            message += "───────────────────\n\n"

            for idx, task in enumerate(tasks, 1):
                message += f"**{idx}. {task['title']}**\n"
                message += f"   ├ Category: {task.get('category', 'N/A')}\n"
                message += f"   ├ Priority: {task.get('priority', 'medium')}\n"
                message += f"   ├ Est. Hours: {task.get('estimated_hours', 0)}\n"

                if task.get('assigned_to'):
                    message += f"   ├ Assigned: {task['assigned_to']}\n"

                if task.get('depends_on'):
                    deps = ", ".join([f"#{d+1}" for d in task['depends_on']])
                    message += f"   ├ Depends on: {deps}\n"

                message += f"   └ {task.get('description', '')}\n\n"

            message += "───────────────────\n\n"
            message += "**What would you like to do?**\n"
            message += "• `/approve` - Create these tasks\n"
            message += "• `/refine` - Request changes\n"
            message += "• `/cancel` - Cancel planning\n\n"
            message += f"Session: `{session_id}`"

            await self.telegram.send_message(
                chat_id,
                message,
                parse_mode="Markdown"
            )

        except Exception as e:
            logger.error(f"Failed to present breakdown: {e}", exc_info=True)

    async def approve_plan(
        self,
        session_id: str,
        chat_id: str
    ) -> Dict[str, Any]:
        """
        Approve plan and create tasks

        Args:
            session_id: Planning session ID
            chat_id: Telegram chat ID

        Returns:
            Dict with created tasks
        """
        try:
            async with get_session() as db:
                planning_repo = get_planning_repository(db)
                draft_repo = get_task_draft_repository(db)
                project_repo = get_project_repository(db)
                task_repo = get_task_repository(db)

                session = await planning_repo.get_by_id_or_fail(session_id, with_drafts=True)

                if not session.ai_breakdown:
                    raise ValueError("No breakdown available to approve")

                # Create project
                project_data = {
                    "name": session.ai_breakdown.get("project_name", "New Project"),
                    "description": session.raw_input,
                    "created_by": session.user_id,
                    "status": "planning"
                }

                project = await project_repo.create(project_data)

                logger.info(f"Created project {project.project_id} from planning session {session_id}")

                # Create tasks from drafts
                created_tasks = []

                for draft in session.task_drafts:
                    task_data = {
                        "title": draft.title,
                        "description": draft.description,
                        "category": draft.category,
                        "priority": draft.priority,
                        "assigned_to": draft.assigned_to,
                        "estimated_hours": draft.estimated_hours,
                        "project_id": project.project_id,
                        "created_by": session.user_id,
                        "status": "pending"
                    }

                    task = await task_repo.create(task_data)
                    created_tasks.append(task)

                    # Update draft with created task ID
                    draft.created_task_id = task.task_id
                    await db.commit()

                # Finalize planning session
                task_ids = [t.task_id for t in created_tasks]
                await planning_repo.finalize(
                    session_id,
                    project.project_id,
                    task_ids
                )

                # GROUP 3 Phase 7: Cancel timeout timer on completion
                self.timeout_handler.cancel_timeout_timer(session_id)

                # Sync to Google Sheets
                try:
                    for task in created_tasks:
                        await self.sheets.add_task(task)
                except Exception as e:
                    logger.error(f"Failed to sync tasks to sheets: {e}", exc_info=True)

                # Send success message
                await self.telegram.send_message(
                    chat_id,
                    f"✅ **Project Created!**\n\n"
                    f"**Project:** {project.name}\n"
                    f"**Tasks:** {len(created_tasks)}\n\n"
                    f"All tasks have been added to your workflow. Check Google Sheets for details!\n\n"
                    f"Project ID: `{project.project_id}`",
                    parse_mode="Markdown"
                )

                logger.info(f"Planning session {session_id} finalized: {len(created_tasks)} tasks created")

                return {
                    "success": True,
                    "project_id": project.project_id,
                    "task_count": len(created_tasks),
                    "task_ids": task_ids
                }

        except Exception as e:
            logger.error(f"Failed to approve plan: {e}", exc_info=True)

            if chat_id:
                await self.telegram.send_message(
                    chat_id,
                    f"❌ Failed to create tasks: {str(e)}",
                    parse_mode="Markdown"
                )

            return {
                "success": False,
                "error": str(e)
            }

    async def cancel_plan(
        self,
        session_id: str,
        chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel planning session

        Args:
            session_id: Planning session ID
            chat_id: Optional Telegram chat ID

        Returns:
            Dict with status
        """
        try:
            async with get_session() as db:
                planning_repo = get_planning_repository(db)

                await planning_repo.update_state(
                    session_id,
                    PlanningStateEnum.CANCELLED
                )

                # GROUP 3 Phase 7: Cancel timeout timer
                self.timeout_handler.cancel_timeout_timer(session_id)

                if chat_id:
                    await self.telegram.send_message(
                        chat_id,
                        "❌ Planning session cancelled.",
                        parse_mode="Markdown"
                    )

                logger.info(f"Cancelled planning session {session_id}")

                return {
                    "success": True,
                    "session_id": session_id
                }

        except Exception as e:
            logger.error(f"Failed to cancel plan: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def refine_plan(
        self,
        session_id: str,
        refinement_request: str,
        chat_id: str
    ) -> Dict[str, Any]:
        """
        Refine the AI-generated plan based on user feedback

        GROUP 2.1: Iterative Refinement

        Args:
            session_id: Planning session ID
            refinement_request: User's refinement instructions
            chat_id: Telegram chat ID

        Returns:
            Dict with updated breakdown
        """
        try:
            async with get_session() as db:
                planning_repo = get_planning_repository(db)
                draft_repo = get_task_draft_repository(db)

                session = await planning_repo.get_by_id_or_fail(session_id, with_drafts=True)

                if not session.ai_breakdown:
                    return {"success": False, "error": "No plan to refine"}

                # Use AI to understand refinement request
                current_breakdown = session.ai_breakdown
                drafts = session.task_drafts

                prompt = f"""Refine this project plan based on user feedback.

CURRENT PLAN:
{self._format_breakdown_for_refinement(current_breakdown, drafts)}

USER FEEDBACK: "{refinement_request}"

Generate an updated plan in JSON format (same structure as original).
Apply the user's requested changes while keeping the rest intact.

OUTPUT FORMAT (JSON):
{{
  "project_name": "name",
  "complexity": "simple|moderate|complex|very_complex",
  "total_hours": <hours>,
  "tasks": [...]
}}
"""

                response = await self.ai.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    response_format={"type": "json_object"}
                )

                import json
                updated_breakdown = json.loads(response.choices[0].message.content)

                # Determine complexity
                complexity_map = {
                    "simple": ProjectComplexityEnum.SIMPLE,
                    "moderate": ProjectComplexityEnum.MODERATE,
                    "complex": ProjectComplexityEnum.COMPLEX,
                    "very_complex": ProjectComplexityEnum.VERY_COMPLEX
                }

                complexity = complexity_map.get(
                    updated_breakdown.get("complexity", "moderate"),
                    ProjectComplexityEnum.MODERATE
                )

                # Save updated breakdown
                await planning_repo.save_ai_breakdown(
                    session_id,
                    updated_breakdown,
                    complexity,
                    updated_breakdown.get("total_hours", 0)
                )

                # Track user edit
                await planning_repo.add_user_edit(
                    session_id,
                    "refine_plan",
                    {"request": refinement_request}
                )

                # Delete old drafts
                for draft in drafts:
                    await draft_repo.delete(draft.draft_id)

                # Create new drafts
                tasks = updated_breakdown.get("tasks", [])
                await draft_repo.bulk_create_from_ai(session_id, tasks)

                # Present updated plan
                await self._present_breakdown(chat_id, session_id, updated_breakdown)

                logger.info(f"Refined plan for session {session_id}")

                return {
                    "success": True,
                    "task_count": len(tasks)
                }

        except Exception as e:
            logger.error(f"Failed to refine plan: {e}", exc_info=True)

            if chat_id:
                await self.telegram.send_message(
                    chat_id,
                    f"❌ Failed to refine plan: {str(e)}",
                    parse_mode="Markdown"
                )

            return {
                "success": False,
                "error": str(e)
            }

    async def refine_task(
        self,
        session_id: str,
        task_id: str,
        changes: Dict[str, Any],
        chat_id: str
    ) -> Dict[str, Any]:
        """
        Refine a specific task with impact analysis.

        GROUP 1 Phase 3: Interactive Refinement Loop

        Args:
            session_id: Planning session ID
            task_id: Task draft ID to modify
            changes: Dict of changes to apply
            chat_id: Telegram chat ID

        Returns:
            Dict with refinement result and impact analysis
        """
        try:
            async with get_session() as db:
                planning_repo = get_planning_repository(db)
                draft_repo = get_task_draft_repository(db)

                # Validate session
                session = await planning_repo.get_by_id_or_fail(session_id)

                # Analyze impact before applying changes
                impact = await self.enhancer.analyze_refinement_impact(
                    session_id,
                    task_id,
                    changes,
                    db
                )

                # Show impact to user
                await self.telegram.send_message(
                    chat_id,
                    impact["message"],
                    parse_mode="Markdown"
                )

                # If valid, apply changes
                if impact["is_valid"]:
                    await draft_repo.update(task_id, changes)

                    # Track refinement
                    await planning_repo.add_user_edit(
                        session_id,
                        "modify_task",
                        {
                            "task_id": task_id,
                            "changes": changes,
                            "impact": {
                                "affected_tasks": impact["affected_tasks"],
                                "timeline_changes": impact["timeline_changes"]
                            }
                        }
                    )

                    logger.info(f"Refined task {task_id} in session {session_id}")

                    return {
                        "success": True,
                        "is_valid": True,
                        "impact": impact
                    }
                else:
                    # Changes create invalid state
                    await self.telegram.send_message(
                        chat_id,
                        "⚠️ Cannot apply changes - please fix validation errors first.",
                        parse_mode="Markdown"
                    )

                    return {
                        "success": False,
                        "is_valid": False,
                        "impact": impact,
                        "error": "Validation failed"
                    }

        except Exception as e:
            logger.error(f"Failed to refine task: {e}", exc_info=True)

            if chat_id:
                await self.telegram.send_message(
                    chat_id,
                    f"❌ Failed to refine task: {str(e)}",
                    parse_mode="Markdown"
                )

            return {
                "success": False,
                "error": str(e)
            }

    def _format_breakdown_for_refinement(
        self,
        breakdown: Dict[str, Any],
        drafts: List
    ) -> str:
        """Format breakdown for AI refinement"""
        tasks = breakdown.get("tasks", [])
        lines = [
            f"Project: {breakdown.get('project_name')}",
            f"Complexity: {breakdown.get('complexity')}",
            f"Total Hours: {breakdown.get('total_hours')}",
            "\nTasks:"
        ]

        for idx, task in enumerate(tasks, 1):
            lines.append(f"{idx}. {task.get('title')}")
            lines.append(f"   - Category: {task.get('category')}")
            lines.append(f"   - Hours: {task.get('estimated_hours')}")
            if task.get('assigned_to'):
                lines.append(f"   - Assigned: {task.get('assigned_to')}")

        return "\n".join(lines)

    async def _gather_planning_context(
        self,
        planning_request: str,
        user_id: str,
        db
    ) -> Dict[str, Any]:
        """
        GROUP 2.2: Context-Aware AI - Gather relevant context

        Returns context data including similar projects and patterns
        """
        try:
            from src.ai.project_recognizer import get_project_recognizer

            recognizer = get_project_recognizer(self.ai)

            # Find related projects
            related = await recognizer.suggest_related_projects(
                planning_request,
                user_id,
                limit=3
            )

            if not related:
                return {"context_prompt": ""}

            # Build context prompt
            context_lines = ["\nCONTEXT FROM SIMILAR PAST PROJECTS:"]

            memory_repo = get_memory_repository(db)

            for proj in related:
                project_id = proj.get("project_id")
                context = await recognizer.get_project_context(
                    project_id,
                    include_memory=True,
                    include_decisions=False,
                    include_discussions=False
                )

                if context.get("challenges"):
                    context_lines.append(f"\nChallenges from '{context.get('name')}':")
                    context_lines.append(str(context["challenges"])[:200])

                if context.get("successes"):
                    context_lines.append(f"\nSuccess patterns:")
                    context_lines.append(str(context["successes"])[:200])

            context_prompt = "\n".join(context_lines)

            return {
                "context_prompt": context_prompt,
                "related_projects": related
            }

        except Exception as e:
            logger.error(f"Failed to gather context: {e}", exc_info=True)
            return {"context_prompt": ""}

    async def _match_template(
        self,
        planning_request: str,
        template_repo
    ) -> Dict[str, Any]:
        """
        GROUP 3.3: Template System - Match planning templates

        Returns matched template with prompt enhancement
        """
        try:
            # Get active templates
            templates = await template_repo.get_all_active()

            if not templates:
                return {"template_prompt": ""}

            # Use AI to find best match
            template_list = [
                {
                    "id": t.template_id,
                    "name": t.name,
                    "description": t.description or "",
                    "category": t.category
                }
                for t in templates
            ]

            prompt = f"""Which template best matches this project request?

REQUEST: "{planning_request}"

TEMPLATES:
{self._format_templates_for_matching(template_list)}

Return JSON with best match:
{{"template_id": "TPL-ID or null", "confidence": 0.8}}

Only match if confidence > 0.6.
"""

            response = await self.ai.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"}
            )

            import json
            result = json.loads(response.choices[0].message.content)

            if not result.get("template_id") or result.get("confidence", 0) < 0.6:
                return {"template_prompt": ""}

            # Get full template
            template = await template_repo.get_by_id(result["template_id"])

            if not template:
                return {"template_prompt": ""}

            # Build template prompt
            template_prompt = f"\nUSE THIS TEMPLATE AS GUIDANCE:\n{template.name}\n"
            if template.description:
                template_prompt += f"{template.description}\n"

            logger.info(f"Matched template: {template.name}")

            return {
                "template_id": template.template_id,
                "template_prompt": template_prompt,
                "template_name": template.name
            }

        except Exception as e:
            logger.error(f"Failed to match template: {e}", exc_info=True)
            return {"template_prompt": ""}

    def _format_templates_for_matching(self, templates: List[Dict]) -> str:
        """Format templates for AI matching"""
        lines = []
        for t in templates:
            lines.append(f"- {t['id']}: {t['name']}")
            if t.get('description'):
                lines.append(f"  {t['description'][:100]}")
            if t.get('category'):
                lines.append(f"  Category: {t['category']}")
        return "\n".join(lines)

    async def _get_planning_context(
        self,
        project_description: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Get relevant context from memory system for planning.

        GROUP 2: Memory System integration.

        Args:
            project_description: Description of the project
            session_id: Planning session ID

        Returns:
            Dictionary with context including similar projects, challenges, templates
        """
        try:
            # Get context from memory retrieval
            context = await memory_retrieval.get_relevant_context(project_description)

            logger.info(
                f"Retrieved planning context for session {session_id}: "
                f"{len(context.get('similar_projects', []))} similar projects, "
                f"{len(context.get('predicted_challenges', []))} challenges"
            )

            return context

        except Exception as e:
            logger.error(f"Failed to get planning context: {e}", exc_info=True)
            return {
                "similar_projects": [],
                "predicted_challenges": [],
                "recommended_templates": [],
                "context_summary": "",
                "has_context": False
            }

    async def _extract_session_insights(self, session_id: str):
        """
        Extract insights from completed planning session.

        GROUP 2: Memory System - Called after session completes.

        Args:
            session_id: Planning session ID
        """
        try:
            # Extract decisions made during session
            await memory_extractor.extract_decisions_from_session(session_id)

            logger.info(f"Extracted insights from planning session {session_id}")

        except Exception as e:
            logger.error(f"Failed to extract session insights: {e}", exc_info=True)

    async def resume_session(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resume a saved planning session.

        GROUP 3 Phase 7: Enhanced Multi-Turn Planning Sessions

        Args:
            user_id: User ID
            session_id: Optional specific session to resume (otherwise uses most recent)
            chat_id: Telegram chat ID for responses

        Returns:
            Dict with resume status and session data
        """
        try:
            # If no session ID provided, find most recent saved session
            if not session_id:
                recovery = await self.session_manager.recover_session(user_id)

                if not recovery:
                    if chat_id:
                        await self.telegram.send_message(
                            chat_id,
                            "📭 No saved planning sessions found.\n\n"
                            "Use `/plan <description>` to start a new planning session.",
                            parse_mode="Markdown"
                        )

                    return {
                        "success": False,
                        "error": "no_saved_sessions"
                    }

                session_id = recovery["session_id"]

            # Resume the session
            resume_result = await self.session_manager.resume_session_with_context(
                session_id
            )

            if not resume_result.get("success"):
                if chat_id:
                    await self.telegram.send_message(
                        chat_id,
                        f"❌ Failed to resume session: {resume_result.get('error')}",
                        parse_mode="Markdown"
                    )

                return resume_result

            # Send context summary to user
            if chat_id:
                message = (
                    f"🔄 **Resuming Planning Session**\n\n"
                    f"{resume_result['context_summary']}\n\n"
                    f"Session ID: `{session_id}`\n"
                    f"Tasks: {resume_result['task_count']}\n"
                    f"State: {resume_result['state']}\n\n"
                )

                # Add appropriate next steps based on state
                state = resume_result['state']

                if state == "reviewing_breakdown":
                    message += (
                        "**What would you like to do?**\n"
                        "• `/approve` - Create these tasks\n"
                        "• `/refine <changes>` - Request changes\n"
                        "• `/cancel` - Cancel planning"
                    )
                elif state == "gathering_info":
                    message += "I'll continue asking questions from where we left off."
                else:
                    message += "Let's continue planning!"

                await self.telegram.send_message(
                    chat_id,
                    message,
                    parse_mode="Markdown"
                )

                # Restart timeout timer
                self.timeout_handler.start_timeout_timer(
                    session_id,
                    user_id,
                    chat_id
                )

                # If state is reviewing_breakdown, re-present the breakdown
                if state == "reviewing_breakdown":
                    session = resume_result["session"]
                    if session.ai_breakdown:
                        await self._present_breakdown(
                            chat_id,
                            session_id,
                            session.ai_breakdown
                        )

            logger.info(f"Resumed planning session {session_id} for user {user_id}")

            return {
                "success": True,
                "session_id": session_id,
                "state": resume_result["state"]
            }

        except Exception as e:
            logger.error(f"Failed to resume planning session: {e}", exc_info=True)

            if chat_id:
                await self.telegram.send_message(
                    chat_id,
                    f"❌ Failed to resume session: {str(e)}",
                    parse_mode="Markdown"
                )

            return {
                "success": False,
                "error": str(e)
            }

    async def list_saved_sessions(
        self,
        user_id: str,
        chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List user's saved planning sessions.

        GROUP 3 Phase 7: Enhanced Multi-Turn Planning Sessions

        Args:
            user_id: User ID
            chat_id: Telegram chat ID for responses

        Returns:
            Dict with session list
        """
        try:
            message = await self.session_manager.list_saved_sessions(user_id)

            if chat_id:
                await self.telegram.send_message(
                    chat_id,
                    message,
                    parse_mode="Markdown"
                )

            return {
                "success": True
            }

        except Exception as e:
            logger.error(f"Failed to list saved sessions: {e}", exc_info=True)

            if chat_id:
                await self.telegram.send_message(
                    chat_id,
                    f"❌ Failed to list saved sessions: {str(e)}",
                    parse_mode="Markdown"
                )

            return {
                "success": False,
                "error": str(e)
            }


def get_planning_handler(
    telegram_client: TelegramClient,
    ai_client: DeepSeekClient,
    sheets_client: GoogleSheetsClient
) -> PlanningHandler:
    """Factory function for planning handler"""
    return PlanningHandler(telegram_client, ai_client, sheets_client)
