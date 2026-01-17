# Boss Workflow Automation - Features Documentation

> **Last Updated:** 2026-01-17
> **Version:** 1.0.0

This document contains the complete list of features, functions, and capabilities of the Boss Workflow Automation system. **This file must be read first and updated last when making changes.**

---

## Table of Contents

1. [Overview](#overview)
2. [Telegram Bot Commands](#telegram-bot-commands)
3. [Natural Language Intents](#natural-language-intents)
4. [AI Capabilities](#ai-capabilities)
5. [Google Sheets Integration](#google-sheets-integration)
6. [Discord Integration](#discord-integration)
7. [Google Calendar Integration](#google-calendar-integration)
8. [Gmail Integration](#gmail-integration)
9. [Scheduler & Automation](#scheduler--automation)
10. [Memory & Learning System](#memory--learning-system)
11. [Task Model](#task-model)
12. [Validation System](#validation-system)
13. [API Endpoints](#api-endpoints)
14. [Configuration](#configuration)
15. [Future Upgrades & Roadmap](#future-upgrades--roadmap)

---

## Overview

Boss Workflow is a conversational task management system that allows a boss to create, assign, and track tasks through natural language via Telegram. The system uses DeepSeek AI for intent detection and clarification, syncs with Google Sheets for tracking, posts to Discord for team visibility, and includes a validation workflow for task completion.

### Architecture

```
Telegram (Boss) ─────┐
                     │
Natural Language ────┼──► DeepSeek AI ──► Task Spec ──┬──► Google Sheets
                     │                                │
Voice/Photos ────────┘                                ├──► Discord
                                                      │
                                                      ├──► Google Calendar
                                                      │
Scheduler ──► Reminders/Reports ──────────────────────┘
```

---

## Telegram Bot Commands

### Task Creation & Management

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Welcome message and introduction | `/start` |
| `/help` | Full command reference | `/help` |
| `/task [description]` | Start conversational task creation | `/task Fix the login bug` |
| `/urgent [description]` | Create high-priority task | `/urgent Server is down` |
| `/skip` | Skip remaining questions, use defaults | `/skip` |
| `/done` | Finalize task with current info | `/done` |
| `/cancel` | Abort current task creation | `/cancel` |

### Task Status & Reporting

| Command | Description |
|---------|-------------|
| `/status` | Current task overview with stats |
| `/daily` | Today's tasks grouped by status |
| `/overdue` | List all overdue tasks |
| `/weekly` | Weekly summary with team metrics |

### Team Management

| Command | Description | Example |
|---------|-------------|---------|
| `/team` | View team members with roles | `/team` |
| `/addteam [name] [role]` | Add new team member | `/addteam John Developer` |
| `/teach [instruction]` | Teach bot preferences | `/teach When I say ASAP, deadline is 4 hours` |
| `/preferences` | View saved preferences | `/preferences` |

### Task Operations

| Command | Description | Example |
|---------|-------------|---------|
| `/note [task-id] [content]` | Add note to task | `/note TASK-001 Waiting for API docs` |
| `/delay [task-id] [deadline] [reason]` | Postpone task | `/delay TASK-001 tomorrow Client request` |

### Validation (Team Members)

| Command | Description |
|---------|-------------|
| `/submit [task-id]` | Start submitting proof |
| `/submitproof` | Finish adding proof, move to notes |
| `/addproof` | Add more proof items |

### Validation (Boss)

| Command | Description | Example |
|---------|-------------|---------|
| `/pending` | View pending validations | `/pending` |
| `/approve [task-id] [message]` | Approve work | `/approve TASK-001 Great job!` |
| `/reject [task-id] [feedback]` | Reject with feedback | `/reject TASK-001 Fix the footer alignment` |

---

## Natural Language Intents

The bot understands natural language without requiring slash commands:

| Intent | Examples | Action |
|--------|----------|--------|
| `CREATE_TASK` | "John needs to fix the login bug" | Starts task creation |
| `TASK_DONE` | "I finished the landing page" | Marks task complete |
| `SUBMIT_PROOF` | Send screenshot or link | Adds to proof collection |
| `CHECK_STATUS` | "what's pending?", "status" | Shows task overview |
| `CHECK_OVERDUE` | "anything overdue?" | Lists overdue tasks |
| `EMAIL_RECAP` | "check my emails" | Generates email summary |
| `DELAY_TASK` | "delay this to tomorrow" | Postpones task |
| `ADD_TEAM_MEMBER` | "John is our backend dev" | Registers team member |
| `TEACH_PREFERENCE` | "when I say ASAP, deadline is 4 hours" | Saves preference |
| `APPROVE_TASK` | "looks good", "approved" | Approves submission |
| `REJECT_TASK` | "no - fix the footer" | Rejects with feedback |
| `HELP` | "help", "what can you do?" | Shows help |
| `GREETING` | "hi", "hello" | Friendly response |

---

## AI Capabilities

### DeepSeek Integration (`src/ai/deepseek.py`)

| Function | Description |
|----------|-------------|
| `analyze_task_request()` | Identify missing info, confidence scores |
| `generate_clarifying_questions()` | Create natural questions |
| `generate_task_spec()` | Generate complete task specification |
| `format_preview()` | Format spec as readable message |
| `process_answer()` | Extract structured info from responses |
| `generate_daily_standup()` | Create standup summaries |
| `generate_weekly_summary()` | Generate weekly reports |

### Intent Detection (`src/ai/intent.py`)

- Fast pattern matching for common intents
- Context-aware matching based on conversation stage
- AI-powered fallback for complex messages
- Confidence scoring

### Task Clarifier (`src/ai/clarifier.py`)

- Smart question generation based on confidence levels
- Preference-based question filtering
- Information extraction (priority, deadline, assignee)
- Answer processing with multi-format support

### Email Summarizer (`src/ai/email_summarizer.py`)

- Batch email analysis (up to 20 emails)
- Action item extraction
- Priority categorization
- Sender/topic grouping
- Urgent attention flagging

### Submission Reviewer (`src/ai/reviewer.py`)

- Auto-review quality checks (0-100 score)
- Proof item validation
- Notes completeness check
- AI-powered improvement suggestions
- Configurable threshold (default 70)

---

## Google Sheets Integration

### Sheet Structure (`src/integrations/sheets.py`)

| Sheet | Purpose | Columns |
|-------|---------|---------|
| **📋 Daily Tasks** | Main task tracker | ID, Title, Description, Assignee, Priority, Status, Type, Deadline, Created, Updated, Effort, Progress, Tags, Created By, Notes, Blocked By |
| **📊 Dashboard** | Overview with live formulas | Metrics, charts, completion rates |
| **👥 Team** | Team directory | Name, Telegram ID, Role, Email, Active Tasks, Completed (Week/Month), Completion Rate, Avg Days, Status |
| **📅 Weekly Reports** | Weekly summaries | Week #, Year, Dates, Tasks Created/Completed/Pending/Blocked, Completion Rate, Priority Breakdown, Top Performer, Overdue, On-Time Rate, Highlights, Blockers |
| **📆 Monthly Reports** | Monthly analytics | Month, Year, Tasks Created/Completed/Cancelled, Completion Rate, Priority Breakdown (Created & Done), EOM Status, Team Performance, Time Metrics, Summary |
| **📝 Notes Log** | All task notes | Timestamp, Task ID, Task Title, Author, Type, Content, Pinned |
| **🗃️ Archive** | Completed tasks | ID, Title, Description, Assignee, Priority, Final Status, Type, Deadline, Created, Completed, Days to Complete, Notes Count, Archived On |
| **⚙️ Settings** | Configuration | Team members, task types, priorities, statuses |

### Key Functions

| Function | Description |
|----------|-------------|
| `add_task()` | Add new task with full metadata |
| `update_task()` | Update task properties |
| `get_all_tasks()` | Retrieve all tasks |
| `get_tasks_by_status()` | Filter by status |
| `get_tasks_by_assignee()` | Filter by person |
| `get_overdue_tasks()` | Get past-deadline tasks |
| `get_tasks_due_soon()` | Get tasks due within X days |
| `add_note()` | Log note for task |
| `generate_weekly_report()` | Auto-generate weekly report |
| `generate_monthly_report()` | Auto-generate monthly report |
| `update_team_member()` | Add/update team member |
| `archive_task()` | Move to archive |
| `archive_old_completed()` | Archive tasks older than X days |

### Formatting Features

- Montserrat font throughout
- Color-coded headers per sheet
- Priority conditional formatting (red/orange/yellow/green)
- Status conditional formatting (8 colors)
- Overdue row highlighting
- Alternating row colors (banding)
- Dropdown validations (Priority, Status, Type, Progress, Role)
- Frozen headers and first columns
- Optimized column widths

---

## Discord Integration

### Webhook Features (`src/integrations/discord.py`)

| Function | Description |
|----------|-------------|
| `post_task()` | Create rich embed with task details |
| `update_task_embed()` | Edit existing task embed |
| `post_standup()` | Daily standup summary |
| `post_weekly_summary()` | Weekly report embed |
| `post_alert()` | Urgent notifications |
| `post_review_feedback()` | Quality assessment for developer |
| `post_submission_approved()` | Approval notification |

### Embed Format

- Task ID and title
- Priority emoji (🟢🟡🟠🔴)
- Status with emoji
- Assignee with Discord mention
- Deadline
- Estimated effort
- Acceptance criteria with checkmarks
- Pinned notes
- Delay reason if delayed

### Configured Webhooks

| Webhook | Purpose |
|---------|---------|
| `DISCORD_WEBHOOK_URL` | General notifications |
| `DISCORD_TASKS_CHANNEL_WEBHOOK` | Task postings |
| `DISCORD_STANDUP_CHANNEL_WEBHOOK` | Standup/report summaries |

---

## Google Calendar Integration

### Features (`src/integrations/calendar.py`)

| Function | Description |
|----------|-------------|
| `create_task_event()` | Add task deadline to calendar |
| `update_task_event()` | Modify event if deadline changes |
| `delete_task_event()` | Remove event if task cancelled |
| `get_events_today()` | Retrieve today's events |

### Event Properties

- Color-coded by priority (Green/Yellow/Orange/Red)
- Multi-step reminders: 2 hours, 1 day, 1 week before
- Description includes: task description, assignee, acceptance criteria, task ID

---

## Gmail Integration

### Features (`src/integrations/gmail.py`)

| Function | Description |
|----------|-------------|
| `get_emails_since()` | Fetch recent emails by timeframe |
| `is_available()` | Check if Gmail configured |
| `generate_digest_for_period()` | Morning/evening summaries |

### Email Digest Contents

- Total and unread counts
- Important email count
- AI-generated summary
- Action items list
- Priority emails
- Category breakdown

---

## Scheduler & Automation

### Scheduled Jobs (`src/scheduler/jobs.py`)

| Job | Schedule | Description |
|-----|----------|-------------|
| `daily_standup_job` | 9 AM daily | Summary of today's tasks, completion %, blocked tasks |
| `eod_reminder_job` | 6 PM daily | Pending/overdue tasks, tomorrow's priorities |
| `weekly_summary_job` | Friday 5 PM | Team performance, completed vs pending, trends |
| `monthly_report_job` | 1st of month 9 AM | Monthly analytics, productivity insights |
| `deadline_reminder` | 2 hours before | Reminder to assignee and boss |
| `overdue_alert` | Every 4 hours | Lists overdue tasks with days count |
| `conversation_cleanup` | Every 5 minutes | Auto-finalize timed-out conversations |
| `morning_digest` | 7 AM | Email summary for morning |
| `evening_digest` | 8 PM | Email summary for evening |

### Configurable Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `TIMEZONE` | Asia/Bangkok | Scheduler timezone |
| `DAILY_STANDUP_HOUR` | 9 | Morning standup time |
| `EOD_REMINDER_HOUR` | 18 | End-of-day reminder time |
| `WEEKLY_SUMMARY_DAY` | friday | Weekly report day |
| `WEEKLY_SUMMARY_HOUR` | 17 | Weekly report time |
| `DEADLINE_REMINDER_HOURS` | 2 | Hours before deadline to remind |
| `OVERDUE_ALERT_INTERVAL_HOURS` | 4 | How often to alert about overdue |

---

## Memory & Learning System

### User Preferences (`src/memory/preferences.py`)

**Defaults:**
- Default priority level
- Deadline behavior (next business day, EOD, etc.)
- Specification format (detailed, brief)

**Question Behavior:**
- `always_ask` - Fields to always ask about
- `skip_questions_for` - Fields to never ask about
- `always_show_preview` - Always preview before creating

**Team Knowledge:**
- Team member registry with name, Telegram ID, Discord ID, email, role, skills, default task types

**Custom Triggers:**
- Pattern → Action mapping
- Example: "ASAP" → deadline: 4 hours

### Learning System (`src/memory/learning.py`)

| Teaching Type | Example |
|---------------|---------|
| Trigger | "When I say ASAP, set deadline to 4 hours" |
| Team member | "John is our backend expert" |
| Question preference | "Always ask about deadline" |
| Defaults | "My default priority is medium" |

---

## Task Model

### Task Properties (`src/models/task.py`)

```
id: TASK-YYYYMMDD-XXX format
title, description
assignee (name)
priority: low, medium, high, urgent
status: (see below)
task_type: task, bug, feature, research
deadline, created_at, updated_at
started_at, completed_at
estimated_effort: "2 hours", "1 day", etc.
acceptance_criteria: List of checkable items
tags: Custom categorization
notes: List with author and timestamp
discord_message_id, sheets_row_id, calendar_event_id
```

### Task Statuses (14 total)

| Status | Description |
|--------|-------------|
| `pending` | Not yet started |
| `in_progress` | Currently being worked on |
| `in_review` | Code/work review stage |
| `awaiting_validation` | Submitted for boss review |
| `needs_revision` | Rejected, needs changes |
| `completed` | Finished successfully |
| `cancelled` | Not doing |
| `blocked` | Can't proceed |
| `delayed` | Postponed with new deadline |
| `undone` | Was completed but needs rework |
| `on_hold` | Paused intentionally |
| `waiting` | Waiting for external dependency |
| `needs_info` | Blocked pending information |
| `overdue` | Past deadline, not completed |

---

## Validation System

### Validation Flow (`src/models/validation.py`)

1. Team member completes task
2. Team member runs `/submit [task-id]`
3. Sends proof (screenshots, links, documents)
4. Adds notes explaining completion
5. Auto-review checks quality (score 0-100)
6. If score >= 70: sent to boss
7. If score < 70: suggestions shown, can improve or send anyway
8. Boss sees submission in Telegram
9. Boss approves or rejects with feedback
10. If rejected: team member can resubmit

### Proof Item Types

- `SCREENSHOT` - Photo/image file
- `VIDEO` - Video recording
- `LINK` - URL to demo/PR/deployment
- `DOCUMENT` - Attached file
- `NOTE` - Text explanation
- `CODE_COMMIT` - Git commit reference

### Auto-Review Checks

- Proof item count (minimum expected)
- Screenshot/link presence
- Notes completeness
- Length validation
- AI quality assessment

---

## API Endpoints

### Health & Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root health check |
| `/health` | GET | Detailed service status |

### Webhooks

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook/telegram` | POST | Telegram updates |
| `/webhook/discord` | POST | Discord reactions |

### Task Operations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tasks/daily` | GET | Today's tasks |
| `/api/tasks/overdue` | GET | Overdue tasks |
| `/api/status` | GET | Overall status |
| `/api/weekly-overview` | GET | Weekly statistics |

### Scheduling

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/trigger-job/{job_id}` | POST | Manually trigger job |

### Preferences

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/preferences/{user_id}` | GET | Get preferences |
| `/api/preferences/{user_id}/teach` | POST | Add preference |

### Database Operations (PostgreSQL)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/db/tasks` | GET | List tasks from database |
| `/api/db/tasks/{task_id}` | GET | Get task with relationships |
| `/api/db/tasks/{task_id}/subtasks` | POST | Add subtask to task |
| `/api/db/tasks/{task_id}/dependencies` | POST | Add dependency between tasks |
| `/api/db/audit/{task_id}` | GET | Get audit history for task |
| `/api/db/projects` | GET | List all projects |
| `/api/db/projects` | POST | Create new project |
| `/api/db/sync` | POST | Trigger Sheets sync |
| `/api/db/stats` | GET | Get database statistics |

---

## PostgreSQL Database

### Overview

PostgreSQL serves as the **source of truth** for all data. Google Sheets remains as the **boss dashboard** for visual tracking. Data flows:

```
┌─────────────────────────────────────────────────────────────────────┐
│                      DATA ARCHITECTURE                               │
├──────────────────┬──────────────────┬───────────────────────────────┤
│   POSTGRESQL     │   GOOGLE SHEETS  │         REDIS                 │
│ (Source of Truth)│ (Boss Dashboard) │   (Cache/Realtime)            │
├──────────────────┼──────────────────┼───────────────────────────────┤
│ • All tasks      │ • Task view      │ • Active sessions             │
│ • Conversations  │ • Reports        │ • Rate limiting               │
│ • Audit logs     │ • Team roster    │ • Temporary state             │
│ • Relationships  │                  │                               │
│ • AI memory      │                  │                               │
└──────────────────┴──────────────────┴───────────────────────────────┘
```

### Database Tables (`src/database/models.py`)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `tasks` | Main task storage | task_id, title, description, status, priority, assignee, deadline, project_id |
| `projects` | Group related tasks | name, description, status, color |
| `subtasks` | Break tasks into pieces | task_id, title, completed, order |
| `task_dependencies` | Task relationships | task_id, depends_on_id, dependency_type |
| `audit_logs` | Full change history | action, entity_id, old_value, new_value, changed_by, timestamp |
| `conversations` | Chat sessions | user_id, stage, context, generated_spec, outcome |
| `messages` | Individual messages | conversation_id, role, content, intent_detected |
| `ai_memory` | User context | user_id, preferences, team_knowledge, custom_triggers |
| `team_members` | Team roster | name, telegram_id, discord_id, email, role, skills |
| `webhook_events` | Event log | source, event_type, payload, processed |

### Task Relationships

**Subtasks** - Break large tasks into smaller pieces:
```python
await task_repo.add_subtask("TASK-001", "Design mockup")
await task_repo.add_subtask("TASK-001", "Implement frontend")
await task_repo.complete_subtask(subtask_id, "John")
```

**Dependencies** - Define task ordering:
```python
# TASK-002 is blocked by TASK-001
await task_repo.add_dependency("TASK-002", "TASK-001", "blocked_by")

# Get what's blocking a task
blocking = await task_repo.get_blocking_tasks("TASK-002")

# Get what a task is blocking
blocked = await task_repo.get_blocked_tasks("TASK-001")
```

Dependency types:
- `blocked_by` - This task cannot start until another completes
- `depends_on` - This task needs another's output
- `blocks` - This task prevents another from starting
- `required_by` - Another task needs this one first

**Projects** - Group related tasks:
```python
project = await project_repo.create(name="Website Redesign")
await task_repo.assign_to_project("TASK-001", project.id)
stats = await project_repo.get_project_stats(project.id)
```

### Audit Logging

Every change is tracked automatically:

| Action | Description |
|--------|-------------|
| `created` | Task/entity created |
| `updated` | Field changed |
| `status_changed` | Status transition |
| `assigned` | Task assigned to someone |
| `note_added` | Note added to task |
| `proof_submitted` | Proof submitted for review |
| `approved` | Task approved by boss |
| `rejected` | Task rejected with feedback |
| `subtask_added` | Subtask created |
| `dependency_added` | Dependency established |
| `synced_to_sheets` | Data synced to Sheets |

Query audit history:
```python
audit_repo = get_audit_repository()

# Get full history for a task
history = await audit_repo.get_task_history("TASK-001")

# Get user activity
activity = await audit_repo.get_user_activity(user_id, days=7)

# Get activity stats
stats = await audit_repo.get_activity_stats(days=7)
```

### Conversation History

All conversations are persisted:

```python
conv_repo = get_conversation_repository()

# Create conversation
conv = await conv_repo.create(user_id, user_name="Mat")

# Add messages
await conv_repo.add_message(conv.conversation_id, "user", "Create task for John")
await conv_repo.add_message(conv.conversation_id, "assistant", "What's the deadline?")

# Complete conversation
await conv_repo.complete(conv.conversation_id, outcome="completed", task_id="TASK-001")

# Get user history
history = await conv_repo.get_user_history(user_id, limit=20)
```

### AI Memory

Persistent context per user:

```python
memory_repo = get_ai_memory_repository()

# Get full context for AI
context = await memory_repo.get_full_context_for_ai(user_id)

# Update preferences
await memory_repo.update_preferences(user_id, {"default_priority": "medium"})

# Add custom trigger
await memory_repo.add_trigger(user_id, "ASAP", {"deadline_hours": 4})

# Add team knowledge
await memory_repo.add_team_member(user_id, "Mayank", {
    "role": "developer",
    "discord_id": "@MAYANK",
    "skills": ["frontend", "react"]
})
```

### Sheets Sync

Tasks automatically sync to Sheets:

```python
sync = get_sheets_sync()

# Sync pending tasks
result = await sync.sync_pending_tasks()
# {"synced": 5, "failed": 0}

# Full sync (all tasks)
result = await sync.full_sync()
# {"total": 50, "synced": 50, "failed": 0}

# Import from Sheets (migration)
result = await sync.sync_from_sheets()
# {"imported": 25, "skipped": 10}
```

Tasks are flagged `needs_sheet_sync=True` on any change. A scheduled job syncs periodically.

### Repository Pattern

All database operations use the repository pattern:

```python
from src.database.repositories import (
    get_task_repository,
    get_audit_repository,
    get_conversation_repository,
    get_ai_memory_repository,
    get_team_repository,
    get_project_repository,
)

# Each repository is a singleton
task_repo = get_task_repository()
audit_repo = get_audit_repository()
conv_repo = get_conversation_repository()
memory_repo = get_ai_memory_repository()
team_repo = get_team_repository()
project_repo = get_project_repository()
```

---

## Configuration

### Environment Variables (`.env`)

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot API token |
| `TELEGRAM_BOSS_CHAT_ID` | Boss's Telegram chat ID |
| `DEEPSEEK_API_KEY` | DeepSeek AI API key |
| `DEEPSEEK_BASE_URL` | DeepSeek API endpoint |
| `DISCORD_WEBHOOK_URL` | Main Discord webhook |
| `DISCORD_TASKS_CHANNEL_WEBHOOK` | Tasks channel webhook |
| `DISCORD_STANDUP_CHANNEL_WEBHOOK` | Standup channel webhook |
| `GOOGLE_CREDENTIALS_JSON` | Service account JSON |
| `GOOGLE_SHEET_ID` | Google Sheets document ID |
| `GOOGLE_CALENDAR_ID` | Google Calendar ID |
| `WEBHOOK_BASE_URL` | Railway/deployment URL |
| `TIMEZONE` | Scheduler timezone |
| `GMAIL_USER_EMAIL` | Gmail for digests |
| `DATABASE_URL` | PostgreSQL connection string (auto-set by Railway) |
| `REDIS_URL` | Redis connection string (optional) |

---

## File Structure

```
boss-workflow/
├── config/
│   ├── __init__.py
│   └── settings.py          # Pydantic settings
├── src/
│   ├── ai/
│   │   ├── clarifier.py     # Question generation
│   │   ├── deepseek.py      # AI integration
│   │   ├── email_summarizer.py
│   │   ├── intent.py        # Intent detection
│   │   ├── prompts.py       # AI prompts
│   │   └── reviewer.py      # Auto-review
│   ├── bot/
│   │   ├── commands.py      # Slash commands
│   │   ├── conversation.py  # Conversation flow
│   │   ├── handler.py       # Unified handler
│   │   ├── telegram.py      # Telegram integration
│   │   ├── telegram_simple.py
│   │   └── validation.py    # Input validation
│   ├── integrations/
│   │   ├── calendar.py      # Google Calendar
│   │   ├── discord.py       # Discord webhooks
│   │   ├── drive.py         # Google Drive
│   │   ├── gmail.py         # Gmail
│   │   ├── meet.py          # Google Meet
│   │   ├── sheets.py        # Google Sheets
│   │   └── tasks.py         # Google Tasks
│   ├── memory/
│   │   ├── context.py       # Conversation context
│   │   ├── learning.py      # Learning system
│   │   └── preferences.py   # User preferences
│   ├── models/
│   │   ├── conversation.py  # Conversation state
│   │   ├── task.py          # Task model
│   │   └── validation.py    # Validation model
│   ├── database/
│   │   ├── __init__.py      # Database module
│   │   ├── connection.py    # Async SQLAlchemy engine
│   │   ├── models.py        # SQLAlchemy models
│   │   ├── sync.py          # Sheets sync layer
│   │   └── repositories/
│   │       ├── tasks.py     # Task CRUD with relationships
│   │       ├── audit.py     # Audit log operations
│   │       ├── conversations.py  # Chat history
│   │       ├── ai_memory.py # AI context persistence
│   │       ├── team.py      # Team member operations
│   │       └── projects.py  # Project operations
│   ├── scheduler/
│   │   ├── jobs.py          # Scheduled jobs
│   │   └── reminders.py     # Reminder service
│   └── main.py              # FastAPI app
├── setup_sheets.py          # Google Sheets setup
├── setup_gmail.py           # Gmail OAuth setup
├── test_all.py              # Test suite
├── requirements.txt         # Dependencies
├── .env                     # Environment variables
├── FEATURES.md              # This file
└── CLAUDE.md                # AI assistant instructions
```

---

## Future Upgrades & Roadmap

### Phase 1: Quick Wins (Ready to Implement)

#### 1. Task Templates
**Status:** 🟡 Planned
**Complexity:** Low
**Files:** `src/bot/commands.py`, `src/memory/preferences.py`

Pre-defined templates for common task types that auto-fill fields:

| Template | Auto-fills |
|----------|------------|
| `bug` | type=bug, priority=high, tags=["bugfix"] |
| `feature` | type=feature, effort="1 day", tags=["feature"] |
| `hotfix` | type=bug, priority=urgent, deadline=4 hours |
| `meeting` | type=meeting, effort="1 hour" |
| `research` | type=research, priority=low |

**Usage:** `/task bug: Login page crashes on Safari`

**Implementation:**
- Store templates in preferences or Settings sheet
- Parse template prefix from task description
- Merge template defaults with extracted info
- Allow custom templates via `/addtemplate`

---

#### 2. Discord Reaction Status Updates
**Status:** 🟡 Planned
**Complexity:** Low
**Files:** `src/integrations/discord.py`, `src/main.py`

Team members react to task embeds to update status without commands:

| Reaction | Action |
|----------|--------|
| ✅ | Mark as completed |
| 🚧 | Set to in_progress |
| 🚫 | Set to blocked |
| ⏸️ | Set to on_hold |
| 🔄 | Set to in_review |
| ❌ | Set to cancelled |

**Implementation:**
- Add Discord bot (not just webhooks) to read reactions
- Store Discord message ID with task
- Listen for reaction events via Discord gateway or interactions
- Map reaction emoji to status change
- Update Sheets and notify boss

---

#### 3. Task Search Command
**Status:** 🟡 Planned
**Complexity:** Low
**Files:** `src/bot/commands.py`, `src/integrations/sheets.py`

Search tasks by keyword, assignee, status, or date:

```
/search login bug        → Tasks containing "login" or "bug"
/search @John            → Tasks assigned to John
/search #urgent          → Tasks with urgent priority
/search status:blocked   → All blocked tasks
/search due:today        → Tasks due today
/search created:week     → Tasks created this week
```

**Implementation:**
- Add `search_tasks()` to sheets.py with filters
- Parse search query for special operators (@, #, status:, due:)
- Return formatted results with task IDs
- Limit to 10 results with pagination hint

---

#### 4. Bulk Status Update
**Status:** 🟡 Planned
**Complexity:** Low
**Files:** `src/bot/commands.py`, `src/integrations/sheets.py`

Update multiple tasks at once:

```
/complete TASK-001 TASK-002 TASK-003
/block TASK-004 TASK-005 "Waiting for API"
/assign @Sarah TASK-006 TASK-007
/priority urgent TASK-008 TASK-009
```

**Implementation:**
- Parse multiple task IDs from command
- Batch update in Sheets (single API call)
- Post summary to Discord
- Return count of updated tasks

---

#### 5. Task Dependencies (Blocked By)
**Status:** 🟡 Planned
**Complexity:** Medium
**Files:** `src/models/task.py`, `src/integrations/sheets.py`, `src/scheduler/jobs.py`

Enforce task dependencies with auto-unblock:

```
/task Fix payment flow blocked_by:TASK-001
/block TASK-002 depends:TASK-001
/deps TASK-001                          → Show dependency tree
```

**Features:**
- `blocked_by` field links to other task IDs
- When blocker completes → auto-unblock dependent tasks
- Prevent completing task if dependencies incomplete
- Visual dependency tree in `/deps` command
- Circular dependency detection

**Implementation:**
- Add `blocked_by_ids` field to task model
- Scheduler job checks completed tasks for dependents
- Auto-update status from `blocked` to `pending`
- Notify assignee when unblocked

---

### Phase 2: Medium Effort (High Value)

#### 6. Recurring Tasks
**Status:** 🔴 Not Started
**Complexity:** Medium
**Files:** `src/models/task.py`, `src/scheduler/jobs.py`, `src/bot/commands.py`

Tasks that auto-recreate on schedule:

```
/recurring "Weekly standup" every:monday 9am assign:@team
/recurring "Monthly report" every:1st 10am
/recurring "Daily backup check" every:day 6pm
```

**Recurrence Patterns:**
- Daily: `every:day [time]`
- Weekly: `every:monday,wednesday,friday [time]`
- Monthly: `every:1st` or `every:15th` or `every:last`
- Custom: `every:2weeks`, `every:3days`

**Implementation:**
- New `RecurringTask` model with schedule pattern
- Scheduler job creates instances from templates
- Link instances to parent recurring task
- `/recurring list` to see all recurring tasks
- `/recurring pause/resume [id]` to control

---

#### 7. Time Tracking
**Status:** 🔴 Not Started
**Complexity:** Medium
**Files:** `src/models/task.py`, `src/bot/commands.py`, `src/integrations/sheets.py`

Track actual time spent on tasks:

```
/start TASK-001          → Start timer
/stop                    → Stop current timer
/log TASK-001 2h30m      → Manual time entry
/time TASK-001           → Show time spent
/timesheet               → Weekly time summary
/timesheet @John         → Person's timesheet
```

**Data Tracked:**
- Start/stop timestamps per session
- Total time per task
- Actual vs estimated comparison
- Time per person per week

**Implementation:**
- Add `time_entries` list to task model
- Track active timer in user context
- New "Time Tracking" sheet for detailed logs
- Calculate actual vs estimated in reports

---

#### 8. Smart Assignee Suggestion
**Status:** 🔴 Not Started
**Complexity:** Medium
**Files:** `src/ai/clarifier.py`, `src/memory/preferences.py`

AI suggests best assignee based on:
- Skills match (from team profile)
- Current workload (active task count)
- Past performance on similar tasks
- Availability (on_hold tasks, leave status)

```
Boss: "Need someone to fix the React dashboard"
Bot: "Based on skills and workload, I suggest:
      1. Sarah (React expert, 2 active tasks)
      2. John (knows React, 4 active tasks)
      Who should I assign?"
```

**Implementation:**
- Enhance team member profiles with skills
- Calculate workload score per person
- AI matches task keywords to skills
- Present ranked suggestions

---

#### 9. Subtasks
**Status:** 🔴 Not Started
**Complexity:** Medium
**Files:** `src/models/task.py`, `src/bot/commands.py`, `src/integrations/sheets.py`

Break tasks into smaller items:

```
/subtask TASK-001 "Design mockup"
/subtask TASK-001 "Implement frontend"
/subtask TASK-001 "Write tests"
/subtasks TASK-001                    → List subtasks
```

**Features:**
- Parent task tracks subtask completion %
- Parent auto-completes when all subtasks done
- Subtasks can have own assignee/deadline
- Nested view in Discord embed

**Implementation:**
- Add `parent_id` and `subtask_ids` to task model
- Calculate completion % from subtasks
- Indented display in task lists
- Subtasks inherit parent priority by default

---

#### 10. Voice Commands (Whisper)
**Status:** 🔴 Not Started
**Complexity:** Medium
**Files:** `src/ai/deepseek.py`, `src/bot/telegram.py`

Transcribe voice messages for hands-free task creation:

```
[Voice] "Create urgent task for John to fix the server, deadline tomorrow"
Bot: "I understood: Urgent task for John - Fix the server, due tomorrow. Create it?"
```

**Implementation:**
- Integrate OpenAI Whisper API or local whisper
- Transcribe voice message to text
- Process transcription through normal intent flow
- Confirm understanding before creating

---

### Phase 3: Major Features

#### 11. PostgreSQL Backend
**Status:** ✅ COMPLETED
**Complexity:** High

PostgreSQL is now the primary data store:
- ✅ Faster queries (sub-millisecond vs 500ms+ API)
- ✅ No rate limits
- ✅ Complex queries (JOINs, aggregations)
- ✅ Full conversation history
- ✅ Audit logs
- ✅ Task relationships (subtasks, dependencies, projects)
- ✅ AI memory persistence
- ✅ Google Sheets sync layer

---

#### 12. Team Member Bot Access
**Status:** 🔴 Not Started
**Complexity:** High

Team members interact directly via Telegram:
- Each member links their Telegram to profile
- Members receive task assignments directly
- Members can `/done`, `/block`, `/note` their tasks
- Members submit proofs directly
- Boss sees all, members see only their tasks

---

#### 13. Web Dashboard
**Status:** 🔴 Not Started
**Complexity:** High

React/Next.js dashboard with:
- Kanban board view
- Gantt chart for timelines
- Team workload visualization
- Burndown charts
- Real-time updates via WebSocket

---

#### 14. Slack Integration
**Status:** 🔴 Not Started
**Complexity:** Medium

Mirror Discord functionality to Slack:
- Task embeds in Slack
- Slash commands in Slack
- Reaction-based status updates
- Thread-based task discussions

---

#### 15. AI Task Breakdown
**Status:** 🔴 Not Started
**Complexity:** Medium

AI auto-splits large tasks:

```
Boss: "Build user authentication system"
Bot: "This is a large task. Suggested breakdown:
      1. Design auth flow (2h)
      2. Set up database schema (1h)
      3. Implement login/register API (4h)
      4. Build frontend forms (3h)
      5. Add password reset (2h)
      6. Write tests (2h)
      Create as subtasks?"
```

---

### Phase 4: Analytics & Intelligence

#### 16. Velocity Tracking
Track story points or task counts per sprint/week for capacity planning.

#### 17. Burndown Charts
Visual progress toward sprint/milestone goals.

#### 18. Prediction Engine
"Based on history, this task will likely take 3 days" using ML on past task data.

#### 19. Bottleneck Detection
AI identifies where tasks get stuck most (in_review? blocked?) and suggests process improvements.

#### 20. Auto-Prioritization
Dynamically adjust priority based on deadline proximity and dependencies.

---

### Implementation Priority

| Priority | Feature | Effort | Impact |
|----------|---------|--------|--------|
| 1 | Task Templates | Low | High |
| 2 | Discord Reactions | Low | High |
| 3 | Task Search | Low | Medium |
| 4 | Bulk Updates | Low | Medium |
| 5 | Task Dependencies | Medium | High |
| 6 | Recurring Tasks | Medium | High |
| 7 | Time Tracking | Medium | Medium |
| 8 | Team Bot Access | High | Very High |
| 9 | PostgreSQL | High | High |
| 10 | Web Dashboard | High | Very High |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.1.0 | 2026-01-17 | PostgreSQL database layer with relationships, audit logs, AI memory |
| 1.0.0 | 2026-01-17 | Initial release with full feature set |

---

*This document is automatically referenced by Claude Code. Always read this file first when working on the project, and update it last after making changes.*
