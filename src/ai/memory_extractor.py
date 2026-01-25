"""
Extract and store project patterns, decisions, and insights.

This module handles:
- AI-powered pattern extraction from completed projects
- Decision extraction from planning sessions
- Discussion summarization
- Completion metrics analysis
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from src.database.repositories import (
    get_memory_repository,
    get_decision_repository,
    get_discussion_repository,
    get_planning_repository,
    get_task_repository
)
from src.database.connection import get_session
from src.ai.deepseek import get_deepseek_client
import json

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """Extract insights from projects for future reference."""

    def __init__(self):
        self.ai = get_deepseek_client()

    async def extract_project_patterns(self, project_id: str) -> bool:
        """
        Extract common patterns from a completed project.

        Args:
            project_id: The project to analyze

        Returns:
            True if patterns were extracted successfully
        """
        async with get_session() as session:
            try:
                memory_repo = get_memory_repository(session)
                task_repo = get_task_repository(session)

                # Get all tasks for project
                tasks = await task_repo.get_by_project(project_id)

                if not tasks:
                    logger.warning(f"No tasks found for project {project_id}")
                    return False

                # Analyze completion metrics
                total_tasks = len(tasks)
                completed = len([t for t in tasks if t.status == "completed"])
                overdue = len([t for t in tasks if t.status == "overdue"])

                completion_rate = completed / total_tasks if total_tasks > 0 else 0

                # Calculate effort accuracy
                effort_errors = []
                for task in tasks:
                    if task.estimated_effort_hours and task.actual_effort_hours:
                        error = abs(task.actual_effort_hours - task.estimated_effort_hours) / task.estimated_effort_hours
                        effort_errors.append(error)

                avg_effort_error = sum(effort_errors) / len(effort_errors) if effort_errors else 0

                # Extract patterns using AI
                task_summaries = "\n".join([
                    f"- {t.title} ({t.status}, priority: {t.priority})"
                    for t in tasks[:15]  # Limit to first 15 for token efficiency
                ])

                pattern_prompt = f"""Analyze this completed project and extract key patterns:

Project: {project_id}
Total Tasks: {total_tasks}
Completion Rate: {completion_rate:.1%}
Overdue Rate: {overdue/total_tasks if total_tasks > 0 else 0:.1%}
Avg Effort Estimation Error: {avg_effort_error:.1%}

Task Summaries:
{task_summaries}

Provide in JSON format:
{{
    "challenges": [
        "Brief challenge description 1",
        "Brief challenge description 2"
    ],
    "successes": [
        "Success pattern 1",
        "Success pattern 2"
    ],
    "team": {{
        "high_performers": ["name1"],
        "skills_utilized": ["skill1", "skill2"],
        "collaboration_notes": "Brief notes"
    }},
    "time_analysis": {{
        "estimation_accuracy": "{avg_effort_error:.1%}",
        "common_delays": ["reason1", "reason2"]
    }},
    "bottlenecks": [
        "Bottleneck pattern 1",
        "Bottleneck pattern 2"
    ],
    "templates": [
        "Recommended template type 1"
    ]
}}"""

                messages = [
                    {"role": "system", "content": "You analyze project patterns and extract structured insights. Always respond with valid JSON."},
                    {"role": "user", "content": pattern_prompt}
                ]

                response = await self.ai.chat(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=1500
                )

                patterns = json.loads(response.choices[0].message.content)

                # Determine confidence based on task count
                confidence = min(1.0, 0.5 + (total_tasks / 20) * 0.5)  # More tasks = higher confidence

                # Store in project_memory
                await memory_repo.update_patterns(
                    project_id=project_id,
                    patterns=patterns,
                    confidence=confidence
                )

                logger.info(f"Extracted patterns from project {project_id} (confidence: {confidence:.2f})")
                return True

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI response for project {project_id}: {e}")
                return False
            except Exception as e:
                logger.error(f"Failed to extract patterns from project {project_id}: {e}", exc_info=True)
                return False

    async def extract_decisions_from_session(self, session_id: str) -> int:
        """
        Extract decisions made during planning session.

        Args:
            session_id: Planning session ID

        Returns:
            Number of decisions extracted
        """
        async with get_session() as session:
            try:
                planning_repo = get_planning_repository(session)
                decision_repo = get_decision_repository(session)

                # Get session with conversation history
                planning_session = await planning_repo.get_by_id(session_id)

                if not planning_session:
                    logger.warning(f"Planning session {session_id} not found")
                    return 0

                # Get conversation messages
                messages = planning_session.conversation_history or []

                if not messages:
                    logger.info(f"No conversation history in session {session_id}")
                    return 0

                # Build conversation text
                conversation_text = "\n".join([
                    f"{m.get('role', 'user')}: {m.get('content', '')}"
                    for m in messages
                ])

                # Use AI to identify decisions
                decision_prompt = f"""Extract all decisions made in this planning conversation:

{conversation_text}

For each decision, provide:
{{
    "decisions": [
        {{
            "decision": "what was decided",
            "reasoning": "why it was decided",
            "made_by": "user or ai",
            "decision_type": "tech_choice, scope_change, resource_allocation, timeline, or other",
            "alternatives_considered": ["alternative1", "alternative2"]
        }}
    ]
}}

Only extract clear, actionable decisions. Ignore casual discussion."""

                ai_messages = [
                    {"role": "system", "content": "You extract structured decisions from conversations. Always respond with valid JSON."},
                    {"role": "user", "content": decision_prompt}
                ]

                response = await self.ai.chat(
                    messages=ai_messages,
                    temperature=0.2,
                    max_tokens=1500
                )

                decisions_data = json.loads(response.choices[0].message.content)

                # Store each decision
                count = 0
                for decision in decisions_data.get("decisions", []):
                    await decision_repo.create(
                        project_id=planning_session.project_id or "UNKNOWN",
                        decision_type=decision.get("decision_type", "other"),
                        decision_text=decision["decision"],
                        made_by=decision.get("made_by", "user"),
                        reasoning=decision.get("reasoning"),
                        alternatives_considered=decision.get("alternatives_considered"),
                        planning_session_id=session_id
                    )
                    count += 1

                logger.info(f"Extracted {count} decisions from session {session_id}")
                return count

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse decisions for session {session_id}: {e}")
                return 0
            except Exception as e:
                logger.error(f"Failed to extract decisions from session {session_id}: {e}", exc_info=True)
                return 0

    async def summarize_discussion(self, messages: List[Dict[str, Any]]) -> str:
        """
        Summarize key points from a discussion.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Summary text (up to 200 words)
        """
        try:
            discussion_text = "\n".join([
                f"{m.get('role', 'user')}: {m.get('content', '')}"
                for m in messages
            ])

            summary_prompt = f"""Summarize the key points and outcomes from this discussion:

{discussion_text}

Focus on:
1. Main topics discussed
2. Key takeaways
3. Action items decided
4. Important concerns raised

Keep summary under 200 words."""

            ai_messages = [
                {"role": "system", "content": "You create concise summaries of planning discussions."},
                {"role": "user", "content": summary_prompt}
            ]

            response = await self.ai.chat(
                messages=ai_messages,
                temperature=0.5,
                max_tokens=300
            )

            summary = response.choices[0].message.content.strip()
            return summary

        except Exception as e:
            logger.error(f"Failed to summarize discussion: {e}", exc_info=True)
            return "Summary generation failed"

    async def analyze_completion_metrics(self, project_id: str) -> Dict[str, Any]:
        """
        Analyze project completion metrics for insights.

        Args:
            project_id: Project to analyze

        Returns:
            Metrics dictionary with statistics and insights
        """
        async with get_session() as session:
            try:
                task_repo = get_task_repository(session)
                tasks = await task_repo.get_by_project(project_id)

                metrics = {
                    "total_tasks": len(tasks),
                    "completed": 0,
                    "overdue": 0,
                    "avg_completion_time_hours": 0,
                    "bottlenecks": [],
                    "high_performers": []
                }

                if not tasks:
                    return metrics

                # Calculate completion stats
                metrics["completed"] = len([t for t in tasks if t.status == "completed"])
                metrics["overdue"] = len([t for t in tasks if t.status == "overdue"])

                # Calculate avg completion time
                completion_times = []
                for task in tasks:
                    if task.completed_at and task.created_at:
                        delta = task.completed_at - task.created_at
                        completion_times.append(delta.total_seconds() / 3600)  # hours

                if completion_times:
                    metrics["avg_completion_time_hours"] = sum(completion_times) / len(completion_times)

                # Identify bottlenecks (tasks that blocked many others)
                task_blockers = {}
                for task in tasks:
                    blocking = await task_repo.get_blocking_tasks(task.task_id)
                    if blocking:
                        task_blockers[task.task_id] = len(blocking)

                if task_blockers:
                    bottlenecks = sorted(task_blockers.items(), key=lambda x: x[1], reverse=True)[:3]
                    metrics["bottlenecks"] = [task_id for task_id, _ in bottlenecks]

                # Identify high performers (by completion rate and speed)
                assignee_performance = {}
                for task in tasks:
                    assignee = task.assignee
                    if not assignee:
                        continue

                    if assignee not in assignee_performance:
                        assignee_performance[assignee] = {
                            "completed": 0,
                            "total": 0,
                            "avg_time": []
                        }

                    assignee_performance[assignee]["total"] += 1
                    if task.status == "completed":
                        assignee_performance[assignee]["completed"] += 1
                        if task.completed_at and task.created_at:
                            time_hours = (task.completed_at - task.created_at).total_seconds() / 3600
                            assignee_performance[assignee]["avg_time"].append(time_hours)

                # Score performers
                for assignee, perf in assignee_performance.items():
                    completion_rate = perf["completed"] / perf["total"] if perf["total"] > 0 else 0
                    avg_time = sum(perf["avg_time"]) / len(perf["avg_time"]) if perf["avg_time"] else float('inf')
                    score = completion_rate * 0.7 + (1 / avg_time if avg_time > 0 else 0) * 0.3
                    assignee_performance[assignee]["score"] = score

                top_performers = sorted(
                    assignee_performance.items(),
                    key=lambda x: x[1]["score"],
                    reverse=True
                )[:3]

                metrics["high_performers"] = [assignee for assignee, _ in top_performers]

                return metrics

            except Exception as e:
                logger.error(f"Failed to analyze completion metrics for project {project_id}: {e}", exc_info=True)
                return {
                    "total_tasks": 0,
                    "completed": 0,
                    "overdue": 0,
                    "avg_completion_time_hours": 0,
                    "bottlenecks": [],
                    "high_performers": []
                }

    async def create_discussion_summary(
        self,
        project_id: str,
        planning_session_id: str,
        messages: List[Dict[str, Any]],
        importance_score: float = 0.7
    ) -> Optional[str]:
        """
        Create and store a discussion summary.

        Args:
            project_id: Project ID
            planning_session_id: Planning session ID
            messages: Conversation messages
            importance_score: Importance score (0-1)

        Returns:
            Discussion ID if created, None otherwise
        """
        async with get_session() as session:
            try:
                discussion_repo = get_discussion_repository(session)

                # Generate summary
                summary = await self.summarize_discussion(messages)

                # Create discussion record
                discussion = await discussion_repo.summarize_conversation(
                    project_id=project_id,
                    planning_session_id=planning_session_id,
                    messages=messages,
                    ai_summary=summary,
                    importance_score=importance_score
                )

                logger.info(f"Created discussion summary {discussion.discussion_id} for session {planning_session_id}")
                return discussion.discussion_id

            except Exception as e:
                logger.error(f"Failed to create discussion summary: {e}", exc_info=True)
                return None


# Global instance
memory_extractor = MemoryExtractor()


# Helper functions for scheduled jobs
async def extract_patterns_for_recent_projects(days: int = 7):
    """
    Extract patterns from projects completed in the last N days.
    Used by scheduled jobs.

    Args:
        days: Number of days to look back
    """
    async with get_db_session() as session:
        try:
            task_repo = get_task_repository(session)

            # Get recently completed projects
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Find projects with tasks completed recently
            query = """
                SELECT DISTINCT project_id
                FROM tasks
                WHERE completed_at >= :cutoff
                AND status = 'completed'
                AND project_id IS NOT NULL
            """

            result = await session.execute(query, {"cutoff": cutoff_date})
            project_ids = [row[0] for row in result]

            logger.info(f"Found {len(project_ids)} projects completed in last {days} days")

            for project_id in project_ids:
                success = await memory_extractor.extract_project_patterns(project_id)
                if success:
                    logger.info(f"✓ Extracted patterns from {project_id}")
                else:
                    logger.warning(f"✗ Failed to extract patterns from {project_id}")

            return len(project_ids)

        except Exception as e:
            logger.error(f"Failed to extract patterns for recent projects: {e}", exc_info=True)
            return 0
