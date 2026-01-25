"""Benchmark performance after dependency updates."""
import asyncio
import time
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def benchmark_cryptography():
    """Test cryptography performance."""
    from cryptography.fernet import Fernet

    print("[*] Benchmarking cryptography...")

    # Generate key
    key = Fernet.generate_key()
    cipher = Fernet(key)

    # Benchmark encryption/decryption
    iterations = 10000
    test_data = b"This is a test message for benchmarking encryption performance."

    start = time.time()

    for _ in range(iterations):
        encrypted = cipher.encrypt(test_data)
        decrypted = cipher.decrypt(encrypted)

    duration = time.time() - start
    ops_per_sec = (iterations * 2) / duration  # 2 ops per iteration (encrypt + decrypt)

    print(f"  [OK] Cryptography: {iterations} encrypt/decrypt pairs in {duration:.2f}s ({ops_per_sec:.2f} ops/s)")
    return ops_per_sec


async def benchmark_protobuf():
    """Test protobuf performance."""
    from google.protobuf import json_format
    from google.protobuf.struct_pb2 import Struct

    print("[*] Benchmarking protobuf...")

    # Create test data
    test_dict = {
        "name": "Test Task",
        "description": "This is a test task for benchmarking",
        "priority": "high",
        "status": "pending",
        "metadata": {
            "created_at": "2026-01-25",
            "updated_at": "2026-01-25",
            "tags": ["test", "benchmark", "performance"]
        }
    }

    iterations = 10000

    start = time.time()

    for _ in range(iterations):
        struct = Struct()
        json_format.ParseDict(test_dict, struct)
        result_dict = json_format.MessageToDict(struct)

    duration = time.time() - start
    ops_per_sec = (iterations * 2) / duration  # 2 ops per iteration (parse + serialize)

    print(f"  [OK] Protobuf: {iterations} parse/serialize pairs in {duration:.2f}s ({ops_per_sec:.2f} ops/s)")
    return ops_per_sec


async def benchmark_redis():
    """Test Redis performance (if available)."""
    try:
        from src.cache.redis_client import cache

        print("[*] Benchmarking Redis...")

        iterations = 1000

        start = time.time()

        for i in range(iterations):
            await cache.set(f"benchmark:test:{i}", f"value:{i}")
            await cache.get(f"benchmark:test:{i}")

        # Cleanup
        for i in range(iterations):
            await cache.delete(f"benchmark:test:{i}")

        duration = time.time() - start
        ops_per_sec = (iterations * 2) / duration  # 2 ops per iteration (set + get)

        print(f"  [OK] Redis: {iterations} set/get pairs in {duration:.2f}s ({ops_per_sec:.2f} ops/s)")
        return ops_per_sec

    except ImportError:
        print("  [WARN] Redis not available (cache module not found)")
        return None
    except Exception as e:
        print(f"  [WARN] Redis benchmark failed: {e}")
        return None


async def benchmark_database():
    """Test database performance (if available)."""
    try:
        from src.database.repositories import get_task_repository

        print("[*] Benchmarking Database...")

        repo = get_task_repository()
        iterations = 100

        start = time.time()

        for _ in range(iterations):
            await repo.get_all(limit=10)

        duration = time.time() - start
        queries_per_sec = iterations / duration

        print(f"  [OK] Database: {iterations} queries in {duration:.2f}s ({queries_per_sec:.2f} queries/s)")
        return queries_per_sec

    except ImportError:
        print("  [WARN] Database not available (repository module not found)")
        return None
    except Exception as e:
        print(f"  [WARN] Database benchmark failed: {e}")
        return None


async def main():
    """Run all benchmarks."""
    print("=" * 60)
    print("  DEPENDENCY PERFORMANCE BENCHMARK")
    print("=" * 60)
    print()

    results = {}

    # Benchmark cryptography
    try:
        results['cryptography'] = await benchmark_cryptography()
    except Exception as e:
        print(f"  [ERROR] Cryptography benchmark failed: {e}")
        results['cryptography'] = None

    print()

    # Benchmark protobuf
    try:
        results['protobuf'] = await benchmark_protobuf()
    except Exception as e:
        print(f"  [ERROR] Protobuf benchmark failed: {e}")
        results['protobuf'] = None

    print()

    # Benchmark Redis
    results['redis'] = await benchmark_redis()

    print()

    # Benchmark Database
    results['database'] = await benchmark_database()

    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print()

    for component, perf in results.items():
        if perf is not None:
            print(f"  {component.title()}: {perf:.2f} ops/s")
        else:
            print(f"  {component.title()}: N/A (not available)")

    print()
    print("TIP: To compare with previous version:")
    print("   diff benchmark_before.txt benchmark_after.txt")
    print()
    print("[OK] Benchmark complete!")


if __name__ == "__main__":
    asyncio.run(main())
