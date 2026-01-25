"""
End-to-end tests for critical conversation flows.

Tests complete user journeys from message to action.
"""

import pytest
import logging
from datetime import datetime, timedelta, UTC

from tests.e2e.framework import ConversationSimulator, ConversationAssertion
from src.models.task import TaskStatus, TaskPriority

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
class TestTaskCreationFlows:
    """Test task creation workflows."""

    async def test_simple_task_creation_flow(self):
        """
        Test: Boss creates simple task with assignee.

        Flow:
        1. Boss: "Create task for John: Fix login bug"
        2. Bot: Shows preview
        3. Boss: "yes"
        4. Bot: Creates task
        """
        sim = ConversationSimulator()

        # Full conversation
        await sim.run_conversation([
            "Create task for John: Fix login bug",
            "yes"  # Confirm
        ])

        # Verify task created
        sim.assert_task_created()
        sim.assert_contains("task created")

        # Verify in database
        task = await sim.assert_task_in_database(
            title_contains="login",
            assignee="John"
        )

        assert task.status == TaskStatus.PENDING
        assert task.description is not None

        # Cleanup
        await sim.cleanup()

    async def test_complex_task_with_questions_flow(self):
        """
        Test: Boss creates complex task, AI asks clarifying questions.

        Flow:
        1. Boss: "Build notification system for user alerts"
        2. Bot: Asks questions (if complexity is high)
        3. Boss: Answers questions
        4. Bot: Shows preview
        5. Boss: "yes"
        6. Bot: Creates task
        """
        sim = ConversationSimulator()

        # Initial message
        await sim.send_message("Build notification system for user alerts")

        # Bot might ask questions OR show preview directly (depends on AI complexity score)
        # Either way, confirm with yes
        await sim.send_message("yes")

        # Verify task created
        sim.assert_task_created()

        task = await sim.assert_task_in_database(
            title_contains="notification"
        )

        assert task.description is not None
        assert len(task.description) > 50  # Should have detailed description

        await sim.cleanup()

    async def test_task_with_deadline_flow(self):
        """
        Test: Boss creates task with deadline.

        Flow:
        1. Boss: "Create task for Zea: Update docs by tomorrow"
        2. Bot: Shows preview with deadline
        3. Boss: "yes"
        4. Bot: Creates task with deadline
        """
        sim = ConversationSimulator()

        await sim.run_conversation([
            "Create task for Zea: Update docs by tomorrow",
            "yes"
        ])

        sim.assert_task_created()

        task = await sim.assert_task_in_database(
            title_contains="docs",
            assignee="Zea"
        )

        # Should have deadline set
        assert task.deadline is not None
        # Deadline should be within next 48 hours (tomorrow +/- buffer)
        assert task.deadline < datetime.now(UTC) + timedelta(days=2)

        await sim.cleanup()

    async def test_task_with_priority_flow(self):
        """
        Test: Boss creates high-priority task.

        Flow:
        1. Boss: "URGENT: Fix production server crash for Mayank"
        2. Bot: Shows preview with high priority
        3. Boss: "yes"
        4. Bot: Creates high-priority task
        """
        sim = ConversationSimulator()

        await sim.run_conversation([
            "URGENT: Fix production server crash for Mayank",
            "yes"
        ])

        sim.assert_task_created()

        task = await sim.assert_task_in_database(
            title_contains="server crash",
            assignee="Mayank"
        )

        # Should detect urgency
        assert task.priority == TaskPriority.HIGH

        await sim.cleanup()


@pytest.mark.asyncio
class TestTaskModificationFlows:
    """Test task modification workflows."""

    async def test_task_status_change_flow(self):
        """
        Test: Boss changes task status.

        Flow:
        1. Boss creates task
        2. Boss: "Change TASK-XXX status to completed"
        3. Bot: Updates status
        """
        sim = ConversationSimulator()

        # Create task first
        await sim.send_message("Create task for John: Test task")
        await sim.send_message("yes")

        task_id = sim.created_tasks[-1]

        # Change status
        await sim.send_message(f"Change {task_id} status to completed")

        sim.assert_contains("status updated")

        # Verify in database
        task = await sim.assert_task_in_database(task_id=task_id)
        assert task.status == TaskStatus.COMPLETED

        await sim.cleanup()

    async def test_task_reassignment_flow(self):
        """
        Test: Boss reassigns task to different person.

        Flow:
        1. Boss creates task for John
        2. Boss: "Reassign TASK-XXX to Zea"
        3. Bot: Updates assignee
        """
        sim = ConversationSimulator()

        # Create task for John
        await sim.send_message("Create task for John: Test reassignment")
        await sim.send_message("yes")

        task_id = sim.created_tasks[-1]

        # Reassign to Zea
        await sim.send_message(f"Reassign {task_id} to Zea")

        sim.assert_contains("reassigned")

        # Verify in database
        task = await sim.assert_task_in_database(task_id=task_id)
        assert task.assignee == "Zea"

        await sim.cleanup()


@pytest.mark.asyncio
class TestRejectionFlows:
    """Test rejection and correction workflows."""

    async def test_boss_rejection_flow(self):
        """
        Test: Boss rejects task spec and provides feedback.

        Flow:
        1. Boss: "Create task for Zea: Update docs"
        2. Bot: Shows preview
        3. Boss: "no" (reject)
        4. Bot: Asks what to change
        5. Boss: Provides feedback
        6. Bot: Shows updated preview
        """
        sim = ConversationSimulator()

        # Initial request
        await sim.send_message("Create task for Zea: Update docs")

        # Reject
        await sim.send_message("no")

        # Bot should ask what to change
        sim.assert_question_asked()
        sim.assert_contains("what")  # "What would you like to change?"

        # Provide feedback
        await sim.send_message("Need more detail about which docs")

        # Bot should show updated preview or ask more questions
        # In any case, no task should be created yet
        await sim.assert_no_task_created()

        await sim.cleanup()

    async def test_cancellation_flow(self):
        """
        Test: Boss cancels task creation mid-flow.

        Flow:
        1. Boss: "Create task for John: Something"
        2. Boss: "cancel"
        3. Bot: Cancels and no task created
        """
        sim = ConversationSimulator()

        await sim.send_message("Create task for John: Test cancellation")

        # Cancel before confirming
        await sim.send_message("cancel")

        sim.assert_contains("cancel")
        await sim.assert_no_task_created()

        await sim.cleanup()


@pytest.mark.asyncio
class TestQueryFlows:
    """Test query and information retrieval flows."""

    async def test_search_flow(self):
        """
        Test: Boss searches for tasks.

        Flow:
        1. Boss: "/search login"
        2. Bot: Shows matching tasks
        """
        sim = ConversationSimulator()

        # Create a task first
        await sim.send_message("Create task for John: Fix login bug")
        await sim.send_message("yes")

        # Search for it
        await sim.send_message("/search login")

        sim.assert_contains("found")
        sim.assert_contains("TASK-")  # Should show task ID

        await sim.cleanup()

    async def test_status_check_flow(self):
        """
        Test: Boss checks overall status.

        Flow:
        1. Boss: "/status"
        2. Bot: Shows task summary
        """
        sim = ConversationSimulator()

        await sim.send_message("/status")

        # Should show task counts
        sim.assert_contains("tasks")

        await sim.cleanup()

    async def test_help_flow(self):
        """
        Test: Boss requests help.

        Flow:
        1. Boss: "/help"
        2. Bot: Shows available commands
        """
        sim = ConversationSimulator()

        await sim.send_message("/help")

        sim.assert_contains("available commands")
        sim.assert_contains("/")  # Should list slash commands

        await sim.cleanup()

    async def test_team_status_flow(self):
        """
        Test: Boss checks team member status.

        Flow:
        1. Boss: "What is John working on?"
        2. Bot: Shows John's tasks
        """
        sim = ConversationSimulator()

        # Create a task for John first
        await sim.send_message("Create task for John: Test task")
        await sim.send_message("yes")

        # Check what John is working on
        await sim.send_message("What is John working on?")

        sim.assert_contains("John")
        sim.assert_contains("task")

        await sim.cleanup()


@pytest.mark.asyncio
class TestMultiTaskFlows:
    """Test flows involving multiple tasks."""

    async def test_create_multiple_tasks_flow(self):
        """
        Test: Boss creates multiple tasks in sequence.

        Flow:
        1. Boss creates task 1
        2. Boss creates task 2
        3. Boss creates task 3
        4. All tasks exist independently
        """
        sim = ConversationSimulator()

        # Create 3 tasks
        await sim.send_message("Create task for John: Task 1")
        await sim.send_message("yes")

        await sim.send_message("Create task for Zea: Task 2")
        await sim.send_message("yes")

        await sim.send_message("Create task for Mayank: Task 3")
        await sim.send_message("yes")

        # Should have 3 tasks
        assert len(sim.created_tasks) == 3

        # All should be in database
        for task_id in sim.created_tasks:
            task = await sim.assert_task_in_database(task_id=task_id)
            assert task is not None

        await sim.cleanup()

    async def test_task_dependency_flow(self):
        """
        Test: Boss creates dependent tasks.

        Flow:
        1. Boss creates task A
        2. Boss creates task B that depends on A
        3. Bot records dependency
        """
        sim = ConversationSimulator()

        # Create first task
        await sim.send_message("Create task for John: Setup database")
        await sim.send_message("yes")
        task_a = sim.created_tasks[-1]

        # Create dependent task
        await sim.send_message(f"Create task for John: Write API endpoints that depends on {task_a}")
        await sim.send_message("yes")

        # Should create task with dependency
        # (This assumes the AI can detect and create dependencies)
        # Verification would require checking task relationships in DB

        await sim.cleanup()


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_invalid_assignee_flow(self):
        """
        Test: Boss assigns task to non-existent person.

        Flow:
        1. Boss: "Create task for NonExistentPerson: Do something"
        2. Bot: Handles gracefully (might ask for clarification or proceed anyway)
        """
        sim = ConversationSimulator()

        await sim.send_message("Create task for NonExistentPerson: Test task")

        # Bot should either:
        # - Ask for clarification
        # - Warn about unknown person
        # - Or proceed (depending on strictness)

        # At minimum, should not crash
        response = sim.get_last_response()
        assert len(response) > 0

        await sim.cleanup()

    async def test_ambiguous_task_flow(self):
        """
        Test: Boss gives vague task description.

        Flow:
        1. Boss: "Do the thing"
        2. Bot: Asks for clarification
        """
        sim = ConversationSimulator()

        await sim.send_message("Do the thing")

        # Bot should ask questions
        sim.assert_question_asked()

        await sim.cleanup()

    async def test_rapid_fire_messages_flow(self):
        """
        Test: Boss sends multiple messages quickly.

        Flow:
        1. Boss sends 5 messages in quick succession
        2. Bot handles all correctly
        """
        sim = ConversationSimulator()

        messages = [
            "Create task for John: Task 1",
            "yes",
            "Create task for Zea: Task 2",
            "yes",
            "/status"
        ]

        # Send all with minimal delay
        await sim.run_conversation(messages, wait_between=0.1)

        # Should have handled all messages
        assert len(sim.conversation_history) == 5

        await sim.cleanup()
