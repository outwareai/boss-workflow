"""
Intent detection tests - tests message understanding without needing Redis.
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")


async def run_tests():
    """Run intent detection tests."""
    from src.ai.intent import get_intent_detector, UserIntent

    detector = get_intent_detector()

    print("\n" + "="*60)
    print("   INTENT DETECTION TESTS")
    print("="*60)

    results = []
    issues = []

    # Test cases: (message, expected_intent, is_boss, description)
    test_cases = [
        # Task creation
        ("Mayank fix the login bug", UserIntent.CREATE_TASK, True, "Simple task assignment"),
        ("Sarah needs to update the docs by tomorrow", UserIntent.CREATE_TASK, True, "Task with deadline"),
        ("assign John to review the PR urgent", UserIntent.CREATE_TASK, True, "Urgent task"),
        ("create new task for mayank", UserIntent.CREATE_TASK, True, "Explicit create"),
        ("Add a task to mayank to fix UI with dropdown by default", UserIntent.CREATE_TASK, True, "Add task with 'by default'"),

        # Formatted task spec
        ("submit new task\n\nTitle: Fix bug\nAssignee: mayank", UserIntent.CREATE_TASK, True, "Formatted spec"),
        ("Title: Deploy app\nAssignee: john\nPriority: high", UserIntent.CREATE_TASK, True, "Spec without 'submit'"),

        # Status checks
        ("what's pending?", UserIntent.CHECK_STATUS, True, "Status query"),
        ("show me the tasks", UserIntent.CHECK_STATUS, True, "Show tasks"),
        ("what's john working on?", UserIntent.SEARCH_TASKS, True, "Search by person"),

        # Clear/delete
        ("clear all tasks", UserIntent.CLEAR_TASKS, True, "Clear all"),
        ("delete all tasks", UserIntent.CLEAR_TASKS, True, "Delete all"),
        ("wipe tasks", UserIntent.CLEAR_TASKS, True, "Wipe tasks"),

        # Greeting
        ("hello", UserIntent.GREETING, True, "Greeting"),
        ("hi", UserIntent.GREETING, True, "Short greeting"),

        # Help
        ("help", UserIntent.HELP, True, "Help request"),

        # Spec generation
        ("/spec TASK-001", UserIntent.GENERATE_SPEC, True, "Spec command"),
        ("generate spec for TASK-123", UserIntent.GENERATE_SPEC, True, "Natural spec request"),

        # Task completion (staff)
        ("I finished the task", UserIntent.TASK_DONE, False, "Task done (staff)"),
        ("done with TASK-001", UserIntent.TASK_DONE, False, "Specific task done"),

        # Cancel
        ("cancel", UserIntent.CANCEL, True, "Cancel"),
        ("nevermind", UserIntent.CANCEL, True, "Nevermind"),
    ]

    passed = 0
    failed = 0

    for message, expected, is_boss, description in test_cases:
        context = {"is_boss": is_boss, "stage": "none"}
        intent, data = await detector.detect_intent(message, context)

        success = intent == expected
        status = "PASS" if success else "FAIL"

        if success:
            passed += 1
        else:
            failed += 1
            issues.append((description, message, expected, intent))

        print(f"[{status}] {description}")
        print(f"       Input: '{message[:40]}{'...' if len(message) > 40 else ''}'")
        print(f"       Expected: {expected.value}, Got: {intent.value}")

    # Summary
    print("\n" + "="*60)
    print("   SUMMARY")
    print("="*60)
    print(f"  Passed: {passed}/{len(test_cases)}")
    print(f"  Failed: {failed}/{len(test_cases)}")

    if issues:
        print("\n  ISSUES:")
        for desc, msg, expected, got in issues:
            print(f"    - {desc}: expected {expected.value}, got {got.value}")
            print(f"      Message: '{msg[:50]}'")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
