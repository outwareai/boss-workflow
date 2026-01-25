"""
Test planning flow by sending a message and monitoring responses.
"""
import asyncio
import time
import subprocess
import json
from telegram import Bot
from config.settings import settings

async def test_planning_flow():
    """Send planning message and monitor response."""
    bot = Bot(settings.telegram_bot_token)
    chat_id = settings.telegram_boss_chat_id

    # Message to send
    message = """Plan a restaurant booking website project for Mayank.

Timeline:
Sunday - Infrastructure (auto-deploy, load balancer, Cloudflare, S3)
Monday - Landing page Maya fully completed
Tuesday - Menu (food & drink) + v1 booking system (simplified, no map)
Wednesday - Mobile adaptation + deploy to test domain
Thursday - Finalize booking system
Friday - Connect with accware.ai for event/customer management
Saturday - Full system testing
Sunday - Production deploy (DEADLINE - cannot be later)"""

    print("=" * 80)
    print("PLANNING FLOW TEST")
    print("=" * 80)

    # Get current update ID to only check new messages
    updates = await bot.get_updates(limit=1, offset=-1)
    if updates:
        last_update_id = updates[0].update_id
    else:
        last_update_id = 0

    # Send message
    print(f"\n[{time.strftime('%H:%M:%S')}] Sending planning message...")
    sent_msg = await bot.send_message(chat_id, message)
    print(f"✓ Message sent (ID: {sent_msg.message_id})")

    # Monitor responses for 90 seconds
    print(f"\n[{time.strftime('%H:%M:%S')}] Monitoring responses (90 seconds)...")
    responses = []
    start_time = time.time()

    while time.time() - start_time < 90:
        # Get new updates
        new_updates = await bot.get_updates(offset=last_update_id + 1, timeout=10)

        for update in new_updates:
            last_update_id = update.update_id

            if update.message and update.message.from_user.is_bot:
                elapsed = time.time() - start_time
                response_text = update.message.text[:200] + "..." if len(update.message.text) > 200 else update.message.text

                print(f"\n[{elapsed:.1f}s] BOT RESPONSE:")
                print(f"  {response_text}")

                responses.append({
                    "time": elapsed,
                    "text": update.message.text
                })

        await asyncio.sleep(2)

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total responses: {len(responses)}")

    if not responses:
        print("\n❌ NO RESPONSES RECEIVED - Checking Railway logs...\n")

        # Check Railway logs
        try:
            result = subprocess.run(
                ["railway", "logs", "--service", "boss-workflow", "--lines", "100"],
                capture_output=True,
                text=True,
                timeout=30
            )

            # Extract errors
            errors = []
            for line in result.stdout.split("\n"):
                if "ERROR" in line or "Traceback" in line or "Exception" in line:
                    errors.append(line)

            if errors:
                print("ERRORS FOUND IN LOGS:")
                for error in errors[-10:]:  # Last 10 errors
                    print(f"  {error}")
            else:
                print("No errors found in logs")

        except Exception as e:
            print(f"Could not fetch logs: {e}")

    else:
        print(f"\n✓ Bot responded {len(responses)} time(s)")
        print(f"  First response: {responses[0]['time']:.1f}s")
        print(f"  Last response: {responses[-1]['time']:.1f}s")

        # Check for validation errors
        has_validation_error = any("FAILED" in r['text'] or "Invalid Dependencies" in r['text'] for r in responses)

        if has_validation_error:
            print("\n⚠️ VALIDATION ERROR DETECTED")
            for r in responses:
                if "FAILED" in r['text'] or "Invalid Dependencies" in r['text']:
                    print(f"\n  Error at {r['time']:.1f}s:")
                    print(f"  {r['text']}")

if __name__ == "__main__":
    asyncio.run(test_planning_flow())
