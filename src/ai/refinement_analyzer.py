"""
Refinement impact analyzer for planning sessions.

Analyzes the impact of task modifications on:
- Dependent task timelines
- Resource allocation
- Project deadlines
- Dependency validity
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.utils.dependency_validator import DependencyValidator, TaskDraft

logger = logging.getLogger(__name__)


@dataclass
class RefinementImpact:
    """Impact analysis result"""
    modified_task_id: str
    affected_tasks: List[str]
    timeline_changes: Dict[str, Any]
    cycles_detected: List[List[str]]
    resource_conflicts: List[str]
    invalid_dependencies: List[str]
    warnings: List[str]
    is_valid: bool


class RefinementAnalyzer:
    """
    Analyze impact of task refinements on planning session.

    Recalculates timelines, validates dependencies, and detects conflicts.
    """

    def __init__(self):
        """Initialize analyzer."""
        pass

    async def analyze_refinement(
        self,
        session_id: str,
        modified_task_id: str,
        changes: Dict[str, Any],
        all_task_drafts: List[Dict[str, Any]],
        planning_repo
    ) -> RefinementImpact:
        """
        Analyze impact of refining a task.

        Args:
            session_id: Planning session ID
            modified_task_id: Task being modified
            changes: Dict of changes being made
            all_task_drafts: All task drafts in session
            planning_repo: Planning repository

        Returns:
            RefinementImpact with analysis results
        """
        try:
            # Apply changes to get updated task list
            updated_drafts = self._apply_changes(
                all_task_drafts,
                modified_task_id,
                changes
            )

            # Convert to TaskDraft objects for validation
            task_draft_objs = self._convert_to_task_drafts(updated_drafts)

            # Validate dependencies
            validator = DependencyValidator(task_draft_objs)
            validation = validator.validate_all()

            # Find affected tasks
            affected_tasks = self._find_affected_tasks(
                modified_task_id,
                updated_drafts,
                changes
            )

            # Calculate timeline impact
            timeline_changes = await self._calculate_timeline_impact(
                modified_task_id,
                changes,
                updated_drafts,
                affected_tasks
            )

            # Build warnings
            warnings = []
            if validation["resource_conflicts"]:
                warnings.append(
                    f"⚠️ {len(validation['resource_conflicts'])} resource conflict(s) detected"
                )
            if timeline_changes.get("critical_path_extended"):
                warnings.append(
                    f"⚠️ Critical path extended by {timeline_changes['critical_path_delta']:.1f} hours"
                )

            impact = RefinementImpact(
                modified_task_id=modified_task_id,
                affected_tasks=affected_tasks,
                timeline_changes=timeline_changes,
                cycles_detected=validation["cycles"],
                resource_conflicts=validation["resource_conflicts"],
                invalid_dependencies=validation["invalid_refs"],
                warnings=warnings,
                is_valid=validation["is_valid"]
            )

            logger.info(
                f"Refinement impact for {modified_task_id}: "
                f"{len(affected_tasks)} affected, valid={impact.is_valid}"
            )

            return impact

        except Exception as e:
            logger.error(f"Failed to analyze refinement impact: {e}", exc_info=True)
            # Return empty impact on error
            return RefinementImpact(
                modified_task_id=modified_task_id,
                affected_tasks=[],
                timeline_changes={},
                cycles_detected=[],
                resource_conflicts=[],
                invalid_dependencies=[],
                warnings=[f"Analysis failed: {str(e)}"],
                is_valid=False
            )

    def _apply_changes(
        self,
        task_drafts: List[Dict[str, Any]],
        modified_task_id: str,
        changes: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Apply changes to task drafts.

        Args:
            task_drafts: Original task drafts
            modified_task_id: Task being modified
            changes: Changes to apply

        Returns:
            Updated task drafts list
        """
        updated = []

        for draft in task_drafts:
            if draft["draft_id"] == modified_task_id:
                # Apply changes to this task
                updated_draft = draft.copy()
                updated_draft.update(changes)
                updated.append(updated_draft)
            else:
                updated.append(draft.copy())

        return updated

    def _convert_to_task_drafts(
        self,
        task_drafts: List[Dict[str, Any]]
    ) -> List[TaskDraft]:
        """
        Convert dict-based drafts to TaskDraft objects.

        Args:
            task_drafts: List of task draft dicts

        Returns:
            List of TaskDraft objects
        """
        objects = []

        for draft in task_drafts:
            obj = TaskDraft(
                task_id=draft.get("draft_id", ""),
                title=draft.get("title", ""),
                assignee=draft.get("assigned_to", "Unassigned"),
                dependencies=draft.get("depends_on", []),
                estimated_hours=draft.get("estimated_hours", 0.0)
            )
            objects.append(obj)

        return objects

    def _find_affected_tasks(
        self,
        modified_task_id: str,
        task_drafts: List[Dict[str, Any]],
        changes: Dict[str, Any]
    ) -> List[str]:
        """
        Find tasks affected by the modification.

        Args:
            modified_task_id: Modified task ID
            task_drafts: All task drafts
            changes: Changes made

        Returns:
            List of affected task IDs
        """
        affected = []

        # Find tasks that depend on the modified task
        for draft in task_drafts:
            dependencies = draft.get("depends_on", [])
            if modified_task_id in dependencies:
                affected.append(draft["draft_id"])

        # If assignee changed, check for resource conflicts
        if "assigned_to" in changes:
            new_assignee = changes["assigned_to"]

            for draft in task_drafts:
                if draft["draft_id"] == modified_task_id:
                    continue

                # Check if this task has same assignee and is dependent
                if draft.get("assigned_to") == new_assignee:
                    dependencies = draft.get("depends_on", [])
                    if modified_task_id in dependencies:
                        if draft["draft_id"] not in affected:
                            affected.append(draft["draft_id"])

        return affected

    async def _calculate_timeline_impact(
        self,
        modified_task_id: str,
        changes: Dict[str, Any],
        task_drafts: List[Dict[str, Any]],
        affected_task_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Calculate timeline impact of changes.

        Args:
            modified_task_id: Modified task ID
            changes: Changes made
            task_drafts: All task drafts
            affected_task_ids: Tasks affected by change

        Returns:
            Dict with timeline impact details
        """
        impact = {
            "effort_delta": 0.0,
            "affected_count": len(affected_task_ids),
            "critical_path_extended": False,
            "critical_path_delta": 0.0
        }

        # Check if estimated_hours changed
        if "estimated_hours" in changes:
            # Find original task
            original_task = next(
                (d for d in task_drafts if d["draft_id"] == modified_task_id),
                None
            )

            if original_task:
                original_hours = original_task.get("estimated_hours", 0.0)
                new_hours = changes["estimated_hours"]
                impact["effort_delta"] = new_hours - original_hours

                # If task is on critical path, this extends the project
                # For now, we'll check if it has dependents
                if affected_task_ids:
                    impact["critical_path_extended"] = impact["effort_delta"] > 0
                    impact["critical_path_delta"] = impact["effort_delta"]

        # Calculate new total project estimate
        total_hours = sum(
            draft.get("estimated_hours", 0.0)
            for draft in task_drafts
        )
        impact["total_project_hours"] = total_hours

        return impact

    async def recalculate_deadlines(
        self,
        session_id: str,
        modified_task_id: str,
        effort_delta: float,
        affected_task_ids: List[str],
        task_draft_repo
    ) -> Dict[str, datetime]:
        """
        Recalculate deadlines for affected tasks.

        Args:
            session_id: Planning session ID
            modified_task_id: Modified task ID
            effort_delta: Change in effort (hours)
            affected_task_ids: Affected task IDs
            task_draft_repo: Task draft repository

        Returns:
            Dict mapping task_id -> new deadline
        """
        new_deadlines = {}

        if effort_delta <= 0:
            # No timeline extension needed
            return new_deadlines

        try:
            # Get all affected tasks
            for task_id in affected_task_ids:
                draft = await task_draft_repo.get_by_id(task_id)

                if draft and hasattr(draft, 'deadline') and draft.deadline:
                    # Shift deadline by effort delta
                    # Assuming 8-hour workdays
                    days_delta = effort_delta / 8.0
                    new_deadline = draft.deadline + timedelta(days=days_delta)
                    new_deadlines[task_id] = new_deadline

            logger.info(f"Recalculated {len(new_deadlines)} deadlines (+{effort_delta:.1f}h)")
            return new_deadlines

        except Exception as e:
            logger.error(f"Failed to recalculate deadlines: {e}", exc_info=True)
            return {}

    async def apply_timeline_updates(
        self,
        session_id: str,
        new_deadlines: Dict[str, datetime],
        task_draft_repo
    ) -> int:
        """
        Apply recalculated deadlines to task drafts.

        Args:
            session_id: Planning session ID
            new_deadlines: Dict of task_id -> new deadline
            task_draft_repo: Task draft repository

        Returns:
            Number of tasks updated
        """
        updated_count = 0

        try:
            for task_id, new_deadline in new_deadlines.items():
                await task_draft_repo.update(
                    task_id,
                    {"deadline": new_deadline}
                )
                updated_count += 1

            logger.info(f"Applied timeline updates to {updated_count} tasks")
            return updated_count

        except Exception as e:
            logger.error(f"Failed to apply timeline updates: {e}", exc_info=True)
            return updated_count

    def format_impact_message(self, impact: RefinementImpact) -> str:
        """
        Format impact analysis as user-friendly message.

        Args:
            impact: Impact analysis result

        Returns:
            Formatted message
        """
        lines = [f"✅ Updated {impact.modified_task_id}"]

        # Timeline impact
        if impact.timeline_changes.get("effort_delta"):
            delta = impact.timeline_changes["effort_delta"]
            sign = "+" if delta > 0 else ""
            lines.append(f"\n⏱️ **Timeline Impact:** {sign}{delta:.1f} hours")

        # Affected tasks
        if impact.affected_tasks:
            lines.append(f"\n📊 **Impact Analysis:**")
            lines.append(f"- {len(impact.affected_tasks)} dependent task(s) affected")

            if impact.timeline_changes.get("critical_path_extended"):
                delta = impact.timeline_changes["critical_path_delta"]
                lines.append(f"- Critical path extended by {delta:.1f} hours")

        # Errors
        if impact.cycles_detected:
            lines.append(f"\n❌ **Circular Dependencies Detected:**")
            for cycle in impact.cycles_detected:
                cycle_str = " → ".join(cycle)
                lines.append(f"- {cycle_str}")
            lines.append("\n⚠️ Please fix these before approving!")

        if impact.invalid_dependencies:
            lines.append(f"\n❌ **Invalid Dependencies:**")
            for error in impact.invalid_dependencies:
                lines.append(f"- {error}")

        # Warnings
        if impact.resource_conflicts:
            lines.append(f"\n⚠️ **Resource Conflicts:**")
            for conflict in impact.resource_conflicts[:3]:  # Show first 3
                lines.append(f"- {conflict}")
            if len(impact.resource_conflicts) > 3:
                lines.append(f"- ... and {len(impact.resource_conflicts) - 3} more")

        # Overall status
        if impact.is_valid:
            lines.append(f"\n✅ Plan is valid and ready to proceed")
        else:
            lines.append(f"\n❌ Plan has errors - please fix before finalizing")

        return "\n".join(lines)
