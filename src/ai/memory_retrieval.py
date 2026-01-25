"""
Retrieve project memory and provide smart recommendations.

This module handles:
- Answering questions about projects using memory
- Retrieving relevant context for planning sessions
- Suggesting next steps based on session state
- Generating proactive warnings
"""

import logging
from typing import Dict, List, Any, Optional
import json
from src.database.repositories import (
    get_memory_repository,
    get_decision_repository,
    get_discussion_repository,
    get_planning_repository
)
from src.database.connection import get_db_session
from src.ai.deepseek import get_deepseek_client
from src.ai.pattern_recognizer import pattern_recognizer

logger = logging.getLogger(__name__)


class MemoryRetrieval:
    """Retrieve memory and provide context-aware recommendations."""

    def __init__(self):
        self.ai = get_deepseek_client()

    async def answer_project_question(
        self,
        question: str,
        project_id: Optional[str] = None
    ) -> str:
        """
        Answer questions about projects using memory.

        Args:
            question: User's question
            project_id: Optional specific project ID

        Returns:
            Answer text based on memory
        """
        async with get_db_session() as session:
            try:
                memory_repo = get_memory_repository(session)
                decision_repo = get_decision_repository(session)
                discussion_repo = get_discussion_repository(session)

                # Get relevant project memories
                if project_id:
                    memory = await memory_repo.get_or_create_for_project(project_id)
                    decisions = await decision_repo.get_by_project(project_id)
                    discussions = await discussion_repo.get_important_for_project(
                        project_id,
                        min_importance=0.7,
                        limit=5
                    )
                    context_scope = f"Project {project_id}"
                else:
                    # Search across all high-confidence projects
                    memories = await memory_repo.get_similar_projects(
                        min_confidence=0.7,
                        limit=5
                    )
                    memory = memories[0] if memories else None
                    decisions = []
                    discussions = []
                    context_scope = "All projects"

                # Build context
                memory_text = "No specific project memory available"
                if memory and memory.pattern_confidence and memory.pattern_confidence >= 0.5:
                    memory_text = f"""
Challenges: {memory.common_challenges or []}
Successes: {memory.success_patterns or []}
Team Insights: {memory.team_insights or {}}
"""

                decisions_text = "\n".join([
                    f"- {d.decision_text}: {d.reasoning or 'No reasoning provided'}"
                    for d in decisions[:5]
                ]) if decisions else "No decisions recorded"

                discussions_text = "\n".join([
                    f"- {disc.topic}: {disc.summary}"
                    for disc in discussions[:5]
                ]) if discussions else "No key discussions recorded"

                context = f"""Question: {question}

Context Scope: {context_scope}

Project Memory:
{memory_text}

Relevant Decisions:
{decisions_text}

Key Discussions:
{discussions_text}"""

                # Use AI to answer
                answer_prompt = f"""Answer this question using the project memory and historical context provided.

{context}

Provide a clear, concise answer with specific examples from past projects.
If the memory doesn't contain relevant information, say so clearly."""

                ai_messages = [
                    {"role": "system", "content": "You answer questions about projects using historical memory. Be specific and cite examples."},
                    {"role": "user", "content": answer_prompt}
                ]

                response = await self.ai.chat(
                    messages=ai_messages,
                    temperature=0.5,
                    max_tokens=500
                )

                answer = response.choices[0].message.content.strip()
                return answer

            except Exception as e:
                logger.error(f"Failed to answer project question: {e}", exc_info=True)
                return "I couldn't retrieve relevant information to answer your question. Please try rephrasing or check if project memory exists."

    async def get_relevant_context(self, project_description: str) -> Dict[str, Any]:
        """
        Get relevant context for a new planning session.

        Args:
            project_description: Description of the new project

        Returns:
            Dictionary with similar projects, challenges, and templates
        """
        try:
            # Find similar projects
            similar = await pattern_recognizer.find_similar_projects(
                project_description,
                limit=3
            )

            # Get predicted challenges
            predicted_challenges = []
            if similar:
                predicted_challenges = await pattern_recognizer.predict_challenges(
                    project_description,
                    team=[]  # Will be filled during planning
                )

            # Get recommended templates
            templates = await pattern_recognizer.recommend_templates(project_description)

            # Build context summary
            context_summary = self._build_context_summary(similar, predicted_challenges)

            return {
                "similar_projects": similar,
                "predicted_challenges": predicted_challenges,
                "recommended_templates": templates,
                "context_summary": context_summary,
                "has_context": len(similar) > 0 or len(predicted_challenges) > 0
            }

        except Exception as e:
            logger.error(f"Failed to get relevant context: {e}", exc_info=True)
            return {
                "similar_projects": [],
                "predicted_challenges": [],
                "recommended_templates": [],
                "context_summary": "No historical context available for this project.",
                "has_context": False
            }

    def _build_context_summary(
        self,
        similar_projects: List[Dict[str, Any]],
        challenges: List[Dict[str, Any]]
    ) -> str:
        """
        Build human-readable context summary.

        Args:
            similar_projects: List of similar project dicts
            challenges: List of predicted challenges

        Returns:
            Formatted summary text
        """
        if not similar_projects and not challenges:
            return "📚 **No similar projects found in memory.**\n\nThis appears to be a unique project type."

        summary = f"📚 **Context from {len(similar_projects)} similar projects:**\n\n"

        for project in similar_projects:
            summary += f"• **{project['project_id']}** (similarity: {project['similarity_score']}%)\n"
            summary += f"  _{project.get('similarity_reason', 'Similar project characteristics')}_\n"

        if challenges:
            summary += f"\n⚠️ **Predicted Challenges:**\n"
            for challenge in challenges[:3]:
                prob_pct = challenge.get('probability', 0) * 100
                summary += f"• {challenge['challenge']} ({prob_pct:.0f}% probability)\n"
                if challenge.get('mitigation'):
                    summary += f"  💡 Mitigation: {challenge['mitigation']}\n"

        return summary

    async def suggest_next_steps(self, session_id: str) -> List[str]:
        """
        Suggest next steps based on current planning state.

        Args:
            session_id: Planning session ID

        Returns:
            List of suggested next steps
        """
        async with get_db_session() as session:
            try:
                from src.database.repositories import get_task_draft_repository

                planning_repo = get_planning_repository(session)
                draft_repo = get_task_draft_repository(session)

                planning_session = await planning_repo.get_by_id(session_id)
                task_drafts = await draft_repo.get_by_session(session_id)

                if not planning_session:
                    return ["Planning session not found"]

                suggestions = []

                # Check if all tasks have assignees
                unassigned = [t for t in task_drafts if not t.assignee]
                if unassigned:
                    suggestions.append(f"📝 Assign {len(unassigned)} tasks that don't have assignees yet")

                # Check if dependencies are defined
                tasks_with_deps = [t for t in task_drafts if t.dependencies]
                if len(tasks_with_deps) < len(task_drafts) * 0.3 and len(task_drafts) > 3:
                    suggestions.append("🔗 Consider adding dependencies between tasks for better planning")

                # Check if effort estimates are present
                tasks_without_effort = [t for t in task_drafts if not t.estimated_effort_hours]
                if tasks_without_effort:
                    suggestions.append(f"⏱️ Add effort estimates to {len(tasks_without_effort)} tasks")

                # Check if deadlines are set
                tasks_without_deadline = [t for t in task_drafts if not t.deadline]
                if len(tasks_without_deadline) > len(task_drafts) * 0.5:
                    suggestions.append("📅 Set deadlines for critical tasks")

                # Suggest based on similar projects
                if planning_session.similar_projects_context:
                    suggestions.append("📖 Review lessons learned from similar projects before approving")

                # If no suggestions, encourage approval
                if not suggestions:
                    suggestions.append("✅ All tasks look well-defined! Ready to approve when you are.")

                return suggestions

            except Exception as e:
                logger.error(f"Failed to suggest next steps for session {session_id}: {e}", exc_info=True)
                return ["Unable to generate suggestions at this time"]

    async def proactive_warnings(self, task_drafts: List[Any]) -> List[str]:
        """
        Generate proactive warnings based on task analysis.

        Args:
            task_drafts: List of task draft objects

        Returns:
            List of warning messages
        """
        try:
            warnings = []

            if not task_drafts:
                return warnings

            # Check for unrealistic timelines
            total_effort = sum(
                t.estimated_effort_hours or 0
                for t in task_drafts
            )

            if total_effort > 160:  # > 4 weeks for one person
                warnings.append(
                    f"⚠️ **Total estimated effort is {total_effort}h** - "
                    f"this may be too much for one sprint. Consider breaking into phases."
                )

            # Check for missing critical tasks
            task_titles_lower = [t.title.lower() for t in task_drafts]

            has_testing = any("test" in title for title in task_titles_lower)
            if not has_testing and len(task_drafts) > 5:
                warnings.append(
                    "⚠️ **No testing tasks found** - consider adding test coverage tasks"
                )

            has_docs = any("doc" in title for title in task_titles_lower)
            if not has_docs and len(task_drafts) > 5:
                warnings.append(
                    "⚠️ **No documentation tasks found** - consider adding documentation tasks"
                )

            # Check for single points of failure
            assignees = [t.assignee for t in task_drafts if t.assignee]
            if assignees:
                assignee_counts = {}
                for assignee in assignees:
                    assignee_counts[assignee] = assignee_counts.get(assignee, 0) + 1

                max_assignment = max(assignee_counts.values())
                max_assignee = [a for a, c in assignee_counts.items() if c == max_assignment][0]

                if max_assignment > len(task_drafts) * 0.6:
                    warnings.append(
                        f"⚠️ **{max_assignee} assigned to {max_assignment} tasks** - "
                        f"consider redistributing to avoid bottlenecks"
                    )

            # Check for very long task titles (may be too vague)
            long_titles = [t for t in task_drafts if len(t.title) > 100]
            if long_titles:
                warnings.append(
                    f"⚠️ **{len(long_titles)} tasks have very long titles** - "
                    f"consider making them more concise"
                )

            # Check for tasks without acceptance criteria
            tasks_without_criteria = [
                t for t in task_drafts
                if not t.acceptance_criteria or len(t.acceptance_criteria) == 0
            ]
            if len(tasks_without_criteria) > len(task_drafts) * 0.7:
                warnings.append(
                    "⚠️ **Most tasks lack acceptance criteria** - "
                    "consider adding clear success metrics"
                )

            return warnings

        except Exception as e:
            logger.error(f"Failed to generate proactive warnings: {e}", exc_info=True)
            return []

    async def generate_project_insights(
        self,
        task_drafts: List[Any]
    ) -> Dict[str, Any]:
        """
        Generate AI-powered insights about the planned project.

        Args:
            task_drafts: List of task draft objects

        Returns:
            Dictionary with insights and recommendations
        """
        try:
            if not task_drafts:
                return {
                    "complexity_score": 0,
                    "estimated_duration_weeks": 0,
                    "risk_factors": [],
                    "recommendations": []
                }

            # Build task summary for AI
            task_summaries = "\n".join([
                f"- {t.title} (priority: {t.priority}, effort: {t.estimated_effort_hours}h)"
                for t in task_drafts[:20]
            ])

            total_effort = sum(t.estimated_effort_hours or 0 for t in task_drafts)

            insights_prompt = f"""Analyze this project plan and provide insights:

Total Tasks: {len(task_drafts)}
Total Estimated Effort: {total_effort}h

Tasks:
{task_summaries}

Provide in JSON format:
{{
    "complexity_score": 1-10,
    "estimated_duration_weeks": number,
    "risk_factors": [
        "Risk factor 1",
        "Risk factor 2"
    ],
    "recommendations": [
        "Recommendation 1",
        "Recommendation 2"
    ],
    "critical_path": [
        "Task that should be done first",
        "Then this task"
    ]
}}"""

            ai_messages = [
                {"role": "system", "content": "You analyze project plans and provide structured insights. Always respond with valid JSON."},
                {"role": "user", "content": insights_prompt}
            ]

            response = await self.ai.chat(
                messages=ai_messages,
                temperature=0.4,
                max_tokens=800
            )

            insights = json.loads(response.choices[0].message.content)
            return insights

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse project insights: {e}")
            return {
                "complexity_score": 5,
                "estimated_duration_weeks": total_effort / 40 if 'total_effort' in locals() else 0,
                "risk_factors": [],
                "recommendations": []
            }
        except Exception as e:
            logger.error(f"Failed to generate project insights: {e}", exc_info=True)
            return {
                "complexity_score": 0,
                "estimated_duration_weeks": 0,
                "risk_factors": [],
                "recommendations": []
            }


# Global instance
memory_retrieval = MemoryRetrieval()
