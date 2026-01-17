"""
Conversation flow tests for Boss Workflow.
Simulates real user interactions to test intent detection and handler responses.
"""

import asyncio
import sys
import codecs
from pathlib import Path

# Fix Windows console encoding for emoji output
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, errors='replace')

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Test results
results = []
issues = []

def log_test(name: str, message: str, response: str, passed: bool, issue: str = None):
    status = "PASS" if passed else "FAIL"
    results.append((name, passed))
    print(f"\n[{status}] {name}")
    print(f"  Input: {message[:60]}{'...' if len(message) > 60 else ''}")
    print(f"  Output: {response[:100]}{'...' if len(response) > 100 else ''}")
    if issue:
        issues.append((name, issue))
        print(f"  ISSUE: {issue}")


async def run_tests():
    """Run all conversation tests."""
    from src.bot.handler import get_unified_handler
    from src.ai.intent import get_intent_detector

    handler = get_unified_handler()
    intent_detector = get_intent_detector()

    user_id = "test_boss_123"
    user_name = "TestBoss"

    print("\n" + "="*60)
    print("   CONVERSATION FLOW TESTS")
    print("="*60)

    # ============================================================
    # TEST 1: Simple task creation
    # ============================================================
    print("\n--- TEST 1: Simple Task Creation ---")
    message = "Mayank fix the login bug by tomorrow"

    intent, data = await intent_detector.detect_intent(message, {"is_boss": True})
    print(f"  Intent detected: {intent}")

    response, _ = await handler.handle_message(
        user_id=user_id,
        message=message,
        user_name=user_name,
        is_boss=True,
        source="telegram"
    )

    passed = "preview" in response.lower() or "title" in response.lower() or "mayank" in response.lower()
    log_test(
        "Simple Task Creation",
        message,
        response,
        passed,
        None if passed else "Should show task preview"
    )

    # ============================================================
    # TEST 2: Confirm task with "yes"
    # ============================================================
    print("\n--- TEST 2: Confirm Task ---")
    message = "yes"

    response, _ = await handler.handle_message(
        user_id=user_id,
        message=message,
        user_name=user_name,
        is_boss=True,
        source="telegram"
    )

    passed = "created" in response.lower() or "task-" in response.lower() or "error" not in response.lower()
    log_test(
        "Confirm Task Creation",
        message,
        response,
        passed,
        None if passed else "Should create task or show error reason"
    )

    # ============================================================
    # TEST 3: Task with correction after preview
    # ============================================================
    print("\n--- TEST 3: Task Creation then Correction ---")

    # First create a task
    message = "Sarah update the docs"
    response, _ = await handler.handle_message(
        user_id=user_id,
        message=message,
        user_name=user_name,
        is_boss=True,
        source="telegram"
    )
    print(f"  Step 1 - Create: {response[:80]}...")

    # Now correct it
    message = "no, make it urgent and assign to John instead"
    response, _ = await handler.handle_message(
        user_id=user_id,
        message=message,
        user_name=user_name,
        is_boss=True,
        source="telegram"
    )

    # Should show updated preview, NOT create 3 tasks
    passed = "3 tasks" not in response.lower() and ("john" in response.lower() or "updated" in response.lower() or "urgent" in response.lower())
    log_test(
        "Task Correction (no, change X)",
        "no, make it urgent and assign to John",
        response,
        passed,
        None if passed else "Should update task, not create multiple new ones"
    )

    # Cancel this pending task
    await handler.handle_message(user_id=user_id, message="cancel", user_name=user_name, is_boss=True, source="telegram")

    # ============================================================
    # TEST 4: Multi-task creation
    # ============================================================
    print("\n--- TEST 4: Multi-Task Creation ---")
    message = "Mayank deploy the backend and Sarah update the frontend docs"

    intent, data = await intent_detector.detect_intent(message, {"is_boss": True})
    print(f"  Intent detected: {intent}")

    response, _ = await handler.handle_message(
        user_id=user_id,
        message=message,
        user_name=user_name,
        is_boss=True,
        source="telegram"
    )

    passed = "2 task" in response.lower() or ("mayank" in response.lower() and "sarah" in response.lower())
    log_test(
        "Multi-Task Creation",
        message,
        response,
        passed,
        None if passed else "Should detect 2 separate tasks"
    )

    # Cancel batch
    await handler.handle_message(user_id=user_id, message="cancel", user_name=user_name, is_boss=True, source="telegram")

    # ============================================================
    # TEST 5: Status check
    # ============================================================
    print("\n--- TEST 5: Status Check ---")
    message = "What's pending?"

    intent, data = await intent_detector.detect_intent(message, {"is_boss": True})
    print(f"  Intent detected: {intent}")

    response, _ = await handler.handle_message(
        user_id=user_id,
        message=message,
        user_name=user_name,
        is_boss=True,
        source="telegram"
    )

    passed = "task" in response.lower() or "pending" in response.lower() or "none" in response.lower() or "no " in response.lower()
    log_test(
        "Status Check",
        message,
        response,
        passed,
        None if passed else "Should show tasks or say none"
    )

    # ============================================================
    # TEST 6: Clear tasks
    # ============================================================
    print("\n--- TEST 6: Clear Tasks Intent ---")
    message = "clear all tasks"

    intent, data = await intent_detector.detect_intent(message, {"is_boss": True})
    print(f"  Intent detected: {intent}")

    passed = "clear" in str(intent).lower()
    log_test(
        "Clear Tasks Intent Detection",
        message,
        f"Intent: {intent}",
        passed,
        None if passed else "Should detect CLEAR_TASKS intent"
    )

    # ============================================================
    # TEST 7: "Submit new task" with details (boss)
    # ============================================================
    print("\n--- TEST 7: Submit New Task (Boss) ---")
    message = """submit new task

Title: Complete deployment
Assignee: mayank
Priority: high"""

    intent, data = await intent_detector.detect_intent(message, {"is_boss": True})
    print(f"  Intent detected: {intent}")

    response, _ = await handler.handle_message(
        user_id=user_id,
        message=message,
        user_name=user_name,
        is_boss=True,
        source="telegram"
    )

    passed = "create_task" in str(intent).lower() or "preview" in response.lower() or "title" in response.lower()
    issue = None
    if "review" in response.lower() and "submit" in response.lower():
        issue = "Incorrectly treating boss as staff (proof submission)"

    log_test(
        "Submit New Task (Boss on Telegram)",
        message[:50],
        response,
        passed and not issue,
        issue
    )

    # Cancel if pending
    await handler.handle_message(user_id=user_id, message="cancel", user_name=user_name, is_boss=True, source="telegram")

    # ============================================================
    # TEST 8: Help command
    # ============================================================
    print("\n--- TEST 8: Help Command ---")
    message = "help"

    response, _ = await handler.handle_message(
        user_id=user_id,
        message=message,
        user_name=user_name,
        is_boss=True,
        source="telegram"
    )

    passed = len(response) > 50  # Should have some help text
    log_test(
        "Help Command",
        message,
        response,
        passed,
        None if passed else "Help response too short"
    )

    # ============================================================
    # TEST 9: Greeting
    # ============================================================
    print("\n--- TEST 9: Greeting ---")
    message = "hello"

    response, _ = await handler.handle_message(
        user_id=user_id,
        message=message,
        user_name=user_name,
        is_boss=True,
        source="telegram"
    )

    passed = "hey" in response.lower() or "hello" in response.lower() or "hi" in response.lower() or user_name.lower() in response.lower()
    log_test(
        "Greeting Response",
        message,
        response,
        passed,
        None if passed else "Should greet back"
    )

    # ============================================================
    # TEST 10: Clear then Create (multi-action)
    # ============================================================
    print("\n--- TEST 10: Clear Then Create (Multi-Action) ---")
    message = "clear all tasks then create new task for Mayank to finish deployment"

    response, _ = await handler.handle_message(
        user_id=user_id,
        message=message,
        user_name=user_name,
        is_boss=True,
        source="telegram"
    )

    passed = ("clear" in response.lower() or "cancel" in response.lower()) and ("mayank" in response.lower() or "deployment" in response.lower() or "preview" in response.lower())
    log_test(
        "Clear Then Create Multi-Action",
        message[:50],
        response,
        passed,
        None if passed else "Should clear tasks AND show new task preview"
    )

    # Cancel any pending
    await handler.handle_message(user_id=user_id, message="cancel", user_name=user_name, is_boss=True, source="telegram")

    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "="*60)
    print("   TEST SUMMARY")
    print("="*60)

    passed_count = sum(1 for _, p in results if p)
    total = len(results)

    for name, passed in results:
        status = "[OK]" if passed else "[X]"
        print(f"  {status} {name}")

    print(f"\n  Total: {passed_count}/{total} tests passed")

    if issues:
        print("\n  ISSUES FOUND:")
        for name, issue in issues:
            print(f"    - {name}: {issue}")

    return passed_count == total


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
