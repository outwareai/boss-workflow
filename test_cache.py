#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Redis caching implementation.

Q3 2026: Verify cache layer functionality.
"""
import asyncio
import sys
import io

# Fix Windows console encoding for emoji/unicode
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from config.settings import get_settings

settings = get_settings()


async def test_redis_connection():
    """Test basic Redis connection."""
    print("\n=== Testing Redis Connection ===")

    from src.cache.redis_client import get_redis, close_redis

    try:
        client = await get_redis()

        if client is None:
            print("[FAIL] Redis not configured (REDIS_URL not set)")
            print(f"       Current REDIS_URL: {settings.redis_url or '(empty)'}")
            return False

        # Test ping
        pong = await client.ping()
        print(f"[PASS] Redis connection successful (ping: {pong})")

        # Test info
        info = await client.info()
        print(f"[PASS] Redis version: {info.get('redis_version')}")
        print(f"[PASS] Connected clients: {info.get('connected_clients')}")
        print(f"[PASS] Used memory: {info.get('used_memory_human')}")

        return True

    except Exception as e:
        print(f"[FAIL] Redis connection failed: {e}")
        return False
    finally:
        await close_redis()


async def test_cache_operations():
    """Test basic cache operations."""
    print("\n=== Testing Cache Operations ===")

    from src.cache.redis_client import cache, close_redis

    try:
        # Test set
        await cache.set("test_key", {"value": "hello", "number": 123}, ttl=60)
        print("[PASS] Cache SET successful")

        # Test get
        value = await cache.get("test_key")
        assert value == {"value": "hello", "number": 123}
        print(f"[PASS] Cache GET successful: {value}")

        # Test exists
        exists = await cache.exists("test_key")
        assert exists is True
        print("[PASS] Cache EXISTS successful")

        # Test TTL
        ttl = await cache.ttl("test_key")
        print(f"[PASS] Cache TTL: {ttl} seconds")

        # Test delete
        await cache.delete("test_key")
        value = await cache.get("test_key")
        assert value is None
        print("[PASS] Cache DELETE successful")

        # Test pattern invalidation
        await cache.set("test:1", "value1", ttl=60)
        await cache.set("test:2", "value2", ttl=60)
        await cache.set("other:1", "value3", ttl=60)

        deleted = await cache.invalidate_pattern("test:*")
        assert deleted == 2
        print(f"[PASS] Pattern invalidation successful ({deleted} keys deleted)")

        # Cleanup
        await cache.delete("other:1")

        return True

    except AssertionError as e:
        print(f"[FAIL] Cache operation assertion failed: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Cache operations failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await close_redis()


async def test_cache_decorator():
    """Test cache decorator."""
    print("\n=== Testing Cache Decorator ===")

    from src.cache.decorators import cached
    from src.cache.redis_client import close_redis

    call_count = 0

    @cached(ttl=60, key_prefix="test_func")
    async def expensive_function(x: int, y: int) -> int:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)  # Simulate expensive operation
        return x + y

    try:
        # First call - should execute function
        result1 = await expensive_function(5, 3)
        assert result1 == 8
        assert call_count == 1
        print(f"[PASS] First call executed function (result: {result1})")

        # Second call - should use cache
        result2 = await expensive_function(5, 3)
        assert result2 == 8
        assert call_count == 1  # Should not increment
        print(f"[PASS] Second call used cache (call_count: {call_count})")

        # Different args - should execute function
        result3 = await expensive_function(10, 20)
        assert result3 == 30
        assert call_count == 2
        print(f"[PASS] Different args executed function (result: {result3})")

        return True

    except AssertionError as e:
        print(f"[FAIL] Decorator test assertion failed: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Decorator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await close_redis()


async def test_cache_stats():
    """Test cache statistics."""
    print("\n=== Testing Cache Statistics ===")

    from src.cache.stats import stats
    from src.cache.redis_client import close_redis

    try:
        # Reset stats
        stats.reset()

        # Record some hits and misses
        stats.record_hit()
        stats.record_hit()
        stats.record_miss()

        summary = stats.get_summary()
        assert summary["hits"] == 2
        assert summary["misses"] == 1
        assert summary["total"] == 3
        print(f"[PASS] Stats tracking successful: {summary}")

        # Test Redis stats
        redis_stats = await stats.get_redis_stats()
        if redis_stats:
            print(f"[PASS] Redis stats retrieved: {redis_stats.get('redis_version')}")
        else:
            print("[WARN] Redis stats not available")

        # Test full stats
        full_stats = await stats.get_full_stats()
        print(f"[PASS] Full stats: {full_stats['application']['hit_rate_percent']}")

        return True

    except Exception as e:
        print(f"[FAIL] Stats test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await close_redis()


async def main():
    """Run all cache tests."""
    print("=" * 60)
    print("Redis Caching Layer Test Suite")
    print("=" * 60)

    results = []

    # Test 1: Redis connection
    results.append(await test_redis_connection())

    # Only continue if Redis is available
    if not results[0]:
        print("\n" + "=" * 60)
        print("SKIPPING remaining tests - Redis not available")
        print("=" * 60)
        return False

    # Test 2: Cache operations
    results.append(await test_cache_operations())

    # Test 3: Cache decorator
    results.append(await test_cache_decorator())

    # Test 4: Cache statistics
    results.append(await test_cache_stats())

    # Summary
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if all(results):
        print("[PASS] ALL TESTS PASSED")
        return True
    else:
        print("[FAIL] SOME TESTS FAILED")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
