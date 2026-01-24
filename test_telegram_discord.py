#!/usr/bin/env python3
"""
Test Script: Send Telegram Message → Read Discord Response

This script tests the full boss-workflow pipeline:
1. Sends a simulated Telegram message to the Railway webhook
2. Waits for processing
3. Reads recent Discord messages to verify the response

Usage:
    python test_telegram_discord.py "Your test message here"
    python test_telegram_discord.py "/status"
    python test_telegram_discord.py "Create a task for John to fix the login bug"
"""

import os
import sys
import json
import time
import asyncio
import aiohttp
from datetime import datetime, timedelta, UTC
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
RAILWAY_URL = "https://boss-workflow-production.up.railway.app"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOSS_CHAT_ID = os.getenv("TELEGRAM_BOSS_CHAT_ID")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_FORUM_CHANNEL_ID") or os.getenv("DISCORD_DEV_TASKS_CHANNEL_ID")

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.HEADER}{text.center(60)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.END}\n")


def print_step(step_num, text):
    print(f"{Colors.CYAN}[Step {step_num}]{Colors.END} {text}")


def print_success(text):
    print(f"{Colors.GREEN}[OK] {text}{Colors.END}")


def print_error(text):
    print(f"{Colors.RED}[ERR] {text}{Colors.END}")


def print_info(text):
    print(f"{Colors.YELLOW}[INFO] {text}{Colors.END}")


async def send_telegram_webhook(message: str) -> dict:
    """Send a simulated Telegram message to the Railway webhook."""

    webhook_url = f"{RAILWAY_URL}/webhook/telegram"

    # Simulate Telegram webhook payload
    payload = {
        "update_id": int(time.time()),
        "message": {
            "message_id": int(time.time()) % 100000,
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
            "text": message
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(webhook_url, json=payload) as response:
            result = await response.json()
            return {
                "status": response.status,
                "response": result
            }


async def read_discord_messages(limit: int = 10, after_time: datetime = None) -> list:
    """Read recent messages from Discord channel."""

    if not DISCORD_BOT_TOKEN:
        return {"error": "DISCORD_BOT_TOKEN not configured"}

    if not DISCORD_CHANNEL_ID:
        return {"error": "DISCORD_CHANNEL_ID not configured"}

    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit={limit}"

    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                messages = await response.json()

                # Filter messages after the specified time
                if after_time:
                    filtered = []
                    for msg in messages:
                        msg_time = datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))
                        if msg_time.replace(tzinfo=None) > after_time.replace(tzinfo=None):
                            filtered.append(msg)
                    return filtered

                return messages
            else:
                error_text = await response.text()
                return {"error": f"Discord API error {response.status}: {error_text}"}


async def read_discord_threads(limit: int = 10) -> list:
    """Read recent threads from Discord forum channel."""

    if not DISCORD_BOT_TOKEN or not DISCORD_CHANNEL_ID:
        return {"error": "Discord credentials not configured"}

    # Get active threads
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/threads/archived/public?limit={limit}"

    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                # Try getting active threads instead
                guild_url = f"https://discord.com/api/v10/guilds/{os.getenv('DISCORD_GUILD_ID', '')}/threads/active"
                async with session.get(guild_url, headers=headers) as guild_response:
                    if guild_response.status == 200:
                        return await guild_response.json()
                    return {"error": f"Could not fetch threads: {response.status}"}


async def check_railway_health() -> dict:
    """Check if Railway deployment is healthy."""

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{RAILWAY_URL}/health") as response:
            return await response.json()


async def get_recent_tasks() -> dict:
    """Get recent tasks from the database API."""

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{RAILWAY_URL}/api/db/tasks") as response:
            return await response.json()


async def main(test_message: str = None):
    """Main test flow."""

    print_header("BOSS WORKFLOW TEST SCRIPT")

    # Default test message
    if not test_message:
        test_message = "/status"

    print_info(f"Test message: {test_message}")
    print_info(f"Railway URL: {RAILWAY_URL}")
    print_info(f"Boss Chat ID: {TELEGRAM_BOSS_CHAT_ID}")
    print()

    # Step 1: Check health
    print_step(1, "Checking Railway deployment health...")
    try:
        health = await check_railway_health()
        if health.get("status") == "healthy":
            print_success(f"Railway is healthy")
            services = health.get("services", {})
            for service, status in services.items():
                status_icon = "[+]" if status in [True, "healthy", "connected"] else "[-]"
                print(f"    {status_icon} {service}: {status}")
        else:
            print_error(f"Railway unhealthy: {health}")
            return
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return

    print()

    # Step 2: Get tasks before
    print_step(2, "Getting current task count...")
    try:
        tasks_before = await get_recent_tasks()
        count_before = tasks_before.get("count", 0)
        print_success(f"Current tasks in database: {count_before}")
    except Exception as e:
        print_error(f"Failed to get tasks: {e}")
        count_before = 0

    print()

    # Step 3: Record timestamp
    timestamp_before = datetime.now(UTC)
    print_step(3, f"Recording timestamp: {timestamp_before.isoformat()}")

    print()

    # Step 4: Send Telegram webhook
    print_step(4, f"Sending Telegram message: '{test_message}'")
    try:
        result = await send_telegram_webhook(test_message)
        if result["status"] == 200 and result["response"].get("ok"):
            print_success("Webhook accepted by Railway")
        else:
            print_error(f"Webhook failed: {result}")
    except Exception as e:
        print_error(f"Failed to send webhook: {e}")
        return

    print()

    # Step 5: Wait for processing
    print_step(5, "Waiting for processing (5 seconds)...")
    for i in range(5):
        print(f"    {5-i}...", end=" ", flush=True)
        await asyncio.sleep(1)
    print()

    print()

    # Step 6: Check Discord messages
    print_step(6, "Reading Discord messages...")
    try:
        messages = await read_discord_messages(limit=5, after_time=timestamp_before)

        if isinstance(messages, dict) and "error" in messages:
            print_error(f"Discord error: {messages['error']}")
        elif messages:
            print_success(f"Found {len(messages)} new Discord message(s):")
            for msg in messages:
                author = msg.get("author", {}).get("username", "Unknown")
                content = msg.get("content", "")[:200]
                embeds = msg.get("embeds", [])

                print(f"\n    {Colors.BLUE}From: {author}{Colors.END}")
                if content:
                    print(f"    Content: {content}")
                if embeds:
                    for embed in embeds:
                        print(f"    {Colors.YELLOW}Embed Title: {embed.get('title', 'N/A')}{Colors.END}")
                        print(f"    Embed Desc: {embed.get('description', 'N/A')[:200]}")
        else:
            print_info("No new Discord messages found in this channel")
            print_info("(Task may have been posted to forum thread or different channel)")
    except Exception as e:
        print_error(f"Failed to read Discord: {e}")

    print()

    # Step 7: Check if new task was created
    print_step(7, "Checking for new tasks...")
    try:
        tasks_after = await get_recent_tasks()
        count_after = tasks_after.get("count", 0)

        if count_after > count_before:
            print_success(f"New task(s) created! ({count_before} → {count_after})")
            # Show the newest task
            tasks = tasks_after.get("tasks", [])
            if tasks:
                newest = tasks[0]
                print(f"\n    {Colors.GREEN}Newest Task:{Colors.END}")
                print(f"    ID: {newest.get('id')}")
                print(f"    Title: {newest.get('title')}")
                print(f"    Assignee: {newest.get('assignee')}")
                print(f"    Status: {newest.get('status')}")
        else:
            print_info(f"No new tasks (still {count_after})")
            print_info("(This is expected for /status or conversation flows)")
    except Exception as e:
        print_error(f"Failed to check tasks: {e}")

    print()
    print_header("TEST COMPLETE")


if __name__ == "__main__":
    # Get message from command line or use default
    message = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    # Run the test
    asyncio.run(main(message))
