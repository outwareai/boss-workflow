"""
Performance tests for database connection pooling.

Q3 2026: Test pool handles concurrent requests and verify health checks.

Note: These tests require a DATABASE_URL to be configured.
Set environment variable or skip with pytest -m "not performance"
"""
import pytest
import asyncio
import time
import os
from sqlalchemy import text

from config import settings
from src.database.connection import get_database, get_pool_status, check_pool_health
from src.database.health import check_connection_leaks, get_detailed_health_report


# Skip all tests if DATABASE_URL is not configured
pytestmark = pytest.mark.skipif(
    not settings.database_url,
    reason="DATABASE_URL not configured - skipping performance tests"
)


@pytest.mark.asyncio
async def test_concurrent_sessions():
    """Test pool handles concurrent sessions without blocking."""
    db = get_database()

    # Ensure database is initialized
    if not db._initialized:
        await db.initialize()

    async def perform_query(session_id: int) -> dict:
        """Simulate a database query."""
        async with db.session() as session:
            # Simulate some work
            await asyncio.sleep(0.05)  # 50ms query
            result = await session.execute(text("SELECT 1 as value"))
            value = result.scalar()
            return {
                "session_id": session_id,
                "value": value,
                "success": True
            }

    # Create 50 concurrent requests (more than pool size)
    start_time = time.time()
    tasks = [perform_query(i) for i in range(50)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.time() - start_time

    # Verify all queries succeeded
    successful = [r for r in results if isinstance(r, dict) and r.get("success")]
    failed = [r for r in results if isinstance(r, Exception)]

    assert len(successful) == 50, f"Expected 50 successful queries, got {len(successful)}"
    assert len(failed) == 0, f"No queries should fail, but got {len(failed)} failures"
    assert all(r["value"] == 1 for r in successful), "All queries should return 1"

    # Performance check: 50 queries should complete in reasonable time
    # With pool_size=20 + max_overflow=10 (30 max), should be fast
    assert elapsed < 5.0, f"Queries took too long: {elapsed:.2f}s (expected < 5s)"

    print(f"\nOK 50 concurrent queries completed in {elapsed:.2f}s")


@pytest.mark.asyncio
async def test_pool_status():
    """Test pool status reporting."""
    db = get_database()

    # Ensure database is initialized
    if not db._initialized:
        await db.initialize()

    status = await get_pool_status()

    # Check required fields
    assert "pool_type" in status
    assert "status" in status

    # If using QueuePool (production mode)
    if status["pool_type"] == "QueuePool":
        assert "size" in status
        assert "checked_out" in status
        assert "checked_in" in status
        assert "overflow" in status
        assert "total_connections" in status
        assert "max_connections" in status
        assert "utilization" in status

        # Verify pool configuration
        assert status["size"] >= 10, "Pool size should be at least 10"
        assert status["max_connections"] >= 20, "Max connections should be at least 20"

        print(f"\nOK Pool status: {status}")
    else:
        # NullPool in test mode
        assert status["pool_type"] == "NullPool"
        print(f"\nOK NullPool detected (test mode)")


@pytest.mark.asyncio
async def test_pool_health_check():
    """Test pool health check function."""
    db = get_database()

    # Ensure database is initialized
    if not db._initialized:
        await db.initialize()

    is_healthy = await check_pool_health()

    # Pool should be healthy at startup
    assert is_healthy is True, "Pool should be healthy initially"

    print(f"\nOK Pool health check passed: {is_healthy}")


@pytest.mark.asyncio
async def test_connection_leak_detection():
    """Test connection leak detection."""
    db = get_database()

    # Ensure database is initialized
    if not db._initialized:
        await db.initialize()

    leak_report = await check_connection_leaks()

    # Check required fields
    assert "has_leak" in leak_report
    assert "warnings" in leak_report

    # At startup, should have no leaks
    # Note: In test mode (NullPool), this might not apply
    status = await get_pool_status()
    if status["pool_type"] == "QueuePool":
        # In production pool, check leak detection
        assert isinstance(leak_report["has_leak"], bool)
        assert isinstance(leak_report["warnings"], list)
        print(f"\nOK Leak detection: has_leak={leak_report['has_leak']}, warnings={len(leak_report['warnings'])}")
    else:
        print(f"\nOK Leak detection skipped (NullPool mode)")


@pytest.mark.asyncio
async def test_detailed_health_report():
    """Test detailed health report generation."""
    db = get_database()

    # Ensure database is initialized
    if not db._initialized:
        await db.initialize()

    report = await get_detailed_health_report()

    # Verify report structure
    assert "timestamp" in report
    assert "pool_status" in report
    assert "is_healthy" in report
    assert "leak_detection" in report
    assert "overall_status" in report

    # Verify overall status
    assert report["overall_status"] in ["healthy", "degraded", "critical"]

    print(f"\nOK Health report: {report['overall_status']}")
    print(f"  Pool: {report['pool_status'].get('status')}")
    print(f"  Leaks: {report['leak_detection'].get('has_leak')}")


@pytest.mark.asyncio
async def test_pool_under_load():
    """Test pool behavior under sustained load."""
    db = get_database()

    # Ensure database is initialized
    if not db._initialized:
        await db.initialize()

    async def sustained_query(query_id: int, duration: float) -> dict:
        """Simulate a longer-running query."""
        async with db.session() as session:
            # Simulate work
            await asyncio.sleep(duration)
            result = await session.execute(text("SELECT :id as query_id"), {"id": query_id})
            return {"query_id": result.scalar(), "success": True}

    # Create 100 queries with 0.1s duration each
    # This will create sustained pressure on the pool
    start_time = time.time()
    tasks = [sustained_query(i, 0.1) for i in range(100)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.time() - start_time

    successful = [r for r in results if isinstance(r, dict) and r.get("success")]
    assert len(successful) == 100, f"All 100 queries should succeed, got {len(successful)}"

    # Check pool status after load
    status = await get_pool_status()
    print(f"\nOK Sustained load test: 100 queries in {elapsed:.2f}s")
    if status["pool_type"] == "QueuePool":
        print(f"  Final pool state: {status['checked_out']}/{status['max_connections']} connections")


@pytest.mark.asyncio
async def test_pool_recovery_after_error():
    """Test pool recovers after connection errors."""
    db = get_database()

    # Ensure database is initialized
    if not db._initialized:
        await db.initialize()

    # Perform valid query first
    async with db.session() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1

    # Try an invalid query (should fail but not break pool)
    try:
        async with db.session() as session:
            await session.execute(text("SELECT * FROM nonexistent_table"))
    except Exception as e:
        # Expected to fail
        print(f"\nOK Expected error caught: {type(e).__name__}")

    # Verify pool still works after error
    async with db.session() as session:
        result = await session.execute(text("SELECT 2"))
        assert result.scalar() == 2

    # Check pool health
    is_healthy = await check_pool_health()
    assert is_healthy is True, "Pool should recover after error"

    print(f"OK Pool recovered successfully after error")


if __name__ == "__main__":
    # Run tests manually
    print("Running connection pool performance tests...")
    asyncio.run(test_concurrent_sessions())
    asyncio.run(test_pool_status())
    asyncio.run(test_pool_health_check())
    asyncio.run(test_connection_leak_detection())
    asyncio.run(test_detailed_health_report())
    asyncio.run(test_pool_under_load())
    asyncio.run(test_pool_recovery_after_error())
    print("\nPASS All tests passed!")
