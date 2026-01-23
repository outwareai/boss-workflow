#!/usr/bin/env python3
"""
REAL CONVERSATION TESTER

This script has an actual back-and-forth conversation with the bot:
1. Send a task message
2. Read bot's response (questions or preview)
3. Answer the questions appropriately
4. Read the preview
5. Confirm or correct
6. Validate final task

Usage:
    python test_conversation.py              # Run default conversation test
    python test_conversation.py --verbose    # Show all details
    python test_conversation.py --custom "Your message"  # Custom test
"""

import os
import sys
import re
import json
import asyncio
import aiohttp
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

RAILWAY_URL = "https://boss-workflow-production.up.railway.app"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOSS_CHAT_ID = os.getenv("TELEGRAM_BOSS_CHAT_ID")

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


def log(msg: str, level: str = "info"):
    """Print log message."""
    if level == "debug" and not VERBOSE:
        return
    prefix = {"info": "[*]", "success": "[+]", "error": "[!]", "debug": "[.]"}.get(level, "[*]")
    print(f"{prefix} {msg}")


@dataclass
class BotResponse:
    """Parsed bot response."""
    raw_text: str
    is_question: bool = False
    is_preview: bool = False
    questions: List[str] = None
    preview_title: str = None
    preview_assignee: str = None
    preview_deadline: str = None
    options: List[List[str]] = None  # Options for each question

    def __post_init__(self):
        if self.questions is None:
            self.questions = []
        if self.options is None:
            self.options = []


class ConversationTester:
    """Has real conversations with the bot."""

    def __init__(self):
        self.message_counter = int(datetime.now().timestamp()) % 100000
        self.conversation_history: List[Dict] = []
        self.test_start_time: datetime = None

    async def clear_conversation(self) -> bool:
        """Clear any active conversation by sending 'cancel'."""
        log("Clearing any active conversation...", "debug")
        await self.send_message("cancel")
        await asyncio.sleep(2)
        return True

    async def send_message(self, text: str) -> bool:
        """Send a message to the bot."""
        self.message_counter += 1
        self.conversation_history.append({"role": "user", "message": text, "time": datetime.now()})

        payload = {
            "update_id": int(datetime.now().timestamp()),
            "message": {
                "message_id": self.message_counter,
                "from": {"id": int(TELEGRAM_BOSS_CHAT_ID), "is_bot": False, "first_name": "Tester"},
                "chat": {"id": int(TELEGRAM_BOSS_CHAT_ID), "type": "private"},
                "date": int(datetime.now().timestamp()),
                "text": text
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{RAILWAY_URL}/webhook/telegram", json=payload) as resp:
                return resp.status == 200

    def read_bot_responses(self, lines: int = 100) -> List[str]:
        """Read recent bot responses from Railway logs."""
        try:
            result = subprocess.run(
                "railway logs -s boss-workflow",
                capture_output=True, text=True, timeout=30, shell=True
            )
            logs = result.stdout.strip().split('\n')
            return logs[-lines:] if len(logs) > lines else logs
        except Exception as e:
            log(f"Error reading logs: {e}", "error")
            return []

    def parse_bot_response(self, logs: List[str]) -> BotResponse:
        """Parse bot response from logs to understand what it said."""
        response = BotResponse(raw_text="\n".join(logs))

        log_text = "\n".join(logs)

        # Check if bot asked questions
        if "Quick questions:" in log_text or "questions to ensure" in log_text:
            response.is_question = True

            # Extract question patterns
            question_pattern = r'(\d+)\.\s+([^\n]+)'
            matches = re.findall(question_pattern, log_text)
            response.questions = [m[1] for m in matches]

            # Extract options for each question
            option_pattern = r'([A-D]\))\s+([^\n]+)'
            options = re.findall(option_pattern, log_text)
            if options:
                response.options = [[opt[1] for opt in options]]

            log(f"Bot asked {len(response.questions)} questions", "debug")

        # Check if bot showed a preview
        if "Task Preview" in log_text or "Title:" in log_text:
            response.is_preview = True

            # Extract title
            title_match = re.search(r'Title[:\s]+([^\n]+)', log_text)
            if title_match:
                response.preview_title = title_match.group(1).strip()

            # Extract assignee
            assignee_match = re.search(r'Assignee[:\s]+([^\n]+)', log_text)
            if assignee_match:
                response.preview_assignee = assignee_match.group(1).strip()

            # Extract deadline
            deadline_match = re.search(r'Deadline[:\s]+([^\n]+)', log_text)
            if deadline_match:
                response.preview_deadline = deadline_match.group(1).strip()

            log(f"Bot showed preview: {response.preview_title}", "debug")

        return response

    async def get_recent_task(self, title_contains: str = None, created_after: datetime = None) -> Optional[Dict]:
        """Get the most recent task from database, optionally filtered by creation time."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{RAILWAY_URL}/api/db/tasks?limit=10") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tasks = data.get("tasks", [])

                    # Filter by creation time if specified
                    if created_after:
                        filtered = []
                        for task in tasks:
                            created_str = task.get("created_at", "")
                            if created_str:
                                try:
                                    # Parse ISO format: 2026-01-23T10:29:53.115934
                                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                                    if created.replace(tzinfo=None) > created_after:
                                        filtered.append(task)
                                except ValueError:
                                    pass
                        tasks = filtered

                    if title_contains:
                        for task in tasks:
                            if title_contains.lower() in task.get("title", "").lower():
                                return task
                    return tasks[0] if tasks else None
        return None

    async def have_conversation(
        self,
        initial_message: str,
        expected_title: str,
        expected_assignee: str = None,
        answers: Dict[str, str] = None
    ) -> Tuple[bool, List[str]]:
        """
        Have a complete conversation with the bot.

        Args:
            initial_message: The task to create
            expected_title: What the task title should contain
            expected_assignee: Expected assignee
            answers: Pre-defined answers for questions (e.g., {"deadline": "tomorrow", "priority": "high"})

        Returns:
            (success, errors)
        """
        errors = []
        answers = answers or {}

        print("\n" + "=" * 60)
        print(" CONVERSATION TEST ")
        print("=" * 60)

        # Step 0: Clear any previous conversation state
        await self.clear_conversation()
        self.test_start_time = datetime.utcnow()
        log(f"Test started at: {self.test_start_time.isoformat()}", "debug")

        # Step 1: Send initial message
        log(f"USER: {initial_message}")
        if not await self.send_message(initial_message):
            return False, ["Failed to send initial message"]

        await asyncio.sleep(8)  # Wait for bot to process

        # Step 2: Read bot's response
        logs = self.read_bot_responses()
        response = self.parse_bot_response(logs)

        # Step 3: Handle based on response type
        if response.is_question:
            log(f"BOT: Asked {len(response.questions)} questions")
            for i, q in enumerate(response.questions):
                log(f"  Q{i+1}: {q[:50]}...", "debug")

            # Generate answers
            answer_text = self._generate_answers(response.questions, answers)
            log(f"USER: {answer_text}")

            if not await self.send_message(answer_text):
                return False, ["Failed to send answers"]

            await asyncio.sleep(8)  # Wait for bot to process answers

            # Read new response
            logs = self.read_bot_responses()
            response = self.parse_bot_response(logs)

        if response.is_preview:
            log(f"BOT: Showed preview")
            log(f"  Title: {response.preview_title}", "debug")
            log(f"  Assignee: {response.preview_assignee}", "debug")

            # Check preview for issues BEFORE confirming
            if response.preview_title:
                # Check for garbage in title
                garbage_indicators = ["1tomorrow", "2a", "1.", "2.", "skip"]
                for garbage in garbage_indicators:
                    if garbage.lower() in response.preview_title.lower():
                        errors.append(f"GARBAGE IN TITLE: '{response.preview_title}' contains '{garbage}'")

                # Check title matches expectation
                if expected_title.lower() not in response.preview_title.lower():
                    errors.append(f"TITLE MISMATCH: Expected '{expected_title}' in '{response.preview_title}'")

            # Check assignee
            if expected_assignee and response.preview_assignee:
                if expected_assignee.lower() not in response.preview_assignee.lower():
                    if response.preview_assignee.lower() not in ["none", "unassigned", ""]:
                        errors.append(f"ASSIGNEE MISMATCH: Expected '{expected_assignee}' but got '{response.preview_assignee}'")

            # If preview looks good, confirm
            if not errors:
                log("USER: yes (confirming)")
                if not await self.send_message("yes"):
                    return False, ["Failed to send confirmation"]

                await asyncio.sleep(5)
        else:
            log("BOT: No clear preview detected in response", "debug")

        # Step 4: Validate final task in database
        log("Checking database for created task...")
        await asyncio.sleep(3)

        task = await self.get_recent_task(expected_title, created_after=self.test_start_time)

        if not task:
            errors.append(f"NO TASK FOUND: Expected task containing '{expected_title}'")
        else:
            log(f"Found task: {task.get('id')}")
            log(f"  Title: {task.get('title')}", "debug")
            log(f"  Assignee: {task.get('assignee')}", "debug")

            # Validate task
            actual_title = task.get("title", "")
            actual_assignee = task.get("assignee") or ""

            # Check for garbage
            for garbage in ["1tomorrow", "2a", "1.", "2."]:
                if garbage.lower() in actual_title.lower():
                    errors.append(f"GARBAGE IN FINAL TASK: '{actual_title}' contains '{garbage}'")

            # Check assignee
            if expected_assignee:
                if expected_assignee.lower() != actual_assignee.lower():
                    errors.append(f"FINAL ASSIGNEE WRONG: Expected '{expected_assignee}' but got '{actual_assignee}'")

        # Print result
        print("-" * 60)
        if errors:
            log("RESULT: FAILED", "error")
            for err in errors:
                log(f"  - {err}", "error")
        else:
            log("RESULT: PASSED", "success")

        return len(errors) == 0, errors

    def _generate_answers(self, questions: List[str], predefined: Dict[str, str]) -> str:
        """Generate appropriate answers for questions."""
        answers = []

        for i, question in enumerate(questions, 1):
            q_lower = question.lower()

            # Match question to predefined answer
            if "deadline" in q_lower or "when" in q_lower or "timeline" in q_lower:
                answer = predefined.get("deadline", "next week")
            elif "priority" in q_lower or "urgent" in q_lower:
                answer = predefined.get("priority", "medium")
            elif "who" in q_lower or "assign" in q_lower:
                answer = predefined.get("assignee", "skip")
            elif "constraint" in q_lower or "technical" in q_lower:
                answer = predefined.get("constraints", "no specific constraints")
            else:
                answer = predefined.get("default", "skip")

            # Format as numbered answer
            answers.append(f"{i}{answer}")

        return " ".join(answers)


async def run_test_suite():
    """Run a suite of conversation tests."""
    tester = ConversationTester()

    test_cases = [
        {
            "name": "Simple task with assignee",
            "message": "Create task for Mayank: Fix the login page typo",
            "expected_title": "login",
            "expected_assignee": "Mayank",
            "answers": {}
        },
        {
            "name": "Complex task with questions",
            "message": "Create task for Mayank: Build a notification system with email and SMS",
            "expected_title": "notification",
            "expected_assignee": "Mayank",
            "answers": {"deadline": "next week", "constraints": "no constraints"}
        },
    ]

    results = []

    for tc in test_cases:
        print(f"\n\n{'#' * 60}")
        print(f"# TEST: {tc['name']}")
        print(f"{'#' * 60}")

        success, errors = await tester.have_conversation(
            initial_message=tc["message"],
            expected_title=tc["expected_title"],
            expected_assignee=tc.get("expected_assignee"),
            answers=tc.get("answers", {})
        )

        results.append({
            "name": tc["name"],
            "passed": success,
            "errors": errors
        })

        # Wait between tests
        await asyncio.sleep(5)

    # Print summary
    print("\n\n" + "=" * 60)
    print(" TEST SUMMARY ")
    print("=" * 60)

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    for r in results:
        status = "[PASS]" if r["passed"] else "[FAIL]"
        print(f"  {status} {r['name']}")
        if r["errors"]:
            for err in r["errors"][:2]:
                print(f"         - {err[:50]}")

    print("-" * 60)
    print(f"  TOTAL: {len(results)} | PASSED: {passed} | FAILED: {failed}")
    print("=" * 60)

    # Save results
    with open("conversation_test_results.json", "w") as f:
        json.dump(results, f, indent=2)

    return failed == 0


async def run_single_test(message: str):
    """Run a single custom test."""
    tester = ConversationTester()

    # Extract expected values from message
    expected_title = message.split(":")[-1].strip().split()[0] if ":" in message else message.split()[0]

    assignee_match = re.search(r'for (\w+):', message, re.IGNORECASE)
    expected_assignee = assignee_match.group(1) if assignee_match else None

    success, errors = await tester.have_conversation(
        initial_message=message,
        expected_title=expected_title,
        expected_assignee=expected_assignee,
        answers={"deadline": "next week", "priority": "medium"}
    )

    return success


async def main():
    if "--custom" in sys.argv:
        idx = sys.argv.index("--custom")
        if idx + 1 < len(sys.argv):
            message = sys.argv[idx + 1]
            await run_single_test(message)
        else:
            print("Usage: python test_conversation.py --custom \"Your message\"")
    else:
        await run_test_suite()


if __name__ == "__main__":
    asyncio.run(main())
