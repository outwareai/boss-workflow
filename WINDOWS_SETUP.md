# Windows Setup for Boss Workflow

## Known Issue: Ralph-Loop Plugin on Windows

The ralph-loop plugin uses bash scripts that don't work natively on Windows CMD/PowerShell due to path conversion issues.

### Solution 1: Use Git Bash (Recommended)

Run Claude Code from Git Bash terminal:

```bash
# Open Git Bash, then:
cd /c/Users/User/Desktop/ACCWARE.AI/AUTOMATION/boss-workflow
claude
```

### Solution 2: Use WSL

If you have Windows Subsystem for Linux:

```bash
wsl
cd /mnt/c/Users/User/Desktop/ACCWARE.AI/AUTOMATION/boss-workflow
claude
```

### Solution 3: Skip Ralph-Loop

Use manual iterative testing instead:

```bash
# Test cycle without ralph-loop:
python test_full_loop.py full-test "Your test message"
# Check results
# Make fixes
# Deploy: railway redeploy -s boss-workflow --yes
# Test again
```

This achieves the same result as ralph-loop but manually.

---

## Environment Variables

Ensure these are set in `.env`:

```
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_BOSS_CHAT_ID=xxx
DISCORD_BOT_TOKEN=xxx
DISCORD_FORUM_CHANNEL_ID=xxx
```

## Quick Test Commands

```bash
# Send test message
python test_full_loop.py send "Task for Mayank: fix login bug"

# Respond to confirmation
python test_full_loop.py respond "yes"

# Check results
python test_full_loop.py read-tasks
python test_full_loop.py read-discord

# Full automated test
python test_full_loop.py full-test "Task for Mayank: fix login"
```
