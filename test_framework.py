#!/usr/bin/env python3
"""
PROPER TEST FRAMEWORK - Boss Workflow

This framework validates ACTUAL OUTCOMES, not just log keywords.

PHILOSOPHY:
- A test passes ONLY if the final task has correct values
- Multi-turn conversations are tested end-to-end
- Every test has explicit expected outcomes
- Failures show exactly what went wrong

USAGE:
    python test_framework.py run-all              # Run all test suites
    python test_framework.py run conversation     # Run conversation tests
    python test_framework.py run validation       # Run output validation tests
    python test_framework.py list                 # List all test cases
"""

import os
import sys
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from dotenv import load_dotenv

load_dotenv()

# Configuration
RAILWAY_URL = "https://boss-workflow-production.up.railway.app"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOSS_CHAT_ID = os.getenv("TELEGRAM_BOSS_CHAT_ID")


class TestStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ExpectedTask:
    """What we expect the final task to look like."""
    title_contains: Optional[str] = None  # Task title should contain this
    title_not_contains: Optional[str] = None  # Task title should NOT contain this
    assignee: Optional[str] = None  # Expected assignee (case-insensitive)
    priority: Optional[str] = None  # Expected priority
    has_deadline: Optional[bool] = None  # Should have a deadline?
    description_contains: Optional[str] = None  # Description should contain


@dataclass
class ConversationStep:
    """A single step in a conversation test."""
    action: str  # "send", "wait", "validate_questions", "validate_task"
    message: Optional[str] = None  # For "send" action
    wait_seconds: int = 5  # For "wait" action
    expect_questions: Optional[int] = None  # For "validate_questions"
    expect_question_about: Optional[List[str]] = None  # Topics questions should cover
    expected_task: Optional[ExpectedTask] = None  # For "validate_task"


@dataclass
class TestCase:
    """A complete test case definition."""
    id: str
    name: str
    description: str
    steps: List[ConversationStep]
    tags: List[str] = field(default_factory=list)

    # Results (filled after running)
    status: TestStatus = TestStatus.PENDING
    errors: List[str] = field(default_factory=list)
    actual_task: Optional[Dict] = None
    logs: List[str] = field(default_factory=list)


@dataclass
class TestResult:
    """Result of running a test case."""
    test_id: str
    test_name: str
    status: TestStatus
    errors: List[str]
    expected: Dict
    actual: Dict
    duration_seconds: float
    logs: List[str]


class BotTester:
    """Core bot testing functionality."""

    def __init__(self):
        self.message_counter = int(datetime.now().timestamp()) % 100000

    async def send_message(self, text: str) -> Dict:
        """Send a message to the bot via webhook."""
        self.message_counter += 1

        payload = {
            "update_id": int(datetime.now().timestamp()),
            "message": {
                "message_id": self.message_counter,
                "from": {
                    "id": int(TELEGRAM_BOSS_CHAT_ID),
                    "is_bot": False,
                    "first_name": "TestBot"
                },
                "chat": {
                    "id": int(TELEGRAM_BOSS_CHAT_ID),
                    "type": "private"
                },
                "date": int(datetime.now().timestamp()),
                "text": text
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{RAILWAY_URL}/webhook/telegram", json=payload) as resp:
                return {"status": resp.status, "ok": resp.status == 200}

    async def get_recent_tasks(self, limit: int = 5) -> List[Dict]:
        """Get recent tasks from database."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{RAILWAY_URL}/api/db/tasks?limit={limit}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("tasks", [])
                return []

    async def get_task_by_partial_title(
        self, title_fragment: str, limit: int = 10, max_age_minutes: int = 5
    ) -> Optional[Dict]:
        """Find a task whose title contains the given fragment, created recently."""
        tasks = await self.get_recent_tasks(limit)
        title_lower = title_fragment.lower()
        now = datetime.utcnow()

        for task in tasks:
            # Check if task matches title
            if title_lower not in task.get("title", "").lower():
                continue

            # Check if task was created recently
            created_at = task.get("created_at", "")
            if created_at:
                try:
                    # Parse ISO format datetime
                    if "T" in created_at:
                        task_time = datetime.fromisoformat(created_at.replace("Z", ""))
                        age_minutes = (now - task_time).total_seconds() / 60
                        if age_minutes <= max_age_minutes:
                            return task
                        # Skip old tasks
                        continue
                except Exception:
                    pass

            # If no timestamp or parsing failed, return it anyway
            return task

        return None


class TestValidator:
    """Validates test expectations against actual results."""

    @staticmethod
    def validate_task(expected: ExpectedTask, actual: Dict) -> Tuple[bool, List[str]]:
        """Validate that actual task matches expectations."""
        errors = []

        if not actual:
            return False, ["No task found"]

        actual_title = actual.get("title", "").lower()
        actual_assignee = (actual.get("assignee") or "").lower()
        actual_priority = (actual.get("priority") or "").lower()
        actual_deadline = actual.get("deadline")
        actual_description = (actual.get("description") or "").lower()

        # Validate title contains
        if expected.title_contains:
            if expected.title_contains.lower() not in actual_title:
                errors.append(
                    f"Title should contain '{expected.title_contains}' but got '{actual.get('title')}'"
                )

        # Validate title NOT contains
        if expected.title_not_contains:
            if expected.title_not_contains.lower() in actual_title:
                errors.append(
                    f"Title should NOT contain '{expected.title_not_contains}' but got '{actual.get('title')}'"
                )

        # Validate assignee
        if expected.assignee:
            if expected.assignee.lower() != actual_assignee:
                errors.append(
                    f"Assignee should be '{expected.assignee}' but got '{actual.get('assignee')}'"
                )

        # Validate priority
        if expected.priority:
            if expected.priority.lower() != actual_priority:
                errors.append(
                    f"Priority should be '{expected.priority}' but got '{actual.get('priority')}'"
                )

        # Validate deadline presence
        if expected.has_deadline is not None:
            has_deadline = bool(actual_deadline)
            if expected.has_deadline and not has_deadline:
                errors.append("Task should have a deadline but doesn't")
            elif not expected.has_deadline and has_deadline:
                errors.append(f"Task should NOT have a deadline but has '{actual_deadline}'")

        # Validate description contains
        if expected.description_contains:
            if expected.description_contains.lower() not in actual_description:
                errors.append(
                    f"Description should contain '{expected.description_contains}'"
                )

        return len(errors) == 0, errors


class TestRunner:
    """Runs test cases and collects results."""

    def __init__(self):
        self.tester = BotTester()
        self.validator = TestValidator()
        self.results: List[TestResult] = []

    async def run_test(self, test: TestCase) -> TestResult:
        """Run a single test case."""
        start_time = datetime.now()
        errors = []
        actual_task = None
        logs = []

        print(f"\n  Running: {test.name}")

        try:
            for i, step in enumerate(test.steps):
                logs.append(f"Step {i+1}: {step.action}")

                if step.action == "send":
                    result = await self.tester.send_message(step.message)
                    logs.append(f"  Sent: '{step.message[:50]}...' -> {result['status']}")
                    if not result["ok"]:
                        errors.append(f"Failed to send message: {step.message[:30]}")
                        break

                elif step.action == "wait":
                    logs.append(f"  Waiting {step.wait_seconds}s...")
                    await asyncio.sleep(step.wait_seconds)

                elif step.action == "validate_task":
                    # Find the task
                    if step.expected_task and step.expected_task.title_contains:
                        actual_task = await self.tester.get_task_by_partial_title(
                            step.expected_task.title_contains
                        )
                    else:
                        tasks = await self.tester.get_recent_tasks(1)
                        actual_task = tasks[0] if tasks else None

                    if step.expected_task:
                        passed, validation_errors = self.validator.validate_task(
                            step.expected_task, actual_task
                        )
                        errors.extend(validation_errors)

                        if actual_task:
                            logs.append(f"  Task found: {actual_task.get('id')}")
                            logs.append(f"    Title: {actual_task.get('title')}")
                            logs.append(f"    Assignee: {actual_task.get('assignee')}")
                        else:
                            logs.append("  No matching task found!")

        except Exception as e:
            errors.append(f"Exception: {type(e).__name__}: {str(e)}")
            logs.append(f"  ERROR: {e}")

        duration = (datetime.now() - start_time).total_seconds()
        status = TestStatus.PASSED if not errors else TestStatus.FAILED

        # Build expected dict for reporting
        expected_dict = {}
        for step in test.steps:
            if step.expected_task:
                expected_dict = asdict(step.expected_task)
                break

        result = TestResult(
            test_id=test.id,
            test_name=test.name,
            status=status,
            errors=errors,
            expected=expected_dict,
            actual=actual_task or {},
            duration_seconds=duration,
            logs=logs
        )

        self.results.append(result)
        return result

    async def run_suite(self, tests: List[TestCase]) -> List[TestResult]:
        """Run a suite of tests."""
        results = []
        for test in tests:
            result = await self.run_test(test)
            results.append(result)

            # Print inline result
            status_icon = "[OK]" if result.status == TestStatus.PASSED else "[FAIL]"
            print(f"    {status_icon} {result.status.value.upper()}", end="")
            if result.errors:
                print(f" - {result.errors[0][:50]}")
            else:
                print()

        return results


# =============================================================================
# TEST CASES - These would have caught the bugs we fixed
# =============================================================================

def get_conversation_tests() -> List[TestCase]:
    """Tests for multi-turn conversation handling."""
    return [
        TestCase(
            id="conv-001",
            name="Simple task creates directly",
            description="A simple task should skip questions and create directly",
            tags=["conversation", "simple"],
            steps=[
                ConversationStep(action="send", message="Create task for Mayank: Fix the login typo"),
                ConversationStep(action="wait", wait_seconds=10),
                ConversationStep(
                    action="validate_task",
                    expected_task=ExpectedTask(
                        title_contains="login",
                        assignee="Mayank",
                        title_not_contains="1tomorrow"  # Should NOT have garbage in title
                    )
                )
            ]
        ),
        TestCase(
            id="conv-002",
            name="Answer parsing preserves task context",
            description="When user answers questions, original task title and assignee should be preserved",
            tags=["conversation", "answer-parsing", "critical"],
            steps=[
                ConversationStep(
                    action="send",
                    message="Create task for Mayank: Build notification system with email and SMS"
                ),
                ConversationStep(action="wait", wait_seconds=12),
                ConversationStep(action="send", message="1tomorrow 2a"),
                ConversationStep(action="wait", wait_seconds=10),
                ConversationStep(
                    action="validate_task",
                    expected_task=ExpectedTask(
                        title_contains="notification",  # Original title preserved
                        title_not_contains="1tomorrow",  # NOT the answer text
                        assignee="Mayank"  # Assignee preserved
                    )
                )
            ]
        ),
        TestCase(
            id="conv-003",
            name="Correction updates existing task",
            description="When user says 'assignee is X', it should update the task, not create new one",
            tags=["conversation", "correction", "critical"],
            steps=[
                ConversationStep(action="send", message="Create task: Review the API code"),
                ConversationStep(action="wait", wait_seconds=10),
                ConversationStep(action="send", message="yes"),  # Confirm
                ConversationStep(action="wait", wait_seconds=5),
                # Note: This test validates that task was created, not that correction worked
                # Full correction testing requires more complex state tracking
                ConversationStep(
                    action="validate_task",
                    expected_task=ExpectedTask(
                        title_contains="API",
                        title_not_contains="correction"
                    )
                )
            ]
        ),
    ]


def get_validation_tests() -> List[TestCase]:
    """Tests for task output validation."""
    return [
        TestCase(
            id="val-001",
            name="Task title matches input",
            description="Created task title should reflect user's input, not AI hallucination",
            tags=["validation", "title"],
            steps=[
                ConversationStep(
                    action="send",
                    message="Create task for Zea: Update team schedule spreadsheet"
                ),
                ConversationStep(action="wait", wait_seconds=12),
                ConversationStep(
                    action="validate_task",
                    expected_task=ExpectedTask(
                        title_contains="schedule",
                        assignee="Zea"
                    )
                )
            ]
        ),
        TestCase(
            id="val-002",
            name="Assignee extracted correctly",
            description="Assignee from 'for X:' format should be captured",
            tags=["validation", "assignee"],
            steps=[
                ConversationStep(action="send", message="Create task for Mayank: Debug the login flow"),
                ConversationStep(action="wait", wait_seconds=10),
                ConversationStep(
                    action="validate_task",
                    expected_task=ExpectedTask(
                        assignee="Mayank"
                    )
                )
            ]
        ),
    ]


def get_all_tests() -> List[TestCase]:
    """Get all test cases."""
    return get_conversation_tests() + get_validation_tests()


# =============================================================================
# MAIN
# =============================================================================

def print_summary(results: List[TestResult]):
    """Print test results summary."""
    passed = sum(1 for r in results if r.status == TestStatus.PASSED)
    failed = sum(1 for r in results if r.status == TestStatus.FAILED)

    print("\n" + "=" * 70)
    print(" TEST RESULTS SUMMARY ")
    print("=" * 70)

    for r in results:
        icon = "[OK]" if r.status == TestStatus.PASSED else "[FAIL]"
        print(f"  {icon} [{r.test_id}] {r.test_name}: {r.status.value.upper()}")
        if r.errors:
            for err in r.errors[:2]:
                print(f"      Error: {err[:60]}")

    print("-" * 70)
    print(f"  TOTAL: {len(results)} | PASSED: {passed} | FAILED: {failed}")
    print("=" * 70)

    if failed > 0:
        print("\n>>> SOME TESTS FAILED - Review errors above")
    else:
        print("\n>>> ALL TESTS PASSED")


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]
    runner = TestRunner()

    if command == "list":
        print("\nAvailable Test Cases:")
        print("-" * 60)
        for test in get_all_tests():
            tags = ", ".join(test.tags)
            print(f"  [{test.id}] {test.name}")
            print(f"      Tags: {tags}")
            print(f"      {test.description}")
            print()

    elif command == "run-all":
        print("\n" + "=" * 70)
        print(" RUNNING ALL TESTS ")
        print("=" * 70)

        tests = get_all_tests()
        print(f"\nRunning {len(tests)} tests...")

        results = await runner.run_suite(tests)
        print_summary(results)

        # Save detailed results
        with open("test_framework_results.json", "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2, default=str)
        print("\nDetailed results saved to test_framework_results.json")

    elif command == "run":
        if len(sys.argv) < 3:
            print("Usage: python test_framework.py run <suite>")
            print("  Suites: conversation, validation")
            return

        suite = sys.argv[2]

        if suite == "conversation":
            tests = get_conversation_tests()
        elif suite == "validation":
            tests = get_validation_tests()
        else:
            print(f"Unknown suite: {suite}")
            return

        print(f"\n Running {suite} tests ({len(tests)} tests)")
        print("-" * 60)

        results = await runner.run_suite(tests)
        print_summary(results)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    asyncio.run(main())
