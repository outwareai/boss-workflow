"""
Test performance tracking and slow query detection.

Q3 2026 Phase 4: Verify performance metrics are working.
"""
import asyncio
import time
from src.monitoring.performance import perf_tracker
from src.database.slow_query_detector import slow_query_detector


async def test_performance_tracking():
    """Test performance tracking functionality."""
    print("\n=== Testing Performance Tracking ===\n")

    # Test 1: Track a fast request
    @perf_tracker.track_request
    async def fast_request():
        await asyncio.sleep(0.05)  # 50ms
        return "fast"

    # Test 2: Track a slow request
    @perf_tracker.track_request
    async def slow_request():
        await asyncio.sleep(1.5)  # 1.5s (exceeds 1s threshold)
        return "slow"

    # Test 3: Track a fast query
    @perf_tracker.track_query("test_fast_query")
    async def fast_query():
        await asyncio.sleep(0.05)  # 50ms
        return "fast query"

    # Test 4: Track a slow query
    @perf_tracker.track_query("test_slow_query")
    async def slow_query():
        await asyncio.sleep(0.15)  # 150ms (exceeds 100ms threshold)
        return "slow query"

    print("1. Testing fast request (50ms)...")
    result = await fast_request()
    print(f"   Result: {result}")

    print("\n2. Testing slow request (1.5s - should log warning)...")
    result = await slow_request()
    print(f"   Result: {result}")

    print("\n3. Testing fast query (50ms)...")
    result = await fast_query()
    print(f"   Result: {result}")

    print("\n4. Testing slow query (150ms - should log warning)...")
    result = await slow_query()
    print(f"   Result: {result}")

    print("\n=== Testing Slow Query Detector ===\n")

    # Test slow query detector
    print("5. Testing slow query detector stats...")

    # Simulate some slow queries
    for i in range(5):
        slow_query_detector.slow_queries.append({
            "statement": f"SELECT * FROM tasks WHERE id = {i}",
            "statement_preview": f"SELECT * FROM tasks WHERE id = {i}",
            "duration_ms": 100 + (i * 50),
            "timestamp": time.time(),
            "parameters": None,
        })

    stats = slow_query_detector.get_stats()
    print(f"   Stats: {stats}")

    queries = slow_query_detector.get_slow_queries(limit=3)
    print(f"\n   Top 3 slow queries:")
    for q in queries:
        print(f"     - {q['duration_ms']:.2f}ms: {q['statement_preview']}")

    print("\n6. Testing clear history...")
    slow_query_detector.clear_history()
    print(f"   Queries after clear: {len(slow_query_detector.slow_queries)}")

    print("\n=== All Tests Completed ===\n")


if __name__ == "__main__":
    asyncio.run(test_performance_tracking())
