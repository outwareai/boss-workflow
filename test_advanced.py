"""
Advanced comprehensive tests for Boss Workflow.
Tests subtask extraction, corrections, edge cases, and multi-task scenarios.
"""

import asyncio
import sys
import codecs
import json
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, errors='replace')

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.issues = []

    def log(self, name: str, passed: bool, details: str = "", issue: str = ""):
        status = "PASS" if passed else "FAIL"
        if passed:
            self.passed += 1
        else:
            self.failed += 1
            if issue:
                self.issues.append((name, issue))

        print(f"\n[{status}] {name}")
        if details:
            print(f"  {details[:150]}{'...' if len(details) > 150 else ''}")
        if issue:
            print(f"  ISSUE: {issue}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"   RESULTS: {self.passed}/{total} passed")
        print(f"{'='*60}")
        if self.issues:
            print("\n   ISSUES FOUND:")
            for name, issue in self.issues:
                print(f"   - {name}: {issue}")
        return self.failed == 0


async def test_subtask_extraction():
    """Test that subtasks are properly extracted from various message formats."""
    from src.ai.deepseek import get_deepseek_client

    results = TestResults()
    ai = get_deepseek_client()

    print("\n" + "="*60)
    print("   SUBTASK EXTRACTION TESTS")
    print("="*60)

    test_cases = [
        {
            "name": "Dash-separated subtasks",
            "message": "Task for Mayank to fix UI. Subtasks: - Fix header - Update colors - Add logo",
            "expected_subtasks": 3,
        },
        {
            "name": "In it make subtasks",
            "message": "Add a task to john to deploy app. In it make subtasks being - Set up server - Configure DNS - Test deployment",
            "expected_subtasks": 3,
        },
        {
            "name": "Numbered subtasks",
            "message": "Create task for sarah: Build dashboard. 1. Design mockups 2. Implement frontend 3. Add backend API 4. Testing",
            "expected_subtasks": 4,
        },
        {
            "name": "With notes",
            "message": "Task for mayank fix login bug. Subtasks - Check auth flow - Fix token refresh. Notes: test on mobile too",
            "expected_subtasks": 2,
            "has_notes": True,
        },
        {
            "name": "Complex real-world message",
            "message": """Add a task to mayank to fix UI. In it make subtasks being
            - PARTNER PROGRAM needs to be thicker
            - Most grey text to be Thicker
            - Needs to add referral code in the first form
            - Third page dropdown by default
            Notes make sure phone is working""",
            "expected_subtasks": 4,
            "has_notes": True,
        },
    ]

    for tc in test_cases:
        try:
            # Use the AI to generate spec
            spec = await ai.generate_task_spec(
                original_message=tc["message"],
                qa_pairs={},
                preferences={},
                extracted_info={}
            )

            subtasks = spec.get("subtasks", [])
            notes = spec.get("notes", "")

            subtask_count = len(subtasks)
            expected = tc["expected_subtasks"]

            # Check subtask count
            passed = subtask_count >= expected - 1  # Allow 1 less for AI variation

            issue = ""
            if subtask_count == 0 and expected > 0:
                issue = f"No subtasks extracted! Expected {expected}"
            elif subtask_count < expected - 1:
                issue = f"Only {subtask_count} subtasks, expected ~{expected}"

            # Check notes if expected
            if tc.get("has_notes") and (not notes or notes == "null"):
                issue = (issue + "; " if issue else "") + "Notes not extracted"
                passed = False

            details = f"Got {subtask_count} subtasks"
            if subtasks:
                details += f": {[s.get('title', s)[:30] for s in subtasks[:3]]}"
            if notes and notes != "null":
                details += f" | Notes: {str(notes)[:40]}"

            results.log(tc["name"], passed, details, issue)

        except Exception as e:
            results.log(tc["name"], False, "", f"Error: {str(e)[:50]}")

    return results


async def test_task_corrections():
    """Test that task corrections work properly."""
    from src.bot.handler import get_unified_handler
    from src.ai.intent import get_intent_detector

    results = TestResults()
    handler = get_unified_handler()
    intent_detector = get_intent_detector()

    print("\n" + "="*60)
    print("   TASK CORRECTION TESTS")
    print("="*60)

    user_id = "test_correction_user"

    # First create a task to get into preview stage
    response1, _ = await handler.handle_message(
        user_id=user_id,
        message="Mayank deploy the app by tomorrow",
        user_name="TestBoss",
        is_boss=True,
        source="telegram"
    )

    if "preview" not in response1.lower() and "title" not in response1.lower():
        results.log("Setup - Create task preview", False, response1[:100], "Didn't get preview")
        return results

    results.log("Setup - Create task preview", True, response1[:100])

    # Test corrections
    correction_tests = [
        {
            "name": "Edit to add something",
            "message": "edit to add favicon requirement",
            "should_contain": ["updated", "preview", "favicon"],
        },
        {
            "name": "Make it urgent",
            "message": "make it urgent",
            "should_contain": ["updated", "urgent"],
        },
        {
            "name": "Change assignee",
            "message": "change assignee to John",
            "should_contain": ["updated", "john"],
        },
        {
            "name": "Add to description",
            "message": "add that we need to test on mobile",
            "should_contain": ["updated", "mobile"],
        },
    ]

    for tc in correction_tests:
        try:
            response, _ = await handler.handle_message(
                user_id=user_id,
                message=tc["message"],
                user_name="TestBoss",
                is_boss=True,
                source="telegram"
            )

            response_lower = response.lower()

            # Check if it's an update (not an error or new task)
            is_update = "updated" in response_lower or "preview" in response_lower
            has_expected = any(kw.lower() in response_lower for kw in tc["should_contain"])

            passed = is_update or has_expected
            issue = ""

            if "couldn't understand" in response_lower or "error" in response_lower:
                passed = False
                issue = "Got error response"
            elif "created" in response_lower and "task-" in response_lower:
                passed = False
                issue = "Created new task instead of editing"

            results.log(tc["name"], passed, response[:100], issue)

        except Exception as e:
            results.log(tc["name"], False, "", f"Error: {str(e)[:50]}")

    # Cancel to clean up
    await handler.handle_message(
        user_id=user_id, message="cancel",
        user_name="TestBoss", is_boss=True, source="telegram"
    )

    return results


async def test_multi_task_with_subtasks():
    """Test multiple tasks with subtasks in one message."""
    from src.bot.handler import get_unified_handler

    results = TestResults()
    handler = get_unified_handler()

    print("\n" + "="*60)
    print("   MULTI-TASK WITH SUBTASKS TESTS")
    print("="*60)

    user_id = "test_multi_subtask_user"

    test_cases = [
        {
            "name": "Two tasks with subtasks",
            "message": """Task 1 for Mayank: Fix UI with subtasks - Update header - Fix colors
            Then another task for John: Deploy backend with subtasks - Setup server - Configure DB""",
            "expected_tasks": 2,
        },
        {
            "name": "Tasks separated by 'and'",
            "message": "Mayank fix the login bug and Sarah update the documentation",
            "expected_tasks": 2,
        },
    ]

    for tc in test_cases:
        try:
            response, _ = await handler.handle_message(
                user_id=user_id,
                message=tc["message"],
                user_name="TestBoss",
                is_boss=True,
                source="telegram"
            )

            response_lower = response.lower()

            # Check for multiple tasks
            has_multiple = "2 task" in response_lower or "**1.**" in response or "**2.**" in response

            passed = has_multiple
            issue = ""

            if not has_multiple:
                issue = "Didn't detect multiple tasks"

            # Check if subtasks are shown in batch preview
            if "subtask" in tc["message"].lower():
                if "subtask" not in response_lower and "📝" not in response:
                    issue = (issue + "; " if issue else "") + "Subtasks not shown in preview"

            results.log(tc["name"], passed, response[:150], issue)

            # Cancel batch
            await handler.handle_message(
                user_id=user_id, message="cancel",
                user_name="TestBoss", is_boss=True, source="telegram"
            )

        except Exception as e:
            results.log(tc["name"], False, "", f"Error: {str(e)[:50]}")

    return results


async def test_edge_cases():
    """Test edge cases and potential issues."""
    from src.ai.intent import get_intent_detector

    results = TestResults()
    detector = get_intent_detector()

    print("\n" + "="*60)
    print("   EDGE CASE TESTS")
    print("="*60)

    from src.ai.intent import UserIntent

    edge_cases = [
        # Should be CREATE_TASK
        ("add task for john fix bug", UserIntent.CREATE_TASK, True, "Add task prefix"),
        ("create a task: deploy the app", UserIntent.CREATE_TASK, True, "Create a task prefix"),
        ("mayank needs to fix by default settings", UserIntent.CREATE_TASK, True, "Contains 'by default'"),
        ("task for john: implement feature by end of day", UserIntent.CREATE_TASK, True, "Task for prefix"),
        ("john should fix the crash asap", UserIntent.CREATE_TASK, True, "Should action"),

        # Should NOT be CREATE_TASK
        ("what's john working on", UserIntent.SEARCH_TASKS, True, "Search person tasks"),
        ("show me all tasks", UserIntent.CHECK_STATUS, True, "Show all tasks"),
        ("my default priority is high", UserIntent.TEACH_PREFERENCE, True, "Set default preference"),

        # Should be CLEAR_TASKS
        ("clear everything", UserIntent.CLEAR_TASKS, True, "Clear everything"),
        ("delete all the tasks", UserIntent.CLEAR_TASKS, True, "Delete all tasks"),

        # Staff vs Boss
        ("I finished the deployment", UserIntent.TASK_DONE, False, "Staff completion"),
    ]

    for message, expected, is_boss, name in edge_cases:
        try:
            context = {"is_boss": is_boss, "stage": "none"}
            intent, data = await detector.detect_intent(message, context)

            passed = intent == expected
            issue = "" if passed else f"Got {intent.value}, expected {expected.value}"

            results.log(name, passed, f"'{message[:40]}' -> {intent.value}", issue)

        except Exception as e:
            results.log(name, False, "", f"Error: {str(e)[:50]}")

    return results


async def test_confirmation_flows():
    """Test yes/no confirmation flows."""
    from src.bot.handler import get_unified_handler

    results = TestResults()
    handler = get_unified_handler()

    print("\n" + "="*60)
    print("   CONFIRMATION FLOW TESTS")
    print("="*60)

    user_id = "test_confirm_user"

    # Test 1: Simple yes confirmation
    await handler.handle_message(
        user_id=user_id,
        message="Mayank fix the bug",
        user_name="TestBoss",
        is_boss=True,
        source="telegram"
    )

    response, _ = await handler.handle_message(
        user_id=user_id,
        message="yes",
        user_name="TestBoss",
        is_boss=True,
        source="telegram"
    )

    passed = "created" in response.lower() or "task-" in response.lower()
    results.log("Simple yes confirmation", passed, response[:100],
                "" if passed else "Task not created on 'yes'")

    # Test 2: No cancellation
    await handler.handle_message(
        user_id=user_id,
        message="Sarah update docs",
        user_name="TestBoss",
        is_boss=True,
        source="telegram"
    )

    response, _ = await handler.handle_message(
        user_id=user_id,
        message="no",
        user_name="TestBoss",
        is_boss=True,
        source="telegram"
    )

    passed = "cancel" in response.lower() or "what would you like" in response.lower()
    results.log("No cancellation", passed, response[:100],
                "" if passed else "Didn't cancel on 'no'")

    # Test 3: Confirmation variants
    variants = ["ok", "confirm", "looks good", "lgtm", "perfect"]
    for variant in variants:
        await handler.handle_message(
            user_id=user_id,
            message="John test the API",
            user_name="TestBoss",
            is_boss=True,
            source="telegram"
        )

        response, _ = await handler.handle_message(
            user_id=user_id,
            message=variant,
            user_name="TestBoss",
            is_boss=True,
            source="telegram"
        )

        passed = "created" in response.lower() or "task-" in response.lower()
        results.log(f"Confirm with '{variant}'", passed, response[:80],
                    "" if passed else f"'{variant}' didn't confirm")

    return results


async def run_all_tests():
    """Run all advanced tests."""
    print("\n" + "="*60)
    print("   ADVANCED COMPREHENSIVE TESTS")
    print("="*60)

    all_results = TestResults()

    # Run each test suite
    test_suites = [
        ("Subtask Extraction", test_subtask_extraction),
        ("Edge Cases", test_edge_cases),
        ("Task Corrections", test_task_corrections),
        ("Multi-Task with Subtasks", test_multi_task_with_subtasks),
        ("Confirmation Flows", test_confirmation_flows),
    ]

    for name, test_fn in test_suites:
        try:
            results = await test_fn()
            all_results.passed += results.passed
            all_results.failed += results.failed
            all_results.issues.extend(results.issues)
        except Exception as e:
            print(f"\n[ERROR] {name} suite failed: {e}")
            all_results.failed += 1
            all_results.issues.append((name, str(e)[:100]))

    # Final summary
    print("\n" + "="*60)
    print("   FINAL SUMMARY")
    print("="*60)
    total = all_results.passed + all_results.failed
    print(f"\n   Total: {all_results.passed}/{total} tests passed")
    print(f"   Failed: {all_results.failed}")

    if all_results.issues:
        print(f"\n   ISSUES TO FIX ({len(all_results.issues)}):")
        for name, issue in all_results.issues:
            print(f"   - {name}: {issue}")

    return all_results.failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
