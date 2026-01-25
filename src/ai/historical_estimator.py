"""
Historical effort estimator using vector similarity.

Analyzes past projects to predict effort for new tasks based on:
- Title similarity (semantic)
- Task type matching
- Complexity patterns
- Team performance history
"""

import logging
import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HistoricalPattern:
    """Pattern extracted from completed project"""
    task_title: str
    task_type: str
    estimated_hours: float
    actual_hours: float
    assignee: str
    complexity_score: float  # 1-10
    success_rate: float  # 0-1
    project_id: str
    completed_at: datetime


class HistoricalEstimator:
    """
    Estimate task effort based on historical data.

    Uses semantic similarity to match new tasks with similar completed tasks.
    """

    def __init__(self, ai_client):
        """
        Initialize estimator.

        Args:
            ai_client: DeepSeek AI client for embeddings/similarity
        """
        self.ai = ai_client

    async def estimate_effort(
        self,
        task_draft: Dict[str, Any],
        historical_patterns: List[HistoricalPattern],
        confidence_threshold: float = 0.6
    ) -> Dict[str, Any]:
        """
        Estimate effort for a task based on historical data.

        Args:
            task_draft: Task to estimate (must have title, description)
            historical_patterns: List of past task patterns
            confidence_threshold: Minimum similarity for high confidence

        Returns:
            Dict with:
            - estimated_hours: float
            - confidence: str (high/medium/low)
            - similar_tasks: List of similar historical tasks
            - reasoning: str explaining the estimate
        """
        if not historical_patterns:
            # No history - use AI-based estimation
            return await self._ai_estimate_effort(task_draft)

        # Calculate similarity scores
        task_title = task_draft.get("title", "")
        task_type = task_draft.get("type", "task")
        task_description = task_draft.get("description", "")

        # Combine title + description for better matching
        task_text = f"{task_title} {task_description}".strip()

        similar_tasks = await self._find_similar_tasks(
            task_text,
            task_type,
            historical_patterns
        )

        if not similar_tasks:
            # No similar tasks found
            return await self._ai_estimate_effort(task_draft)

        # Calculate weighted average of similar tasks
        total_weight = 0.0
        weighted_hours = 0.0

        for pattern, similarity in similar_tasks[:5]:  # Top 5 matches
            # Weight by similarity and success rate
            weight = similarity * pattern.success_rate
            weighted_hours += pattern.actual_hours * weight
            total_weight += weight

        if total_weight == 0:
            return await self._ai_estimate_effort(task_draft)

        estimated_hours = weighted_hours / total_weight

        # Determine confidence based on similarity and count
        avg_similarity = sum(s for _, s in similar_tasks[:5]) / min(len(similar_tasks), 5)

        if avg_similarity >= confidence_threshold and len(similar_tasks) >= 3:
            confidence = "high"
        elif avg_similarity >= 0.4 and len(similar_tasks) >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        # Build reasoning
        top_match = similar_tasks[0][0]
        reasoning = (
            f"Based on {len(similar_tasks)} similar past tasks. "
            f"Most similar: '{top_match.task_title}' took {top_match.actual_hours:.1f}h "
            f"(estimated {top_match.estimated_hours:.1f}h). "
            f"Average similarity: {avg_similarity:.0%}."
        )

        logger.info(
            f"Historical estimate for '{task_title}': {estimated_hours:.1f}h "
            f"(confidence: {confidence}, {len(similar_tasks)} similar tasks)"
        )

        return {
            "estimated_hours": round(estimated_hours, 1),
            "confidence": confidence,
            "similar_tasks": [
                {
                    "title": p.task_title,
                    "actual_hours": p.actual_hours,
                    "similarity": round(s, 2)
                }
                for p, s in similar_tasks[:3]
            ],
            "reasoning": reasoning,
            "method": "historical"
        }

    async def _find_similar_tasks(
        self,
        task_text: str,
        task_type: str,
        historical_patterns: List[HistoricalPattern]
    ) -> List[tuple[HistoricalPattern, float]]:
        """
        Find similar tasks using semantic similarity.

        Args:
            task_text: Combined title + description
            task_type: Task type to match
            historical_patterns: Available historical data

        Returns:
            List of (pattern, similarity_score) tuples, sorted by similarity
        """
        # Filter by task type first (if specified)
        candidates = historical_patterns

        if task_type and task_type != "task":
            candidates = [
                p for p in candidates
                if p.task_type == task_type
            ]

        if not candidates:
            candidates = historical_patterns  # Fall back to all types

        # Calculate similarity for each candidate
        similarities = []

        for pattern in candidates:
            pattern_text = f"{pattern.task_title}"
            similarity = await self._calculate_similarity(task_text, pattern_text)
            similarities.append((pattern, similarity))

        # Sort by similarity (highest first)
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Filter out very low similarity matches
        filtered = [(p, s) for p, s in similarities if s >= 0.3]

        logger.debug(f"Found {len(filtered)} similar tasks (threshold: 0.3)")
        return filtered

    async def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate semantic similarity between two texts.

        Uses AI to compare task descriptions.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1)
        """
        # Simple keyword-based similarity as fallback
        keywords1 = set(self._extract_keywords(text1.lower()))
        keywords2 = set(self._extract_keywords(text2.lower()))

        if not keywords1 or not keywords2:
            return 0.0

        # Jaccard similarity
        intersection = keywords1 & keywords2
        union = keywords1 | keywords2

        jaccard = len(intersection) / len(union) if union else 0.0

        # Boost for exact word matches
        exact_matches = sum(1 for w in keywords1 if w in text2.lower())
        exact_boost = min(exact_matches * 0.1, 0.3)

        similarity = min(jaccard + exact_boost, 1.0)

        return similarity

    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract meaningful keywords from text.

        Args:
            text: Input text

        Returns:
            List of keywords
        """
        # Remove common words
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "be", "been",
            "this", "that", "these", "those", "it", "its", "i", "you", "we", "they"
        }

        # Extract words (alphanumeric only)
        words = re.findall(r'\b[a-z0-9]+\b', text.lower())

        # Filter stopwords and short words
        keywords = [w for w in words if w not in stopwords and len(w) > 2]

        return keywords

    async def _ai_estimate_effort(self, task_draft: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use AI to estimate effort when no historical data available.

        Args:
            task_draft: Task to estimate

        Returns:
            Estimation dict
        """
        title = task_draft.get("title", "Untitled task")
        description = task_draft.get("description", "")
        task_type = task_draft.get("type", "task")
        priority = task_draft.get("priority", "medium")

        prompt = f"""Estimate the time required to complete this task in hours.

Task Type: {task_type}
Priority: {priority}
Title: {title}
Description: {description or 'No description provided'}

Consider:
- Complexity of the work
- Typical time for similar tasks
- Need for testing/review

Respond with ONLY a JSON object:
{{
    "estimated_hours": <number>,
    "reasoning": "<brief explanation>",
    "confidence": "<low/medium/high>"
}}
"""

        try:
            messages = [
                {"role": "system", "content": "You are a project estimation expert."},
                {"role": "user", "content": prompt}
            ]

            response = await self.ai.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=300
            )

            result = json.loads(response.choices[0].message.content)

            logger.info(f"AI estimate for '{title}': {result['estimated_hours']}h")

            result["method"] = "ai"
            result["similar_tasks"] = []
            return result

        except Exception as e:
            logger.error(f"AI estimation failed: {e}", exc_info=True)

            # Fallback estimates based on task type
            default_hours = {
                "bug": 2.0,
                "feature": 8.0,
                "task": 4.0,
                "research": 6.0,
                "design": 4.0
            }

            return {
                "estimated_hours": default_hours.get(task_type, 4.0),
                "confidence": "low",
                "similar_tasks": [],
                "reasoning": f"Default estimate for {task_type} task (AI estimation failed)",
                "method": "default"
            }

    async def enhance_with_historical_effort(
        self,
        task_draft: Dict[str, Any],
        project_id: str,
        memory_repo
    ) -> Dict[str, Any]:
        """
        Add effort estimation to task draft based on historical data.

        Args:
            task_draft: Task draft dict
            project_id: Current project ID
            memory_repo: Memory repository for fetching patterns

        Returns:
            Enhanced task draft with estimation fields
        """
        try:
            # Fetch similar historical patterns
            similar_patterns = await self._fetch_similar_patterns(
                task_draft,
                project_id,
                memory_repo
            )

            # Estimate effort
            estimation = await self.estimate_effort(
                task_draft,
                similar_patterns
            )

            # Enhance task draft
            task_draft["estimated_hours"] = estimation["estimated_hours"]
            task_draft["estimation_confidence"] = estimation["confidence"]
            task_draft["estimation_reasoning"] = estimation["reasoning"]
            task_draft["similar_tasks"] = estimation["similar_tasks"]

            return task_draft

        except Exception as e:
            logger.error(f"Failed to enhance task with historical effort: {e}", exc_info=True)
            # Return task draft unchanged if enhancement fails
            return task_draft

    async def _fetch_similar_patterns(
        self,
        task_draft: Dict[str, Any],
        project_id: str,
        memory_repo
    ) -> List[HistoricalPattern]:
        """
        Fetch similar patterns from project memory.

        Args:
            task_draft: Task to match
            project_id: Current project
            memory_repo: Memory repository

        Returns:
            List of historical patterns
        """
        try:
            # Get similar projects from memory
            similar_projects = await memory_repo.get_similar_projects(
                category=task_draft.get("category"),
                min_confidence=0.5,
                limit=10
            )

            patterns = []

            for project_memory in similar_projects:
                # Extract patterns from project memory
                if project_memory.estimated_vs_actual:
                    for task_data in project_memory.estimated_vs_actual.get("tasks", []):
                        pattern = HistoricalPattern(
                            task_title=task_data.get("title", ""),
                            task_type=task_data.get("type", "task"),
                            estimated_hours=task_data.get("estimated_hours", 0),
                            actual_hours=task_data.get("actual_hours", 0),
                            assignee=task_data.get("assignee", ""),
                            complexity_score=task_data.get("complexity", 5),
                            success_rate=task_data.get("success_rate", 0.8),
                            project_id=project_memory.project_id,
                            completed_at=datetime.fromisoformat(
                                task_data.get("completed_at", datetime.utcnow().isoformat())
                            )
                        )
                        patterns.append(pattern)

            logger.info(f"Fetched {len(patterns)} historical patterns from {len(similar_projects)} projects")
            return patterns

        except Exception as e:
            logger.error(f"Failed to fetch historical patterns: {e}", exc_info=True)
            return []
