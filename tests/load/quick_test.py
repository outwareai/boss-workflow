#!/usr/bin/env python3
"""
Quick load test runner.

Simplified interface for running load tests without full Locust setup.
"""
import argparse
import subprocess
import sys
import os

def run_benchmark(host: str):
    """Run quick performance benchmark."""
    print(f"\n🔍 Running benchmark against {host}...\n")
    subprocess.run([sys.executable, "tests/load/benchmark.py", host])

def run_scenario(scenario: str, host: str):
    """Run specific load test scenario."""
    scenarios = ["light", "medium", "heavy", "spike"]

    if scenario not in scenarios:
        print(f"❌ Unknown scenario: {scenario}")
        print(f"Available: {', '.join(scenarios)}")
        sys.exit(1)

    os.environ["LOAD_TEST_HOST"] = host
    subprocess.run([sys.executable, "tests/load/scenarios.py", scenario])

def main():
    parser = argparse.ArgumentParser(
        description="Quick load test runner for Boss Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run benchmark
  python tests/load/quick_test.py benchmark

  # Run light load test
  python tests/load/quick_test.py test light

  # Run heavy load test against production
  python tests/load/quick_test.py test heavy --host https://boss-workflow.railway.app

  # Run full suite
  python tests/load/quick_test.py full
        """
    )

    parser.add_argument(
        "command",
        choices=["benchmark", "test", "full"],
        help="Command to run"
    )

    parser.add_argument(
        "scenario",
        nargs="?",
        choices=["light", "medium", "heavy", "spike"],
        help="Load test scenario (required for 'test' command)"
    )

    parser.add_argument(
        "--host",
        default="http://localhost:8000",
        help="Target host URL (default: http://localhost:8000)"
    )

    args = parser.parse_args()

    if args.command == "benchmark":
        run_benchmark(args.host)

    elif args.command == "test":
        if not args.scenario:
            print("❌ Scenario required for 'test' command")
            print("Available: light, medium, heavy, spike")
            sys.exit(1)
        run_scenario(args.scenario, args.host)

    elif args.command == "full":
        print("🚀 Running full load test suite...\n")

        # Run benchmark
        run_benchmark(args.host)

        # Run all scenarios
        for scenario in ["light", "medium", "heavy", "spike"]:
            print(f"\n{'='*60}")
            print(f"Running {scenario} scenario...")
            print('='*60)
            run_scenario(scenario, args.host)

        print("\n✅ Full test suite complete!")
        print(f"📊 Reports available in tests/load/reports/\n")

if __name__ == "__main__":
    main()
