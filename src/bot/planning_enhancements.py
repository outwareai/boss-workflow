"""
Planning enhancements for GROUP 1: Conversational Planning Engine.

Adds:
- Historical effort estimation
- Team performance-based assignee suggestions
- Dependency validation
- Refinement impact analysis
"""

import logging
from typing import Dict, Any, List, Optional

from src.ai.historical_estimator import HistoricalEstimator, HistoricalPattern
from src.ai.team_performance_analyzer import TeamPerformanceAnalyzer
from src.ai.refinement_analyzer import RefinementAnalyzer
from src.utils.dependency_validator import DependencyValidator, TaskDraft
from src.database.repositories import (
    get_memory_repository,
    get_team_repository,
    get_task_repository,
    get_planning_repository,
    get_task_draft_repository
)

logger = logging.getLogger(__name__)


class PlanningEnhancer:
    """
    Enhances planning sessions with intelligent features.

    GROUP 1 Phase 2-3 Implementation:
    - Historical effort estimation
    - Smart assignee recommendations
    - Dependency validation
    - Refinement impact analysis
    """

    def __init__(self, ai_client):
        """
        Initialize enhancer.

        Args:
            ai_client: DeepSeek AI client
        """
        self.ai = ai_client
        self.historical_estimator = HistoricalEstimator(ai_client)
        self.team_analyzer = TeamPerformanceAnalyzer(ai_client)
        self.refinement_analyzer = RefinementAnalyzer()

    async def enhance_task_drafts(
        self,
        session_id: str,
        task_drafts: List[Dict[str, Any]],
        project_id: str,
        db_session
    ) -> List[Dict[str, Any]]:
        """
        Enhance task drafts with historical estimates and assignee suggestions.

        Args:
            session_id: Planning session ID
            task_drafts: AI-generated task drafts
            project_id: Project ID
            db_session: Database session

        Returns:
            Enhanced task drafts
        """
        try:
            memory_repo = get_memory_repository(db_session)
            team_repo = get_team_repository(db_session)
            task_repo = get_task_repository(db_session)

            enhanced = []

            for draft in task_drafts:
                # 1. Add historical effort estimation
                draft_with_effort = await self.historical_estimator.enhance_with_historical_effort(
                    draft,
                    project_id,
                    memory_repo
                )

                # 2. Suggest assignee based on team performance
                if not draft_with_effort.get("assigned_to"):
                    suggested_assignee = await self.team_analyzer.suggest_assignee(
                        draft_with_effort,
                        project_id,
                        team_repo,
                        task_repo
                    )
                    draft_with_effort["assigned_to"] = suggested_assignee
                    draft_with_effort["assignment_reasoning"] = (
                        "Suggested based on historical performance"
                    )

                enhanced.append(draft_with_effort)

            logger.info(
                f"Enhanced {len(enhanced)} task drafts for session {session_id} "
                f"with effort estimates and assignee suggestions"
            )

            return enhanced

        except Exception as e:
            logger.error(f"Failed to enhance task drafts: {e}", exc_info=True)
            # Return original drafts if enhancement fails
            return task_drafts

    async def validate_plan(
        self,
        session_id: str,
        task_drafts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate plan for dependency issues.

        Args:
            session_id: Planning session ID
            task_drafts: Task drafts to validate

        Returns:
            Validation result dict
        """
        try:
            # Convert to TaskDraft objects
            draft_objs = [
                TaskDraft(
                    task_id=d.get("draft_id", ""),
                    title=d.get("title", ""),
                    assignee=d.get("assigned_to", "Unassigned"),
                    dependencies=d.get("depends_on", []),
                    estimated_hours=d.get("estimated_hours", 0.0)
                )
                for d in task_drafts
            ]

            # Validate
            validator = DependencyValidator(draft_objs)
            validation = validator.validate_all()

            # Add execution order if valid
            if validation["is_valid"]:
                execution_order = validator.get_execution_order()
                critical_path, critical_hours = validator.estimate_critical_path()

                validation["execution_order"] = execution_order
                validation["critical_path"] = critical_path
                validation["critical_path_hours"] = critical_hours

            logger.info(
                f"Validated plan for session {session_id}: "
                f"valid={validation['is_valid']}, "
                f"cycles={len(validation['cycles'])}, "
                f"invalid_refs={len(validation['invalid_refs'])}"
            )

            return validation

        except Exception as e:
            logger.error(f"Failed to validate plan: {e}", exc_info=True)
            return {
                "is_valid": False,
                "cycles": [],
                "invalid_refs": [],
                "resource_conflicts": [],
                "warnings": [f"Validation failed: {str(e)}"]
            }

    async def analyze_refinement_impact(
        self,
        session_id: str,
        modified_task_id: str,
        changes: Dict[str, Any],
        db_session
    ) -> Dict[str, Any]:
        """
        Analyze impact of task refinement.

        Args:
            session_id: Planning session ID
            modified_task_id: Task being modified
            changes: Changes to apply
            db_session: Database session

        Returns:
            Impact analysis result
        """
        try:
            planning_repo = get_planning_repository(db_session)
            draft_repo = get_task_draft_repository(db_session)

            # Get all task drafts
            drafts = await draft_repo.get_by_session(session_id)

            # Convert to dicts
            draft_dicts = [
                {
                    "draft_id": d.draft_id,
                    "title": d.title,
                    "description": d.description,
                    "assigned_to": d.assigned_to,
                    "estimated_hours": d.estimated_hours,
                    "depends_on": d.depends_on or [],
                    "deadline": d.deadline if hasattr(d, 'deadline') else None
                }
                for d in drafts
            ]

            # Analyze impact
            impact = await self.refinement_analyzer.analyze_refinement(
                session_id,
                modified_task_id,
                changes,
                draft_dicts,
                planning_repo
            )

            # If timeline affected, recalculate deadlines
            if impact.timeline_changes.get("effort_delta", 0) > 0:
                new_deadlines = await self.refinement_analyzer.recalculate_deadlines(
                    session_id,
                    modified_task_id,
                    impact.timeline_changes["effort_delta"],
                    impact.affected_tasks,
                    draft_repo
                )

                # Apply new deadlines
                if new_deadlines:
                    await self.refinement_analyzer.apply_timeline_updates(
                        session_id,
                        new_deadlines,
                        draft_repo
                    )

                    impact.timeline_changes["deadlines_updated"] = len(new_deadlines)

            logger.info(
                f"Refinement impact analysis for {modified_task_id}: "
                f"valid={impact.is_valid}, affected={len(impact.affected_tasks)}"
            )

            return {
                "is_valid": impact.is_valid,
                "affected_tasks": impact.affected_tasks,
                "timeline_changes": impact.timeline_changes,
                "cycles": impact.cycles_detected,
                "resource_conflicts": impact.resource_conflicts,
                "invalid_refs": impact.invalid_dependencies,
                "warnings": impact.warnings,
                "message": self.refinement_analyzer.format_impact_message(impact)
            }

        except Exception as e:
            logger.error(f"Failed to analyze refinement impact: {e}", exc_info=True)
            return {
                "is_valid": False,
                "affected_tasks": [],
                "timeline_changes": {},
                "cycles": [],
                "resource_conflicts": [],
                "invalid_refs": [],
                "warnings": [f"Impact analysis failed: {str(e)}"],
                "message": f"❌ Failed to analyze impact: {str(e)}"
            }

    async def get_planning_insights(
        self,
        session_id: str,
        task_drafts: List[Dict[str, Any]],
        db_session
    ) -> Dict[str, Any]:
        """
        Get comprehensive planning insights.

        Args:
            session_id: Planning session ID
            task_drafts: Task drafts
            db_session: Database session

        Returns:
            Insights dict
        """
        try:
            # Validate plan
            validation = await self.validate_plan(session_id, task_drafts)

            # Get team performance summary
            team_repo = get_team_repository(db_session)
            task_repo = get_task_repository(db_session)

            team_summary = await self.team_analyzer.get_team_performance_summary(
                team_repo,
                task_repo
            )

            # Calculate project metrics
            total_hours = sum(d.get("estimated_hours", 0) for d in task_drafts)
            avg_hours_per_task = total_hours / len(task_drafts) if task_drafts else 0

            # Workload distribution
            workload_by_assignee = {}
            for draft in task_drafts:
                assignee = draft.get("assigned_to", "Unassigned")
                hours = draft.get("estimated_hours", 0)
                workload_by_assignee[assignee] = workload_by_assignee.get(assignee, 0) + hours

            insights = {
                "validation": validation,
                "team_performance": team_summary,
                "project_metrics": {
                    "total_hours": total_hours,
                    "task_count": len(task_drafts),
                    "avg_hours_per_task": round(avg_hours_per_task, 1),
                    "workload_distribution": workload_by_assignee
                }
            }

            if validation.get("critical_path_hours"):
                insights["project_metrics"]["critical_path_duration"] = validation["critical_path_hours"]
                insights["project_metrics"]["parallelization_potential"] = (
                    total_hours / validation["critical_path_hours"]
                    if validation["critical_path_hours"] > 0 else 1.0
                )

            logger.info(f"Generated planning insights for session {session_id}")
            return insights

        except Exception as e:
            logger.error(f"Failed to get planning insights: {e}", exc_info=True)
            return {
                "validation": {"is_valid": False, "warnings": [str(e)]},
                "team_performance": {"team_members": []},
                "project_metrics": {}
            }

    def format_validation_message(self, validation: Dict[str, Any]) -> str:
        """
        Format validation results as user-friendly message.

        Args:
            validation: Validation result

        Returns:
            Formatted message
        """
        lines = []

        if validation["is_valid"]:
            lines.append("✅ **Plan Validation: PASSED**")
        else:
            lines.append("❌ **Plan Validation: FAILED**")

        # Errors
        if validation["cycles"]:
            lines.append(f"\n❌ **Circular Dependencies ({len(validation['cycles'])}):**")
            for cycle in validation["cycles"][:3]:  # Show first 3
                cycle_str = " → ".join(cycle)
                lines.append(f"- {cycle_str}")

        if validation["invalid_refs"]:
            lines.append(f"\n❌ **Invalid Dependencies ({len(validation['invalid_refs'])}):**")
            for error in validation["invalid_refs"][:3]:
                lines.append(f"- {error}")

        # Warnings
        if validation["resource_conflicts"]:
            lines.append(f"\n⚠️ **Resource Conflicts ({len(validation['resource_conflicts'])}):**")
            for conflict in validation["resource_conflicts"][:3]:
                lines.append(f"- {conflict}")

        # Positive info
        if validation.get("execution_order"):
            levels = validation["execution_order"]
            lines.append(f"\n📊 **Execution Plan:** {len(levels)} phases")

        if validation.get("critical_path_hours"):
            lines.append(f"⏱️ **Critical Path:** {validation['critical_path_hours']:.1f} hours")

        return "\n".join(lines)
