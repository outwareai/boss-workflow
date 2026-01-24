#!/usr/bin/env python3
"""
Test all 6 handlers individually.
"""

import requests
import time
import os
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8554064690:AAGkkr_ChY8mXqtlg2wpR5kbGCrDXMgkLqw")
TELEGRAM_BOSS_CHAT_ID = os.getenv("TELEGRAM_BOSS_CHAT_ID", "1606655791")

def send_message(text):
    """Send message to Telegram bot."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(url, json={
        "chat_id": TELEGRAM_BOSS_CHAT_ID,
        "text": text
    })
    return response.json()

def main():
    tests = [
        ("1. CommandHandler", "/help"),
        ("2. QueryHandler", "show my tasks"),
        ("3. ModificationHandler", "update TASK-20260124-6F7 status to in_progress"),
        ("4. ApprovalHandler", "delete task TASK-20260124-6F7"),
        ("5. ValidationHandler", "Create task: Test handler validation - assign to Mayank"),
        ("6. RoutingHandler", "Build notification system for Mayank")
    ]

    print("=== HANDLER TESTING ===\n")
    print("Sending test messages to bot...\n")

    for name, message in tests:
        print(f"{name}")
        print(f"  Message: {message}")

        result = send_message(message)
        if result.get("ok"):
            print(f"  OK - Sent successfully")
        else:
            print(f"  FAILED: {result}")

        print()
        time.sleep(3)  # Wait between messages

    print("\n=== DONE ===")
    print("Check Telegram and Railway logs to verify handler responses")
    print("\nTo check Railway logs:")
    print("  railway logs -s boss-workflow --tail")

if __name__ == "__main__":
    main()
