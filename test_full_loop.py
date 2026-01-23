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

        logs = self.read_railway_logs(lines=30)
        bot_responses = self.extract_bot_responses(logs)
        results["railway_logs"] = logs[-10:]  # Last 10 lines
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


def print_results(results: dict):
    """Pretty print test results."""
    print("\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)

    print(f"\nInput: {results['input'][:100]}")
    print(f"Timestamp: {results['timestamp']}")

    print(f"\n--- Webhook ---")
    print(f"Status: {results['webhook_response']['status']}")

    print(f"\n--- Bot Processing (from logs) ---")
    for resp in results.get('bot_responses', []):
        print(f"  [{resp['type']}] {resp['log'][:100]}")

    print(f"\n--- Tasks ---")
    print(f"Before: {results['tasks_before']}")
    print(f"After: {results['tasks_after']}")
    print(f"New task created: {results['task_created']}")

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
