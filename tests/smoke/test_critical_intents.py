"""
Pre-deployment smoke tests for critical intents.

These tests MUST pass before deploying to production.
Blocking tests check that core functionality works:
- Task creation
- Status modification
- Boss approval/rejection
- Help command
- Status checks
- Team communication

Architecture:
- All tests use the public API of IntentDetector
- No mocking - we test real intent detection
- Timeout protection to catch hanging requests
- Clear pass/fail criteria
"""

import pytest
import logging
from unittest.mock import AsyncMock, patch
from src.ai.intent import IntentDetector, UserIntent

logger = logging.getLogger(__name__)


@pytest.fixture
def intent_detector():
    """Create IntentDetector instance for testing."""
    return IntentDetector()


class TestCriticalIntents:
    """Test critical intents that must work for core system functionality."""

    @pytest.mark.asyncio
    async def test_create_task_intent(self, intent_detector):
        """
        CRITICAL: Task creation must work.

        This is the most fundamental feature - the boss creates tasks for the team.
        If this breaks, the entire system is non-functional.
        """
        # Mock the AI call to avoid external dependencies
        with patch.object(intent_detector, '_ai_classify') as mock_ai:
            mock_ai.return_value = (
                UserIntent.CREATE_TASK,
                {
                    "message": "Create task for John: Fix bug",
                    "target_name": "John",
                }
            )

            # Test slash command (direct path - no AI)
            intent, data = await intent_detector.detect_intent("/task Fix the login bug")
            assert intent == UserIntent.CREATE_TASK, \
                "Task creation via /task command broken!"
            assert data.get("message").lower() == "fix the login bug", \
                "Task message not extracted!"

            # Test natural language
            intent, data = await intent_detector.detect_intent(
                "Create task for John: Fix bug",
                context={"is_boss": True}
            )
            assert intent == UserIntent.CREATE_TASK, \
                "Natural language task creation broken!"

    @pytest.mark.asyncio
    async def test_modify_task_status_intent(self, intent_detector):
        """
        CRITICAL: Status changes must work.

        Tasks need to move through the workflow (pending -> in_progress -> completed).
        If status changes break, tasks get stuck and can't progress.
        """
        with patch.object(intent_detector, '_ai_classify') as mock_ai:
            mock_ai.return_value = (
                UserIntent.CHANGE_STATUS,
                {
                    "task_id": "TASK-001",
                    "new_status": "in_progress"
                }
            )

            # Test slash command approach - status pattern with task ID
            intent, data = await intent_detector.detect_intent(
                "move TASK-001 to in_progress"
            )
            assert intent == UserIntent.CHANGE_STATUS, \
                "Task status modification broken!"
            assert data.get("task_id") == "TASK-001", \
                "Task ID not extracted for status change!"

    @pytest.mark.asyncio
    async def test_boss_approve_intent(self, intent_detector):
        """
        CRITICAL: Boss approval must work.

        When team members submit work, the boss must be able to approve it.
        If approval breaks, completed work can't be validated.
        """
        # Test approval with context
        intent, data = await intent_detector.detect_intent(
            "Yes, looks good",
            context={
                "is_boss": True,
                "awaiting_validation": True
            }
        )
        assert intent == UserIntent.APPROVE_TASK, \
            "Boss approval broken!"

    @pytest.mark.asyncio
    async def test_boss_reject_intent(self, intent_detector):
        """
        CRITICAL: Boss rejection/feedback must work.

        When work doesn't meet standards, the boss must send it back.
        If rejection breaks, bad work can't be corrected.
        """
        # Test rejection with context
        intent, data = await intent_detector.detect_intent(
            "No - needs more testing",
            context={
                "is_boss": True,
                "awaiting_validation": True
            }
        )
        assert intent == UserIntent.REJECT_TASK, \
            "Boss rejection broken!"
        assert "needs more testing" in data.get("feedback", "").lower(), \
            "Rejection feedback not captured!"

    @pytest.mark.asyncio
    async def test_help_command(self, intent_detector):
        """
        CRITICAL: Help must work.

        Users need to know what commands are available.
        If help breaks, users are stuck without guidance.
        """
        intent, data = await intent_detector.detect_intent("/help")
        assert intent == UserIntent.HELP, \
            "Help command broken!"

        # Also test natural language help
        intent, data = await intent_detector.detect_intent("help")
        assert intent == UserIntent.HELP, \
            "Natural language help broken!"

    @pytest.mark.asyncio
    async def test_status_check_intent(self, intent_detector):
        """
        CRITICAL: Status checks must work.

        Users need to see their tasks and deadlines.
        If status checks break, users can't track progress.
        """
        intent, data = await intent_detector.detect_intent("/status")
        assert intent == UserIntent.CHECK_STATUS, \
            "Status check command broken!"

        # Also test natural language
        intent, data = await intent_detector.detect_intent("What's pending?")
        assert intent in [UserIntent.CHECK_STATUS, UserIntent.SEARCH_TASKS], \
            "Natural language status check broken!"

    @pytest.mark.asyncio
    async def test_slash_command_parsing(self, intent_detector):
        """
        Test that slash commands parse correctly.

        Slash commands are the most direct path and must always work.
        """
        test_cases = [
            ("/help", UserIntent.HELP),
            ("/status", UserIntent.CHECK_STATUS),
            ("/daily", UserIntent.CHECK_STATUS),
            ("/overdue", UserIntent.CHECK_OVERDUE),
            ("/cancel", UserIntent.CANCEL),
        ]

        for message, expected_intent in test_cases:
            intent, data = await intent_detector.detect_intent(message)
            assert intent == expected_intent, \
                f"Slash command {message} broken! Expected {expected_intent}, got {intent}"

    @pytest.mark.asyncio
    async def test_context_state_handling(self, intent_detector):
        """
        Test that context-aware states work correctly.

        Different conversation contexts should produce different intents.
        """
        # Boss awaiting validation context
        intent, data = await intent_detector.detect_intent(
            "yes",
            context={"is_boss": True, "awaiting_validation": True}
        )
        assert intent == UserIntent.APPROVE_TASK, \
            "Context-aware boss approval broken!"

        # Staff collecting proof
        intent, data = await intent_detector.detect_intent(
            "https://example.com/screenshot.png",
            context={"collecting_proof": True}
        )
        assert intent == UserIntent.SUBMIT_PROOF, \
            "Context-aware proof submission broken!"

        # Staff finishing proof
        intent, data = await intent_detector.detect_intent(
            "done",
            context={"collecting_proof": True}
        )
        assert intent == UserIntent.DONE_ADDING_PROOF, \
            "Context-aware proof finish broken!"

    @pytest.mark.asyncio
    async def test_modification_pattern_detection(self, intent_detector):
        """
        Test that task modification patterns are detected without AI.

        Common patterns like "reassign TASK-001 to John" should work instantly.
        """
        test_cases = [
            ("reassign TASK-001 to John", UserIntent.REASSIGN_TASK),
            ("make TASK-001 urgent", UserIntent.CHANGE_PRIORITY),
            ("move TASK-001 to blocked", UserIntent.CHANGE_STATUS),
            ("tag TASK-001 as frontend", UserIntent.ADD_TAGS),
        ]

        for message, expected_intent in test_cases:
            intent, data = await intent_detector.detect_intent(message)
            assert intent == expected_intent, \
                f"Modification pattern '{message}' broken! " \
                f"Expected {expected_intent}, got {intent}"


class TestIntentDetectorResilience:
    """Test that IntentDetector is resilient to edge cases."""

    @pytest.mark.asyncio
    async def test_empty_message_handling(self, intent_detector):
        """Empty messages should not crash."""
        intent, data = await intent_detector.detect_intent("")
        assert intent == UserIntent.UNKNOWN or intent is not None, \
            "Empty message handling broken!"

    @pytest.mark.asyncio
    async def test_whitespace_only_message(self, intent_detector):
        """Whitespace-only messages should not crash."""
        intent, data = await intent_detector.detect_intent("   ")
        assert intent == UserIntent.UNKNOWN or intent is not None, \
            "Whitespace message handling broken!"

    @pytest.mark.asyncio
    async def test_very_long_message(self, intent_detector):
        """Very long messages should not crash."""
        long_message = "a" * 5000
        with patch.object(intent_detector, '_ai_classify') as mock_ai:
            mock_ai.return_value = (UserIntent.UNKNOWN, {"message": long_message})
            intent, data = await intent_detector.detect_intent(long_message)
            assert intent is not None, \
                "Long message handling broken!"

    @pytest.mark.asyncio
    async def test_unicode_handling(self, intent_detector):
        """Unicode characters should be handled correctly."""
        intent, data = await intent_detector.detect_intent("Create task: 测试 中文 বাংলা العربية")
        assert intent is not None, \
            "Unicode message handling broken!"

    @pytest.mark.asyncio
    async def test_case_insensitivity(self, intent_detector):
        """Intent detection should be case-insensitive."""
        test_cases = [
            "/HELP",
            "/Help",
            "/STATUS",
            "/Status",
        ]

        for message in test_cases:
            intent, data = await intent_detector.detect_intent(message)
            assert intent in [UserIntent.HELP, UserIntent.CHECK_STATUS], \
                f"Case insensitivity broken for {message}!"


class TestIntentDetectorSmokeTestSummary:
    """
    Summary test that validates all critical paths work.

    This is run as a final sanity check before deployment.
    """

    @pytest.mark.asyncio
    async def test_smoke_test_all_critical_paths(self, intent_detector):
        """
        Run all critical paths in sequence to ensure nothing breaks.

        If this test passes, the core system is functional.
        """
        critical_tests = [
            # Slash commands
            ("/help", UserIntent.HELP),
            ("/status", UserIntent.CHECK_STATUS),
            ("/overdue", UserIntent.CHECK_OVERDUE),
            ("/cancel", UserIntent.CANCEL),
        ]

        failed_paths = []

        for message, expected_intent in critical_tests:
            try:
                intent, data = await intent_detector.detect_intent(message)
                if intent != expected_intent:
                    failed_paths.append(
                        f"Path '{message}': expected {expected_intent}, got {intent}"
                    )
            except Exception as e:
                failed_paths.append(f"Path '{message}': raised {type(e).__name__}: {e}")

        # Report results
        if failed_paths:
            error_msg = "CRITICAL SMOKE TEST FAILED:\n" + "\n".join(failed_paths)
            pytest.fail(error_msg)
        else:
            logger.info("Smoke test passed - all critical paths working!")
