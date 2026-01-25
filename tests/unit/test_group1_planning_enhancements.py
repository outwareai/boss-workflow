"""
Unit tests for GROUP 1: Conversational Planning Engine enhancements.

Tests:
- Historical effort estimation
- Team performance analysis
- Dependency validation
- Refinement impact analysis
"""

import pytest
from datetime import datetime, timedelta
from src.utils.dependency_validator import DependencyValidator, TaskDraft
from src.ai.historical_estimator import HistoricalEstimator, HistoricalPattern
from src.ai.team_performance_analyzer import TeamPerformanceAnalyzer
from src.ai.refinement_analyzer import RefinementAnalyzer


class TestDependencyValidator:
    """Test dependency validation functionality"""

    def test_detect_simple_cycle(self):
        """Test detection of simple circular dependency"""
        tasks = [
            TaskDraft("T1", "Task 1", "Alice", ["T2"], 4.0),
            TaskDraft("T2", "Task 2", "Bob", ["T1"], 3.0),
        ]

        validator = DependencyValidator(tasks)
        cycles = validator.detect_circular_dependencies()

        assert len(cycles) > 0
        assert "T1" in cycles[0]
        assert "T2" in cycles[0]

    def test_detect_complex_cycle(self):
        """Test detection of multi-task cycle"""
        tasks = [
            TaskDraft("T1", "Task 1", "Alice", ["T3"], 4.0),
            TaskDraft("T2", "Task 2", "Bob", ["T1"], 3.0),
            TaskDraft("T3", "Task 3", "Charlie", ["T2"], 2.0),
        ]

        validator = DependencyValidator(tasks)
        cycles = validator.detect_circular_dependencies()

        assert len(cycles) > 0
        # Cycle should include all three tasks
        cycle = cycles[0]
        assert "T1" in cycle
        assert "T2" in cycle
        assert "T3" in cycle

    def test_no_cycles_valid_dependencies(self):
        """Test that valid linear dependencies are allowed"""
        tasks = [
            TaskDraft("T1", "Task 1", "Alice", [], 4.0),
            TaskDraft("T2", "Task 2", "Bob", ["T1"], 3.0),
            TaskDraft("T3", "Task 3", "Charlie", ["T2"], 2.0),
        ]

        validator = DependencyValidator(tasks)
        cycles = validator.detect_circular_dependencies()

        assert len(cycles) == 0

    def test_invalid_dependency_reference(self):
        """Test detection of non-existent dependency"""
        tasks = [
            TaskDraft("T1", "Task 1", "Alice", ["T99"], 4.0),
            TaskDraft("T2", "Task 2", "Bob", [], 3.0),
        ]

        validator = DependencyValidator(tasks)
        invalid = validator.validate_dependencies_exist()

        assert len(invalid) > 0
        assert "T99" in invalid[0]

    def test_resource_conflict_detection(self):
        """Test detection of same person on dependent tasks"""
        tasks = [
            TaskDraft("T1", "Task 1", "Alice", [], 4.0),
            TaskDraft("T2", "Task 2", "Alice", ["T1"], 3.0),
        ]

        validator = DependencyValidator(tasks)
        conflicts = validator.check_resource_conflicts()

        assert len(conflicts) > 0
        assert "Alice" in conflicts[0]

    def test_execution_order_linear(self):
        """Test topological sort for linear dependencies"""
        tasks = [
            TaskDraft("T1", "Task 1", "Alice", [], 4.0),
            TaskDraft("T2", "Task 2", "Bob", ["T1"], 3.0),
            TaskDraft("T3", "Task 3", "Charlie", ["T2"], 2.0),
        ]

        validator = DependencyValidator(tasks)
        levels = validator.get_execution_order()

        assert len(levels) == 3
        assert "T1" in levels[0]  # T1 has no dependencies
        assert "T2" in levels[1]  # T2 depends on T1
        assert "T3" in levels[2]  # T3 depends on T2

    def test_execution_order_parallel(self):
        """Test topological sort with parallel tasks"""
        tasks = [
            TaskDraft("T1", "Task 1", "Alice", [], 4.0),
            TaskDraft("T2", "Task 2", "Bob", [], 3.0),
            TaskDraft("T3", "Task 3", "Charlie", ["T1", "T2"], 2.0),
        ]

        validator = DependencyValidator(tasks)
        levels = validator.get_execution_order()

        assert len(levels) == 2
        # T1 and T2 can run in parallel
        assert set(levels[0]) == {"T1", "T2"}
        # T3 waits for both
        assert "T3" in levels[1]

    def test_critical_path_calculation(self):
        """Test critical path estimation"""
        tasks = [
            TaskDraft("T1", "Task 1", "Alice", [], 5.0),
            TaskDraft("T2", "Task 2", "Bob", [], 2.0),
            TaskDraft("T3", "Task 3", "Charlie", ["T1"], 3.0),
        ]

        validator = DependencyValidator(tasks)
        path, hours = validator.estimate_critical_path()

        # Critical path is T1 -> T3 = 8 hours
        assert hours == 8.0
        assert "T1" in path
        assert "T3" in path

    def test_validate_all_comprehensive(self):
        """Test comprehensive validation"""
        tasks = [
            TaskDraft("T1", "Task 1", "Alice", [], 4.0),
            TaskDraft("T2", "Task 2", "Bob", ["T1"], 3.0),
        ]

        validator = DependencyValidator(tasks)
        result = validator.validate_all()

        assert result["is_valid"] == True
        assert len(result["cycles"]) == 0
        assert len(result["invalid_refs"]) == 0


class TestHistoricalEstimator:
    """Test historical effort estimation"""

    @pytest.mark.asyncio
    async def test_similarity_calculation(self):
        """Test keyword-based similarity"""
        estimator = HistoricalEstimator(None)

        # Similar tasks should have high similarity
        similarity = await estimator._calculate_similarity(
            "Build user login system",
            "Create authentication and login"
        )

        assert similarity > 0.2  # Should have some overlap (login keyword matches)

    def test_keyword_extraction(self):
        """Test keyword extraction from text"""
        estimator = HistoricalEstimator(None)

        keywords = estimator._extract_keywords("Build the user authentication system")

        assert "build" in keywords
        assert "user" in keywords
        assert "authentication" in keywords
        assert "system" in keywords
        # Stopwords should be removed
        assert "the" not in keywords

    @pytest.mark.asyncio
    async def test_estimate_with_similar_history(self):
        """Test estimation when similar tasks exist"""
        estimator = HistoricalEstimator(None)

        patterns = [
            HistoricalPattern(
                task_title="Build login page",
                task_type="feature",
                estimated_hours=5.0,
                actual_hours=6.0,
                assignee="Alice",
                complexity_score=5.0,
                success_rate=0.9,
                project_id="PRJ-001",
                completed_at=datetime.now()
            ),
            HistoricalPattern(
                task_title="Create authentication API",
                task_type="feature",
                estimated_hours=8.0,
                actual_hours=7.5,
                assignee="Bob",
                complexity_score=6.0,
                success_rate=0.85,
                project_id="PRJ-002",
                completed_at=datetime.now()
            )
        ]

        task = {
            "title": "Build user login system",
            "description": "Create login page with authentication",
            "type": "feature"
        }

        result = await estimator.estimate_effort(task, patterns)

        assert "estimated_hours" in result
        assert result["estimated_hours"] > 0
        assert result["confidence"] in ["low", "medium", "high"]
        assert "similar_tasks" in result


class TestTeamPerformanceAnalyzer:
    """Test team performance analysis"""

    def test_extract_skills_from_role(self):
        """Test skill extraction from role"""
        analyzer = TeamPerformanceAnalyzer()

        skills = analyzer._extract_skills_from_role("Developer")
        assert "development" in skills
        assert "coding" in skills

        skills = analyzer._extract_skills_from_role("Designer")
        assert "design" in skills
        assert "ui" in skills

    def test_skill_match_calculation(self):
        """Test skill matching for task"""
        analyzer = TeamPerformanceAnalyzer()

        member_skills = ["development", "coding", "api", "bug"]

        task = {
            "title": "Fix login API bug",
            "type": "bug",
            "category": "development",
            "tags": ["api"]
        }

        score = analyzer._calculate_skill_match(member_skills, task)

        # Should have high match (bug, development, api all match)
        assert score > 0.5


class TestRefinementAnalyzer:
    """Test refinement impact analysis"""

    def test_apply_changes(self):
        """Test applying changes to task drafts"""
        analyzer = RefinementAnalyzer()

        drafts = [
            {"draft_id": "D1", "title": "Task 1", "estimated_hours": 4.0},
            {"draft_id": "D2", "title": "Task 2", "estimated_hours": 3.0},
        ]

        changes = {"estimated_hours": 6.0}

        updated = analyzer._apply_changes(drafts, "D1", changes)

        # D1 should be updated
        d1 = next(d for d in updated if d["draft_id"] == "D1")
        assert d1["estimated_hours"] == 6.0

        # D2 should be unchanged
        d2 = next(d for d in updated if d["draft_id"] == "D2")
        assert d2["estimated_hours"] == 3.0

    def test_find_affected_tasks(self):
        """Test finding affected tasks"""
        analyzer = RefinementAnalyzer()

        drafts = [
            {"draft_id": "D1", "title": "Task 1", "depends_on": []},
            {"draft_id": "D2", "title": "Task 2", "depends_on": ["D1"]},
            {"draft_id": "D3", "title": "Task 3", "depends_on": ["D2"]},
        ]

        # Modifying D1 should affect D2 (direct dependent)
        affected = analyzer._find_affected_tasks("D1", drafts, {})

        assert "D2" in affected

    @pytest.mark.asyncio
    async def test_timeline_impact_calculation(self):
        """Test timeline impact when effort changes"""
        analyzer = RefinementAnalyzer()

        drafts = [
            {
                "draft_id": "D1",
                "title": "Task 1",
                "estimated_hours": 4.0,
                "depends_on": []
            },
            {
                "draft_id": "D2",
                "title": "Task 2",
                "estimated_hours": 3.0,
                "depends_on": ["D1"]
            },
        ]

        changes = {"estimated_hours": 8.0}  # Increased by 4 hours

        impact = await analyzer._calculate_timeline_impact(
            "D1",
            changes,
            drafts,
            ["D2"]
        )

        assert impact["effort_delta"] == 4.0
        assert impact["affected_count"] == 1

    def test_format_impact_message(self):
        """Test impact message formatting"""
        analyzer = RefinementAnalyzer()

        from src.ai.refinement_analyzer import RefinementImpact

        impact = RefinementImpact(
            modified_task_id="D1",
            affected_tasks=["D2", "D3"],
            timeline_changes={"effort_delta": 2.0},
            cycles_detected=[],
            resource_conflicts=[],
            invalid_dependencies=[],
            warnings=[],
            is_valid=True
        )

        message = analyzer.format_impact_message(impact)

        assert "D1" in message
        assert "2" in message  # effort delta
        assert "affected" in message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
