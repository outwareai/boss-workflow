"""
Dependency validation for task drafts in planning sessions.

Provides graph-based validation for:
- Circular dependencies detection
- Invalid dependency references
- Resource conflicts (same person on dependent tasks)
"""

import logging
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TaskDraft:
    """Minimal task draft structure for validation"""
    task_id: str
    title: str
    assignee: str
    dependencies: List[str]  # List of task_ids this task depends on
    estimated_hours: float


class DependencyValidator:
    """
    Validate task dependencies for cycles and conflicts.

    Uses graph algorithms to detect:
    1. Circular dependencies (cycles in dependency graph)
    2. Invalid references (dependencies that don't exist)
    3. Resource conflicts (same person assigned to dependent tasks)
    """

    def __init__(self, task_drafts: List[TaskDraft]):
        """
        Initialize validator with task drafts.

        Args:
            task_drafts: List of task draft objects
        """
        self.tasks = {t.task_id: t for t in task_drafts}
        self.graph = self._build_graph()

    def _build_graph(self) -> Dict[str, List[str]]:
        """
        Build adjacency list of dependencies.

        Returns:
            Dict mapping task_id -> list of task_ids it depends on
        """
        graph = {tid: [] for tid in self.tasks.keys()}

        for task in self.tasks.values():
            if task.dependencies:
                graph[task.task_id] = task.dependencies.copy()

        return graph

    def detect_circular_dependencies(self) -> List[List[str]]:
        """
        Detect cycles using Depth-First Search (DFS).

        Returns:
            List of cycles, where each cycle is a list of task_ids forming a loop
        """
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: List[str]) -> None:
            """
            DFS helper to detect cycles.

            Args:
                node: Current task_id
                path: Path taken so far
            """
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self.graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path.copy())
                elif neighbor in rec_stack:
                    # Found a cycle - extract the cycle from path
                    try:
                        cycle_start = path.index(neighbor)
                        cycle = path[cycle_start:] + [neighbor]

                        # Normalize cycle (start with smallest task_id for deduplication)
                        min_idx = cycle.index(min(cycle[:-1]))  # Exclude duplicate last element
                        normalized = cycle[min_idx:-1] + cycle[:min_idx] + [cycle[min_idx]]

                        if normalized not in cycles:
                            cycles.append(normalized)
                    except ValueError:
                        pass

            rec_stack.remove(node)

        # Run DFS from each unvisited node
        for task_id in self.graph:
            if task_id not in visited:
                dfs(task_id, [])

        if cycles:
            logger.warning(f"Detected {len(cycles)} circular dependencies")

        return cycles

    def validate_dependencies_exist(self) -> List[str]:
        """
        Check if all dependencies reference valid tasks.

        Returns:
            List of error messages for invalid dependencies
        """
        invalid = []

        for task_id, deps in self.graph.items():
            for dep in deps:
                if dep not in self.tasks:
                    task_title = self.tasks[task_id].title
                    error = f"{task_id} ('{task_title}') depends on non-existent task {dep}"
                    invalid.append(error)

        if invalid:
            logger.warning(f"Found {len(invalid)} invalid dependency references")

        return invalid

    def check_resource_conflicts(self) -> List[str]:
        """
        Detect if same person assigned to dependent tasks.

        This can indicate unrealistic planning where one person
        must complete a task before starting the next, but both
        are assigned to them.

        Returns:
            List of conflict descriptions
        """
        conflicts = []

        for task in self.tasks.values():
            if not task.dependencies or not task.assignee:
                continue

            for dep_id in task.dependencies:
                dep_task = self.tasks.get(dep_id)

                if dep_task and dep_task.assignee == task.assignee:
                    conflict = (
                        f"{task.assignee} assigned to both {task.task_id} ('{task.title}') "
                        f"and its dependency {dep_id} ('{dep_task.title}')"
                    )
                    conflicts.append(conflict)

        if conflicts:
            logger.info(f"Found {len(conflicts)} resource conflicts (may be intentional)")

        return conflicts

    def validate_all(self) -> Dict[str, any]:
        """
        Run all validations and return comprehensive report.

        Returns:
            Dict with validation results:
            - is_valid: bool (True if no critical errors)
            - cycles: List of circular dependency cycles
            - invalid_refs: List of invalid dependency references
            - resource_conflicts: List of resource conflicts
            - warnings: List of warning messages
        """
        cycles = self.detect_circular_dependencies()
        invalid_refs = self.validate_dependencies_exist()
        resource_conflicts = self.check_resource_conflicts()

        # Critical errors
        has_critical_errors = bool(cycles or invalid_refs)

        # Build warnings list
        warnings = []
        if resource_conflicts:
            warnings.append(
                f"⚠️ {len(resource_conflicts)} resource conflict(s): "
                "Same person assigned to dependent tasks"
            )

        result = {
            "is_valid": not has_critical_errors,
            "cycles": cycles,
            "invalid_refs": invalid_refs,
            "resource_conflicts": resource_conflicts,
            "warnings": warnings
        }

        logger.info(f"Validation complete: valid={result['is_valid']}, "
                   f"cycles={len(cycles)}, invalid_refs={len(invalid_refs)}")

        return result

    def get_execution_order(self) -> List[List[str]]:
        """
        Get topological sort of tasks (execution order by dependencies).

        Returns:
            List of "levels" where tasks in each level can run in parallel.
            Returns empty list if cycles exist.
        """
        # Check for cycles first
        if self.detect_circular_dependencies():
            logger.error("Cannot generate execution order: circular dependencies exist")
            return []

        # Kahn's algorithm for topological sort
        in_degree = {task_id: 0 for task_id in self.tasks}

        # Calculate in-degrees
        for task_id, deps in self.graph.items():
            for dep in deps:
                if dep in in_degree:  # Only count valid dependencies
                    in_degree[dep] += 1

        # Start with tasks that have no dependencies
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        levels = []

        while queue:
            # Current level: all tasks with no remaining dependencies
            current_level = queue.copy()
            levels.append(current_level)
            queue = []

            # Remove current level tasks and update in-degrees
            for task_id in current_level:
                # Find tasks that depend on this one
                for potential_next in self.tasks:
                    if task_id in self.graph.get(potential_next, []):
                        in_degree[potential_next] -= 1
                        if in_degree[potential_next] == 0:
                            queue.append(potential_next)

        return levels

    def estimate_critical_path(self) -> Tuple[List[str], float]:
        """
        Calculate critical path (longest path by time estimates).

        Returns:
            Tuple of (path as list of task_ids, total hours)
        """
        # Get execution order
        levels = self.get_execution_order()
        if not levels:
            return [], 0.0

        # Calculate earliest start times
        earliest_start = {task_id: 0.0 for task_id in self.tasks}

        for level in levels:
            for task_id in level:
                task = self.tasks[task_id]

                # Start time is max of all dependency completion times
                if task.dependencies:
                    dep_completion_times = []
                    for dep_id in task.dependencies:
                        if dep_id in self.tasks:
                            dep_task = self.tasks[dep_id]
                            completion = earliest_start[dep_id] + dep_task.estimated_hours
                            dep_completion_times.append(completion)

                    if dep_completion_times:
                        earliest_start[task_id] = max(dep_completion_times)

        # Find critical path by backtracking from longest task
        max_completion = 0.0
        last_task = None

        for task_id, start_time in earliest_start.items():
            completion = start_time + self.tasks[task_id].estimated_hours
            if completion > max_completion:
                max_completion = completion
                last_task = task_id

        if not last_task:
            return [], 0.0

        # Backtrack to build critical path
        critical_path = [last_task]
        current = last_task

        while self.tasks[current].dependencies:
            # Find which dependency is on critical path
            max_dep_completion = -1.0
            critical_dep = None

            for dep_id in self.tasks[current].dependencies:
                if dep_id in self.tasks:
                    dep_completion = (earliest_start[dep_id] +
                                    self.tasks[dep_id].estimated_hours)
                    if dep_completion > max_dep_completion:
                        max_dep_completion = dep_completion
                        critical_dep = dep_id

            if critical_dep:
                critical_path.insert(0, critical_dep)
                current = critical_dep
            else:
                break

        logger.info(f"Critical path: {len(critical_path)} tasks, {max_completion:.1f} hours")
        return critical_path, max_completion
