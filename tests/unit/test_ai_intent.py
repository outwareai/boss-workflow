"""
Unit tests for AI-First Intent Detection System.

Tests:
- classify_intent() - Intent detection
- extract_entities() - Entity extraction
- confidence_threshold() - Confidence checking
- Pattern matching for all 15+ intents
- Context-aware state handling
- Modification pattern detection
- Slash command parsing
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from src.ai.intent import IntentDetector, UserIntent, TEAM_NAMES


@pytest.fixture
def intent_detector():
    """Create IntentDetector instance."""
    return IntentDetector()


class TestSlashCommands:
    """Test slash command detection."""

    @pytest.mark.asyncio
    async def test_help_command(self, intent_detector):
        """Test /help command."""
        intent, data = await intent_detector.detect_intent("/help")

        assert intent == UserIntent.HELP
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_status_command(self, intent_detector):
        """Test /status command."""
        intent, data = await intent_detector.detect_intent("/status")

        assert intent == UserIntent.CHECK_STATUS

    @pytest.mark.asyncio
    async def test_daily_command(self, intent_detector):
        """Test /daily command."""
        intent, data = await intent_detector.detect_intent("/daily")

        assert intent == UserIntent.CHECK_STATUS
        assert data.get("filter") == "today"

    @pytest.mark.asyncio
    async def test_weekly_command(self, intent_detector):
        """Test /weekly command."""
        intent, data = await intent_detector.detect_intent("/weekly")

        assert intent == UserIntent.CHECK_STATUS
        assert data.get("filter") == "week"

    @pytest.mark.asyncio
    async def test_overdue_command(self, intent_detector):
        """Test /overdue command."""
        intent, data = await intent_detector.detect_intent("/overdue")

        assert intent == UserIntent.CHECK_OVERDUE

    @pytest.mark.asyncio
    async def test_task_command_with_args(self, intent_detector):
        """Test /task <message> command."""
        intent, data = await intent_detector.detect_intent("/task Fix the login bug")

        assert intent == UserIntent.CREATE_TASK
        assert data["message"] == "Fix the login bug"

    @pytest.mark.asyncio
    async def test_urgent_command_with_args(self, intent_detector):
        """Test /urgent <message> command."""
        intent, data = await intent_detector.detect_intent("/urgent Critical production issue")

        assert intent == UserIntent.CREATE_TASK
        assert data["message"] == "Critical production issue"
        assert data["priority"] == "urgent"

    @pytest.mark.asyncio
    async def test_search_command(self, intent_detector):
        """Test /search <query> command."""
        intent, data = await intent_detector.detect_intent("/search Mayank tasks")

        assert intent == UserIntent.SEARCH_TASKS
        assert data["query"] == "Mayank tasks"

    @pytest.mark.asyncio
    async def test_complete_command(self, intent_detector):
        """Test /complete TASK-001 command."""
        intent, data = await intent_detector.detect_intent("/complete TASK-001")

        assert intent == UserIntent.BULK_COMPLETE
        assert "TASK-001" in data["task_ids"]

    @pytest.mark.asyncio
    async def test_spec_command(self, intent_detector):
        """Test /spec TASK-001 command."""
        intent, data = await intent_detector.detect_intent("/spec TASK-001")

        assert intent == UserIntent.GENERATE_SPEC
        assert data["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_cancel_command(self, intent_detector):
        """Test /cancel command."""
        intent, data = await intent_detector.detect_intent("/cancel")

        assert intent == UserIntent.CANCEL

    @pytest.mark.asyncio
    async def test_skip_command(self, intent_detector):
        """Test /skip command."""
        intent, data = await intent_detector.detect_intent("/skip")

        assert intent == UserIntent.SKIP


class TestContextStates:
    """Test context-aware state handling."""

    @pytest.mark.asyncio
    async def test_boss_approval_positive(self, intent_detector):
        """Test boss approving task with positive response."""
        context = {"is_boss": True, "awaiting_validation": True}
        intent, data = await intent_detector.detect_intent("yes", context)

        assert intent == UserIntent.APPROVE_TASK

    @pytest.mark.asyncio
    async def test_boss_approval_lgtm(self, intent_detector):
        """Test boss approval with 'lgtm'."""
        context = {"is_boss": True, "awaiting_validation": True}
        intent, data = await intent_detector.detect_intent("lgtm", context)

        assert intent == UserIntent.APPROVE_TASK

    @pytest.mark.asyncio
    async def test_boss_rejection(self, intent_detector):
        """Test boss rejecting task."""
        context = {"is_boss": True, "awaiting_validation": True}
        intent, data = await intent_detector.detect_intent("no - fix the footer", context)

        assert intent == UserIntent.REJECT_TASK
        assert data["feedback"] == "no - fix the footer"

    @pytest.mark.asyncio
    async def test_collecting_proof_link(self, intent_detector):
        """Test collecting proof with link."""
        context = {"collecting_proof": True}
        intent, data = await intent_detector.detect_intent("https://example.com/screenshot", context)

        assert intent == UserIntent.SUBMIT_PROOF
        assert data["proof_type"] == "link"
        assert data["content"] == "https://example.com/screenshot"

    @pytest.mark.asyncio
    async def test_collecting_proof_note(self, intent_detector):
        """Test collecting proof with text note."""
        context = {"collecting_proof": True}
        intent, data = await intent_detector.detect_intent("Tested on Chrome and Safari", context)

        assert intent == UserIntent.SUBMIT_PROOF
        assert data["proof_type"] == "note"

    @pytest.mark.asyncio
    async def test_collecting_proof_done(self, intent_detector):
        """Test finishing proof collection."""
        context = {"collecting_proof": True}
        intent, data = await intent_detector.detect_intent("that's all", context)

        assert intent == UserIntent.DONE_ADDING_PROOF

    @pytest.mark.asyncio
    async def test_awaiting_confirmation_yes(self, intent_detector):
        """Test confirming action."""
        context = {"awaiting_confirm": True}
        intent, data = await intent_detector.detect_intent("yes", context)

        assert intent == UserIntent.CONFIRM_SUBMISSION

    @pytest.mark.asyncio
    async def test_awaiting_confirmation_no(self, intent_detector):
        """Test canceling action."""
        context = {"awaiting_confirm": True}
        intent, data = await intent_detector.detect_intent("no", context)

        assert intent == UserIntent.CANCEL


class TestModificationPatterns:
    """Test task modification pattern detection."""

    @pytest.mark.asyncio
    async def test_modify_task_title(self, intent_detector):
        """Test changing task title."""
        intent, data = await intent_detector.detect_intent("change TASK-001 title to New Title")

        assert intent == UserIntent.MODIFY_TASK
        assert data["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_modify_task_description(self, intent_detector):
        """Test updating task description."""
        intent, data = await intent_detector.detect_intent("update TASK-001 description")

        assert intent == UserIntent.MODIFY_TASK
        assert data["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_reassign_task(self, intent_detector):
        """Test reassigning task to person."""
        intent, data = await intent_detector.detect_intent("reassign TASK-001 to Mayank")

        assert intent == UserIntent.REASSIGN_TASK
        assert data["task_id"] == "TASK-001"
        assert data.get("new_assignee") == "Mayank"

    @pytest.mark.asyncio
    async def test_change_priority_urgent(self, intent_detector):
        """Test making task urgent."""
        intent, data = await intent_detector.detect_intent("make TASK-001 urgent")

        assert intent == UserIntent.CHANGE_PRIORITY
        assert data["task_id"] == "TASK-001"
        assert data["new_priority"] == "urgent"

    @pytest.mark.asyncio
    async def test_change_priority_high(self, intent_detector):
        """Test changing priority to high."""
        intent, data = await intent_detector.detect_intent("TASK-001 high priority")

        assert intent == UserIntent.CHANGE_PRIORITY
        assert data["new_priority"] == "high"

    @pytest.mark.asyncio
    async def test_change_deadline(self, intent_detector):
        """Test extending deadline."""
        intent, data = await intent_detector.detect_intent("extend TASK-001 deadline to Friday")

        assert intent == UserIntent.CHANGE_DEADLINE
        assert data["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_change_status(self, intent_detector):
        """Test changing task status."""
        intent, data = await intent_detector.detect_intent("move TASK-001 to in_progress")

        assert intent == UserIntent.CHANGE_STATUS
        assert data["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_add_tags(self, intent_detector):
        """Test adding tags to task."""
        intent, data = await intent_detector.detect_intent("tag TASK-001 as frontend")

        assert intent == UserIntent.ADD_TAGS
        assert data["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_remove_tags(self, intent_detector):
        """Test removing tags from task."""
        intent, data = await intent_detector.detect_intent("remove tag from TASK-001")

        assert intent == UserIntent.REMOVE_TAGS
        assert data["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_add_subtask(self, intent_detector):
        """Test adding subtask."""
        intent, data = await intent_detector.detect_intent("add subtask to TASK-001")

        assert intent == UserIntent.ADD_SUBTASK
        assert data["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_complete_subtask(self, intent_detector):
        """Test completing subtask."""
        intent, data = await intent_detector.detect_intent("complete subtask #1 for TASK-001")

        assert intent == UserIntent.COMPLETE_SUBTASK
        assert data["task_id"] == "TASK-001"
        assert data.get("subtask_number") == 1

    @pytest.mark.asyncio
    async def test_add_dependency(self, intent_detector):
        """Test adding task dependency."""
        intent, data = await intent_detector.detect_intent("TASK-002 depends on TASK-001")

        assert intent == UserIntent.ADD_DEPENDENCY
        assert "TASK-001" in data["task_ids"]
        assert "TASK-002" in data["task_ids"]

    @pytest.mark.asyncio
    async def test_duplicate_task(self, intent_detector):
        """Test duplicating task."""
        intent, data = await intent_detector.detect_intent("duplicate TASK-001")

        assert intent == UserIntent.DUPLICATE_TASK
        assert data["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_split_task(self, intent_detector):
        """Test splitting task."""
        intent, data = await intent_detector.detect_intent("split TASK-001 into 2 tasks")

        assert intent == UserIntent.SPLIT_TASK
        assert data["task_id"] == "TASK-001"


class TestAIClassification:
    """Test AI-powered intent classification."""

    @pytest.mark.asyncio
    async def test_create_task_intent(self, intent_detector):
        """Test detecting task creation intent."""
        mock_response = {
            "intent": "create_task",
            "confidence": 0.95,
            "reasoning": "Boss assigning work",
            "extracted_data": {
                "message": "Mayank needs to fix the login bug",
                "assignee": "Mayank"
            }
        }

        with patch.object(intent_detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_ai_response = MagicMock()
            mock_ai_response.choices = [MagicMock()]
            mock_ai_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_ai_response

            intent, data = await intent_detector.detect_intent("Mayank needs to fix the login bug")

            assert intent == UserIntent.CREATE_TASK
            assert data["message"] == "Mayank needs to fix the login bug"

    @pytest.mark.asyncio
    async def test_ask_team_member_vs_create_task(self, intent_detector):
        """Test distinguishing ask_team_member from create_task."""
        mock_response = {
            "intent": "ask_team_member",
            "confidence": 0.92,
            "reasoning": "Boss wants to communicate, not assign work",
            "extracted_data": {
                "target_name": "Mayank",
                "original_request": "ask Mayank what tasks are left"
            }
        }

        with patch.object(intent_detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_ai_response = MagicMock()
            mock_ai_response.choices = [MagicMock()]
            mock_ai_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_ai_response

            intent, data = await intent_detector.detect_intent("ask Mayank what tasks are left")

            assert intent == UserIntent.ASK_TEAM_MEMBER
            assert data.get("target_name") == "Mayank"

    @pytest.mark.asyncio
    async def test_search_tasks_intent(self, intent_detector):
        """Test detecting search intent."""
        mock_response = {
            "intent": "search_tasks",
            "confidence": 0.9,
            "reasoning": "User wants to find tasks",
            "extracted_data": {
                "query": "What's Mayank working on?"
            }
        }

        with patch.object(intent_detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_ai_response = MagicMock()
            mock_ai_response.choices = [MagicMock()]
            mock_ai_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_ai_response

            intent, data = await intent_detector.detect_intent("What's Mayank working on?")

            assert intent == UserIntent.SEARCH_TASKS
            assert "query" in data

    @pytest.mark.asyncio
    async def test_report_absence_intent(self, intent_detector):
        """Test detecting attendance report."""
        mock_response = {
            "intent": "report_absence",
            "confidence": 0.95,
            "reasoning": "Boss reporting team member absence",
            "extracted_data": {
                "message": "Mayank didn't come today"
            }
        }

        with patch.object(intent_detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_ai_response = MagicMock()
            mock_ai_response.choices = [MagicMock()]
            mock_ai_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_ai_response

            intent, data = await intent_detector.detect_intent("Mayank didn't come today")

            assert intent == UserIntent.REPORT_ABSENCE

    @pytest.mark.asyncio
    async def test_task_done_intent(self, intent_detector):
        """Test detecting task completion."""
        mock_response = {
            "intent": "task_done",
            "confidence": 0.9,
            "reasoning": "User completed a task",
            "extracted_data": {
                "message": "I finished the landing page"
            }
        }

        with patch.object(intent_detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_ai_response = MagicMock()
            mock_ai_response.choices = [MagicMock()]
            mock_ai_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_ai_response

            intent, data = await intent_detector.detect_intent("I finished the landing page")

            assert intent == UserIntent.TASK_DONE

    @pytest.mark.asyncio
    async def test_low_confidence_returns_unknown(self, intent_detector):
        """Test low confidence returns UNKNOWN."""
        mock_response = {
            "intent": "create_task",
            "confidence": 0.3,  # Low confidence
            "reasoning": "Unclear message",
            "extracted_data": {}
        }

        with patch.object(intent_detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_ai_response = MagicMock()
            mock_ai_response.choices = [MagicMock()]
            mock_ai_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_ai_response

            intent, data = await intent_detector.detect_intent("Ambiguous message")

            assert intent == UserIntent.UNKNOWN

    @pytest.mark.asyncio
    async def test_invalid_json_returns_unknown(self, intent_detector):
        """Test invalid JSON from AI returns UNKNOWN."""
        with patch.object(intent_detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_ai_response = MagicMock()
            mock_ai_response.choices = [MagicMock()]
            mock_ai_response.choices[0].message.content = "Invalid JSON"
            mock_create.return_value = mock_ai_response

            intent, data = await intent_detector.detect_intent("Some message")

            assert intent == UserIntent.UNKNOWN

    @pytest.mark.asyncio
    async def test_api_error_returns_unknown(self, intent_detector):
        """Test API error returns UNKNOWN."""
        with patch.object(intent_detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("API error")

            intent, data = await intent_detector.detect_intent("Test message")

            assert intent == UserIntent.UNKNOWN


class TestPostProcessing:
    """Test post-processing of extracted data."""

    def test_extracts_task_ids_from_message(self, intent_detector):
        """Test extracting TASK-XXX IDs from message."""
        data = intent_detector._post_process_data(
            UserIntent.MODIFY_TASK,
            "Change TASK-001 and TASK-002",
            {}
        )

        assert "task_ids" in data
        assert "TASK-001" in data["task_ids"]
        assert "TASK-002" in data["task_ids"]

    def test_ensures_message_for_create_task(self, intent_detector):
        """Test message is always included for task creation."""
        message = "Fix the bug"
        data = intent_detector._post_process_data(
            UserIntent.CREATE_TASK,
            message,
            {}
        )

        assert data["message"] == message

    def test_extracts_team_member_for_ask(self, intent_detector):
        """Test extracting team member from ask_team_member."""
        data = intent_detector._post_process_data(
            UserIntent.ASK_TEAM_MEMBER,
            "Ask Mayank about the status",
            {}
        )

        assert data.get("target_name") == "Mayank"

    def test_extracts_priority_for_change_priority(self, intent_detector):
        """Test extracting priority level."""
        data = intent_detector._post_process_data(
            UserIntent.CHANGE_PRIORITY,
            "Make it urgent",
            {"task_id": "TASK-001"}
        )

        assert data.get("new_priority") == "urgent"

    def test_extracts_status_for_change_status(self, intent_detector):
        """Test extracting status."""
        data = intent_detector._post_process_data(
            UserIntent.CHANGE_STATUS,
            "Move to in_progress",
            {"task_id": "TASK-001"}
        )

        assert data.get("new_status") == "in_progress"

    def test_extracts_subtask_number(self, intent_detector):
        """Test extracting subtask number."""
        data = intent_detector._post_process_data(
            UserIntent.COMPLETE_SUBTASK,
            "Complete subtask #3 for TASK-001",
            {"task_id": "TASK-001"}
        )

        assert data.get("subtask_number") == 3


class TestHelperMethods:
    """Test helper methods."""

    def test_is_photo_proof_true(self, intent_detector):
        """Test detecting photo as proof."""
        assert intent_detector.is_photo_proof(True, {"collecting_proof": True}) is True

    def test_is_photo_proof_false_not_collecting(self, intent_detector):
        """Test photo not proof when not collecting."""
        assert intent_detector.is_photo_proof(True, {}) is False

    def test_is_link_http(self, intent_detector):
        """Test detecting HTTP link."""
        assert intent_detector.is_link("http://example.com") is True

    def test_is_link_https(self, intent_detector):
        """Test detecting HTTPS link."""
        assert intent_detector.is_link("https://example.com") is True

    def test_is_link_false(self, intent_detector):
        """Test non-link returns False."""
        assert intent_detector.is_link("not a link") is False


class TestDetailedModeDetection:
    """Test detecting detailed/spec sheet mode."""

    @pytest.mark.asyncio
    async def test_detects_specsheets_keyword(self, intent_detector):
        """Test detecting SPECSHEETS keyword."""
        mock_response = {
            "intent": "create_task",
            "confidence": 0.95,
            "reasoning": "Creating detailed spec",
            "extracted_data": {
                "message": "SPECSHEETS: Build authentication system",
                "detailed_mode": True
            }
        }

        with patch.object(intent_detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_ai_response = MagicMock()
            mock_ai_response.choices = [MagicMock()]
            mock_ai_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_ai_response

            intent, data = await intent_detector.detect_intent("SPECSHEETS: Build auth system")

            assert intent == UserIntent.CREATE_TASK
            assert data.get("detailed_mode") is True


class TestGreetingAndHelp:
    """Test greeting and help intents."""

    @pytest.mark.asyncio
    async def test_greeting_intent(self, intent_detector):
        """Test detecting greeting."""
        mock_response = {
            "intent": "greeting",
            "confidence": 0.99,
            "reasoning": "User saying hello",
            "extracted_data": {}
        }

        with patch.object(intent_detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_ai_response = MagicMock()
            mock_ai_response.choices = [MagicMock()]
            mock_ai_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_ai_response

            intent, data = await intent_detector.detect_intent("Hello!")

            assert intent == UserIntent.GREETING

    @pytest.mark.asyncio
    async def test_teach_preference_intent(self, intent_detector):
        """Test detecting preference teaching."""
        mock_response = {
            "intent": "teach",
            "confidence": 0.9,
            "reasoning": "User teaching preference",
            "extracted_data": {
                "message": "When I say urgent, deadline is today"
            }
        }

        with patch.object(intent_detector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_ai_response = MagicMock()
            mock_ai_response.choices = [MagicMock()]
            mock_ai_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_ai_response

            intent, data = await intent_detector.detect_intent("When I say urgent, deadline is today")

            assert intent == UserIntent.TEACH
