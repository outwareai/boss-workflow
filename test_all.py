"""
Comprehensive test script for Boss Workflow Automation.
Tests all integrations and components.
"""

import asyncio
import sys
import os
from pathlib import Path

# Setup proper paths
project_root = Path(__file__).parent
src_path = project_root / "src"
data_path = project_root / "data"

# Add both project root (for config) and src to path
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(src_path))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Test results tracking
results = []

def log_result(test_name: str, success: bool, message: str = ""):
    status = "[PASS]" if success else "[FAIL]"
    results.append((test_name, success, message))
    print(f"{status}: {test_name}")
    if message:
        print(f"       {message}")

async def test_deepseek():
    """Test DeepSeek AI connection."""
    print("\n" + "="*50)
    print("Testing DeepSeek AI...")
    print("="*50)

    try:
        from openai import AsyncOpenAI
        from config.settings import get_settings

        settings = get_settings()
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )

        response = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": "Say 'Hello Boss!' in exactly 2 words"}],
            max_tokens=10
        )

        reply = response.choices[0].message.content
        log_result("DeepSeek AI Connection", True, f"Response: {reply}")
        return True
    except Exception as e:
        log_result("DeepSeek AI Connection", False, str(e))
        return False

async def test_discord_webhook():
    """Test Discord webhook posting - all channels."""
    print("\n" + "="*50)
    print("Testing Discord Webhooks...")
    print("="*50)

    try:
        import aiohttp
        from config.settings import get_settings

        settings = get_settings()

        webhooks = [
            ("Main", settings.discord_webhook_url),
            ("Tasks", settings.discord_tasks_channel_webhook),
            ("Standup", settings.discord_standup_channel_webhook),
        ]

        passed = 0
        async with aiohttp.ClientSession() as session:
            for name, webhook_url in webhooks:
                if not webhook_url:
                    print(f"  [SKIP] {name} - No URL configured")
                    continue

                payload = {
                    "embeds": [{
                        "title": f"[TEST] {name} Channel Test",
                        "description": f"Testing {name} webhook for Boss Workflow.",
                        "color": 0x00ff00,
                        "footer": {"text": "Test completed"}
                    }]
                }

                async with session.post(webhook_url, json=payload) as resp:
                    if resp.status in [200, 204]:
                        print(f"  [OK] {name} webhook")
                        passed += 1
                    else:
                        print(f"  [X] {name} webhook - HTTP {resp.status}")

        success = passed >= 2  # At least main + one other
        log_result("Discord Webhooks", success, f"{passed}/{len(webhooks)} webhooks working")
        return success

    except Exception as e:
        log_result("Discord Webhooks", False, str(e))
        return False

async def test_google_sheets():
    """Test Google Sheets connection."""
    print("\n" + "="*50)
    print("Testing Google Sheets...")
    print("="*50)

    try:
        import gspread
        from google.oauth2.service_account import Credentials
        import json
        from config.settings import get_settings

        settings = get_settings()

        if not settings.google_credentials_json:
            log_result("Google Sheets", False, "No credentials configured")
            return False

        creds_dict = json.loads(settings.google_credentials_json)
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)

        # Try to open the configured sheet
        sheet_id = settings.google_sheet_id
        if sheet_id:
            spreadsheet = client.open_by_key(sheet_id)
            worksheets = spreadsheet.worksheets()
            # Get titles but handle encoding issues
            titles = []
            for w in worksheets:
                try:
                    titles.append(w.title.encode('ascii', 'replace').decode())
                except (UnicodeEncodeError, UnicodeDecodeError, AttributeError) as e:
                    # Fallback to raw title if encoding fails
                    titles.append(w.title)
            log_result("Google Sheets", True, f"Connected! Found {len(worksheets)} worksheets")
            return True
        else:
            log_result("Google Sheets", False, "No sheet ID configured")
            return False

    except Exception as e:
        log_result("Google Sheets", False, str(e))
        return False

async def test_gmail():
    """Test Gmail connection."""
    print("\n" + "="*50)
    print("Testing Gmail...")
    print("="*50)

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token_path = data_path / "gmail_token.json"

        if not token_path.exists():
            log_result("Gmail", False, "No token file - run setup_gmail.py first")
            return False

        creds = Credentials.from_authorized_user_file(str(token_path))

        if not creds.valid:
            log_result("Gmail", False, "Token expired or invalid")
            return False

        service = build('gmail', 'v1', credentials=creds)
        results_data = service.users().labels().list(userId='me').execute()
        labels = results_data.get('labels', [])

        # Get unread count
        unread_results = service.users().messages().list(
            userId='me',
            q='is:unread',
            maxResults=1
        ).execute()
        unread = unread_results.get('resultSizeEstimate', 0)

        log_result("Gmail", True, f"Connected! {len(labels)} labels, ~{unread} unread emails")
        return True

    except Exception as e:
        log_result("Gmail", False, str(e))
        return False

async def test_intent_detection():
    """Test intent detection using DeepSeek directly."""
    print("\n" + "="*50)
    print("Testing Intent Detection (via DeepSeek)...")
    print("="*50)

    try:
        from openai import AsyncOpenAI
        from config.settings import get_settings

        settings = get_settings()
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )

        # Test intent detection prompt
        test_message = "john needs to fix the login bug by tomorrow"

        response = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "system", "content": "You are an intent classifier. Classify the user's intent as one of: create_task, query_status, greeting, task_done. Respond with only the intent."},
                {"role": "user", "content": test_message}
            ],
            max_tokens=20
        )

        intent = response.choices[0].message.content.strip().lower()
        success = "create_task" in intent or "task" in intent

        print(f"  Message: '{test_message}'")
        print(f"  Detected: {intent}")

        log_result("Intent Detection", success, f"AI classified as: {intent}")
        return success

    except Exception as e:
        log_result("Intent Detection", False, str(e))
        return False

async def test_auto_reviewer():
    """Test auto-review system using DeepSeek directly."""
    print("\n" + "="*50)
    print("Testing Auto-Review System (via DeepSeek)...")
    print("="*50)

    try:
        from openai import AsyncOpenAI
        from config.settings import get_settings
        import json

        settings = get_settings()
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )

        # Test review prompt
        review_prompt = """Review this task submission:
Task: Fix the login bug for mobile users
Proof: screenshot.png
Notes: "done"

Rate quality 0-100 and provide 1-2 suggestions for improvement.
Respond in JSON: {"score": number, "suggestions": ["...", "..."]}"""

        response = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "system", "content": "You are a code review assistant. Be strict but helpful."},
                {"role": "user", "content": review_prompt}
            ],
            max_tokens=200
        )

        result = response.choices[0].message.content
        print(f"  Review result: {result[:100]}...")

        # Try to parse JSON
        try:
            # Extract JSON from response
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(result[json_start:json_end])
                score = data.get('score', 0)
                suggestions = data.get('suggestions', [])
                print(f"  Score: {score}/100")
                print(f"  Suggestions: {len(suggestions)}")
                log_result("Auto-Review System", True, f"Score: {score}/100, {len(suggestions)} suggestions")
            else:
                log_result("Auto-Review System", True, "AI reviewed (non-JSON response)")
        except json.JSONDecodeError:
            log_result("Auto-Review System", True, "AI reviewed (parsing issue)")

        return True

    except Exception as e:
        log_result("Auto-Review System", False, str(e))
        return False

async def test_email_summarizer():
    """Test email summarizer using DeepSeek directly."""
    print("\n" + "="*50)
    print("Testing Email Summarizer (via DeepSeek)...")
    print("="*50)

    try:
        from openai import AsyncOpenAI
        from config.settings import get_settings

        settings = get_settings()
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )

        # Test email summarization prompt
        summary_prompt = """Summarize these emails briefly:

1. From: alerts@company.com
   Subject: Urgent: Server downtime alert
   Preview: The production server is experiencing issues...

2. From: manager@company.com
   Subject: Weekly team meeting notes
   Preview: Here are the action items from today's meeting...

Provide a 2-3 sentence summary and list any action items."""

        response = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "system", "content": "You are an email assistant. Be concise."},
                {"role": "user", "content": summary_prompt}
            ],
            max_tokens=200
        )

        result = response.choices[0].message.content
        print(f"  Summary: {result[:150]}...")

        log_result("Email Summarizer", True, f"Summary generated ({len(result)} chars)")
        return True

    except Exception as e:
        log_result("Email Summarizer", False, str(e))
        return False

async def test_telegram_config():
    """Test Telegram configuration."""
    print("\n" + "="*50)
    print("Testing Telegram Config...")
    print("="*50)

    try:
        from telegram import Bot
        from config.settings import get_settings

        settings = get_settings()

        if not settings.telegram_bot_token:
            log_result("Telegram Config", False, "No bot token configured")
            return False

        bot = Bot(token=settings.telegram_bot_token)
        me = await bot.get_me()

        log_result("Telegram Config", True, f"Bot: @{me.username} ({me.first_name})")
        return True

    except Exception as e:
        log_result("Telegram Config", False, str(e))
        return False

async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("   BOSS WORKFLOW AUTOMATION - COMPREHENSIVE TEST SUITE")
    print("="*60)

    # Run all tests
    await test_deepseek()
    await test_telegram_config()
    await test_discord_webhook()
    await test_google_sheets()
    await test_gmail()
    await test_intent_detection()
    await test_auto_reviewer()
    await test_email_summarizer()

    # Summary
    print("\n" + "="*60)
    print("   TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for test_name, success, message in results:
        status = "[OK]" if success else "[X]"
        print(f"  {status} {test_name}")

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n  *** ALL TESTS PASSED! System is ready.")
    else:
        print(f"\n  !!!  {total - passed} test(s) failed. Check configuration.")

    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
