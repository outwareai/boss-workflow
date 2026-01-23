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

## ULTIMATE WORKFLOW: Automatic Agent Orchestration

### How It Works

Claude AUTOMATICALLY detects task type and uses the right orchestration - no manual `/commands` needed.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TASK RECEIVED                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 0: AUTO-DETECT TASK TYPE                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Simple fix (1-2 lines)?      ──→ QUICK PATH (direct fix + deploy)          │
│  Bug with unclear cause?      ──→ /systematic-debugging first               │
│  New feature?                 ──→ /feature-dev (full 7-phase)               │
│  Have a plan to execute?      ──→ /subagent-driven-development              │
│  Multiple independent parts?  ──→ /dispatching-parallel-agents              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### QUICK PATH (Simple Fixes)

**Auto-triggered when:** 1-2 line fix, typo, obvious bug

```
Fix → Commit → Push → Wait 30s → Verify health → Done
```

No brainstorming, no agents, just fix and verify.

---

### STANDARD PATH (Most Tasks)

**Auto-triggered when:** Feature, refactor, multi-file change

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: UNDERSTAND                                                        │
│  /brainstorming automatically triggered                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Generate 2-4 approaches                                                  │
│  • Recommend BEST (not simplest)                                            │
│  • ASK USER which approach ← MANDATORY                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 2: PLAN                                                              │
│  /writing-plans automatically triggered                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Create detailed implementation plan                                      │
│  • Break into discrete tasks                                                │
│  • Identify files to change                                                 │
│  • Set checkpoints                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: IMPLEMENT (Auto-choose orchestration)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─ IF 2+ independent tasks ─────────────────────────────────────────────┐  │
│  │  /dispatching-parallel-agents                                         │  │
│  │                                                                       │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                   │  │
│  │  │  Agent 1    │  │  Agent 2    │  │  Agent 3    │  ← RUN PARALLEL   │  │
│  │  │  Task A     │  │  Task B     │  │  Task C     │                   │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                   │  │
│  │         └────────────────┴────────────────┘                          │  │
│  │                          │                                            │  │
│  │                   Integrate results                                   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─ IF sequential dependencies ──────────────────────────────────────────┐  │
│  │  /subagent-driven-development                                         │  │
│  │                                                                       │  │
│  │  For EACH task in plan:                                               │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │  │
│  │  │ 1. Implementer Agent → writes code                              │ │  │
│  │  │ 2. Spec Reviewer Agent → checks requirements met                │ │  │
│  │  │ 3. Quality Reviewer Agent → checks code quality                 │ │  │
│  │  │ 4. AUTO-DEPLOY + TEST ← after each task, not just at end!       │ │  │
│  │  └─────────────────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 4: VERIFY (After EACH agent task)                                    │
│  /verification-before-completion automatically triggered                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Commit changes: git add -A && git commit -m "feat: ..."                  │
│  • Push: git push origin master                                             │
│  • Wait 30s for Railway deploy                                              │
│  • Test: python test_conversation.py --verbose                              │
│  • Check logs: railway logs -s boss-workflow | tail -30                     │
│  • IF FAIL → fix and repeat (don't proceed to next task)                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 5: REVIEW (After all tasks complete)                                 │
│  /requesting-code-review automatically triggered                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  5 Reviewer Agents (parallel):                                              │
│  • Security reviewer                                                        │
│  • Performance reviewer                                                     │
│  • Code style reviewer                                                      │
│  • Architecture reviewer                                                    │
│  • Test coverage reviewer                                                   │
│                                                                             │
│  → Address any issues found                                                 │
│  → Re-deploy and test after fixes                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 6: COMPLETE                                                          │
│  /finishing-a-development-branch automatically triggered                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Update FEATURES.md                                                       │
│  • Final commit                                                             │
│  • End-of-workflow summary (see below)                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### DEBUGGING PATH

**Auto-triggered when:** Bug report, test failure, unexpected behavior

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  /systematic-debugging automatically triggered                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. Reproduce the issue                                                     │
│  2. Gather evidence (logs, state, errors)                                   │
│  3. Form hypothesis                                                         │
│  4. Test hypothesis                                                         │
│  5. Fix root cause (not symptoms)                                           │
│  6. Verify fix works                                                        │
│  7. Add regression test                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
            THEN → QUICK PATH (deploy fix)
```

---

### FEATURE-DEV PATH (Major Features)

**Auto-triggered when:** "Build X", "Add new Y system", major new functionality

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  /feature-dev automatically triggered (7 phases, up to 9 agents)            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Phase 1: Discovery                                                         │
│     └→ Clarify requirements with user                                       │
│                                                                             │
│  Phase 2: Codebase Exploration                                              │
│     └→ 2-3 Explorer Agents (parallel) find patterns, similar code           │
│                                                                             │
│  Phase 3: Clarifying Questions                                              │
│     └→ Ask user about edge cases, scope, preferences                        │
│                                                                             │
│  Phase 4: Architecture Design                                               │
│     └→ 2-3 Architect Agents (parallel) propose different approaches         │
│     └→ Present options, get user choice                                     │
│                                                                             │
│  Phase 5: Implementation                                                    │
│     └→ Build the feature following chosen architecture                      │
│     └→ Deploy + test after each component                                   │
│                                                                             │
│  Phase 6: Quality Review                                                    │
│     └→ 3 Reviewer Agents (parallel) check quality                           │
│     └→ Fix issues, re-test                                                  │
│                                                                             │
│  Phase 7: Summary                                                           │
│     └→ Document what was built                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Auto-Detection Rules

| Task Pattern | Auto-Triggers |
|--------------|---------------|
| "fix typo", "change X to Y" | QUICK PATH |
| "bug", "broken", "not working", "error" | DEBUGGING PATH |
| "build", "create", "add new", "implement" | FEATURE-DEV PATH |
| Multi-part task, plan exists | STANDARD PATH with parallel/subagents |
| Unclear scope | /brainstorming first |

---

### Test Commands Reference

```bash
# Real conversation test (recommended)
python test_conversation.py --verbose

# Quick validation
python test_full_loop.py test-all

# Individual tests
python test_full_loop.py test-simple      # Simple task flow
python test_full_loop.py test-complex     # Complex task with questions
python test_full_loop.py test-routing     # Role-based routing

# Deployment verification
python test_full_loop.py verify-deploy    # Health check
python test_full_loop.py check-logs       # Error scan
railway logs -s boss-workflow | tail -30  # Live logs
```

---

### End-of-Workflow Summary (REQUIRED)

**At the end of EVERY task, provide:**

1. **What was implemented** - Features/changes and files modified
2. **Agents used** - Which orchestration path, how many agents
3. **What was tested** - Tests run and results
4. **Commits made** - Hashes and messages
5. **Status** - Complete, partial, or blocked
6. **Next steps** - If anything remains

**Example:**

> **Task Complete: Notification System**
>
> **Implemented:**
> Built email + SMS notification system across 4 files: `notifications.py` (core), `email_sender.py`, `sms_sender.py`, `handler.py` (integration).
>
> **Agents Used:**
> - FEATURE-DEV PATH (7 phases)
> - 2 Explorer agents (found existing email patterns)
> - 2 Architect agents (chose async queue approach)
> - 3 Reviewer agents (security, performance, style)
> - Total: 7 agents
>
> **Tested:**
> - test_conversation.py: PASSED (notification triggers correctly)
> - test_full_loop.py test-all: 3/3 PASSED
> - Manual Telegram test: PASSED
>
> **Commits:**
> - `abc1234`: feat(notify): Add notification service core
> - `def5678`: feat(notify): Add email and SMS senders
> - `ghi9012`: feat(notify): Integrate with handler
>
> **Status:** Complete
>
> **Next steps:** None

---

### Key Rules

1. **Always ask user** before implementing (after brainstorming)
2. **Deploy + test after EACH task**, not just at the end
3. **Don't proceed** if tests fail - fix first
4. **Use parallel agents** when tasks are independent
5. **Use sequential agents** when tasks depend on each other
6. **Summary is mandatory** - never skip it

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
