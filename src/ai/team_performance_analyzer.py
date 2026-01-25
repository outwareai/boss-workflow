"""
Team performance analyzer with skill matching.

Analyzes team member performance on past projects to recommend
best assignees for new tasks based on:
- Historical success rate
- Skill match
- Current workload
- Task type expertise
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TeamMemberPerformance:
    """Performance metrics for a team member"""
    name: str
    role: str
    success_rate: float  # 0-1
    avg_completion_time: float  # hours
    task_count: int
    skills: List[str]
    current_workload: float  # 0-1 (0=free, 1=fully loaded)
    skill_match_score: float  # 0-1 for current task
    on_time_rate: float  # 0-1


class TeamPerformanceAnalyzer:
    """
    Analyze team performance and recommend assignees.

    Uses historical project data to match tasks with best-suited team members.
    """

    def __init__(self, ai_client=None):
        """
        Initialize analyzer.

        Args:
            ai_client: Optional AI client for skill extraction
        """
        self.ai = ai_client

    async def suggest_assignee(
        self,
        task_draft: Dict[str, Any],
        project_id: str,
        team_repo,
        task_repo
    ) -> str:
        """
        Suggest best assignee based on historical performance.

        Args:
            task_draft: Task to assign
            project_id: Current project ID
            team_repo: Team repository
            task_repo: Task repository

        Returns:
            Recommended assignee name
        """
        try:
            # Get team members
            team_members = await team_repo.get_all_active()

            if not team_members:
                logger.warning("No team members found - cannot suggest assignee")
                return "Unassigned"

            # Get performance metrics for each member
            performances = []

            for member in team_members:
                performance = await self._calculate_performance(
                    member,
                    task_draft,
                    task_repo
                )
                performances.append(performance)

            # Score and rank assignees
            best_assignee = self._rank_assignees(performances, task_draft)

            logger.info(
                f"Suggested assignee for '{task_draft.get('title')}': {best_assignee.name} "
                f"(score: success={best_assignee.success_rate:.0%}, "
                f"skill_match={best_assignee.skill_match_score:.0%}, "
                f"workload={best_assignee.current_workload:.0%})"
            )

            return best_assignee.name

        except Exception as e:
            logger.error(f"Failed to suggest assignee: {e}", exc_info=True)
            return "Unassigned"

    async def _calculate_performance(
        self,
        team_member,
        task_draft: Dict[str, Any],
        task_repo
    ) -> TeamMemberPerformance:
        """
        Calculate performance metrics for a team member.

        Args:
            team_member: Team member DB object
            task_draft: Task to evaluate for
            task_repo: Task repository

        Returns:
            Performance metrics
        """
        member_name = team_member.name

        # Get completed tasks by this member
        completed_tasks = await task_repo.get_by_assignee(
            assignee=member_name,
            status="completed",
            limit=50
        )

        if not completed_tasks:
            # New team member - use defaults
            return TeamMemberPerformance(
                name=member_name,
                role=team_member.role or "Team Member",
                success_rate=0.7,  # Default moderate success
                avg_completion_time=0.0,
                task_count=0,
                skills=self._extract_skills_from_role(team_member.role),
                current_workload=0.0,
                skill_match_score=0.5,  # Neutral
                on_time_rate=0.7
            )

        # Calculate metrics from completed tasks
        total_tasks = len(completed_tasks)
        on_time_count = 0
        total_completion_time = 0.0

        for task in completed_tasks:
            # Check if completed on time
            if task.deadline and task.completed_at:
                if task.completed_at <= task.deadline:
                    on_time_count += 1

            # Calculate completion time (if we have time tracking data)
            if hasattr(task, 'actual_effort_hours') and task.actual_effort_hours:
                total_completion_time += task.actual_effort_hours

        # Success rate (for now, based on on-time completion)
        success_rate = on_time_count / total_tasks if total_tasks > 0 else 0.5
        on_time_rate = success_rate  # Same metric for now

        # Average completion time
        avg_completion_time = (
            total_completion_time / total_tasks
            if total_tasks > 0 and total_completion_time > 0
            else 0.0
        )

        # Extract skills from past tasks
        skills = await self._extract_skills_from_tasks(completed_tasks)

        # Calculate current workload
        current_workload = await self._calculate_current_workload(
            member_name,
            task_repo
        )

        # Calculate skill match for this specific task
        skill_match_score = self._calculate_skill_match(
            skills,
            task_draft
        )

        return TeamMemberPerformance(
            name=member_name,
            role=team_member.role or "Team Member",
            success_rate=success_rate,
            avg_completion_time=avg_completion_time,
            task_count=total_tasks,
            skills=skills,
            current_workload=current_workload,
            skill_match_score=skill_match_score,
            on_time_rate=on_time_rate
        )

    async def _extract_skills_from_tasks(
        self,
        completed_tasks: List
    ) -> List[str]:
        """
        Extract skills from completed tasks.

        Args:
            completed_tasks: List of completed task objects

        Returns:
            List of skill keywords
        """
        skills = set()

        for task in completed_tasks:
            # Extract from task type
            if hasattr(task, 'type') and task.type:
                skills.add(task.type)

            # Extract from category
            if hasattr(task, 'category') and task.category:
                skills.add(task.category.lower())

            # Extract from tags
            if hasattr(task, 'tags') and task.tags:
                skills.update(tag.lower() for tag in task.tags)

        return list(skills)

    def _extract_skills_from_role(self, role: Optional[str]) -> List[str]:
        """
        Extract default skills based on role.

        Args:
            role: Team member role

        Returns:
            List of skills
        """
        if not role:
            return []

        role_lower = role.lower()

        # Role-based skill mapping
        skill_map = {
            "developer": ["coding", "development", "bug", "feature", "api"],
            "designer": ["design", "ui", "ux", "mockup", "wireframe"],
            "admin": ["admin", "management", "coordination", "documentation"],
            "qa": ["testing", "qa", "bug", "verification"],
            "devops": ["deployment", "infrastructure", "ci/cd", "server"],
        }

        for role_key, skills in skill_map.items():
            if role_key in role_lower:
                return skills

        return []

    async def _calculate_current_workload(
        self,
        member_name: str,
        task_repo
    ) -> float:
        """
        Calculate current workload (0=free, 1=fully loaded).

        Args:
            member_name: Team member name
            task_repo: Task repository

        Returns:
            Workload score (0-1)
        """
        try:
            # Get active tasks (not completed/cancelled)
            active_tasks = await task_repo.get_by_assignee(
                assignee=member_name,
                status_not_in=["completed", "cancelled"],
                limit=100
            )

            # Calculate workload based on:
            # 1. Number of active tasks
            # 2. Estimated hours remaining

            task_count = len(active_tasks)
            total_estimated_hours = 0.0

            for task in active_tasks:
                if hasattr(task, 'estimated_effort_hours') and task.estimated_effort_hours:
                    total_estimated_hours += task.estimated_effort_hours

            # Normalize workload
            # Assume 40 hours/week as "full load", 10 tasks as "very busy"
            hour_load = min(total_estimated_hours / 40.0, 1.0)
            task_load = min(task_count / 10.0, 1.0)

            # Combined workload (weighted average)
            workload = (hour_load * 0.7) + (task_load * 0.3)

            return min(workload, 1.0)

        except Exception as e:
            logger.error(f"Failed to calculate workload for {member_name}: {e}", exc_info=True)
            return 0.5  # Default moderate load

    def _calculate_skill_match(
        self,
        member_skills: List[str],
        task_draft: Dict[str, Any]
    ) -> float:
        """
        Calculate skill match score for task.

        Args:
            member_skills: List of member's skills
            task_draft: Task to evaluate

        Returns:
            Match score (0-1)
        """
        if not member_skills:
            return 0.5  # Neutral if no skills known

        # Extract task requirements
        task_type = task_draft.get("type", "").lower()
        task_category = task_draft.get("category", "").lower()
        task_tags = [t.lower() for t in task_draft.get("tags", [])]
        task_title = task_draft.get("title", "").lower()
        task_desc = task_draft.get("description", "").lower()

        # Combine task keywords
        task_keywords = set()
        if task_type:
            task_keywords.add(task_type)
        if task_category:
            task_keywords.add(task_category)
        task_keywords.update(task_tags)

        # Extract keywords from title/description
        for skill in member_skills:
            if skill in task_title or skill in task_desc:
                task_keywords.add(skill)

        # Calculate overlap
        member_skill_set = set(s.lower() for s in member_skills)
        matches = member_skill_set & task_keywords

        if not task_keywords:
            return 0.5  # Neutral if no task keywords

        match_score = len(matches) / len(task_keywords)

        # Boost for exact task type match
        if task_type in member_skill_set:
            match_score = min(match_score + 0.2, 1.0)

        return match_score

    def _rank_assignees(
        self,
        performances: List[TeamMemberPerformance],
        task_draft: Dict[str, Any]
    ) -> TeamMemberPerformance:
        """
        Rank assignees and return best match.

        Scoring formula:
        score = (success_rate * 0.4) + (skill_match * 0.4) + ((1 - workload) * 0.2)

        Args:
            performances: List of performance metrics
            task_draft: Task to assign

        Returns:
            Best assignee
        """
        if not performances:
            raise ValueError("No team members to evaluate")

        # Calculate scores
        scored = []

        for perf in performances:
            # Weighted scoring
            score = (
                perf.success_rate * 0.4 +           # 40% success history
                perf.skill_match_score * 0.4 +      # 40% skill match
                (1 - perf.current_workload) * 0.2   # 20% availability
            )

            scored.append((score, perf))

        # Sort by score (highest first)
        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_assignee = scored[0]

        logger.debug(
            f"Assignee ranking for '{task_draft.get('title')}':\n" +
            "\n".join([
                f"  {i+1}. {p.name}: {s:.2f} (success={p.success_rate:.2f}, "
                f"skill={p.skill_match_score:.2f}, avail={1-p.current_workload:.2f})"
                for i, (s, p) in enumerate(scored[:5])
            ])
        )

        return best_assignee

    async def get_team_performance_summary(
        self,
        team_repo,
        task_repo,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive team performance summary.

        Args:
            team_repo: Team repository
            task_repo: Task repository
            project_id: Optional project filter

        Returns:
            Dict with team performance metrics
        """
        try:
            team_members = await team_repo.get_all_active()

            summaries = []

            for member in team_members:
                # Get basic performance (without task_draft for general summary)
                dummy_task = {"title": "", "type": "task", "category": "", "tags": []}

                performance = await self._calculate_performance(
                    member,
                    dummy_task,
                    task_repo
                )

                summaries.append({
                    "name": performance.name,
                    "role": performance.role,
                    "success_rate": round(performance.success_rate, 2),
                    "on_time_rate": round(performance.on_time_rate, 2),
                    "task_count": performance.task_count,
                    "current_workload": round(performance.current_workload, 2),
                    "skills": performance.skills
                })

            # Overall team stats
            total_tasks = sum(s["task_count"] for s in summaries)
            avg_success = (
                sum(s["success_rate"] for s in summaries) / len(summaries)
                if summaries else 0
            )

            return {
                "team_members": summaries,
                "total_tasks_completed": total_tasks,
                "average_success_rate": round(avg_success, 2),
                "team_size": len(summaries)
            }

        except Exception as e:
            logger.error(f"Failed to get team performance summary: {e}", exc_info=True)
            return {
                "team_members": [],
                "total_tasks_completed": 0,
                "average_success_rate": 0.0,
                "team_size": 0
            }
