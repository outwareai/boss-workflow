"""
Recognize patterns and find similar projects.

This module handles:
- Finding similar projects using AI-based similarity scoring
- Extracting common patterns across multiple projects
- Predicting challenges based on historical data
- Recommending planning templates
"""

import logging
from typing import List, Dict, Any, Optional
import json
from src.database.repositories import (
    get_memory_repository,
    get_template_repository
)
from src.database.connection import get_db_session
from src.ai.deepseek import get_deepseek_client

logger = logging.getLogger(__name__)


class PatternRecognizer:
    """Find patterns and similarities across projects."""

    def __init__(self):
        self.ai = get_deepseek_client()

    async def find_similar_projects(
        self,
        description: str,
        limit: int = 5,
        min_confidence: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Find projects similar to the given description.

        Args:
            description: New project description
            limit: Maximum number of results
            min_confidence: Minimum pattern confidence to consider

        Returns:
            List of similar projects with similarity scores
        """
        async with get_db_session() as session:
            try:
                memory_repo = get_memory_repository(session)

                # Get all project memories with decent confidence
                all_memories = await memory_repo.get_similar_projects(
                    min_confidence=min_confidence,
                    limit=50  # Get more candidates for AI to rank
                )

                if not all_memories:
                    logger.info("No project memories found for similarity matching")
                    return []

                # Build project summaries for AI
                project_summaries = []
                for i, memory in enumerate(all_memories):
                    summary = {
                        "index": i,
                        "project_id": memory.project_id,
                        "challenges": memory.common_challenges or [],
                        "successes": memory.success_patterns or [],
                        "team_insights": memory.team_insights or {},
                        "confidence": memory.pattern_confidence or 0.5
                    }
                    project_summaries.append(summary)

                summaries_text = "\n".join([
                    f"{i+1}. {s['project_id']}: Challenges={s['challenges'][:2]}, Successes={s['successes'][:2]}"
                    for i, s in enumerate(project_summaries[:20])  # Limit for tokens
                ])

                # Use AI to score similarity
                similarity_prompt = f"""Rate the similarity between this new project description and each past project.

New Project: "{description}"

Past Projects:
{summaries_text}

For each project, provide similarity score 0-100 based on:
- Similar goals/outcomes
- Similar complexity
- Similar technical requirements
- Similar team structure

Return JSON:
{{
    "similarities": [
        {{"project_id": "...", "score": 85, "reason": "Brief explanation"}}
    ]
}}

Only include projects with score >= 50."""

                ai_messages = [
                    {"role": "system", "content": "You analyze project similarity and provide structured scoring. Always respond with valid JSON."},
                    {"role": "user", "content": similarity_prompt}
                ]

                response = await self.ai.chat(
                    messages=ai_messages,
                    temperature=0.3,
                    max_tokens=1000
                )

                similarities = json.loads(response.choices[0].message.content)

                # Sort by score and return top matches
                ranked = sorted(
                    similarities.get("similarities", []),
                    key=lambda x: x["score"],
                    reverse=True
                )[:limit]

                # Fetch full memory details
                similar_projects = []
                for match in ranked:
                    # Find memory object
                    memory = next(
                        (m for m in all_memories if m.project_id == match["project_id"]),
                        None
                    )
                    if memory:
                        project_dict = {
                            "project_id": memory.project_id,
                            "common_challenges": memory.common_challenges,
                            "success_patterns": memory.success_patterns,
                            "team_insights": memory.team_insights,
                            "pattern_confidence": memory.pattern_confidence,
                            "last_analyzed_at": memory.last_analyzed_at,
                            "similarity_score": match["score"],
                            "similarity_reason": match["reason"]
                        }
                        similar_projects.append(project_dict)

                logger.info(f"Found {len(similar_projects)} similar projects for description")
                return similar_projects

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse similarity response: {e}")
                return []
            except Exception as e:
                logger.error(f"Failed to find similar projects: {e}", exc_info=True)
                return []

    async def extract_common_patterns(self, project_ids: List[str]) -> Dict[str, Any]:
        """
        Extract common patterns across multiple projects.

        Args:
            project_ids: List of project IDs to analyze

        Returns:
            Dictionary with aggregated patterns
        """
        async with get_db_session() as session:
            try:
                memory_repo = get_memory_repository(session)

                # Fetch all memories
                memories = []
                for pid in project_ids:
                    memory = await memory_repo.get_or_create_for_project(pid)
                    if memory and memory.pattern_confidence and memory.pattern_confidence >= 0.5:
                        memories.append(memory)

                if not memories:
                    logger.warning(f"No valid memories found for projects: {project_ids}")
                    return {
                        "common_challenges": [],
                        "common_successes": [],
                        "key_lessons": []
                    }

                # Aggregate challenges, successes, lessons
                all_challenges = []
                all_successes = []

                for m in memories:
                    if m.common_challenges:
                        all_challenges.extend(m.common_challenges if isinstance(m.common_challenges, list) else [])
                    if m.success_patterns:
                        all_successes.extend(m.success_patterns if isinstance(m.success_patterns, list) else [])

                # Find most common using AI
                pattern_prompt = f"""Find the most common patterns across these project insights:

Challenges mentioned:
{json.dumps(all_challenges, indent=2)}

Successes mentioned:
{json.dumps(all_successes, indent=2)}

Group similar items and return top 5 most common in each category.

Return JSON:
{{
    "common_challenges": [
        "Challenge pattern (appeared in X projects)"
    ],
    "common_successes": [
        "Success pattern (appeared in X projects)"
    ],
    "key_lessons": [
        "Key lesson derived from patterns"
    ]
}}"""

                ai_messages = [
                    {"role": "system", "content": "You analyze patterns across multiple projects and identify common themes. Always respond with valid JSON."},
                    {"role": "user", "content": pattern_prompt}
                ]

                response = await self.ai.chat(
                    messages=ai_messages,
                    temperature=0.4,
                    max_tokens=800
                )

                patterns = json.loads(response.choices[0].message.content)
                return patterns

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse pattern extraction: {e}")
                return {
                    "common_challenges": [],
                    "common_successes": [],
                    "key_lessons": []
                }
            except Exception as e:
                logger.error(f"Failed to extract common patterns: {e}", exc_info=True)
                return {
                    "common_challenges": [],
                    "common_successes": [],
                    "key_lessons": []
                }

    async def predict_challenges(
        self,
        project_description: str,
        team: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Predict challenges based on project type and team.

        Args:
            project_description: Description of the new project
            team: List of team member names

        Returns:
            List of predicted challenges with probabilities
        """
        async with get_db_session() as session:
            try:
                memory_repo = get_memory_repository(session)

                # Get high-confidence memories
                similar_memories = await memory_repo.get_similar_projects(
                    min_confidence=0.7,
                    limit=10
                )

                if not similar_memories:
                    logger.info("No historical data for challenge prediction")
                    return []

                # Extract all challenges from similar projects
                all_challenges = []
                for memory in similar_memories:
                    if memory.common_challenges:
                        challenges = memory.common_challenges if isinstance(memory.common_challenges, list) else []
                        for challenge in challenges:
                            all_challenges.append({
                                "challenge": challenge,
                                "project_id": memory.project_id,
                                "confidence": memory.pattern_confidence
                            })

                if not all_challenges:
                    return []

                challenges_text = "\n".join([
                    f"- {c['challenge']} (from {c['project_id']})"
                    for c in all_challenges[:15]
                ])

                # Use AI to predict which are most likely
                prediction_prompt = f"""Based on past projects, predict which challenges are most likely to occur in this new project.

New Project: "{project_description}"
Team: {', '.join(team)}

Past Challenges:
{challenges_text}

Consider:
- Team experience level
- Historical frequency
- Project complexity
- Similar past projects

Return top 5 predicted challenges with probability:
{{
    "predicted_challenges": [
        {{
            "challenge": "Specific challenge description",
            "probability": 0.75,
            "historical_frequency": 3,
            "mitigation": "Suggested mitigation strategy"
        }}
    ]
}}"""

                ai_messages = [
                    {"role": "system", "content": "You predict project challenges based on historical data. Always respond with valid JSON."},
                    {"role": "user", "content": prediction_prompt}
                ]

                response = await self.ai.chat(
                    messages=ai_messages,
                    temperature=0.3,
                    max_tokens=1000
                )

                predictions = json.loads(response.choices[0].message.content)
                return predictions.get("predicted_challenges", [])

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse challenge predictions: {e}")
                return []
            except Exception as e:
                logger.error(f"Failed to predict challenges: {e}", exc_info=True)
                return []

    async def recommend_templates(self, project_description: str) -> List[Dict[str, Any]]:
        """
        Recommend planning templates based on description.

        Args:
            project_description: Description of the new project

        Returns:
            List of recommended templates with match scores
        """
        async with get_db_session() as session:
            try:
                template_repo = get_template_repository(session)

                # Get all available templates
                templates = await template_repo.get_all_active()

                if not templates:
                    logger.info("No templates available for recommendations")
                    return []

                # Build template descriptions
                template_descriptions = []
                for template in templates:
                    desc = {
                        "template_id": template.template_id,
                        "name": template.template_name,
                        "description": template.description or "No description",
                        "category": template.category or "general"
                    }
                    template_descriptions.append(desc)

                templates_text = "\n".join([
                    f"{i+1}. {t['name']} ({t['category']}): {t['description']}"
                    for i, t in enumerate(template_descriptions)
                ])

                # Score template relevance
                template_prompt = f"""Match this project description to the most relevant planning templates:

Project: "{project_description}"

Available Templates:
{templates_text}

Score each template 0-100 for relevance based on:
- Project type match
- Complexity level
- Industry/domain fit

Return JSON:
{{
    "matches": [
        {{
            "template_id": "...",
            "score": 90,
            "reason": "Brief explanation"
        }}
    ]
}}

Only include templates with score >= 50."""

                ai_messages = [
                    {"role": "system", "content": "You match projects to planning templates. Always respond with valid JSON."},
                    {"role": "user", "content": template_prompt}
                ]

                response = await self.ai.chat(
                    messages=ai_messages,
                    temperature=0.3,
                    max_tokens=800
                )

                matches = json.loads(response.choices[0].message.content)

                # Return top 3 matches
                ranked = sorted(
                    matches.get("matches", []),
                    key=lambda x: x["score"],
                    reverse=True
                )[:3]

                recommendations = []
                for match in ranked:
                    # Find template object
                    template = next(
                        (t for t in templates if t.template_id == match["template_id"]),
                        None
                    )
                    if template:
                        rec = {
                            "template_id": template.template_id,
                            "template_name": template.template_name,
                            "description": template.description,
                            "category": template.category,
                            "task_sections": template.task_sections,
                            "match_score": match["score"],
                            "match_reason": match["reason"]
                        }
                        recommendations.append(rec)

                logger.info(f"Recommended {len(recommendations)} templates for project")
                return recommendations

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse template recommendations: {e}")
                return []
            except Exception as e:
                logger.error(f"Failed to recommend templates: {e}", exc_info=True)
                return []


# Global instance
pattern_recognizer = PatternRecognizer()
