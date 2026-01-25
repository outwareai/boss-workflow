#!/usr/bin/env python3
"""
Convenient script to run E2E tests with various options.

Usage:
    python run_e2e_tests.py                    # Run all E2E tests
    python run_e2e_tests.py --critical         # Run critical flows only
    python run_e2e_tests.py --performance      # Run performance tests only
    python run_e2e_tests.py --smoke            # Run smoke tests (fastest)
    python run_e2e_tests.py --coverage         # Run with coverage report
    python run_e2e_tests.py --verbose          # Verbose output
    python run_e2e_tests.py --debug            # Debug mode (very verbose)
"""

import sys
import subprocess
from pathlib import Path


def run_tests(args: list[str]):
    """Run pytest with given arguments."""
    cmd = ["pytest"] + args
    print(f"Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    return result.returncode


def main():
    # Base pytest args
    base_args = ["tests/e2e/"]

    # Parse custom arguments
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0

    if "--critical" in sys.argv:
        base_args = ["tests/e2e/test_critical_flows.py"]
        print("Running critical flows only...")

    elif "--performance" in sys.argv:
        base_args = ["tests/e2e/test_performance.py"]
        print("Running performance tests only...")

    elif "--smoke" in sys.argv:
        base_args = [
            "tests/e2e/test_critical_flows.py::TestTaskCreationFlows::test_simple_task_creation_flow",
            "tests/e2e/test_critical_flows.py::TestQueryFlows::test_status_check_flow",
        ]
        print("Running smoke tests (critical paths only)...")

    # Add common options
    pytest_args = base_args.copy()

    if "--coverage" in sys.argv:
        pytest_args.extend([
            "--cov=src",
            "--cov-report=html",
            "--cov-report=term-missing"
        ])
        print("Coverage reporting enabled...")

    if "--verbose" in sys.argv or "-v" in sys.argv:
        pytest_args.append("-vv")

    if "--debug" in sys.argv:
        pytest_args.extend(["-vv", "-s", "--log-cli-level=DEBUG"])
        print("Debug mode enabled...")

    # Always add these
    pytest_args.extend([
        "--tb=short",
        "--timeout=300",  # 5 minute timeout per test
    ])

    # Run tests
    return run_tests(pytest_args)


if __name__ == "__main__":
    sys.exit(main())
