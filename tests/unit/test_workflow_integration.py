"""
Unit tests for end-to-end workflow integration.

Tests complete workflows:
- Task creation workflow (input → AI → questions → creation)
- Task update workflow (detection → validation → update)
- Search workflow (query → AI → results)
- Standup workflow (data gathering → AI summary → posting)
- Task completion workflow (done → proof → validation → approval)
- Attendance reporting workflow
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from datetime import datetime

from src.ai.intent import UserIntent
from src.models.conversation import ConversationState, ConversationStage


class TestTaskCreationWorkflow:
    """Test complete task creation workflow."""

    @pytest.mark.asyncio
    async def test_simple_task_creation_no_questions(self):
        """Test simple task creation skips questions."""
        from src.ai.intent import IntentDetector
        from src.ai.clarifier import TaskClarifier

        # Step 1: Detect intent
        detector = IntentDetector()
        with patch.object(detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "intent": "create_task",
                "confidence": 0.95,
                "reasoning": "Boss assigning work",
                "extracted_data": {"message": "Fix typo in README"}
            })
            mock_create.return_value = mock_response

            intent, data = await detector.detect_intent("Fix typo in README")

            assert intent == UserIntent.CREATE_TASK

        # Step 2: Analyze and decide questions
        clarifier = TaskClarifier(deepseek_client=MagicMock())
        conversation = ConversationState(
            user_id="boss",
            chat_id=123,
            original_message="Fix typo in README",
            stage=ConversationStage.ANALYZING
        )

        with patch.object(clarifier.ai, 'analyze_task_request') as mock_analyze:
            mock_analyze.return_value = {
                "understood": {"title": "Fix typo", "assignee": "Mayank"},
                "suggested_questions": [],
                "missing_info": [],
                "confidence": {"title": 0.95},
                "can_proceed_without_questions": True
            }

            should_ask, analysis = await clarifier.analyze_and_decide(
                conversation,
                {},
                {"Mayank": "Developer"}
            )

            # Simple task should skip questions
            assert should_ask is False
            assert analysis["complexity"] <= 3

    @pytest.mark.asyncio
    async def test_complex_task_asks_questions(self):
        """Test complex task generates questions."""
        from src.ai.clarifier import TaskClarifier

        clarifier = TaskClarifier(deepseek_client=MagicMock())
        conversation = ConversationState(
            user_id="boss",
            chat_id=123,
            original_message="Build complete authentication system with OAuth, JWT, and 2FA",
            stage=ConversationStage.ANALYZING
        )

        with patch.object(clarifier.ai, 'analyze_task_request') as mock_analyze:
            mock_analyze.return_value = {
                "understood": {"title": "Build auth system"},
                "suggested_questions": [
                    {"question": "Which OAuth providers?", "field": "oauth"}
                ],
                "missing_info": ["oauth"],
                "confidence": {"title": 0.9},
                "can_proceed_without_questions": False
            }

            with patch.object(clarifier, '_intelligent_self_answer') as mock_self_answer:
                mock_self_answer.return_value = ({}, [
                    {"question": "Which OAuth providers?", "field": "oauth"}
                ])

                should_ask, analysis = await clarifier.analyze_and_decide(
                    conversation,
                    {},
                    {}
                )

                # Complex task should ask questions
                assert should_ask is True
                assert analysis["complexity"] >= 7

    @pytest.mark.asyncio
    async def test_task_creation_with_template(self):
        """Test task creation applies template defaults."""
        from src.ai.clarifier import TaskClarifier

        clarifier = TaskClarifier(deepseek_client=MagicMock())
        conversation = ConversationState(
            user_id="boss",
            chat_id=123,
            original_message="Bug: Users can't login",
            stage=ConversationStage.ANALYZING
        )

        with patch.object(clarifier.ai, 'analyze_task_request') as mock_analyze:
            mock_analyze.return_value = {
                "understood": {"title": "Login bug"},
                "suggested_questions": [],
                "missing_info": [],
                "confidence": {"title": 0.95},
                "can_proceed_without_questions": True
            }

            should_ask, analysis = await clarifier.analyze_and_decide(
                conversation,
                {},
                {}
            )

            # Bug template should be applied
            assert "template_applied" in analysis
            assert conversation.extracted_info.get("task_type") == "bug"
            assert conversation.extracted_info.get("priority") == "high"


class TestTaskUpdateWorkflow:
    """Test task update workflows."""

    @pytest.mark.asyncio
    async def test_detect_task_modification(self):
        """Test detecting task modification intent."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()

        # Should detect modification without AI (pattern match)
        intent, data = await detector.detect_intent("change TASK-001 title to New Title")

        assert intent == UserIntent.MODIFY_TASK
        assert data["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_priority_change_workflow(self):
        """Test changing task priority."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()

        intent, data = await detector.detect_intent("make TASK-001 urgent")

        assert intent == UserIntent.CHANGE_PRIORITY
        assert data["task_id"] == "TASK-001"
        assert data["new_priority"] == "urgent"

    @pytest.mark.asyncio
    async def test_reassign_task_workflow(self):
        """Test reassigning task to different person."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()

        intent, data = await detector.detect_intent("reassign TASK-001 to Sarah")

        assert intent == UserIntent.REASSIGN_TASK
        assert data["task_id"] == "TASK-001"
        assert data.get("new_assignee") == "Sarah"


class TestSearchWorkflow:
    """Test search workflow."""

    @pytest.mark.asyncio
    async def test_search_by_assignee(self):
        """Test searching tasks by assignee."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()
        with patch.object(detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "intent": "search_tasks",
                "confidence": 0.9,
                "reasoning": "User wants to find tasks",
                "extracted_data": {"query": "What's Mayank working on?"}
            })
            mock_create.return_value = mock_response

            intent, data = await detector.detect_intent("What's Mayank working on?")

            assert intent == UserIntent.SEARCH_TASKS
            assert "query" in data

    @pytest.mark.asyncio
    async def test_slash_search_command(self):
        """Test /search command."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()

        intent, data = await detector.detect_intent("/search bug tasks")

        assert intent == UserIntent.SEARCH_TASKS
        assert data["query"] == "bug tasks"


class TestStandupWorkflow:
    """Test daily standup workflow."""

    @pytest.mark.asyncio
    async def test_generate_daily_standup(self):
        """Test generating daily standup summary."""
        from src.ai.deepseek import DeepSeekClient

        client = DeepSeekClient()
        with patch.object(client, '_call_api') as mock_api:
            mock_api.return_value = "**Daily Standup**\n\n✅ 3 tasks completed\n🔨 2 tasks in progress"

            summary = await client.generate_daily_standup(
                today_tasks=[{"id": "TASK-001", "status": "in_progress"}],
                completed_yesterday=[{"id": "TASK-002", "status": "completed"}]
            )

            assert "Daily Standup" in summary
            assert "completed" in summary.lower()

    @pytest.mark.asyncio
    async def test_weekly_summary_workflow(self):
        """Test generating weekly summary."""
        from src.ai.deepseek import DeepSeekClient

        client = DeepSeekClient()
        with patch.object(client, '_call_api') as mock_api:
            mock_api.return_value = "**Weekly Summary**\n\n📊 Stats:\n- Completed: 15 tasks\n- In Progress: 5 tasks"

            summary = await client.generate_weekly_summary(
                stats={"completed": 15, "in_progress": 5},
                top_contributors={},
                highlights={}
            )

            assert "Weekly Summary" in summary
            assert "15 tasks" in summary


class TestTaskCompletionWorkflow:
    """Test task completion and validation workflow."""

    @pytest.mark.asyncio
    async def test_staff_reports_task_done(self):
        """Test staff member reporting task completion."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()
        with patch.object(detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "intent": "task_done",
                "confidence": 0.95,
                "reasoning": "User completed task",
                "extracted_data": {"message": "I finished the landing page"}
            })
            mock_create.return_value = mock_response

            intent, data = await detector.detect_intent("I finished the landing page")

            assert intent == UserIntent.TASK_DONE

    @pytest.mark.asyncio
    async def test_collecting_proof_link(self):
        """Test submitting proof with link."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()
        context = {"collecting_proof": True}

        intent, data = await detector.detect_intent("https://example.com/screenshot.png", context)

        assert intent == UserIntent.SUBMIT_PROOF
        assert data["proof_type"] == "link"

    @pytest.mark.asyncio
    async def test_boss_approves_task(self):
        """Test boss approving completed task."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()
        context = {"is_boss": True, "awaiting_validation": True}

        intent, data = await detector.detect_intent("looks good!", context)

        assert intent == UserIntent.APPROVE_TASK

    @pytest.mark.asyncio
    async def test_boss_rejects_task(self):
        """Test boss rejecting task with feedback."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()
        context = {"is_boss": True, "awaiting_validation": True}

        intent, data = await detector.detect_intent("no - fix the footer alignment", context)

        assert intent == UserIntent.REJECT_TASK
        assert "footer" in data["feedback"]


class TestAttendanceWorkflow:
    """Test attendance reporting workflow."""

    @pytest.mark.asyncio
    async def test_report_absence(self):
        """Test boss reporting team member absence."""
        from src.ai.intent import IntentDetector
        from src.ai.deepseek import DeepSeekClient

        # Step 1: Detect intent
        detector = IntentDetector()
        with patch.object(detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "intent": "report_absence",
                "confidence": 0.95,
                "reasoning": "Boss reporting absence",
                "extracted_data": {"message": "Mayank didn't come today"}
            })
            mock_create.return_value = mock_response

            intent, data = await detector.detect_intent("Mayank didn't come today")

            assert intent == UserIntent.REPORT_ABSENCE

        # Step 2: Analyze attendance details
        client = DeepSeekClient()
        with patch.object(client, '_call_api') as mock_api:
            mock_api.return_value = json.dumps({
                "affected_person": "Mayank",
                "status_type": "absence_reported",
                "affected_date": "2026-01-25",
                "reason": "Not specified",
                "confidence": 0.95
            })

            details = await client.analyze_attendance_report(
                "Mayank didn't come today",
                {"Mayank": "Developer"}
            )

            assert details["affected_person"] == "Mayank"
            assert details["status_type"] == "absence_reported"


class TestCommunicationWorkflow:
    """Test direct communication vs task creation."""

    @pytest.mark.asyncio
    async def test_ask_team_member_vs_create_task(self):
        """Test distinguishing ask_team_member from create_task."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()

        # Should be ask_team_member (communication)
        with patch.object(detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "intent": "ask_team_member",
                "confidence": 0.92,
                "reasoning": "Communication not assignment",
                "extracted_data": {
                    "target_name": "Mayank",
                    "original_request": "ask Mayank what tasks are left"
                }
            })
            mock_create.return_value = mock_response

            intent, data = await detector.detect_intent("ask Mayank what tasks are left")

            assert intent == UserIntent.ASK_TEAM_MEMBER
            assert data.get("target_name") == "Mayank"

        # Should be create_task (assignment)
        with patch.object(detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "intent": "create_task",
                "confidence": 0.95,
                "reasoning": "Boss assigning work",
                "extracted_data": {"message": "Mayank needs to finish the tasks"}
            })
            mock_create.return_value = mock_response

            intent, data = await detector.detect_intent("Mayank needs to finish the tasks")

            assert intent == UserIntent.CREATE_TASK


class TestSpecSheetsWorkflow:
    """Test detailed spec sheets (SPECSHEETS) workflow."""

    @pytest.mark.asyncio
    async def test_detect_specsheets_mode(self):
        """Test detecting SPECSHEETS keyword."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()
        with patch.object(detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "intent": "create_task",
                "confidence": 0.95,
                "reasoning": "Creating detailed spec",
                "extracted_data": {
                    "message": "SPECSHEETS: Build authentication system",
                    "detailed_mode": True
                }
            })
            mock_create.return_value = mock_response

            intent, data = await detector.detect_intent("SPECSHEETS: Build auth system")

            assert intent == UserIntent.CREATE_TASK
            assert data.get("detailed_mode") is True

    @pytest.mark.asyncio
    async def test_generate_detailed_spec(self):
        """Test generating detailed spec with subtasks."""
        from src.ai.deepseek import DeepSeekClient

        client = DeepSeekClient()
        with patch.object(client, '_call_api') as mock_api:
            mock_api.return_value = json.dumps({
                "title": "Build Authentication System",
                "description": "Complete auth system with OAuth",
                "priority": "high",
                "subtasks": [
                    {"title": "Design database schema", "description": "Create tables"},
                    {"title": "Build API endpoints", "description": "REST API"}
                ],
                "technical_details": "Use JWT tokens",
                "acceptance_criteria": ["Security audit passed"]
            })

            spec = await client.generate_task_spec(
                "Build auth system",
                {},
                {},
                {},
                detailed_mode=True
            )

            assert "subtasks" in spec
            assert len(spec["subtasks"]) >= 2
            assert "technical_details" in spec


class TestBulkOperations:
    """Test bulk task operations."""

    @pytest.mark.asyncio
    async def test_bulk_complete_tasks(self):
        """Test completing multiple tasks at once."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()

        intent, data = await detector.detect_intent("/complete TASK-001 TASK-002 TASK-003")

        assert intent == UserIntent.BULK_COMPLETE
        assert len(data["task_ids"]) == 3
        assert "TASK-001" in data["task_ids"]

    @pytest.mark.asyncio
    async def test_clear_multiple_tasks(self):
        """Test clearing/deleting multiple tasks."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()

        intent, data = await detector.detect_intent("/clear TASK-001 TASK-002")

        assert intent == UserIntent.CLEAR_TASKS
        assert len(data["task_ids"]) == 2


class TestDependencyWorkflow:
    """Test task dependency management."""

    @pytest.mark.asyncio
    async def test_add_task_dependency(self):
        """Test adding dependency between tasks."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()

        intent, data = await detector.detect_intent("TASK-002 depends on TASK-001")

        assert intent == UserIntent.ADD_DEPENDENCY
        assert "TASK-001" in data["task_ids"]
        assert "TASK-002" in data["task_ids"]

    @pytest.mark.asyncio
    async def test_find_potential_dependencies(self):
        """Test AI finding potential dependencies."""
        from src.ai.clarifier import TaskClarifier

        clarifier = TaskClarifier(deepseek_client=MagicMock())

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "potential_dependencies": [
                {"task_id": "TASK-001", "reason": "Needs DB first"}
            ],
            "explanation": "API needs database"
        })

        with patch.object(clarifier.ai.client.chat.completions, 'create', return_value=mock_response):
            with patch('src.ai.clarifier.get_sheets_integration') as mock_sheets:
                mock_sheets_instance = MagicMock()
                mock_sheets_instance.get_all_tasks = AsyncMock(return_value=[
                    {"ID": "TASK-001", "Title": "Setup DB", "Status": "in_progress"}
                ])
                mock_sheets.return_value = mock_sheets_instance

                deps = await clarifier.find_potential_dependencies("Build API")

                assert len(deps) == 1
                assert deps[0]["task_id"] == "TASK-001"


class TestSubtaskWorkflow:
    """Test subtask management."""

    @pytest.mark.asyncio
    async def test_add_subtask_to_task(self):
        """Test adding subtask to existing task."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()

        intent, data = await detector.detect_intent("add subtask to TASK-001: Review code")

        assert intent == UserIntent.ADD_SUBTASK
        assert data["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_complete_specific_subtask(self):
        """Test completing specific subtask."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()

        intent, data = await detector.detect_intent("complete subtask #2 for TASK-001")

        assert intent == UserIntent.COMPLETE_SUBTASK
        assert data["task_id"] == "TASK-001"
        assert data.get("subtask_number") == 2

    @pytest.mark.asyncio
    async def test_ai_breakdown_complex_task(self):
        """Test AI breaking down complex task into subtasks."""
        from src.ai.deepseek import DeepSeekClient

        client = DeepSeekClient()
        with patch.object(client, '_call_api') as mock_api:
            mock_api.return_value = json.dumps({
                "analysis": "Complex feature requiring multiple steps",
                "is_complex_enough": True,
                "recommended": True,
                "subtasks": [
                    {"title": "Design schema", "description": "DB tables"},
                    {"title": "Build API", "description": "REST endpoints"}
                ]
            })

            breakdown = await client.breakdown_task(
                "Build authentication system",
                "Complete auth with sessions",
                "feature",
                "high"
            )

            assert breakdown["is_complex_enough"] is True
            assert len(breakdown["subtasks"]) == 2


class TestErrorHandling:
    """Test error handling in workflows."""

    @pytest.mark.asyncio
    async def test_api_error_returns_unknown_intent(self):
        """Test API error gracefully returns UNKNOWN."""
        from src.ai.intent import IntentDetector

        detector = IntentDetector()
        with patch.object(detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("API error")

            intent, data = await detector.detect_intent("Some message")

            assert intent == UserIntent.UNKNOWN

    @pytest.mark.asyncio
    async def test_invalid_json_from_ai(self):
        """Test handling invalid JSON from AI."""
        from src.ai.deepseek import DeepSeekClient

        client = DeepSeekClient()
        with patch.object(client, '_call_api') as mock_api:
            mock_api.return_value = "Invalid JSON response"

            spec = await client.generate_task_spec(
                "Fix bug",
                {},
                {},
                {"title": "Fix bug"}
            )

            # Should return minimal spec
            assert spec["title"] == "Fix bug"
            assert spec["priority"] == "medium"  # Default
