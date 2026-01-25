"""
Example E2E tests demonstrating the framework usage.

These tests serve as templates for writing new E2E tests.
"""

import pytest
import time
from tests.e2e.framework import ConversationSimulator, TestScenario, ConversationAssertion


@pytest.mark.asyncio
@pytest.mark.e2e
class TestExamples:
    """Example tests showing framework usage."""

    async def test_basic_conversation(self):
        """
        Example: Most basic conversation test.

        Shows the minimal code needed for a simple test.
        """
        # Create simulator
        sim = ConversationSimulator()

        # Send message
        await sim.send_message("Hello")

        # Assert response contains something
        sim.assert_contains("hello")

        # Cleanup
        await sim.cleanup()

    async def test_task_creation_example(self):
        """
        Example: Task creation with validation.

        Shows how to create a task and verify it in database.
        """
        sim = ConversationSimulator()

        # Create task
        await sim.send_message("Create task for John: Example task")
        await sim.send_message("yes")

        # Verify task created
        sim.assert_task_created()

        # Verify in database
        task = await sim.assert_task_in_database(
            title_contains="example",
            assignee="John"
        )

        # Additional checks
        assert task.description is not None
        assert task.status.value == "pending"

        # Cleanup
        await sim.cleanup()

    async def test_multi_turn_conversation_example(self):
        """
        Example: Multi-turn conversation.

        Shows how to run a complete conversation flow.
        """
        sim = ConversationSimulator()

        # Run multi-turn conversation
        responses = await sim.run_conversation([
            "Create task for Zea: Update documentation",
            "yes",
            "/status",
            "/help"
        ])

        # Verify we got 4 responses
        assert len(responses) == 4

        # Check conversation history
        assert len(sim.conversation_history) == 4

        # Check specific response
        sim.assert_contains("command")  # Last response (help) should mention commands

        # Cleanup
        await sim.cleanup()

    async def test_rejection_example(self):
        """
        Example: Boss rejects task and provides feedback.

        Shows how to test rejection flows.
        """
        sim = ConversationSimulator()

        # Request task
        await sim.send_message("Create task for John: Vague task")

        # Reject
        await sim.send_message("no")

        # Should ask what to change
        sim.assert_question_asked()

        # Provide feedback
        await sim.send_message("Add more details please")

        # No task should be created yet
        await sim.assert_no_task_created()

        # Cleanup
        await sim.cleanup()

    async def test_scenario_framework_example(self):
        """
        Example: Using TestScenario for reusable test cases.

        Shows the higher-level scenario API.
        """
        # Create a scenario
        scenario = TestScenario(
            name="Simple task creation",
            messages=[
                "Create task for John: Test task",
                "yes"
            ],
            assertions=[
                ConversationAssertion("task_created", None, "Task ID in response"),
                ConversationAssertion(
                    "task_in_db",
                    {"title_contains": "test", "assignee": "John"},
                    "Task in database"
                )
            ]
        )

        # Run scenario
        success, errors = await scenario.run()

        # Check results
        assert success, f"Scenario failed: {errors}"

    async def test_performance_example(self):
        """
        Example: Testing response time.

        Shows how to measure performance.
        """
        sim = ConversationSimulator()

        # Measure response time
        start = time.time()
        await sim.send_message("/status")
        duration = time.time() - start

        # Assert fast response
        assert duration < 2.0, f"Response took {duration:.2f}s (expected <2s)"

        # Cleanup
        await sim.cleanup()

    async def test_concurrent_example(self):
        """
        Example: Testing concurrent conversations.

        Shows how to test multiple users simultaneously.
        """
        import asyncio

        # Create 3 simulators (different users)
        sims = [
            ConversationSimulator(user_id=f"TEST_USER_{i}")
            for i in range(3)
        ]

        # All send messages at once
        results = await asyncio.gather(*[
            sim.send_message("Hello")
            for sim in sims
        ])

        # All should get responses
        assert len(results) == 3
        for response in results:
            assert len(response) > 0

        # Cleanup all
        for sim in sims:
            await sim.cleanup()

    async def test_debug_example(self):
        """
        Example: Debugging failed tests.

        Shows debugging utilities.
        """
        sim = ConversationSimulator()

        # Run conversation
        await sim.run_conversation([
            "Create task for John: Debug test",
            "yes"
        ])

        # Print full conversation for debugging
        if False:  # Set to True when debugging
            sim.print_conversation()

        # Get last response
        last_response = sim.get_last_response()
        print(f"Last response: {last_response[:100]}...")

        # Get created tasks
        print(f"Created tasks: {sim.created_tasks}")

        # Cleanup
        await sim.cleanup()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.smoke
async def test_smoke_example():
    """
    Example: Smoke test (critical path).

    Smoke tests are minimal tests that verify core functionality.
    They should be fast and test only the most critical paths.
    """
    sim = ConversationSimulator()

    # Minimal critical path: create task
    await sim.send_message("Create task for John: Smoke test")
    await sim.send_message("yes")

    # Verify it worked
    sim.assert_task_created()

    # That's it - keep smoke tests minimal
    await sim.cleanup()
