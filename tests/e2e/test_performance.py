"""
Performance tests for conversation handling.

Tests response times, concurrency, and scalability.
"""

import pytest
import time
import asyncio
import logging
from typing import List

from tests.e2e.framework import ConversationSimulator

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
class TestResponseTimes:
    """Test response time requirements."""

    async def test_response_time_under_2_seconds(self):
        """
        Test: Bot responds to simple message within 2 seconds.

        Requirement: Fast responses for good UX.
        """
        sim = ConversationSimulator()

        start = time.time()
        await sim.send_message("Create task for John: Test")
        duration = time.time() - start

        assert duration < 2.0, f"Response took {duration:.2f}s (>2s)"

        await sim.cleanup()

    async def test_complex_task_response_under_5_seconds(self):
        """
        Test: Bot responds to complex task within 5 seconds.

        Complex tasks may need AI processing, but should still be fast.
        """
        sim = ConversationSimulator()

        start = time.time()
        await sim.send_message(
            "Create task for team: Build complete user authentication system "
            "with OAuth, 2FA, and password reset functionality"
        )
        duration = time.time() - start

        assert duration < 5.0, f"Response took {duration:.2f}s (>5s)"

        await sim.cleanup()

    async def test_search_response_under_1_second(self):
        """
        Test: Search queries return within 1 second.

        Searches should be very fast (database indexed).
        """
        sim = ConversationSimulator()

        # Create a few tasks first
        await sim.send_message("Create task for John: Test task 1")
        await sim.send_message("yes")

        # Now search
        start = time.time()
        await sim.send_message("/search test")
        duration = time.time() - start

        assert duration < 1.0, f"Search took {duration:.2f}s (>1s)"

        await sim.cleanup()

    async def test_status_check_under_1_second(self):
        """
        Test: Status checks return within 1 second.
        """
        sim = ConversationSimulator()

        start = time.time()
        await sim.send_message("/status")
        duration = time.time() - start

        assert duration < 1.0, f"Status check took {duration:.2f}s (>1s)"

        await sim.cleanup()


@pytest.mark.asyncio
class TestConcurrency:
    """Test concurrent conversation handling."""

    async def test_concurrent_conversations_5_users(self):
        """
        Test: Handle 5 concurrent conversations simultaneously.

        Simulates 5 different users talking to the bot at once.
        """
        # Create 5 simulators (different users)
        sims = [
            ConversationSimulator(user_id=f"TEST_USER_{i}", user_name=f"Test User {i}")
            for i in range(5)
        ]

        # All users send messages simultaneously
        tasks = [
            sim.send_message(f"Create task for John: Test from user {i}")
            for i, sim in enumerate(sims)
        ]

        # Run concurrently
        results = await asyncio.gather(*tasks)

        # All should get responses
        assert len(results) == 5
        for result in results:
            assert len(result) > 0, "Empty response"

        # Cleanup
        for sim in sims:
            await sim.cleanup()

    async def test_concurrent_conversations_10_users(self):
        """
        Test: Handle 10 concurrent conversations.

        Stress test for higher concurrency.
        """
        sims = [
            ConversationSimulator(user_id=f"TEST_USER_{i}")
            for i in range(10)
        ]

        tasks = [
            sim.send_message("Create task for John: Test")
            for sim in sims
        ]

        start = time.time()
        results = await asyncio.gather(*tasks)
        duration = time.time() - start

        # All should succeed
        assert len(results) == 10

        # Should handle all within reasonable time (not 10x single request)
        # Allow up to 10 seconds for 10 concurrent (vs 2s for 1)
        assert duration < 10.0, f"10 concurrent took {duration:.2f}s (>10s)"

        # Cleanup
        for sim in sims:
            await sim.cleanup()

    async def test_sequential_vs_concurrent_performance(self):
        """
        Test: Compare sequential vs concurrent performance.

        Concurrent should be significantly faster than sequential.
        """
        # Sequential: 5 messages one after another
        sim = ConversationSimulator()

        start_seq = time.time()
        for i in range(5):
            await sim.send_message(f"Create task for John: Test {i}")
        seq_duration = time.time() - start_seq

        await sim.cleanup()

        # Concurrent: 5 messages at once from different users
        sims = [ConversationSimulator(user_id=f"USER_{i}") for i in range(5)]

        start_conc = time.time()
        await asyncio.gather(*[
            sim.send_message("Create task for John: Test")
            for sim in sims
        ])
        conc_duration = time.time() - start_conc

        # Concurrent should be faster (at least 2x)
        speedup = seq_duration / conc_duration
        logger.info(f"Speedup: {speedup:.2f}x (sequential={seq_duration:.2f}s, concurrent={conc_duration:.2f}s)")

        assert speedup >= 1.5, f"Concurrent not faster enough: {speedup:.2f}x speedup"

        # Cleanup
        for sim in sims:
            await sim.cleanup()


@pytest.mark.asyncio
class TestThroughput:
    """Test message throughput capacity."""

    async def test_handle_100_messages_in_sequence(self):
        """
        Test: Handle 100 messages in rapid sequence.

        Tests sustained load handling.
        """
        sim = ConversationSimulator()

        start = time.time()

        # Send 100 simple queries
        for i in range(100):
            await sim.send_message("/status", wait_seconds=0.05)

        duration = time.time() - start

        # Should handle 100 messages in reasonable time
        # Target: <30 seconds (3.33 msgs/sec)
        assert duration < 30.0, f"100 messages took {duration:.2f}s (>30s)"

        logger.info(f"Throughput: {100/duration:.2f} msgs/sec")

        await sim.cleanup()

    async def test_conversation_memory_under_load(self):
        """
        Test: Conversation context preserved under load.

        Even with rapid messages, context should be maintained.
        """
        sim = ConversationSimulator()

        # Create a task
        await sim.send_message("Create task for John: Test task")
        await sim.send_message("yes")

        # Flood with other messages
        for _ in range(20):
            await sim.send_message("/status", wait_seconds=0.05)

        # Context should still work
        await sim.send_message("What was the last task I created?")

        # Should mention the task
        sim.assert_contains("task")

        await sim.cleanup()


@pytest.mark.asyncio
class TestScalability:
    """Test system scalability."""

    async def test_large_task_description(self):
        """
        Test: Handle task with very large description.
        """
        sim = ConversationSimulator()

        # Create a large description (500 words)
        large_desc = "Create task for John: " + " ".join([f"word{i}" for i in range(500)])

        start = time.time()
        await sim.send_message(large_desc)
        duration = time.time() - start

        # Should still respond quickly (AI processing might take time)
        assert duration < 10.0, f"Large description took {duration:.2f}s (>10s)"

        await sim.cleanup()

    async def test_many_tasks_in_database(self):
        """
        Test: Performance when database has many tasks.

        Create 50 tasks, then test query performance.
        """
        sim = ConversationSimulator()

        # Create 50 tasks quickly
        for i in range(50):
            await sim.send_message(f"Create task for John: Test task {i}", wait_seconds=0.1)
            await sim.send_message("yes", wait_seconds=0.1)

        # Now test search performance
        start = time.time()
        await sim.send_message("/search test")
        duration = time.time() - start

        # Should still be fast (indexed search)
        assert duration < 2.0, f"Search with 50 tasks took {duration:.2f}s (>2s)"

        await sim.cleanup()


@pytest.mark.asyncio
class TestResourceUsage:
    """Test resource usage and cleanup."""

    async def test_memory_cleanup_after_conversation(self):
        """
        Test: Memory is cleaned up after conversation ends.

        Run a conversation, verify cleanup.
        """
        import gc

        sim = ConversationSimulator()

        # Run full conversation
        await sim.run_conversation([
            "Create task for John: Test task",
            "yes"
        ])

        # Cleanup
        await sim.cleanup()

        # Force garbage collection
        gc.collect()

        # Verify conversation history is cleared
        assert len(sim.conversation_history) == 0
        assert len(sim.created_tasks) == 0

    async def test_no_memory_leak_in_long_conversation(self):
        """
        Test: Long conversations don't leak memory.

        Send 50 messages and verify cleanup.
        """
        sim = ConversationSimulator()

        # Long conversation
        for i in range(50):
            await sim.send_message(f"/status", wait_seconds=0.05)

        # Should have all in history
        assert len(sim.conversation_history) == 50

        # Cleanup
        await sim.cleanup()

        # Should be empty
        assert len(sim.conversation_history) == 0


@pytest.mark.asyncio
class TestPerformanceRegression:
    """Test for performance regressions."""

    async def test_baseline_task_creation_performance(self):
        """
        Test: Baseline performance for task creation.

        This test establishes a performance baseline for comparison.
        """
        sim = ConversationSimulator()

        # Measure average time for 10 task creations
        times = []

        for i in range(10):
            start = time.time()
            await sim.send_message(f"Create task for John: Test {i}")
            await sim.send_message("yes")
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)
        max_time = max(times)
        min_time = min(times)

        logger.info(f"Task creation baseline: avg={avg_time:.2f}s, min={min_time:.2f}s, max={max_time:.2f}s")

        # Set baseline threshold (update if system improves)
        assert avg_time < 3.0, f"Average task creation time {avg_time:.2f}s exceeds baseline (3s)"
        assert max_time < 5.0, f"Max task creation time {max_time:.2f}s exceeds baseline (5s)"

        await sim.cleanup()
