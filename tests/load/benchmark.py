"""
Performance benchmarking utilities.

Measure system performance under load.
"""
import asyncio
import aiohttp
import time
import statistics
from typing import List, Dict
import sys

class PerformanceBenchmark:
    """Benchmark system performance."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: List[float] = []

    async def measure_endpoint(
        self,
        endpoint: str,
        method: str = "GET",
        data: dict = None,
        concurrent: int = 10
    ) -> Dict[str, float]:
        """
        Measure endpoint performance.

        Returns metrics: min, max, mean, median, p95, p99
        """
        async with aiohttp.ClientSession() as session:
            tasks = []

            for _ in range(concurrent):
                tasks.append(
                    self._single_request(session, endpoint, method, data)
                )

            durations = await asyncio.gather(*tasks)

        # Filter out failed requests
        valid_durations = [d for d in durations if d > 0]

        if not valid_durations:
            return {
                "min": 0,
                "max": 0,
                "mean": 0,
                "median": 0,
                "p95": 0,
                "p99": 0,
                "requests": 0,
                "failures": len(durations)
            }

        # Calculate statistics
        sorted_durations = sorted(valid_durations)
        return {
            "min": min(sorted_durations),
            "max": max(sorted_durations),
            "mean": statistics.mean(sorted_durations),
            "median": statistics.median(sorted_durations),
            "p95": sorted_durations[int(len(sorted_durations) * 0.95)] if len(sorted_durations) > 1 else sorted_durations[0],
            "p99": sorted_durations[int(len(sorted_durations) * 0.99)] if len(sorted_durations) > 1 else sorted_durations[0],
            "requests": len(valid_durations),
            "failures": len(durations) - len(valid_durations)
        }

    async def _single_request(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        method: str,
        data: dict
    ) -> float:
        """Make single request and measure duration."""
        url = f"{self.base_url}{endpoint}"
        start = time.time()

        try:
            if method == "GET":
                async with session.get(url) as response:
                    await response.text()
            elif method == "POST":
                async with session.post(url, json=data) as response:
                    await response.text()

            return time.time() - start

        except Exception as e:
            print(f"Request failed: {e}")
            return -1.0

async def run_benchmarks(base_url: str = "http://localhost:8000"):
    """Run all benchmarks."""
    bench = PerformanceBenchmark(base_url=base_url)

    print("\n" + "="*60)
    print("BOSS WORKFLOW PERFORMANCE BENCHMARKS")
    print("="*60)
    print(f"Target: {base_url}")
    print("="*60)

    # Benchmark: List tasks
    print("\n1. List Tasks Endpoint")
    results = await bench.measure_endpoint("/api/db/tasks", concurrent=50)
    print(f"   Concurrent Requests: 50")
    print(f"   Mean: {results['mean']*1000:.2f}ms")
    print(f"   Median: {results['median']*1000:.2f}ms")
    print(f"   P95: {results['p95']*1000:.2f}ms")
    print(f"   P99: {results['p99']*1000:.2f}ms")
    print(f"   Failures: {results['failures']}")

    # Benchmark: Create task
    print("\n2. Create Task Endpoint")
    task_data = {
        "title": "Benchmark Task",
        "assignee": "Test",
        "priority": "medium"
    }
    results = await bench.measure_endpoint(
        "/api/db/tasks",
        method="POST",
        data=task_data,
        concurrent=20
    )
    print(f"   Concurrent Requests: 20")
    print(f"   Mean: {results['mean']*1000:.2f}ms")
    print(f"   Median: {results['median']*1000:.2f}ms")
    print(f"   P95: {results['p95']*1000:.2f}ms")
    print(f"   Failures: {results['failures']}")

    # Benchmark: Health check
    print("\n3. Health Check Endpoint")
    results = await bench.measure_endpoint("/health", concurrent=100)
    print(f"   Concurrent Requests: 100")
    print(f"   Mean: {results['mean']*1000:.2f}ms")
    print(f"   Median: {results['median']*1000:.2f}ms")
    print(f"   P95: {results['p95']*1000:.2f}ms")
    print(f"   Failures: {results['failures']}")

    # Benchmark: Task by status
    print("\n4. Get Tasks by Status Endpoint")
    results = await bench.measure_endpoint("/api/db/tasks?status=pending", concurrent=30)
    print(f"   Concurrent Requests: 30")
    print(f"   Mean: {results['mean']*1000:.2f}ms")
    print(f"   Median: {results['median']*1000:.2f}ms")
    print(f"   P95: {results['p95']*1000:.2f}ms")
    print(f"   Failures: {results['failures']}")

    print("\n" + "="*60)
    print("BENCHMARKS COMPLETE!")
    print("="*60)
    print("\nSuccess Criteria:")
    print("  P95 < 500ms: ✓" if results['p95']*1000 < 500 else "  P95 < 500ms: ✗")
    print("  P99 < 1000ms: ✓" if results['p99']*1000 < 1000 else "  P99 < 1000ms: ✗")
    print("="*60 + "\n")

if __name__ == "__main__":
    import os

    # Allow custom URL via CLI or environment
    base_url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("LOAD_TEST_HOST", "http://localhost:8000")

    asyncio.run(run_benchmarks(base_url))
