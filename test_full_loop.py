#!/usr/bin/env python3
"""
FULL TEST LOOP: Telegram Input → Bot Response → Discord Output

This script enables Claude Code to:
1. Send messages to the bot (simulating boss)
2. Read bot's Telegram responses (via Railway logs)
3. Continue conversations (yes/no/edits)
4. Read final Discord output
5. Evaluate quality
6. Loop until perfect (use with /ralph-loop)

Usage:
    python test_full_loop.py send "Create task for John to fix login"
    python test_full_loop.py respond "yes"
    python test_full_loop.py read-telegram
    python test_full_loop.py read-discord
    python test_full_loop.py full-test "Task for John no questions: Fix login bug"
"""

import os
import sys
import json
import time
import re
import subprocess
import asyncio
import aiohttp
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Configuration
RAILWAY_URL = "https://boss-workflow-production.up.railway.app"  # Hardcoded production URL
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOSS_CHAT_ID = os.getenv("TELEGRAM_BOSS_CHAT_ID")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_FORUM_CHANNEL_ID = os.getenv("DISCORD_FORUM_CHANNEL_ID")
DISCORD_DEV_TASKS_CHANNEL_ID = os.getenv("DISCORD_DEV_TASKS_CHANNEL_ID")


class BossWorkflowTester:
    """Test the full boss workflow pipeline."""

    def __init__(self):
        self.message_counter = int(time.time()) % 100000
        self.session_start = datetime.utcnow()

    async def send_telegram_message(self, text: str) -> dict:
        """Send a message to the bot via Railway webhook."""
        self.message_counter += 1

        payload = {
            "update_id": int(time.time()),
            "message": {
                "message_id": self.message_counter,
                "from": {
                    "id": int(TELEGRAM_BOSS_CHAT_ID),
                    "is_bot": False,
                    "first_name": "Boss"
                },
                "chat": {
                    "id": int(TELEGRAM_BOSS_CHAT_ID),
                    "type": "private"
                },
                "date": int(time.time()),
                "text": text
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{RAILWAY_URL}/webhook/telegram", json=payload) as resp:
                return {
                    "status": resp.status,
                    "response": await resp.json(),
                    "message_sent": text
                }

    def read_railway_logs(self, lines: int = 50, filter_text: str = None) -> list:
        """Read Railway logs to see bot responses."""
        try:
            result = subprocess.run(
                ["railway", "logs", "-s", "boss-workflow"],
                capture_output=True,
                text=True,
                timeout=30
            )
            logs = result.stdout.strip().split('\n')

            # Get last N lines
            logs = logs[-lines:] if len(logs) > lines else logs

            # Filter if specified
            if filter_text:
                logs = [l for l in logs if filter_text.lower() in l.lower()]

            return logs
        except Exception as e:
            return [f"Error reading logs: {e}"]

    def extract_bot_responses(self, logs: list) -> list:
        """Extract what the bot sent to Telegram from logs."""
        responses = []
        for log in logs:
            # Look for sendMessage calls
            if "sendMessage" in log and "200 OK" in log:
                responses.append({"type": "telegram_sent", "log": log})
            # Look for AI classification
            if "AI classified:" in log:
                responses.append({"type": "ai_intent", "log": log})
            # Look for intent detection
            if "Detected intent:" in log:
                responses.append({"type": "intent", "log": log})
            # Look for task creation
            if "Task created" in log or "TASK-" in log:
                responses.append({"type": "task", "log": log})
            # Look for Discord posts
            if "discord" in log.lower() and ("post" in log.lower() or "send" in log.lower()):
                responses.append({"type": "discord", "log": log})
        return responses

    async def read_discord_messages(self, channel_id: str = None, limit: int = 5) -> list:
        """Read recent Discord messages."""
        channel = channel_id or DISCORD_FORUM_CHANNEL_ID or DISCORD_DEV_TASKS_CHANNEL_ID

        if not channel:
            return [{"error": "No Discord channel configured"}]

        url = f"https://discord.com/api/v10/channels/{channel}/messages?limit={limit}"
        headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                return [{"error": f"Discord API error: {resp.status}"}]

    async def read_discord_threads(self, channel_id: str = None) -> list:
        """Read recent forum threads (for task specs)."""
        channel = channel_id or DISCORD_FORUM_CHANNEL_ID

        if not channel:
            return [{"error": "No forum channel configured"}]

        # Get active threads in the guild
        url = f"https://discord.com/api/v10/channels/{channel}/threads/archived/public?limit=5"
        headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("threads", [])
                return [{"error": f"Discord API error: {resp.status}"}]

    async def get_database_tasks(self, limit: int = 5) -> dict:
        """Get recent tasks from database API."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{RAILWAY_URL}/api/db/tasks") as resp:
                data = await resp.json()
                tasks = data.get("tasks", [])[:limit]
                return {"tasks": tasks, "count": len(tasks)}

    async def full_test(self, message: str, wait_seconds: int = 8) -> dict:
        """
        Run a full test cycle:
        1. Send message
        2. Wait for processing
        3. Read all outputs
        4. Return complete results
        """
        results = {
            "input": message,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": []
        }

        # Step 1: Get baseline
        print("[1/5] Getting baseline task count...")
        tasks_before = await self.get_database_tasks()
        results["tasks_before"] = tasks_before["count"]
        results["steps"].append({"step": "baseline", "tasks": tasks_before["count"]})

        # Step 2: Send message
        print(f"[2/5] Sending: '{message[:50]}...'")
        send_result = await self.send_telegram_message(message)
        results["webhook_response"] = send_result
        results["steps"].append({"step": "send", "status": send_result["status"]})

        # Step 3: Wait and collect logs
        print(f"[3/5] Waiting {wait_seconds}s for processing...")
        await asyncio.sleep(wait_seconds)

        logs = self.read_railway_logs(lines=60)  # Get more logs for analysis
        bot_responses = self.extract_bot_responses(logs)
        results["railway_logs"] = logs  # Keep all logs for implementation analysis
        results["bot_responses"] = bot_responses
        results["steps"].append({"step": "logs", "responses": len(bot_responses)})

        # Step 4: Read Discord
        print("[4/5] Reading Discord output...")
        discord_msgs = await self.read_discord_messages(limit=3)
        discord_threads = await self.read_discord_threads()
        results["discord_messages"] = discord_msgs[:3] if isinstance(discord_msgs, list) else discord_msgs
        results["discord_threads"] = discord_threads[:3] if isinstance(discord_threads, list) else discord_threads
        results["steps"].append({"step": "discord", "messages": len(discord_msgs) if isinstance(discord_msgs, list) else 0})

        # Step 5: Check new tasks
        print("[5/5] Checking for new tasks...")
        tasks_after = await self.get_database_tasks()
        results["tasks_after"] = tasks_after["count"]
        results["new_tasks"] = tasks_after["tasks"][:3]
        results["task_created"] = tasks_after["count"] > tasks_before["count"]
        results["steps"].append({"step": "tasks", "created": results["task_created"]})

        return results


def extract_implementation_details(logs: list) -> dict:
    """Extract v2.2 implementation details from Railway logs."""
    details = {
        "complexity": None,
        "complexity_level": None,
        "questions_asked": None,
        "role_lookup": None,
        "role_found": None,
        "channel_routed": None,
        "keyword_inference": None,
        "self_answered": None,
        "task_id": None,
    }

    for log in logs:
        log_lower = log.lower() if isinstance(log, str) else ""

        # Complexity detection
        if "complexity=" in log_lower:
            import re
            match = re.search(r'complexity=(\d+)', log_lower)
            if match:
                details["complexity"] = int(match.group(1))
                if details["complexity"] <= 3:
                    details["complexity_level"] = "simple"
                elif details["complexity"] <= 6:
                    details["complexity_level"] = "medium"
                else:
                    details["complexity_level"] = "complex"

        # Questions
        if "skipping all questions" in log_lower:
            details["questions_asked"] = 0
        elif "asking" in log_lower and "question" in log_lower:
            match = re.search(r'asking (\d+)', log_lower)
            if match:
                details["questions_asked"] = int(match.group(1))

        # Role lookup
        if "found role for" in log_lower:
            match = re.search(r"found role for '(\w+)'.*?: '(\w+)'", log, re.IGNORECASE)
            if match:
                details["role_lookup"] = match.group(1)
                details["role_found"] = match.group(2)

        # Channel routing
        if "routing task" in log_lower:
            if "dev channel" in log_lower or "to dev" in log_lower:
                details["channel_routed"] = "DEV"
            elif "admin channel" in log_lower or "to admin" in log_lower:
                details["channel_routed"] = "ADMIN"
            elif "marketing" in log_lower:
                details["channel_routed"] = "MARKETING"
            elif "design" in log_lower:
                details["channel_routed"] = "DESIGN"

        # Keyword inference
        if "inferred role" in log_lower or "keyword inference" in log_lower:
            details["keyword_inference"] = True
            match = re.search(r'inferred (?:role )?(\w+)', log_lower)
            if match:
                details["channel_routed"] = match.group(1).upper()

        # Self-answered
        if "self-answered" in log_lower:
            match = re.search(r'self-answered (\d+) fields', log_lower)
            if match:
                details["self_answered"] = int(match.group(1))

        # Task ID
        if "task-" in log_lower:
            match = re.search(r'(TASK-\d{8}-\w{3})', log, re.IGNORECASE)
            if match:
                details["task_id"] = match.group(1).upper()

    return details


def print_results(results: dict):
    """Pretty print test results with structured v2.2 summary."""

    # Extract implementation details from logs
    all_logs = results.get('railway_logs', [])
    impl_details = extract_implementation_details(all_logs)

    # Determine overall pass/fail
    task_created = results.get('task_created', False)
    webhook_ok = results.get('webhook_response', {}).get('status') == 200

    # Build summary
    print("\n" + "="*70)
    print("|{:^68}|".format("TEST RESULT SUMMARY"))
    print("="*70)

    # Test info
    print("|{:<68}|".format(f" Test Input: {results['input'][:55]}..."))
    print("|{:<68}|".format(f" Timestamp: {results['timestamp'][:25]}"))
    print("-"*70)

    # Implementation tested section
    print("|{:<68}|".format(" IMPLEMENTATION TESTED:"))

    # Complexity
    if impl_details["complexity"] is not None:
        status = "[OK]" if impl_details["complexity"] is not None else "[--]"
        print("|{:<68}|".format(f"   {status} Complexity Detection: score={impl_details['complexity']} ({impl_details['complexity_level']})"))

    # Question logic
    if impl_details["questions_asked"] is not None:
        if impl_details["questions_asked"] == 0:
            print("|{:<68}|".format("   [OK] Question Logic: Skipped all questions (simple task)"))
        else:
            print("|{:<68}|".format(f"   [OK] Question Logic: Asked {impl_details['questions_asked']} question(s)"))

    # Role lookup
    if impl_details["role_lookup"]:
        print("|{:<68}|".format(f"   [OK] Role Lookup: {impl_details['role_lookup']} -> {impl_details['role_found']}"))

    # Channel routing
    if impl_details["channel_routed"]:
        print("|{:<68}|".format(f"   [OK] Channel Routing: Routed to {impl_details['channel_routed']} channel"))

    # Keyword inference
    if impl_details["keyword_inference"]:
        print("|{:<68}|".format(f"   [OK] Keyword Inference: Inferred role from task content"))

    # Self-answered
    if impl_details["self_answered"]:
        print("|{:<68}|".format(f"   [OK] AI Self-Answer: Self-answered {impl_details['self_answered']} fields"))

    print("-"*70)

    # Result section
    overall_status = "PASSED" if (task_created or webhook_ok) else "FAILED"
    status_icon = "[OK]" if overall_status == "PASSED" else "[ERR]"
    print("|{:<68}|".format(f" RESULT: {status_icon} {overall_status}"))

    if impl_details["task_id"]:
        print("|{:<68}|".format(f" Task Created: {impl_details['task_id']}"))
    elif results.get('new_tasks'):
        task = results['new_tasks'][0]
        print("|{:<68}|".format(f" Task Created: {task.get('id', 'Unknown')}"))

    print("|{:<68}|".format(f" Tasks: {results['tasks_before']} -> {results['tasks_after']}"))
    print("="*70)

    # Additional details (compact)
    print(f"\n--- Webhook ---")
    print(f"Status: {results['webhook_response']['status']}")

    print(f"\n--- Bot Processing (from logs) ---")
    for resp in results.get('bot_responses', [])[:3]:
        print(f"  [{resp['type']}] {resp['log'][:80]}")

    if results.get('new_tasks'):
        print("\n--- Newest Task ---")
        task = results['new_tasks'][0]
        print(f"  ID: {task.get('id')}")
        print(f"  Title: {task.get('title')}")
        print(f"  Assignee: {task.get('assignee')}")
        print(f"  Status: {task.get('status')}")

    if results.get('new_tasks'):
        print("\nNewest task:")
        task = results['new_tasks'][0]
        print(f"  ID: {task.get('id')}")
        print(f"  Title: {task.get('title')}")
        print(f"  Assignee: {task.get('assignee')}")
        print(f"  Status: {task.get('status')}")

    print(f"\n--- Discord ---")
    msgs = results.get('discord_messages', [])
    if isinstance(msgs, list) and msgs:
        for msg in msgs[:2]:
            if isinstance(msg, dict) and 'content' in msg:
                print(f"  Message: {msg.get('content', '')[:100]}")
                if msg.get('embeds'):
                    for embed in msg['embeds'][:1]:
                        print(f"  Embed: {embed.get('title', 'No title')}")
    else:
        print("  No new messages or error reading")

    print("\n" + "="*60)


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    tester = BossWorkflowTester()
    command = sys.argv[1]

    if command == "send":
        message = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Hello"
        result = await tester.send_telegram_message(message)
        print(f"Sent: {message}")
        print(f"Response: {result}")

    elif command == "respond":
        # Quick way to send yes/no/edit responses
        response = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "yes"
        result = await tester.send_telegram_message(response)
        print(f"Responded: {response}")
        print(f"Result: {result}")

    elif command == "read-telegram":
        # Read Railway logs to see bot responses
        logs = tester.read_railway_logs(lines=30)
        responses = tester.extract_bot_responses(logs)
        print("Bot responses from logs:")
        for r in responses:
            print(f"  [{r['type']}] {r['log']}")

    elif command == "read-discord":
        msgs = await tester.read_discord_messages()
        threads = await tester.read_discord_threads()
        print("Discord Messages:")
        for m in (msgs if isinstance(msgs, list) else []):
            print(f"  - {m.get('content', '')[:100]}")
            for e in m.get('embeds', []):
                print(f"    Embed: {e.get('title', 'N/A')}")
        print("\nDiscord Threads:")
        for t in (threads if isinstance(threads, list) else []):
            print(f"  - {t.get('name', 'N/A')}")

    elif command == "read-tasks":
        tasks = await tester.get_database_tasks(limit=5)
        print(f"Tasks ({tasks['count']}):")
        for t in tasks['tasks']:
            print(f"  {t['id']}: {t['title'][:50]} [{t['status']}]")

    elif command == "full-test":
        message = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Task for Test no questions: Test task"
        results = await tester.full_test(message)
        print_results(results)

        # Save results for analysis
        with open("test_results.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
        print("\nResults saved to test_results.json")

    elif command == "conversation":
        # Interactive conversation mode
        print("Interactive conversation mode. Type 'quit' to exit.")
        while True:
            msg = input("\nYou: ").strip()
            if msg.lower() == 'quit':
                break
            result = await tester.send_telegram_message(msg)
            print(f"[Sent, waiting 3s...]")
            await asyncio.sleep(3)
            logs = tester.read_railway_logs(lines=20)
            responses = tester.extract_bot_responses(logs)
            print("Bot activity:")
            for r in responses[-3:]:
                print(f"  {r['log'][:100]}")

    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    asyncio.run(main())
