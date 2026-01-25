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
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.database.connection import get_async_session
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
from src.integrations.telegram_client import TelegramClient
from src.integrations.sheets import GoogleSheetsClient
from config.settings import settings

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

                response = await self.ai.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )

                answer = response.strip().upper()

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
            async with get_async_session() as db:
                planning_repo = get_planning_repository(db)

                # Check for active session
                active_session = await planning_repo.get_active_for_user(user_id)

                if active_session:
                    logger.warning(f"User {user_id} already has active planning session: {active_session.session_id}")

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

                # Create new session
                session = await planning_repo.create(
                    user_id=user_id,
                    raw_input=raw_input,
                    conversation_id=conversation_id
                )

                logger.info(f"Created planning session {session.session_id} for user {user_id}")

                # Send welcome message
                if chat_id:
                    await self.telegram.send_message(
                        chat_id,
                        f"🎯 **Planning Mode Activated**\n\n"
                        f"Let's break down your project into actionable tasks!\n\n"
                        f"**Your request:** {raw_input}\n\n"
                        f"I'll ask a few questions to understand the scope...",
                        parse_mode="Markdown"
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
            async with get_async_session() as db:
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

        Args:
            raw_input: Original planning request
            max_questions: Maximum questions to generate

        Returns:
            List of questions
        """
        try:
            prompt = f"""You are helping a boss plan a project. Based on their request, generate {max_questions} SHORT clarifying questions.

Request: "{raw_input}"

Questions should cover:
- Scope (what's included/excluded)
- Timeline (when needed)
- Team (who will work on it)
- Dependencies (what's needed first)

Keep questions SHORT and SPECIFIC. Format as numbered list.

Example:
1. When do you need this completed?
2. Who should work on this?
3. Are there any existing systems this needs to integrate with?"""

            response = await self.ai.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )

            # Parse numbered list
            questions = []
            for line in response.strip().split("\n"):
                line = line.strip()
                if line and line[0].isdigit():
                    # Remove number prefix
                    question = line.split(".", 1)[1].strip() if "." in line else line
                    questions.append(question)

            logger.info(f"Generated {len(questions)} clarifying questions")
            return questions[:max_questions]

        except Exception as e:
            logger.error(f"Failed to generate questions: {e}", exc_info=True)
            # Fallback questions
            return [
                "When do you need this completed?",
                "Who should work on this?",
                "What's the most important outcome?"
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
            async with get_async_session() as db:
                planning_repo = get_planning_repository(db)
                session = await planning_repo.get_by_id_or_fail(session_id)

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
            async with get_async_session() as db:
                planning_repo = get_planning_repository(db)
                draft_repo = get_task_draft_repository(db)

                session = await planning_repo.get_by_id_or_fail(session_id)

                # Generate task breakdown
                prompt = f"""You are an expert project manager. Break down this project into specific, actionable tasks.

PROJECT REQUEST:
{session.raw_input}

INSTRUCTIONS:
1. Create 4-10 discrete tasks (not too many, not too few)
2. Each task should be SPECIFIC and ACTIONABLE
3. Order tasks logically (dependencies first)
4. Estimate hours for each task (be realistic)
5. Suggest team members if mentioned
6. Identify dependencies between tasks

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

                response = await self.ai.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    response_format={"type": "json_object"}
                )

                import json
                breakdown = json.loads(response)

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

                # Create task drafts
                tasks = breakdown.get("tasks", [])
                await draft_repo.bulk_create_from_ai(session_id, tasks)

                # Present to user
                await self._present_breakdown(chat_id, session_id, breakdown)

                logger.info(f"Generated breakdown for session {session_id}: {len(tasks)} tasks")

                return {
                    "success": True,
                    "breakdown": breakdown,
                    "task_count": len(tasks)
                }

        except Exception as e:
            logger.error(f"AI breakdown failed: {e}", exc_info=True)

            if chat_id:
                await self.telegram.send_message(
                    chat_id,
                    f"❌ Failed to generate task breakdown: {str(e)}\n\n"
                    "Please try rephrasing your project description.",
                    parse_mode="Markdown"
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
            async with get_async_session() as db:
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
            async with get_async_session() as db:
                planning_repo = get_planning_repository(db)

                await planning_repo.update_state(
                    session_id,
                    PlanningStateEnum.CANCELLED
                )

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


def get_planning_handler(
    telegram_client: TelegramClient,
    ai_client: DeepSeekClient,
    sheets_client: GoogleSheetsClient
) -> PlanningHandler:
    """Factory function for planning handler"""
    return PlanningHandler(telegram_client, ai_client, sheets_client)
