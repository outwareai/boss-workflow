# CLAUDE.MD - Boss Workflow Automation

## Critical Instructions

**ALWAYS READ `FEATURES.md` FIRST** before making any changes to this codebase.

**ALWAYS UPDATE `FEATURES.md` LAST** after completing any changes to document what was added/modified.

---

## Project Overview

Boss Workflow is a conversational task management system for a boss to manage their team via Telegram. It uses AI-powered natural language understanding to create tasks, track progress, and automate reporting.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    TELEGRAM     │────►│   DEEPSEEK AI   │────►│  TASK CREATED   │
│  (Boss Input)   │     │ (Intent + Spec) │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
         ┌───────────────────────────────────────────────┼───────────────────────────────────┐
         │                                               │                                   │
         ▼                                               ▼                                   ▼
┌─────────────────┐                             ┌─────────────────┐                 ┌─────────────────┐
│  GOOGLE SHEETS  │                             │     DISCORD     │                 │ GOOGLE CALENDAR │
│   (Tracking)    │                             │   (Team View)   │                 │  (Deadlines)    │
└─────────────────┘                             └─────────────────┘                 └─────────────────┘
```

---

## Key Files to Know

| File | Purpose |
|------|---------|
| `FEATURES.md` | **READ FIRST** - Complete feature documentation |
| `TEST.MD` | **Comprehensive testing guide** - All test files, commands, best practices |
| `src/main.py` | FastAPI entry point, webhooks, API endpoints |
| `src/bot/handler.py` | Unified message handler, intent routing |
| `src/bot/commands.py` | All slash commands |
| `src/ai/deepseek.py` | AI integration for task generation |
| `src/ai/clarifier.py` | Smart question generation |
| `src/integrations/sheets.py` | Google Sheets operations |
| `src/integrations/discord.py` | Discord webhook posting |
| `src/scheduler/jobs.py` | Scheduled tasks (standup, reports) |
| `src/memory/preferences.py` | User preferences storage |
| `src/models/task.py` | Task model with 14 statuses |
| `src/database/` | **PostgreSQL database layer** |
| `src/database/models.py` | SQLAlchemy models |
| `src/database/repositories/` | CRUD operations |
| `src/database/sync.py` | Sheets ↔ DB sync |
| `setup_sheets.py` | Google Sheets initialization script |
| `config/settings.py` | Environment configuration |
| `.env` | API keys and credentials |

---

## Development Commands

### Run Locally
```bash
cd boss-workflow
pip install -r requirements.txt
python -m src.main
```

### Setup Google Sheets
```bash
python setup_sheets.py
```

### Run Tests
```bash
# Comprehensive integration test
python test_all.py

# Full E2E test suite (v2.3)
python test_full_loop.py test-all

# Unit tests (pytest)
pytest tests/unit/ -v

# See TEST.MD for complete testing documentation
```

---

## Sheet Names (Emoji Prefixed)

When working with Google Sheets, always use these exact names:

```python
SHEET_DAILY_TASKS = "📋 Daily Tasks"
SHEET_DASHBOARD = "📊 Dashboard"
SHEET_TEAM = "👥 Team"
SHEET_WEEKLY = "📅 Weekly Reports"
SHEET_MONTHLY = "📆 Monthly Reports"
SHEET_NOTES = "📝 Notes Log"
SHEET_ARCHIVE = "🗃️ Archive"
SHEET_SETTINGS = "⚙️ Settings"
```

---

## Task Statuses

The system uses 14 task statuses:

| Status | Use Case |
|--------|----------|
| `pending` | Not started |
| `in_progress` | Being worked on |
| `in_review` | Under review |
| `awaiting_validation` | Submitted to boss |
| `needs_revision` | Rejected, needs fixes |
| `completed` | Done |
| `cancelled` | Not doing |
| `blocked` | Can't proceed |
| `delayed` | Postponed |
| `undone` | Needs rework |
| `on_hold` | Paused |
| `waiting` | External dependency |
| `needs_info` | Missing information |
| `overdue` | Past deadline |

---

## API Credentials Required

| Service | Env Variable | Notes |
|---------|--------------|-------|
| Telegram | `TELEGRAM_BOT_TOKEN` | From @BotFather |
| Telegram | `TELEGRAM_BOSS_CHAT_ID` | Boss's chat ID |
| DeepSeek | `DEEPSEEK_API_KEY` | AI provider |
| Discord | `DISCORD_WEBHOOK_URL` | Main channel |
| Discord | `DISCORD_TASKS_CHANNEL_WEBHOOK` | Tasks channel |
| Discord | `DISCORD_STANDUP_CHANNEL_WEBHOOK` | Reports channel |
| Google | `GOOGLE_CREDENTIALS_JSON` | Service account JSON |
| Google | `GOOGLE_SHEET_ID` | Spreadsheet ID |
| Google | `GOOGLE_CALENDAR_ID` | Calendar ID |

---

## Adding New Features

1. **Read `FEATURES.md`** to understand existing functionality
2. **Identify the right file** based on feature type:
   - Bot commands → `src/bot/commands.py`
   - Natural language → `src/bot/handler.py` + `src/ai/intent.py`
   - Sheets operations → `src/integrations/sheets.py`
   - Scheduled jobs → `src/scheduler/jobs.py`
   - New model → `src/models/`
3. **Implement the feature**
4. **Test locally** with `python -m src.main`
5. **Update `FEATURES.md`** with the new functionality

---

## Common Tasks

### Add a New Slash Command
1. Add handler in `src/bot/commands.py`
2. Register in command list
3. Update `/help` output
4. Document in `FEATURES.md`

### Add a New Intent
1. Add pattern in `src/ai/intent.py`
2. Add handler in `src/bot/handler.py`
3. Document in `FEATURES.md`

### Add a New Scheduled Job
1. Create job function in `src/scheduler/jobs.py`
2. Add to scheduler in `get_scheduler_manager()`
3. Add config variables if needed in `config/settings.py`
4. Document in `FEATURES.md`

### Modify Google Sheets Structure
1. Update `setup_sheets.py` with new columns/tabs
2. Update `src/integrations/sheets.py` with new operations
3. Run `python setup_sheets.py` to recreate sheets
4. Document in `FEATURES.md`

---

## Deployment

### Railway Deployment
1. Connect GitHub repo to Railway
2. Add all `.env` variables in Railway dashboard
3. Get deployment URL
4. Update `WEBHOOK_BASE_URL` in Railway variables
5. Telegram webhook auto-registers on startup

### Railway CLI Commands (Claude has access!)

```bash
# View variables
railway variables -s boss-workflow

# Set a variable
railway variables set -s boss-workflow "VAR_NAME=value"

# Redeploy after changes
railway redeploy -s boss-workflow --yes

# View logs
railway logs -s boss-workflow

# Check deployment status
railway status -s boss-workflow
```

**Note:** Railway auto-deploys on git push to master. Use CLI for manual operations.

### Required Railway Variables
```
# Core
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_BOSS_CHAT_ID=xxx
DEEPSEEK_API_KEY=xxx
WEBHOOK_BASE_URL=https://boss-workflow-production.up.railway.app

# Discord (full URLs - don't truncate!)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/xxx
DISCORD_TASKS_CHANNEL_WEBHOOK=https://discord.com/api/webhooks/xxx/xxx
DISCORD_STANDUP_CHANNEL_WEBHOOK=https://discord.com/api/webhooks/xxx/xxx

# Google
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
GOOGLE_SHEET_ID=xxx
GOOGLE_CALENDAR_ID=xxx

# Database (auto-set by Railway PostgreSQL)
DATABASE_URL=postgresql://postgres:xxx@postgres.railway.internal:5432/railway

# Optional
REDIS_URL=redis://default:xxx@redis.railway.internal:6379
TIMEZONE=Asia/Bangkok
```

---

## PostgreSQL Database

The system uses PostgreSQL as the source of truth, with Google Sheets as the boss dashboard.

### Data Architecture
```
┌──────────────────┬──────────────────┬───────────────────┐
│   POSTGRESQL     │   GOOGLE SHEETS  │       REDIS       │
│ (Source of Truth)│ (Boss Dashboard) │  (Cache/Realtime) │
├──────────────────┼──────────────────┼───────────────────┤
│ • All tasks      │ • Task view      │ • Active sessions │
│ • Conversations  │ • Reports        │ • Rate limiting   │
│ • Audit logs     │ • Team roster    │ • Temp state      │
│ • Relationships  │                  │                   │
│ • AI memory      │                  │                   │
└──────────────────┴──────────────────┴───────────────────┘
```

### Database Tables
- `tasks` - Main task storage with all fields
- `projects` - Group related tasks
- `subtasks` - Break tasks into smaller pieces
- `task_dependencies` - Blocked-by, depends-on relationships
- `audit_logs` - Full change history
- `conversations` - Chat history
- `messages` - Individual messages
- `ai_memory` - User preferences and context
- `team_members` - Team roster
- `webhook_events` - Incoming events log

### Database API Endpoints
```
GET  /api/db/tasks                    # List tasks
GET  /api/db/tasks/{task_id}          # Get task with relationships
POST /api/db/tasks/{task_id}/subtasks # Add subtask
POST /api/db/tasks/{task_id}/dependencies # Add dependency
GET  /api/db/audit/{task_id}          # Get audit history
GET  /api/db/projects                 # List projects
POST /api/db/projects                 # Create project
POST /api/db/sync                     # Trigger Sheets sync
GET  /api/db/stats                    # Database statistics
GET  /health/db                       # Database health & connection pool metrics
```

### v2.3.0 Performance Optimizations (Q1 2026)

**Implemented:** 2026-01-23

The system has been optimized for 10x performance improvement and 30% cost reduction:

**Database Performance:**
- ✅ 5 composite indexes (tasks, time_entries, attendance, audit_logs)
- ✅ Connection pooling (pool_size=10, max_overflow=20)
- ✅ N+1 query fixes (selectinload, JOIN queries)
- ✅ 6 major dependencies updated

**Performance Targets:**
| Operation | Before | After | Improvement |
|-----------|--------|-------|-------------|
| Daily task report | 5s | 500ms | 10x faster |
| Weekly overview | 12s | 1.2s | 10x faster |
| API latency | 2-3s | 200-300ms | 10x faster |
| Queries per request | 50-100 | 5-10 | 90% reduction |

**Monitoring:**
- `/health/db` - Connection pool metrics
- GitHub Actions performance workflow (runs every 6 hours)
- Alerts if latency > 300ms for database queries

**Admin Endpoints (Q1 2026 Security):**
```bash
# Run database migrations remotely
curl -X POST ".../admin/run-migration-simple" \
  -H "Content-Type: application/json" \
  -d '{"secret":"your_admin_secret"}'

# Clear active conversations (testing)
curl -X POST ".../admin/clear-conversations" \
  -H "Content-Type: application/json" \
  -d '{"secret":"your_admin_secret"}'

# Seed test team members (Mayank/Zea)
curl -X POST ".../admin/seed-test-team" \
  -H "Content-Type: application/json" \
  -d '{"secret":"your_admin_secret"}'
```

**Note:** Set `ADMIN_SECRET` in Railway variables for admin endpoints.

---

## CI/CD Pipeline

**GitHub Actions workflows auto-run on every push:**

### Test Workflow (`.github/workflows/test.yml`)

**Runs automatically on push to master:**
1. **Unit Tests** - Pytest for Pydantic validation, encryption, rate limiting
2. **Integration Tests** - Intent detection, task operations
3. **E2E Tests** - Full pipeline (Telegram → Bot → Discord)

**Status badges appear in GitHub Actions tab**

**Manual trigger:**
```bash
# Trigger via GitHub UI: Actions → Test Suite → Run workflow
```

### Performance Workflow (`.github/workflows/performance.yml`)

**Runs every 6 hours automatically:**
- Tracks `/health` and `/api/db/stats` latency
- Monitors connection pool utilization
- Alerts if metrics exceed targets
- Saves metrics as artifacts

**Manual trigger:**
```bash
# Trigger via GitHub UI: Actions → Performance Monitoring → Run workflow
```

**View Results:**
- GitHub Actions → Workflow runs → Latest run → Summary
- Artifacts → Download performance-metrics

---

## Testing Framework

**See `TEST.MD` for comprehensive testing documentation.**

**Quick Reference:**
```bash
# Full test suite
python test_full_loop.py test-all

# Specialized tests
python test_full_loop.py test-simple    # Simple task (no questions)
python test_full_loop.py test-complex   # Complex task (with questions)
python test_full_loop.py test-routing   # Role-based routing

# Pre/Post deployment
python test_full_loop.py verify-deploy  # Check Railway health
python test_full_loop.py check-logs     # Scan for errors

# Unit tests
pytest tests/unit/ -v
```

**Test Categories:**
- 🔵 **End-to-End** (3 files) - Full pipeline testing
- 🟢 **Integration** (6 files) - Component integration
- 🟡 **Unit** (3 files) - Pydantic validation, pytest

**Total:** 12 test files, ~200 test cases, ~4,100 lines of test code

---

### Using Repositories
```python
from src.database.repositories import get_task_repository

task_repo = get_task_repository()

# Create task
task = await task_repo.create({"task_id": "TASK-001", "title": "..."})

# Add subtask
subtask = await task_repo.add_subtask("TASK-001", "Subtask title")

# Add dependency
await task_repo.add_dependency("TASK-002", "TASK-001", "blocked_by")

# Get with relationships
task = await task_repo.get_by_id("TASK-001")
blocking = await task_repo.get_blocking_tasks("TASK-001")
```

---

## Code Style

- Use async/await for all I/O operations
- Type hints on all function signatures
- Docstrings for public functions
- Logger instead of print statements
- Handle exceptions gracefully (don't crash the bot)

---

## MANDATORY: Development Workflow

### Step 1: Brainstorm (ALWAYS ASK USER)

When presenting approaches after brainstorming:
1. Present 2-4 distinct approaches
2. **Recommend based on BEST solution, not simplest**
3. Consider: scalability, maintainability, completeness
4. **ALWAYS ASK USER which approach** before implementing

```
Example - GOOD:
"Here are 3 approaches:
A) Quick fix (simplest)
B) Moderate refactor
C) Full redesign (RECOMMENDED - most robust, future-proof)

Which approach would you like?"

Example - BAD:
"Here are 3 approaches... Proceeding with recommended option."
← WRONG: Didn't ask user!
```

### Step 2: Implement with Testing

Use `test_full_loop.py` for real-world testing:

**Basic Commands:**
```bash
python test_full_loop.py send "message"         # Send to bot
python test_full_loop.py respond "yes"          # Answer confirmation
python test_full_loop.py read-telegram          # See bot responses
python test_full_loop.py read-discord           # See Discord output
python test_full_loop.py read-tasks             # See database tasks
python test_full_loop.py full-test "message"    # Complete test cycle
```

**Specialized Tests (v2.3):**
```bash
python test_full_loop.py test-simple            # Test simple task (no questions)
python test_full_loop.py test-complex           # Test complex task (with questions)
python test_full_loop.py test-routing           # Test Mayank→DEV, Zea→ADMIN routing
python test_full_loop.py test-all               # Run all 3 tests in sequence
```

**Pre/Post Deployment:**
```bash
python test_full_loop.py verify-deploy          # Check Railway health after deploy
python test_full_loop.py check-logs             # Quick check for errors in logs
```

**Session Continuity:**
```bash
python test_full_loop.py save-progress "task"   # Save current progress
python test_full_loop.py resume                 # Show saved progress
```

### Step 3: Deploy and Verify

After implementation:
1. Commit and push: `git add . && git commit -m "feat: description" && git push`
2. Wait for Railway auto-deploy (or manual: `railway redeploy -s boss-workflow --yes`)
3. Verify deployment: `python test_full_loop.py verify-deploy`
4. Run tests: `python test_full_loop.py test-all`
5. Check logs if issues: `python test_full_loop.py check-logs`

### Step 4: End-of-Workflow Summary (REQUIRED)

**At the end of EVERY significant task, provide a clear summary covering:**

1. **What was implemented** - Describe each feature/change made and which files were modified

2. **What was tested** - List the tests run and their results (passed/failed)

3. **Commits made** - List commit hashes and messages

4. **Status** - Is the task complete, partial, or blocked?

5. **Next steps** - If anything remains to be done

**Example:**

> **Task Complete: v2.2 Smart AI Upgrade**
>
> **Implemented:**
> I added complexity detection to `clarifier.py` that scores tasks 1-10 based on keywords like "fix" (simple) vs "build system" (complex). Simple tasks now skip questions entirely, while complex tasks ask 1-2 fallback questions even if AI self-answered. Also added role-based routing in `discord.py` so Mayank's tasks go to DEV channel and Zea's go to ADMIN channel.
>
> **Tested:**
> Ran 3 tests with `test_full_loop.py`:
> - Simple task "fix login typo" - PASSED (complexity=1, no questions)
> - Admin task for Zea - PASSED (routed to ADMIN channel)
> - Complex task "build notification system" - PASSED (complexity=9, asked 2 questions)
>
> **Commits:**
> - `4faed9b`: feat(ai): v2.2 Smart AI - complexity detection and role-aware routing
> - `2fe6513`: docs(features): document v2.2 features
>
> **Status:** Complete
>
> **Next steps:** None - ready for production use

**This summary is MANDATORY - never skip it!**

---

## Remember

1. **READ `FEATURES.md` FIRST** - Understand what exists
2. **Don't duplicate** - Check if feature already exists
3. **Keep sheet names exact** - Emoji prefixes matter
4. **Test locally before deploy** - `python -m src.main`
5. **UPDATE `FEATURES.md` LAST** - Document your changes

---

## GitHub Repository

**URL:** https://github.com/outwareai/boss-workflow

```bash
git add .
git commit -m "Description of changes"
git push
```

---

*Last updated: 2026-01-23*

**Recent Updates:**
- **v2.3.0** (2026-01-23): Performance optimization - 10x faster queries, connection pooling, N+1 fixes, 5 composite indexes
- **TEST.MD** (2026-01-23): Comprehensive testing documentation - 12 test files categorized and documented
- **CI/CD** (2026-01-23): GitHub Actions workflows for testing and performance monitoring
- **v2.3 Testing** (2026-01-23): Enhanced test framework with test-simple, test-complex, test-routing, verify-deploy
