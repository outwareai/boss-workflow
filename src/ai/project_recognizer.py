"""
Project Recognition & Context Retrieval

GROUP 1.3: Project Memory Core
- Detect project references in conversation
- Retrieve relevant project context for planning
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from src.database.connection import get_session
from src.database.repositories import (
    get_project_repository,
    get_memory_repository,
    get_decision_repository,
    get_discussion_repository
)
from src.ai.deepseek import DeepSeekClient

logger = logging.getLogger(__name__)


class ProjectRecognizer:
    """Recognize project references and retrieve context"""

    def __init__(self, ai_client: DeepSeekClient):
        self.ai = ai_client

    async def detect_project_reference(
        self,
        message: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Detect if message references an existing project

        Args:
            message: User message
            user_id: User ID

        Returns:
            Dict with project_id and confidence, or None
        """
        try:
            async with get_session() as db:
                project_repo = get_project_repository(db)

                # Get recent projects for this user
                recent_projects = await project_repo.get_by_creator(user_id, limit=20)

                if not recent_projects:
                    return None

                # Build project context for AI
                project_list = []
                for proj in recent_projects:
                    project_list.append({
                        "id": proj.project_id,
                        "name": proj.name,
                        "description": proj.description or "",
                        "status": proj.status
                    })

                # Ask AI to match
                prompt = f"""Does this message reference any of these existing projects?

MESSAGE: "{message}"

PROJECTS:
{self._format_projects_for_ai(project_list)}

If the message clearly references one of these projects, respond with JSON:
{{"project_id": "PROJECT-ID", "confidence": 0.8}}

If no clear match, respond with:
{{"project_id": null, "confidence": 0.0}}

Only match if the message CLEARLY refers to the project by name or description.
"""

                response = await self.ai.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )

                import json
                result = json.loads(response)

                if result.get("project_id") and result.get("confidence", 0) > 0.5:
                    logger.info(f"Detected project reference: {result['project_id']} (confidence: {result['confidence']})")
                    return result

                return None

        except Exception as e:
            logger.error(f"Project detection failed: {e}", exc_info=True)
            return None

    def _format_projects_for_ai(self, projects: List[Dict]) -> str:
        """Format project list for AI prompt"""
        lines = []
        for proj in projects:
            lines.append(f"- {proj['id']}: {proj['name']}")
            if proj.get('description'):
                lines.append(f"  Description: {proj['description'][:100]}")
            lines.append(f"  Status: {proj['status']}")
        return "\n".join(lines)

    async def get_project_context(
        self,
        project_id: str,
        include_memory: bool = True,
        include_decisions: bool = True,
        include_discussions: bool = True
    ) -> Dict[str, Any]:
        """
        Retrieve full context for a project

        Args:
            project_id: Project ID
            include_memory: Include AI-extracted patterns
            include_decisions: Include key decisions
            include_discussions: Include important discussions

        Returns:
            Dict with project context
        """
        try:
            async with get_session() as db:
                project_repo = get_project_repository(db)
                project = await project_repo.get_by_id(project_id)

                if not project:
                    logger.warning(f"Project {project_id} not found")
                    return {}

                context = {
                    "project_id": project.project_id,
                    "name": project.name,
                    "description": project.description,
                    "status": project.status,
                    "created_at": project.created_at.isoformat() if project.created_at else None
                }

                # Add memory patterns
                if include_memory:
                    memory_repo = get_memory_repository(db)
                    memory = await memory_repo.get_or_create_for_project(project_id)

                    if memory.common_challenges:
                        context["challenges"] = memory.common_challenges
                    if memory.success_patterns:
                        context["successes"] = memory.success_patterns
                    if memory.team_insights:
                        context["team_insights"] = memory.team_insights
                    if memory.bottleneck_patterns:
                        context["bottlenecks"] = memory.bottleneck_patterns

                # Add key decisions
                if include_decisions:
                    decision_repo = get_decision_repository(db)
                    decisions = await decision_repo.get_by_project(project_id)

                    if decisions:
                        context["decisions"] = [
                            {
                                "type": d.decision_type,
                                "text": d.decision_text,
                                "reasoning": d.reasoning,
                                "date": d.decided_at.isoformat() if d.decided_at else None
                            }
                            for d in decisions[:5]  # Last 5 decisions
                        ]

                # Add important discussions
                if include_discussions:
                    discussion_repo = get_discussion_repository(db)
                    discussions = await discussion_repo.get_important_for_project(
                        project_id,
                        min_importance=0.7,
                        limit=5
                    )

                    if discussions:
                        context["discussions"] = [
                            {
                                "topic": d.topic,
                                "summary": d.summary,
                                "key_points": d.key_points,
                                "date": d.occurred_at.isoformat() if d.occurred_at else None
                            }
                            for d in discussions
                        ]

                logger.info(f"Retrieved context for project {project_id}")
                return context

        except Exception as e:
            logger.error(f"Failed to get project context: {e}", exc_info=True)
            return {}

    async def suggest_related_projects(
        self,
        planning_request: str,
        user_id: str,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Suggest projects related to planning request

        Args:
            planning_request: User's planning request
            user_id: User ID
            limit: Max suggestions

        Returns:
            List of related projects with relevance scores
        """
        try:
            async with get_session() as db:
                project_repo = get_project_repository(db)

                # Get recent completed projects (good for learning)
                recent_projects = await project_repo.get_by_creator(
                    user_id,
                    status="completed",
                    limit=20
                )

                if not recent_projects:
                    return []

                # Use AI to find related projects
                project_list = [
                    {
                        "id": p.project_id,
                        "name": p.name,
                        "description": p.description or ""
                    }
                    for p in recent_projects
                ]

                prompt = f"""Which of these past projects are most relevant to this new planning request?

NEW REQUEST: "{planning_request}"

PAST PROJECTS:
{self._format_projects_for_ai(project_list)}

Return JSON array of up to {limit} most relevant projects, sorted by relevance:
[
  {{"project_id": "PROJECT-ID", "relevance": 0.9, "reason": "why relevant"}},
  ...
]

Only include projects with relevance > 0.5.
"""

                response = await self.ai.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )

                import json
                result = json.loads(response)

                suggestions = result.get("suggestions", [])

                logger.info(f"Found {len(suggestions)} related projects for planning")
                return suggestions[:limit]

        except Exception as e:
            logger.error(f"Failed to suggest related projects: {e}", exc_info=True)
            return []


def get_project_recognizer(ai_client: DeepSeekClient) -> ProjectRecognizer:
    """Factory function for project recognizer"""
    return ProjectRecognizer(ai_client)
