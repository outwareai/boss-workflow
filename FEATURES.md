# Boss Workflow Automation - Features Documentation

> **Last Updated:** 2026-01-23
> **Version:** 2.2.0
> **Total Lines:** ~2182 | **Total Features:** 113+

**Purpose:** Complete reference for all features, functions, and capabilities of the Boss Workflow Automation system.
**Usage Rule:** **Read this file FIRST when starting work, update LAST after making changes.**

---

## 🎯 Quick Reference Guide

### System Status at a Glance

| Component | Status | Key Features |
|-----------|--------|--------------|
| **AI Engine** | ✅ Production | DeepSeek AI, Intent Detection, Voice/Vision |
| **Telegram Bot** | ✅ Production | 40+ commands, Natural language, Multi-task |
| **Discord Integration** | ✅ Production | 4 channels/dept, Reactions, Forum threads |
| **Google Sheets** | ✅ Production | 8 sheets, Auto-sync, Reports |
| **Database** | ✅ Production | PostgreSQL with full relationships |
| **Automation** | ✅ Production | Scheduled jobs, Reminders, Auto-review |
| **Team Access** | 🔴 Planned | Multi-user bot access |
| **Web Dashboard** | 🔴 Planned | React/Next.js UI |

### Most Used Commands

```bash
# Task Creation
/task [description]              # Create task with AI assistance
/urgent [description]            # High-priority task
"John fix the login bug"         # Natural language (no command needed)

# Status & Reports
/status                          # Current overview
/daily                           # Today's tasks
/weekly                          # Weekly summary

# Team Operations
/team                            # View team members
/syncteam                        # Sync team from config to DB/Sheets

# Validation
/submit [task-id]                # Team member submits work
/approve [task-id] [message]     # Boss approves task
```

### File Location Quick Index

| Component | File Path |
|-----------|-----------|
| Main Entry | `src/main.py` |
| Bot Handler | `src/bot/handler.py` |
| AI Intent | `src/ai/intent.py` |
| Task Creation | `src/ai/task_processor.py` |
| DeepSeek AI | `src/ai/deepseek.py` |
| Discord | `src/integrations/discord.py` |
| Sheets | `src/integrations/sheets.py` |
| Database Models | `src/database/models.py` |
| Scheduler | `src/scheduler/jobs.py` |

---

## 📋 Table of Contents

1. [Overview & Architecture](#overview--architecture)
2. [Telegram Bot Interface](#telegram-bot-interface)
   - [Commands Reference](#telegram-bot-commands)
   - [Natural Language Intents](#natural-language-intents)
3. [AI Capabilities](#ai-capabilities)
4. [Integrations](#integrations)
   - [Google Sheets](#google-sheets-integration)
   - [Discord](#discord-integration)
   - [Google Calendar](#google-calendar-integration)
   - [Gmail](#gmail-integration)
5. [Automation & Scheduling](#scheduler--automation)
6. [Data Systems](#data-systems)
   - [Memory & Learning](#memory--learning-system)
   - [Task Model](#task-model)
   - [Validation System](#validation-system)
7. [API & Technical](#api--technical)
   - [API Endpoints](#api-endpoints)
   - [Utility Modules](#utility-modules)
   - [Configuration](#configuration)
8. [Team Features](#team-features)
   - [Time Clock System](#time-clock--attendance-system)
9. [Roadmap & Future](#future-upgrades--roadmap)
10. [Version History](#version-history)

---

## Overview & Architecture

### System Summary

**Boss Workflow** is a conversational task management system enabling bosses to create, assign, and track tasks through natural language via Telegram.

**Core Technology Stack:**
- **Frontend:** Telegram Bot (Python-telegram-bot)
- **AI:** DeepSeek AI (intent detection, task generation, analysis)
- **Backend:** FastAPI + PostgreSQL + Redis
- **Integrations:** Discord, Google Sheets, Google Calendar, Gmail
- **Deployment:** Railway (with auto-scaling)

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         INPUT LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│  Telegram (Boss) ──► Voice Messages ──► Photos ──► Text         │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                       AI PROCESSING LAYER                        │
├─────────────────────────────────────────────────────────────────┤
│  DeepSeek AI ──► Intent Detection ──► Task Spec Generation      │
│  Whisper ──► Voice Transcription                                │
│  Vision AI ──► Image Analysis                                    │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                       DATA PERSISTENCE                           │
├─────────────────────────────────────────────────────────────────┤
│  PostgreSQL (Source of Truth) ◄──► Redis (Cache/Sessions)      │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      OUTPUT/SYNC LAYER                           │
├─────────────────────────────────────────────────────────────────┤
│  Google Sheets ──► Discord ──► Google Calendar ──► Gmail       │
└─────────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AUTOMATION LAYER                            │
├─────────────────────────────────────────────────────────────────┤
│  Scheduler ──► Reminders ──► Reports ──► Proactive Check-ins   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Differentiators

1. **AI-First Architecture** - Intent detection uses DeepSeek AI, not brittle regex
2. **Zero-Command Interface** - Natural language works for 95% of operations
3. **Multi-Modal Input** - Text, voice, images all supported
4. **Auto-Review System** - AI validates submissions before boss sees them
5. **Pattern Learning** - System learns from interactions over time
6. **Department Routing** - Tasks auto-route to correct Discord channels by role

---

## Telegram Bot Interface

### Telegram Bot Commands

#### 🎯 Task Creation & Management

| Command | Description | Example | Status |
|---------|-------------|---------|--------|
| `/start` | Welcome message and introduction | `/start` | ✅ Core |
| `/help` | Full command reference | `/help` | ✅ Core |
| `/task [description]` | Start conversational task creation | `/task Fix the login bug` | ✅ Core |
| `/urgent [description]` | Create high-priority task | `/urgent Server is down` | ✅ Core |
| `/skip` | Skip remaining questions, use defaults | `/skip` | ✅ Core |
| `/done` | Finalize task with current info | `/done` | ✅ Core |
| `/cancel` | Abort current task creation | `/cancel` | ✅ Core |

**Implementation:** `src/bot/commands.py`

---

#### 🔄 Multi-Task Handling (v1.4+)

**Status:** ✅ Production (Enhanced in v1.7.5)

**Feature:** Sequential processing of multiple tasks in one message

**How it works:**
```
User: "John fix the login bug, then Sarah update the homepage, and Mike review the API"

Bot: "📋 Task 1 of 3
      [Shows first task preview]

      yes = create & next | skip = skip & next | no = cancel all"

User: "yes"

Bot: "✅ Task 1 created!

      📋 Task 2 of 3
      [Shows second task preview]..."
```

**Detected Separators:**
- `"then"`
- `"and also"`
- `"another task"`
- `"next task"`
- Numbered lists (1., 2., 3.)

**Single-Assignee Multi-Task (v1.7.5):**

Send multiple tasks for the **same person** using ordinal phrases:

```
User: "Tasks for Mayank no questions:
      First one will be to add the referral code
      Second one correct the error sequence
      Third one run Stripe payment testing
      Fourth one fix the email and deploy"

Bot: "📋 Task 1 of 4
      Title: Add referral code functionality
      Assignee: Mayank
      ..."
```

**Ordinal Patterns Detected:**
- `"First one"`, `"Second task"`, `"Third item"`
- `"1st one"`, `"2nd task"`, `"3rd"`, `"4th"`
- Preamble detection: `"Tasks for [name]"` or `"For [name]"` auto-assigns all

**Implementation:** `src/ai/task_processor.py` (deterministic splitting, no AI hallucination)

---

#### 📝 SPECSHEETS Mode (v1.4+)

**Status:** ✅ Production

**Feature:** Detailed PRD-level specification generation

**Trigger Keywords:**
- `"specsheet"`
- `"spec sheet"`
- `"detailed spec"`
- `"detailed for:"`
- `"full spec"`
- `"comprehensive"`
- `"more developed"`
- `"more detailed"`
- `"with details"`

**Example:**
```
User: "SPECSHEETS detailed for: Build authentication system for John"

Bot: [Generates comprehensive PRD with:]
     - Multi-paragraph description (3-5 paragraphs)
     - 4-6 detailed acceptance criteria
     - Comprehensive subtask breakdown
     - Technical considerations
     - DB schema, API structure, patterns
```

**Output:** Posted as Discord Forum thread with full PRD formatting

**Implementation:** `src/ai/deepseek.py` (PRD prompt), `src/integrations/discord.py` (forum posting)

---

#### 📊 Task Status & Reporting

| Command | Description | Output |
|---------|-------------|--------|
| `/status` | Current task overview with stats | All tasks by status with counts |
| `/daily` | Today's tasks grouped by status | Daily breakdown |
| `/overdue` | List all overdue tasks | Tasks past deadline |
| `/weekly` | Weekly summary with team metrics | Full week report |

**Implementation:** `src/bot/commands.py`, `src/integrations/sheets.py`

---

#### 👥 Team Management

| Command | Description | Example | Permissions |
|---------|-------------|---------|-------------|
| `/team` | View team members with roles | `/team` | All |
| `/addteam [name] [role]` | Add new team member | `/addteam John Developer` | Boss only |
| `/syncteam` | Sync team from config/team.py to Sheets + DB | `/syncteam` | Boss only |
| `/syncteam --clear` | Clear mock data first, then sync | `/syncteam --clear` | Boss only |
| `/clearteam` | Clear all data from Team sheet | `/clearteam` | Boss only |
| `/teach [instruction]` | Teach bot preferences | `/teach When I say ASAP, deadline is 4 hours` | Boss only |
| `/preferences` | View saved preferences | `/preferences` | All |

**Team Data Sources:**
1. **Primary:** `config/team.py` (code-defined team)
2. **Synced to:** PostgreSQL `team_members` table
3. **Synced to:** Google Sheets "👥 Team" sheet
4. **Used for:** Discord routing, task assignment, workload tracking

**Implementation:** `src/bot/commands.py`, `src/database/repositories/team.py`

---

#### ⚙️ Task Operations

| Command | Description | Example |
|---------|-------------|---------|
| `/note [task-id] [content]` | Add note to task | `/note TASK-001 Waiting for API docs` |
| `/delay [task-id] [deadline] [reason]` | Postpone task | `/delay TASK-001 tomorrow Client request` |
| `/templates` | View available task templates | `/templates` |

**Implementation:** `src/bot/commands.py`

---

#### 🔧 Comprehensive Task Operations (v2.2+)

**Status:** ✅ Production

**Feature:** Complete task management operations via natural language - no slash commands required.

The bot now understands comprehensive task modifications through conversational language, making task management as simple as describing what you want.

##### Task Modification

| Operation | Natural Language Examples | What Happens |
|-----------|--------------------------|--------------|
| **Modify Title** | "change the title of TASK-001 to 'Fix login bug'" | Updates task title |
| | "rename TASK-001 to 'New Title'" | |
| **Modify Description** | "update TASK-001 description to needs API integration" | Updates description |
| | "change description of TASK-001" | |
| **Reassign Task** | "reassign TASK-001 to Sarah" | Changes assignee |
| | "give the login task to John" | |
| | "transfer TASK-001 to Mayank" | |
| **Change Priority** | "make TASK-001 urgent" | Updates priority level |
| | "lower priority of TASK-002 to medium" | |
| | "high priority for TASK-003" | |
| **Change Deadline** | "extend TASK-001 deadline to Friday" | Updates due date |
| | "push TASK-002 deadline to next week" | |
| | "deadline tomorrow for TASK-003" | |
| **Change Status** | "move TASK-001 to in_progress" | Updates status |
| | "mark TASK-002 as blocked" | |
| | "status to review for TASK-003" | |

##### Tags & Labels

| Operation | Examples |
|-----------|----------|
| **Add Tags** | "tag TASK-001 as frontend" |
| | "label TASK-002 as urgent" |
| | "add tag backend to TASK-003" |
| **Remove Tags** | "remove urgent tag from TASK-001" |
| | "untag frontend from TASK-002" |
| | "delete tag backend from TASK-003" |

##### Subtasks

| Operation | Examples |
|-----------|----------|
| **Add Subtask** | "add subtask to TASK-001: design mockup" |
| | "TASK-002 subtask: write tests" |
| **Complete Subtask** | "mark subtask 1 done on TASK-001" |
| | "subtask #2 complete for TASK-002" |
| | "finish subtask 3 on TASK-003" |

##### Dependencies

| Operation | Examples |
|-----------|----------|
| **Add Dependency** | "TASK-001 depends on TASK-002" |
| | "TASK-003 is blocked by TASK-001" |
| | "after TASK-002, do TASK-004" |
| **Remove Dependency** | "remove dependency between TASK-001 and TASK-002" |
| | "unblock TASK-003 from TASK-001" |

##### Advanced Operations

| Operation | Examples |
|-----------|----------|
| **Duplicate Task** | "duplicate TASK-001 for Sarah" |
| | "copy TASK-002 for the frontend team" |
| **Split Task** | "split TASK-001 into 2 tasks" |
| | "break TASK-002 into multiple tasks" |

**How It Works:**
1. **AI-Powered:** DeepSeek AI detects intent and extracts task details
2. **Context-Aware:** Can reference "this task" in ongoing conversations
3. **Flexible Phrasing:** Natural language works - no rigid syntax
4. **Auto-Sync:** Changes sync to PostgreSQL, Google Sheets, and Discord
5. **Audit Trail:** All changes logged with user and timestamp
6. **Discord Notifications:** Team sees updates in real-time

**Valid Task Statuses:**
- `pending` - Not started
- `in_progress` - Currently working
- `in_review` - Ready for review
- `awaiting_validation` - Boss review needed
- `needs_revision` - Needs changes
- `completed` - Finished
- `cancelled` - Cancelled
- `blocked` - Cannot proceed
- `delayed` - Postponed
- `on_hold` - Paused temporarily
- `waiting` - Waiting on external factor
- `needs_info` - Missing information
- `overdue` - Past deadline

**Valid Priority Levels:**
- `urgent` 🔴 - Immediate attention
- `high` 🟠 - Important
- `medium` 🟡 - Normal (default)
- `low` 🟢 - When time permits

**Implementation Details:**
- **Intent Detection:** `src/ai/intent.py` (13 new intents)
- **Handlers:** `src/bot/handler.py` (13 new handler methods)
- **Repository:** `src/database/repositories/tasks.py`
- **Discord:** `src/integrations/discord.py` (post_simple_message)
- **Sheets Sync:** `src/integrations/sheets.py`

**Example Workflow:**
```
Boss: "change TASK-001 title to 'Implement user authentication'"
Bot: "✅ Updated TASK-001: title updated"

Boss: "make it urgent and reassign to Sarah"
Bot: "✅ Changed TASK-001 priority: medium → urgent"
Bot: "✅ Reassigned TASK-001 from John to Sarah"

Boss: "add tag security to it"
Bot: "✅ Added tags to TASK-001: security"
```

**Natural Language Power:**
- "the login bug" → AI identifies TASK-001 from context
- "postpone this to Friday" → Understands "this" from conversation
- "make urgent" → Extracts priority without explicit "priority to urgent"
- "assign to John" → Identifies team member automatically

---

#### 🔍 Search & Filter (v1.1+)

**Status:** ✅ Production

| Command | Description | Example | Search Scope |
|---------|-------------|---------|--------------|
| `/search [query]` | Search tasks by keyword | `/search login bug` | Title + Description |
| `/search @name` | Find tasks by assignee | `/search @John` | Assignee field |
| `/search #priority` | Filter by priority | `/search #urgent` | Priority field |
| `/search status:X` | Filter by status | `/search status:blocked` | Status field |
| `/search due:X` | Filter by deadline | `/search due:today` | Deadline field |

**Natural Language Support:**
- `"What's John working on?"` → Automatically parsed and searched
- `"Show me urgent tasks"` → Filters by priority
- `"What's due today?"` → Deadline filter

**Implementation:** `src/bot/commands.py`, `src/integrations/sheets.py` (search_tasks method)

---

#### 📦 Bulk Operations (v1.1+)

**Status:** ✅ Production

| Command | Description | Example |
|---------|-------------|---------|
| `/complete ID ID ID` | Mark multiple tasks done | `/complete TASK-001 TASK-002` |
| `/block ID ID [reason]` | Block multiple tasks | `/block TASK-001 TASK-002 API down` |
| `/assign @name ID ID` | Assign tasks to someone | `/assign @Sarah TASK-003 TASK-004` |

**Natural Language Support:**
- `"Mark these 3 as done"` → AI extracts task IDs from context
- `"Block all of John's tasks"` → Filters + bulk update

**Implementation:** `src/bot/commands.py`, `src/integrations/sheets.py` (bulk_update_status, bulk_assign)

---

#### 🔁 Recurring Tasks (v1.2+)

**Status:** ✅ Production

**Feature:** Tasks that auto-recreate on schedule

| Command | Description | Example |
|---------|-------------|---------|
| `/recurring "title" pattern time` | Create recurring task | `/recurring "Weekly standup" every:monday 9am` |
| `/recurring list` | List all recurring tasks | `/recurring list` |
| `/recurring pause REC-ID` | Pause a recurring task | `/recurring pause REC-001` |
| `/recurring resume REC-ID` | Resume paused recurring | `/recurring resume REC-001` |
| `/recurring delete REC-ID` | Delete recurring task | `/recurring delete REC-001` |

**Recurrence Patterns:**

| Pattern | Description | Example |
|---------|-------------|---------|
| `every:day` | Every day | Daily standup |
| `every:weekday` | Monday-Friday only | Workday check-in |
| `every:monday` | Every Monday | Weekly meeting |
| `every:monday,wednesday,friday` | Multiple days | MWF workout |
| `every:1st` | 1st of every month | Monthly report |
| `every:15th` | 15th of every month | Mid-month review |
| `every:last` | Last day of month | EOM summary |
| `every:2weeks` | Every 2 weeks | Bi-weekly sprint |
| `every:3days` | Every 3 days | Regular check-in |

**Scheduler:** Checks every 5 minutes for due recurring tasks

**Implementation:** `src/database/models.py` (RecurringTaskDB), `src/database/repositories/recurring.py`, `src/scheduler/jobs.py`

---

#### ⏱️ Time Tracking (v1.2+)

**Status:** ✅ Production

**Feature:** Full time tracking with timers and manual logging

| Command | Description | Example |
|---------|-------------|---------|
| `/start TASK-ID` | Start timer on a task | `/start TASK-001` |
| `/stop` | Stop current timer | `/stop` |
| `/log TASK-ID duration` | Log time manually | `/log TASK-001 2h30m` |
| `/time TASK-ID` | Show time spent on task | `/time TASK-001` |
| `/timesheet` | Your weekly timesheet | `/timesheet` |
| `/timesheet week` | This week's timesheet | `/timesheet week` |
| `/timesheet @name` | Someone's timesheet | `/timesheet @John` |
| `/timesheet team` | Team timesheet | `/timesheet team` |

**Duration Formats:**

| Format | Parsed As | Example |
|--------|-----------|---------|
| `2h30m` | 150 minutes | 2 hours 30 minutes |
| `1.5h` | 90 minutes | 1.5 hours |
| `45m` | 45 minutes | 45 minutes |
| `1d` | 480 minutes | 1 day (8 hours) |

**Implementation:** `src/database/models.py` (TimeEntryDB), `src/database/repositories/time_tracking.py`

---

#### 📋 Subtasks (v1.2+)

**Status:** ✅ Production

**Feature:** Break tasks into smaller items with progress tracking

| Command | Description | Example |
|---------|-------------|---------|
| `/subtask TASK-ID "title"` | Add subtask to a task | `/subtask TASK-001 "Design mockup"` |
| `/subtasks TASK-ID` | List subtasks for a task | `/subtasks TASK-001` |
| `/subdone TASK-ID #num` | Mark subtask complete | `/subdone TASK-001 1` |
| `/subdone TASK-ID all` | Mark all subtasks done | `/subdone TASK-001 all` |
| `/breakdown TASK-ID` | AI-powered task breakdown (v1.3) | `/breakdown TASK-001` |

**Features:**
- Automatic ordering (order number auto-assigned)
- Parent task tracks completion percentage
- Mark complete by order number
- List shows checkbox status (☐/☑)

**AI Breakdown Example:**
```
Boss: /breakdown TASK-001

Bot: "AI Task Breakdown: TASK-001
     Build user authentication system

     Analysis: Multi-step feature requiring backend and frontend work.

     Suggested Subtasks:
     1. Design auth flow ~30min
     2. Create database schema ~1h
     3. Implement login/register API ~2h (after #2)
     4. Build frontend forms ~2h (after #3)
     5. Add password reset ~1h
     6. Write tests ~1h

     Total Estimated Effort: 7h 30m

     Create these subtasks? Reply yes or no."
```

**Implementation:** `src/database/models.py` (SubtaskDB), `src/database/repositories/tasks.py`, `src/ai/deepseek.py` (breakdown_task)

---

#### ✅ Validation (Team Members)

**Status:** ✅ Production

| Command | Description | Flow |
|---------|-------------|------|
| `/submit [task-id]` | Start submitting proof | Initiates proof collection |
| `/submitproof` | Finish adding proof, move to notes | Transitions to notes phase |
| `/addproof` | Add more proof items | Adds to existing proof |

**Submission Flow:**
```
1. Team member: /submit TASK-001
2. Bot: "Send proof (screenshots, links, files)"
3. Member: [sends screenshots/links]
4. Member: "that's all"
5. Bot: "Add notes about what you did?"
6. Member: "Fixed login bug, tested on Chrome/Safari"
7. Bot: "Send to boss? (yes/no)"
8. Member: "yes"
   → Auto-review kicks in (scores submission)
   → If score ≥ 70: Sent to boss
   → If score < 70: Suggestions shown, ask to improve
```

**Implementation:** `src/bot/validation.py`, `src/ai/reviewer.py`

---

#### ✅ Validation (Boss)

**Status:** ✅ Production

| Command | Description | Example |
|---------|-------------|---------|
| `/pending` | View pending validations | `/pending` |
| `/approve [task-id] [message]` | Approve work | `/approve TASK-001 Great job!` |
| `/reject [task-id] [feedback]` | Reject with feedback | `/reject TASK-001 Fix the footer alignment` |

**Approval Flow:**
```
Boss receives notification with:
- Task details
- All proof items (screenshots, links)
- Team member's notes
- AI analysis (if images)

Boss replies:
- "approved" or "yes" or "looks good" → Task marked completed
- "no - [feedback]" → Task marked needs_revision, feedback sent to member
```

**Implementation:** `src/bot/validation.py`, `src/bot/handler.py`

---

### Natural Language Intents

**System:** AI-First Intent Detection (v2.0) - DeepSeek AI classifies ALL natural language

**Architecture:**
```
Message → Slash Command? ──Yes──► Direct mapping
              │
              No
              ▼
        Context State? ──Yes──► Direct mapping (awaiting confirmation, etc.)
              │
              No
              ▼
        AI Classification ──► Structured JSON ──► Validate ──► Execute
```

**AI Output Format:**
```json
{
  "intent": "CREATE_TASK",
  "confidence": 0.95,
  "reasoning": "User mentions person and action",
  "extracted_data": {
    "assignee": "John",
    "title": "Fix login bug",
    "priority": "medium"
  }
}
```

#### Supported Intents

| Intent | Examples | Action | Confidence Threshold |
|--------|----------|--------|---------------------|
| `CREATE_TASK` | "John needs to fix the login bug" | Starts task creation | 0.7+ |
| `TASK_DONE` | "I finished the landing page" | Marks task complete | 0.8+ |
| `SUBMIT_PROOF` | Send screenshot or link | Adds to proof collection | 0.9+ |
| `CHECK_STATUS` | "what's pending?", "status" | Shows task overview | 0.7+ |
| `CHECK_OVERDUE` | "anything overdue?" | Lists overdue tasks | 0.8+ |
| `EMAIL_RECAP` | "check my emails" | Generates email summary | 0.8+ |
| `SEARCH_TASKS` | "What's John working on?" | Searches and filters tasks | 0.7+ |
| `BULK_COMPLETE` | "Mark these 3 as done" | Bulk status update | 0.8+ |
| `LIST_TEMPLATES` | "What templates are available?" | Shows task templates | 0.9+ |
| `DELAY_TASK` | "delay this to tomorrow" | Postpones task | 0.8+ |
| `ADD_TEAM_MEMBER` | "John is our backend dev" | Registers team member | 0.8+ |
| `ASK_TEAM_MEMBER` | "ask Mayank what tasks are left" | Sends message via Discord (v1.8.3) | 0.8+ |
| `TEACH_PREFERENCE` | "when I say ASAP, deadline is 4 hours" | Saves preference | 0.8+ |
| `APPROVE_TASK` | "looks good", "approved" | Approves submission | 0.9+ |
| `REJECT_TASK` | "no - fix the footer" | Rejects with feedback | 0.9+ |
| `HELP` | "help", "what can you do?" | Shows help | 0.9+ |
| `GREETING` | "hi", "hello" | Friendly response | 0.9+ |

**Key Features:**
- No brittle regex patterns
- Handles ANY phrasing naturally
- Self-healing through examples in prompt
- Confidence scoring with fallback
- Clear distinctions (communication vs task creation)

**Implementation:** `src/ai/intent.py` (AI classification), `src/bot/handler.py` (intent routing)

---

## AI Capabilities

### AI Components Overview

| Component | Model/Tech | Purpose | Status |
|-----------|------------|---------|--------|
| **Intent Detection** | DeepSeek Chat | Classify user messages | ✅ Production |
| **Task Generation** | DeepSeek Chat | Generate task specs | ✅ Production |
| **Voice Transcription** | OpenAI Whisper | Audio → Text | ✅ Production |
| **Image Analysis** | DeepSeek VL | Vision understanding | ✅ Production |
| **Email Summarization** | DeepSeek Chat | Email digests | ✅ Production |
| **Submission Review** | DeepSeek Chat | Quality scoring | ✅ Production |
| **Pattern Learning** | Custom ML | Learn from interactions | ✅ Production |
| **Task Breakdown** | DeepSeek Chat | Generate subtasks | ✅ Production |

---

### DeepSeek Integration

**File:** `src/ai/deepseek.py`

**Key Functions:**

| Function | Description | Input | Output |
|----------|-------------|-------|--------|
| `analyze_task_request()` | Identify missing info, confidence scores | User message | Analysis dict |
| `generate_clarifying_questions()` | Create natural questions | Missing fields | List of questions |
| `generate_task_spec()` | Generate complete task specification | Context dict | Task spec |
| `format_preview()` | Format spec as readable message | Task spec | Formatted string |
| `process_answer()` | Extract structured info from responses | User answer | Extracted data |
| `generate_daily_standup()` | Create standup summaries | Task list | Standup text |
| `generate_weekly_summary()` | Generate weekly reports | Week data | Report text |
| `breakdown_task()` | Analyze task and suggest subtasks | Task details | Subtask list |

**API Configuration:**
- **Endpoint:** `https://api.deepseek.com/v1/chat/completions`
- **Model:** `deepseek-chat`
- **Max Tokens:** 4000 (configurable)
- **Temperature:** 0.7 (task generation), 0.3 (structured extraction)

---

### Intent Detection (AI-FIRST v2.0)

**File:** `src/ai/intent.py`

**Architecture:**
```python
def detect_intent(message: str, context: dict) -> IntentResult:
    """
    AI-powered intent classification

    Returns:
        IntentResult(
            intent: str,           # Intent name
            confidence: float,     # 0.0 - 1.0
            reasoning: str,        # Why this intent?
            extracted_data: dict   # Extracted entities
        )
    """
```

**Prompt Strategy:**
- Includes 20+ examples of each intent
- Clear distinctions between similar intents
- Context-aware (considers conversation state)
- Handles edge cases explicitly

**Fallback Behavior:**
- If confidence < 0.6: Ask clarifying question
- If confidence 0.6-0.7: Confirm with user
- If confidence > 0.7: Execute directly

**Benefits over Regex:**
- ✅ Handles ANY phrasing
- ✅ Understands context and nuance
- ✅ Self-healing through examples
- ✅ No pattern maintenance
- ✅ Adapts to new phrasings naturally

---

### Task Clarifier

**File:** `src/ai/clarifier.py`

**Features:**

1. **Smart Question Generation** - Based on confidence levels
2. **Preference-Based Filtering** - Doesn't ask if preference exists
3. **Information Extraction** - Priority, deadline, assignee from text
4. **Answer Processing** - Multi-format support
5. **Template Detection** (v1.1) - Auto-applies templates from keywords
6. **Dependency Detection** (v1.1) - Suggests potential dependencies
7. **Complexity Detection** (v2.2) - Scores task complexity 1-10
8. **Role-Aware Defaults** (v2.2) - Smart defaults based on assignee role
9. **Intelligent Self-Answering** (v2.2) - AI tries to answer questions before asking user

**v2.2 Smart AI Features:**

| Feature | Description | Behavior |
|---------|-------------|----------|
| **Complexity Detection** | Scores tasks 1-10 based on keywords, length, scope | 1-3: Skip questions, 4-6: 1-2 critical questions, 7-10: Full clarification |
| **Role-Aware Defaults** | Applies defaults based on assignee role | Developer: 4h effort, Admin: 2h effort, Marketing: 3h effort, Design: 6h effort |
| **Keyword Inference** | Infers role from task keywords when no assignee | "fix bug" → Developer, "schedule meeting" → Admin, "design mockup" → Design |
| **Self-Answering Loop** | AI attempts to answer its own questions first | Only asks user truly ambiguous questions |

**Complexity Keywords:**

| Category | Keywords | Effect |
|----------|----------|--------|
| **Simple** (-2 to score) | fix, typo, small, quick, simple, minor, update | Lower complexity |
| **Skip Indicators** (-3 to score) | "no questions", "just do", "straightforward" | Force simple mode |
| **Complex** (+2 to score) | system, architecture, integration, design, build | Higher complexity |
| **Scope** (+2 to score) | multiple, several, complex, comprehensive, complete | Higher complexity |
| **Technical** (+1 to score) | api, database, migration, authentication, payment | Slightly higher |

**Role-Based Routing:**

| Role Keywords | Category | Channel |
|---------------|----------|---------|
| dev, engineer, backend, frontend | Developer | DEV Forum |
| admin, manager, lead, director | Admin | ADMIN Forum |
| market, content, social, growth | Marketing | MARKETING Forum |
| design, ui, ux, graphic | Design | DESIGN Forum |

**Template Keywords:**

| Keyword | Template Applied | Default Priority | Default Effort |
|---------|------------------|------------------|----------------|
| `bug:` | Bug Fix | High | 2h |
| `hotfix:` | Hotfix | Critical | 1h |
| `feature:` | New Feature | Medium | 1 day |
| `research:` | Research | Low | 4h |
| `meeting:` | Meeting | Medium | 1h |
| `docs:` | Documentation | Low | 2h |
| `refactor:` | Code Refactor | Medium | 4h |
| `test:` | Testing | Medium | 3h |

**Example Flow:**
```
User: "bug: Login page crashes on mobile"

AI:
- Detects "bug:" keyword
- Applies Bug Fix template
- Sets priority: High
- Sets effort: 2h
- Skips priority question
- Only asks: "Who should fix this?"
```

---

### Email Summarizer

**File:** `src/ai/email_summarizer.py`

**Features:**
- Batch email analysis (up to 20 emails)
- Action item extraction
- Priority categorization
- Sender/topic grouping
- Urgent attention flagging

**Output Format:**
```
☀️ Morning Email Digest
Jan 16 - 7:00 AM

📬 23 emails | 8 unread

Summary:
Received 3 client updates requiring responses, 5 internal
notifications, and 15 newsletters. Client X needs approval
on the new proposal by EOD.

Action Items:
  ☐ Reply to Client X proposal (deadline today)
  ☐ Review John's PR comments
  ☐ Schedule team sync for next week

Priority:
  📧 Re: Contract Approval Needed...
     _Client X_
  📧 Urgent: Production Issue...
     _DevOps Team_

Breakdown: work: 8 | clients: 3 | newsletters: 12
```

**Scheduling:**
- Morning digest: 7 AM (configurable via `MORNING_DIGEST_HOUR`)
- Evening digest: 8 PM (configurable via `EVENING_DIGEST_HOUR`)

**Implementation:** Sent via Telegram (boss only, not Discord for privacy)

---

### Submission Reviewer

**File:** `src/ai/reviewer.py`

**Feature:** Auto-review quality checks before boss sees submission

**Scoring Criteria (0-100):**

| Criteria | Weight | What It Checks |
|----------|--------|----------------|
| Proof Quality | 40% | Screenshots clear? Links working? Files relevant? |
| Notes Completeness | 30% | Detailed explanation? What was done? What was tested? |
| Acceptance Criteria | 20% | All criteria addressed? Evidence provided? |
| Communication | 10% | Clear writing? Professional? |

**Thresholds:**
- **70+:** Pass → Send to boss
- **50-69:** Warning → Suggest improvements
- **<50:** Fail → Require revision

**Example Flow:**
```
Developer: "I finished the landing page"
→ sends 1 screenshot
→ "that's all"
→ "tested it quickly"

Bot: "⚠️ Your submission needs some work:
      • Notes are too brief (score: 40/100)
      • Missing details about what was tested
      • Only 1 proof item (expected 2-3)

      Suggested notes: 'Completed landing page redesign.
      Tested on Chrome and Safari. All responsive
      breakpoints working.'

      Score: 55/100 (need 70+)

      Reply:
      • 'yes' - Apply my suggestions
      • 'no' - Send to boss anyway
      • 'edit' - Type better notes yourself"

Developer: "yes"

Bot: "✨ Applied! Score now: 85/100. Ready to send to boss? (yes/no)"
```

**Configuration:**
- Threshold: `SUBMISSION_REVIEW_THRESHOLD=70` (env variable)
- Can be disabled: `ENABLE_AUTO_REVIEW=false`

---

### Voice Transcription (v1.2+)

**File:** `src/ai/transcriber.py`
**Status:** ✅ Production

**Technology:** OpenAI Whisper API

**Functions:**

| Function | Description |
|----------|-------------|
| `transcribe()` | Convert audio to text |
| `transcribe_with_context()` | Transcribe with context prompt for accuracy |
| `transcribe_voice_message()` | Telegram voice message wrapper |

**Features:**
- Context-aware prompts: "assignments, deadlines, priorities"
- Automatic temp file handling
- Supports: OGG, MP3, WAV, and other formats
- Requires: `OPENAI_API_KEY` environment variable

**Usage Flow:**
```
1. User sends voice message in Telegram
2. Bot downloads audio file
3. Whisper transcribes with task management context
4. Bot shows: 📝 "Create urgent task for John"
5. Processes transcription as normal text command
```

**Accuracy Tips:**
- Speak clearly
- Mention names explicitly
- State deadlines clearly ("by Friday")
- Use task-related keywords

---

### Image Vision Analysis (v1.3+)

**File:** `src/ai/vision.py`
**Status:** ✅ Production

**Technology:** DeepSeek VL (Vision-Language) model

**Functions:**

| Function | Description | Use Case |
|----------|-------------|----------|
| `analyze_image()` | Analyze image with custom prompt | General analysis |
| `analyze_screenshot()` | Extract structured info from screenshots | UI/UX review |
| `analyze_proof()` | Validate proof images for task completion | Submission validation |
| `extract_text()` | OCR text extraction | Document scanning |
| `describe_for_task()` | Analyze in task creation context | Reference images |

**Features:**
- Automatic base64 encoding for API calls
- Context-aware analysis prompts
- Proof validation with relevance assessment
- Integration with auto-review system

**Usage - Proof Analysis:**
```
1. Team member submits task with screenshot
2. Vision AI analyzes: "Shows completed login page with email/password fields, Google OAuth button, responsive design on mobile view"
3. Analysis shown in preview
4. Included in boss notification
5. Auto-reviewer uses analysis for quality scoring
```

**Usage - Task Creation:**
```
User: [sends mockup image] "Build this dashboard for Sarah"

Bot: 🔍 Analyzing image...
     "I see a dashboard with 3 charts (line, bar, pie),
     user stats panel, and recent activity feed.

     Creating task: Build dashboard with analytics..."
```

**Supported Formats:** JPEG, PNG, GIF, WebP

---

### AI Task Breakdown (v1.3+)

**File:** `src/ai/deepseek.py`
**Status:** ✅ Production
**Function:** `breakdown_task()`

**Feature:** AI analyzes task and generates subtask suggestions

**Input Analysis:**
- Task title and description
- Task type (feature, bug, research)
- Acceptance criteria
- Estimated effort

**Output:**
- 3-8 logical subtasks
- Effort estimates per subtask
- Dependency relationships
- Total estimated time
- Detects if task is too simple

**Example:**
```
Command: /breakdown TASK-001

Input: "Build user authentication system"

Output:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI Task Breakdown: TASK-001
"Build user authentication system"

Analysis: This is a multi-step feature requiring
backend, frontend, and testing work.

Suggested Subtasks:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Design auth flow diagram
   Effort: ~30min

2. Create database schema for users
   Effort: ~1h

3. Implement login/register API
   Effort: ~2h
   Dependencies: After #2

4. Build frontend login form
   Effort: ~2h
   Dependencies: After #3

5. Add password reset flow
   Effort: ~1h
   Dependencies: After #3

6. Write integration tests
   Effort: ~1h
   Dependencies: After #4, #5
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total Estimated Effort: 7h 30m

Create these subtasks? Reply yes or no.
```

**Smart Detection:**
- If task is too simple (e.g., "Update README"), AI responds: "This task is straightforward and doesn't need breakdown"
- If dependencies are circular, AI resolves them

**Integration:** Subtasks created directly in database and synced to Sheets

---

## Integrations

### Google Sheets Integration

**File:** `src/integrations/sheets.py`
**Status:** ✅ Production

#### Sheet Structure

**Workbook:** Single Google Sheet with 8 tabs

| Sheet Name | Purpose | Row Limit | Update Frequency |
|------------|---------|-----------|------------------|
| **📋 Daily Tasks** | Main task tracker | Unlimited | Real-time |
| **📊 Dashboard** | Live metrics & charts | Formula-driven | Real-time |
| **👥 Team** | Team directory | ~50 | On syncteam |
| **📅 Weekly Reports** | Weekly summaries | ~52/year | Weekly (Monday) |
| **📆 Monthly Reports** | Monthly analytics | ~12/year | Monthly (1st) |
| **📝 Notes Log** | All task notes | Unlimited | Real-time |
| **🗃️ Archive** | Completed tasks | Unlimited | Daily cleanup |
| **⚙️ Settings** | Configuration | Static | Manual |

#### 📋 Daily Tasks Sheet

**Columns:**

| Column | Type | Description | Validation |
|--------|------|-------------|------------|
| ID | Text | Task ID (TASK-001) | Auto-generated |
| Title | Text | Task title (max 120 chars) | Required |
| Description | Text | Full description | Optional |
| Assignee | Text | Team member name | Dropdown |
| Priority | Text | urgent/high/medium/low | Dropdown |
| Status | Text | One of 14 statuses | Dropdown |
| Type | Text | feature/bug/hotfix/etc | Dropdown |
| Deadline | DateTime | ISO format or formatted | Date validation |
| Created | DateTime | Creation timestamp | Auto |
| Updated | DateTime | Last update timestamp | Auto |
| Effort | Text | 2h30m, 1d, etc | Duration format |
| Progress | Number | 0-100% | Number validation |
| Tags | Text | Comma-separated | Optional |
| Created By | Text | Creator name | Auto |
| Notes | Text | Latest note | Auto-sync |
| Blocked By | Text | Task ID dependencies | Optional |

**Formatting:**
- Priority conditional: Red (urgent), Orange (high), Yellow (medium), Green (low)
- Status conditional: 14 colors (one per status)
- Overdue highlighting: Red background if past deadline
- Frozen: Header row + first column
- Banding: Alternating row colors for readability

#### 📊 Dashboard Sheet

**Sections:**

1. **Overview Metrics**
   - Total tasks
   - Completed this week
   - Completion rate
   - Average days to complete

2. **Status Breakdown** (Pie chart)
   - Tasks by status with counts

3. **Priority Distribution** (Bar chart)
   - Tasks by priority level

4. **Team Performance** (Table)
   - Tasks per member
   - Completion rates
   - Average effort

5. **Trends** (Line chart)
   - Tasks created vs completed (last 30 days)

**Formula Examples:**
```
Total Tasks: =COUNTA('📋 Daily Tasks'!A:A) - 1
Completed This Week: =COUNTIFS('📋 Daily Tasks'!F:F, "completed", '📋 Daily Tasks'!I:I, ">=TODAY()-7")
Completion Rate: =COUNTIF('📋 Daily Tasks'!F:F, "completed") / COUNTA('📋 Daily Tasks'!A:A)
```

#### 👥 Team Sheet

**Columns:**

| Column | Description | Auto-Calculated? |
|--------|-------------|------------------|
| Name | Team member name | ❌ |
| Telegram ID | Numeric Telegram ID | ❌ |
| Discord ID | Discord user ID | ❌ |
| Role | Dev/Admin/Marketing/Design | ❌ |
| Email | Contact email | ❌ |
| Calendar ID | Google Calendar ID | ❌ (defaults to email) |
| Timezone | e.g., America/New_York | ❌ |
| Work Start | e.g., 09:00 | ❌ |
| Active Tasks | Count of in_progress tasks | ✅ |
| Completed (Week) | Completed this week | ✅ |
| Completed (Month) | Completed this month | ✅ |
| Completion Rate | Percentage | ✅ |
| Avg Days | Average days to complete | ✅ |
| Status | Active/On Leave/Inactive | ❌ |

**Team Data Flow:**
```
config/team.py (Source of Truth)
       ↓ /syncteam command
PostgreSQL team_members table
       ↓ Auto-sync
Google Sheets 👥 Team sheet
       ↓ Used by
Discord routing, Task assignment, Workload tracking
```

#### 📅 Weekly Reports Sheet

**Columns:**

| Column | Description | Generated How |
|--------|-------------|---------------|
| Week # | Week number of year | Auto (ISO week) |
| Year | 2026 | Auto |
| Dates | "Jan 13 - Jan 19" | Auto (Mon-Sun) |
| Tasks Created | Count | Query |
| Tasks Completed | Count | Query |
| Tasks Pending | Count | Query |
| Tasks Blocked | Count | Query |
| Completion Rate | Percentage | Calculated |
| Priority Breakdown | "Urgent: 5, High: 10..." | Query |
| Top Performer | Team member with most completions | Query |
| Overdue | Count of overdue tasks | Query |
| On-Time Rate | % completed before deadline | Calculated |
| Highlights | Key achievements | AI-generated |
| Blockers | Main blockers | AI-generated |

**Generation:** Scheduled job runs every Monday at 10 AM

#### 📆 Monthly Reports Sheet

**Similar structure to Weekly**, but aggregated monthly

**Additional Fields:**
- EOM Status (end of month snapshot)
- Team Performance (detailed breakdown per member)
- Time Metrics (average effort, total hours logged)
- Summary (AI-generated monthly summary)

**Generation:** Scheduled job runs on the 1st of each month at 9 AM

#### 📝 Notes Log Sheet

**Columns:**

| Column | Description |
|--------|-------------|
| Timestamp | When note was added |
| Task ID | Associated task |
| Task Title | For reference |
| Author | Who added the note |
| Type | Status Change/Comment/Update |
| Content | Note text |
| Pinned | Boolean (important notes) |

**Purpose:** Audit trail of all task notes and status changes

#### 🗃️ Archive Sheet

**Purpose:** Store completed/cancelled tasks to keep Daily Tasks clean

**Columns:** Same as Daily Tasks, plus:
- Final Status (completed/cancelled)
- Days to Complete (deadline - created)
- Notes Count (number of notes added)
- Archived On (timestamp)

**Archiving Rules:**
- Auto-archive completed tasks > 30 days old
- Manual archive via command
- Cancelled tasks archived immediately

#### ⚙️ Settings Sheet

**Purpose:** Configuration and reference data

**Sections:**
1. **Task Types** (feature, bug, hotfix, research, meeting, docs, refactor, test)
2. **Priorities** (urgent, high, medium, low)
3. **Statuses** (14 statuses with descriptions)
4. **Roles** (Developer, Admin, Marketing, Design)

**Used for:** Dropdown validations in Daily Tasks sheet

---

#### Key Functions

**File:** `src/integrations/sheets.py`

| Function | Description | Parameters | Returns |
|----------|-------------|------------|---------|
| `add_task()` | Add new task | Task data dict | Task ID |
| `update_task()` | Update task properties | Task ID, update dict | Success bool |
| `get_all_tasks()` | Retrieve all tasks | None | List of tasks |
| `get_tasks_by_status()` | Filter by status | Status string | List of tasks |
| `get_tasks_by_assignee()` | Filter by person | Assignee name | List of tasks |
| `get_overdue_tasks()` | Get past-deadline tasks | None | List of tasks |
| `get_tasks_due_soon()` | Get tasks due within X days | Days (int) | List of tasks |
| `add_note()` | Log note for task | Task ID, content | Note ID |
| `generate_weekly_report()` | Auto-generate weekly report | Week number | Report dict |
| `generate_monthly_report()` | Auto-generate monthly report | Month number | Report dict |
| `update_team_member()` | Add/update team member | Member data | Success bool |
| `archive_task()` | Move to archive | Task ID | Success bool |
| `archive_old_completed()` | Archive tasks older than X days | Days (int) | Count archived |
| `search_tasks()` | Search with filters | Filters dict | List of tasks |
| `bulk_update_status()` | Update status for multiple | Task IDs, status | Success bool |
| `bulk_assign()` | Assign multiple tasks | Task IDs, assignee | Success bool |

**Error Handling:**
- Retries on transient errors (3 attempts, exponential backoff)
- Detailed logging
- Fallback to database if Sheets unavailable

**Performance:**
- Batch operations where possible
- Caching for read-heavy operations
- Async updates to avoid blocking

---

### Discord Integration

**File:** `src/integrations/discord.py`
**Status:** ✅ Production (v1.5.0+)

**Major Change (v1.5.0):** Switched from webhooks to **Bot API with Channel IDs** for full permissions

#### Channel Structure

**Per Department:** Dev, Admin, Marketing, Design

Each department has **4 dedicated channels:**

| Channel Type | Purpose | Content | Permissions |
|--------------|---------|---------|-------------|
| **Forum** | Detailed specs | Spec sheets, complex tasks | Create/delete threads |
| **Tasks** | Regular tasks | Simple tasks, alerts, cancellations | Post/edit/delete messages |
| **Report** | Reports | Daily standup, weekly summary | Post messages |
| **General** | General | Help, announcements | Post messages |

#### Dev Department (Configured)

| Channel | ID | Type |
|---------|-----|------|
| Dev Forum | `1459834094304104653` | Forum |
| Dev Tasks | `1461760665873158349` | Text |
| Dev Report | `1461760697334632651` | Text |
| Dev General | `1461760791719182590` | Text |

#### Admin Department (Configured)

| Channel | ID | Type |
|---------|-----|------|
| Admin Forum | `1462370539858432145` | Forum |
| Admin Tasks | *(not set)* | Text |
| Admin Report | `1462370845908402268` | Text |
| Admin General | `1462370950627725362` | Text |

**Note:** Marketing and Design departments not yet configured

---

#### Key Functions

**File:** `src/integrations/discord.py`

| Function | Description | Parameters |
|----------|-------------|------------|
| `send_message()` | Send message to any channel | channel_id, content, embed |
| `edit_message()` | Edit existing message | channel_id, message_id, new_content |
| `delete_message()` | Delete message | channel_id, message_id |
| `create_forum_thread()` | Create forum post with embed | forum_id, title, content, tags |
| `delete_thread()` | Delete thread/forum post | thread_id |
| `add_reaction()` | Add reaction to message | channel_id, message_id, emoji |
| `get_channel_threads()` | List all threads | channel_id |
| `bulk_delete_threads()` | Delete threads matching prefix | channel_id, title_prefix |
| `post_task()` | Smart task posting (forum or text) | task_data, department |
| `post_spec_sheet()` | Detailed spec as forum thread | spec_data, department |
| `post_standup()` | Daily standup to report channel | standup_data, department |
| `post_weekly_summary()` | Weekly report embed | summary_data, department |
| `post_alert()` | Alerts to tasks channel | alert_message, department |
| `post_general_message()` | Post to general channel | message, department |
| `post_help()` | Help message with reaction guide | department |
| `cleanup_task_channel()` | Clean all task threads | department |
| `send_direct_message_to_team()` | Send boss message to team member (v1.8.3) | member_name, message |
| `ask_team_member_status()` | Ask question via Discord (v1.8.3) | member_name, question |

---

#### Smart Content Routing

**Algorithm:**
```python
def post_task(task, department):
    if task.is_specsheet or task.detailed_mode:
        # Complex tasks → Forum (as thread)
        create_forum_thread(forum_id, task)
    else:
        # Simple tasks → Tasks channel
        send_message(tasks_channel_id, task_embed)
```

**Department Routing:**
```python
def get_department_channels(assignee):
    role = get_team_member_role(assignee)

    if role == "Developer":
        return DEV_CHANNELS
    elif role == "Admin":
        return ADMIN_CHANNELS
    elif role == "Marketing":
        return MARKETING_CHANNELS
    elif role == "Design":
        return DESIGN_CHANNELS
    else:
        return DEV_CHANNELS  # Default
```

---

#### Task Embed Format

**Regular Task:**
```
┌─────────────────────────────────────┐
│ 🎯 TASK-001: Fix login bug          │
├─────────────────────────────────────┤
│ Assignee: @John                     │
│ Priority: 🔴 High                   │
│ Deadline: Jan 16, 2026 5:00 PM     │
│ Status: pending                     │
│                                     │
│ Description:                         │
│ Users cannot log in on mobile...    │
│                                     │
│ Acceptance Criteria:                │
│ ☐ Login works on iOS              │
│ ☐ Login works on Android           │
│ ☐ Error messages are clear         │
├─────────────────────────────────────┤
│ Reactions:                          │
│ ✅ Done | 🚧 Working | 🚫 Blocked  │
│ ⏸️ Paused | 🔄 Review              │
└─────────────────────────────────────┘
```

**Spec Sheet (Forum):**
```
📋 Authentication System Implementation

🎯 Overview
────────────────────────────────────
[5-paragraph description with executive summary,
business value, technical approach, integrations,
success metrics]

🏗️ Implementation Tasks
────────────────────────────────────
1. Design auth flow diagram
   ~30min

2. Create database schema for users
   ~1h
   [Dependencies: None]

3. Implement login/register API
   ~2h
   [Dependencies: Task #2]
   [Technical: FastAPI endpoints, JWT tokens,
   bcrypt password hashing]

[... more tasks ...]

✅ Acceptance Criteria
────────────────────────────────────
☐ Users can register with email/password
☐ Login with email/password works
☐ JWT tokens expire after 24 hours
☐ Password reset flow functional
☐ OAuth with Google works
☐ All endpoints return proper error messages

🔧 Technical Considerations
────────────────────────────────────
Database Schema:
- users table: id, email, hashed_password, created_at
- sessions table: id, user_id, token, expires_at

API Structure:
- POST /auth/register
- POST /auth/login
- POST /auth/refresh
- POST /auth/reset-password

Security:
- bcrypt for password hashing (cost factor 12)
- JWT with RS256 signing
- Rate limiting: 5 requests/minute per IP
- HTTPS only

Performance:
- Redis caching for session tokens
- Database indexes on email, user_id

────────────────────────────────────
Assignee: @John | Priority: High
Deadline: Jan 20, 2026
Created: Jan 16, 2026 by Boss
```

---

#### Reaction System

**Emoji → Status Mapping:**

| Emoji | Status | Auto-Update |
|-------|--------|-------------|
| ✅ | completed | Yes |
| 🚧 | in_progress | Yes |
| 🚫 | blocked | Yes |
| ⏸️ | on_hold | Yes |
| 🔄 | in_review | Yes |
| 📝 | needs_info | Yes |
| ⏰ | overdue | No (auto-set by system) |
| 👍 | (no change) | No |

**Implementation:** Discord bot listens for reactions, updates PostgreSQL + Google Sheets

**File:** `src/integrations/discord_bot.py`

---

#### Direct Team Communication (v1.8.3)

**Feature:** Boss can message team members via Discord WITHOUT creating a task

**Use Cases:**
- "ask Mayank what tasks are left"
- "tell Sarah to update me"
- "check with John about the deployment"
- "ping Mike for status"

**Flow:**
```
Boss (Telegram): "ask Mayank what tasks are left"

Bot:
1. Detects ASK_TEAM_MEMBER intent
2. Finds Mayank's role (Developer)
3. Routes to Dev General channel
4. Posts message with @mention:

   "Hey @Mayank! Boss wants to know: what tasks do you have left?"

Bot (Telegram response): "✅ Sent message to Mayank in Dev General channel"
```

**Reformulation:** Messages are AI-reformulated to be directed AT the team member

**Implementation:** `send_direct_message_to_team()`, `ask_team_member_status()`

---

### Google Calendar Integration

**File:** `src/integrations/calendar.py`
**Status:** ✅ Production

#### Features

**Per-User Calendars (v1.5.1):**
- Events created directly on assignee's personal calendar
- Requires calendar shared with service account
- Falls back to boss's calendar if not shared
- Calendar ID stored in Team sheet (defaults to email)

#### Event Types

| Event Type | When Created | Duration | Reminders |
|------------|-------------|----------|-----------|
| **Task Deadline** | Task created with deadline | 30 min | 2h, 1h before |
| **Meeting** | Task type = "meeting" | Custom | 30min, 10min before |
| **Recurring Task** | Recurring task instance | 30 min | 1h before |

#### Event Format

**Title:** `[TASK-001] Fix login bug`

**Description:**
```
Task: TASK-001
Title: Fix login bug
Assignee: John
Priority: High
Status: pending

Description:
Users cannot log in on mobile devices.

Acceptance Criteria:
- Login works on iOS
- Login works on Android
- Error messages are clear

Google Sheets: [Link]
Discord: [Thread Link]
```

**Reminders:**
- 2 hours before (email)
- 1 hour before (notification)
- 30 minutes before (popup)

#### Key Functions

| Function | Description |
|----------|-------------|
| `create_task_event()` | Create calendar event for task |
| `update_task_event()` | Update existing event (deadline change) |
| `delete_task_event()` | Remove event (task completed/cancelled) |
| `get_user_calendar_id()` | Lookup assignee's calendar ID |
| `create_meeting_event()` | Create meeting with attendees |

**Calendar Lookup Flow:**
```
1. Check Team sheet "Calendar ID" column
2. If empty, use email as calendar ID
3. If sharing error, fall back to config default
4. Log warning if fallback used
```

**Configuration:**
- `GOOGLE_CALENDAR_ID` - Default/fallback calendar
- Service account must have "Make changes to events" permission

---

### Gmail Integration

**File:** `src/integrations/gmail.py`
**Status:** ✅ Production

#### Features

1. **Email Digests** (v1.4.1)
   - Morning: 7 AM (configurable)
   - Evening: 8 PM (configurable)
   - Boss-only (privacy)
   - Sent via Telegram, not Discord

2. **Email Summarization**
   - AI-powered summary
   - Action item extraction
   - Priority categorization
   - Sender grouping

#### Digest Format

```
☀️ Morning Email Digest
Jan 16 - 7:00 AM

📬 23 emails | 8 unread

Summary:
────────────────────────────────────
Received 3 client updates requiring responses,
5 internal notifications, and 15 newsletters.
Client X needs approval on proposal by EOD.

Action Items:
────────────────────────────────────
  ☐ Reply to Client X proposal (deadline today)
  ☐ Review John's PR comments
  ☐ Schedule team sync for next week

Priority Emails:
────────────────────────────────────
  📧 Re: Contract Approval Needed
     From: Client X
     Received: 8:30 AM

  📧 Urgent: Production Issue
     From: DevOps Team
     Received: 6:15 AM

Breakdown:
────────────────────────────────────
Work: 8 | Clients: 3 | Newsletters: 12
```

#### Key Functions

| Function | Description |
|----------|-------------|
| `fetch_recent_emails()` | Get last N emails |
| `generate_digest()` | Create AI summary |
| `send_digest_telegram()` | Send to boss via Telegram |
| `categorize_emails()` | Work/Client/Newsletter classification |

**Scheduling:**
- Morning job: `send_morning_digest` (cron: `0 7 * * *`)
- Evening job: `send_evening_digest` (cron: `0 20 * * *`)

**Configuration:**
- `MORNING_DIGEST_HOUR=7` (env)
- `EVENING_DIGEST_HOUR=20` (env)
- `TIMEZONE=America/New_York` (for correct timing)

---

## Scheduler & Automation

**File:** `src/scheduler/jobs.py`
**Status:** ✅ Production

**Technology:** APScheduler (Advanced Python Scheduler)

### Scheduled Jobs

| Job Name | Schedule | Description | Runs |
|----------|----------|-------------|------|
| `send_daily_standup` | 9:00 AM daily | Daily summary to Discord Report channel | 1x/day |
| `send_morning_digest` | 7:00 AM daily | Email digest via Telegram | 1x/day |
| `send_evening_digest` | 8:00 PM daily | Evening email digest | 1x/day |
| `send_deadline_reminders` | Every 15 min | Task deadline notifications | 96x/day |
| `send_overdue_alerts` | 10:00 AM, 2:00 PM | Overdue task alerts | 2x/day |
| `generate_weekly_report` | Monday 10:00 AM | Weekly summary to Sheets + Discord | 1x/week |
| `generate_monthly_report` | 1st of month 9:00 AM | Monthly analytics | 1x/month |
| `process_recurring_tasks` | Every 5 min | Check and create due recurring tasks | 288x/day |
| `sync_attendance` | Every 15 min | Sync attendance to Sheets (v1.5.4) | 96x/day |
| `weekly_time_report` | Monday 10:00 AM | Weekly time report (v1.5.4) | 1x/week |
| `proactive_checkins` | Every hour | Check in on stalled tasks (v2.0.5) | 24x/day |
| `cleanup_old_tasks` | Sunday 2:00 AM | Archive old completed tasks | 1x/week |
| `process_message_queue` | Every 15 sec | Retry failed messages (v2.0.5) | 240x/hour |

### Job Details

#### Daily Standup

**Trigger:** 9:00 AM daily
**Target:** Discord Report channel (per department)
**Content:**

```
🌅 Daily Standup - Jan 16, 2026
─────────────────────────────────────

📊 Overview
────────────
✅ Completed Yesterday: 5 tasks
🚧 In Progress: 8 tasks
📋 Pending: 12 tasks
🚫 Blocked: 2 tasks

👥 Team Activity
────────────
John (Dev):
  ✅ Fixed login bug
  ✅ Deployed hotfix
  🚧 Working on: Dashboard refactor

Sarah (Dev):
  ✅ Completed homepage update
  🚧 Working on: API optimization

Mayank (Dev):
  🚧 Working on: Stripe integration
  🚧 Working on: Email deploy

🔔 Action Required
────────────
⚠️ TASK-005 blocked by API access
⏰ TASK-012 due today (John)
⏰ TASK-018 due today (Sarah)

💡 Focus Areas Today
────────────
- Complete Stripe payment testing
- Fix email deployment issues
- Address API blocker
```

**Implementation:** `send_daily_standup()` → Posts to all departments

---

#### Deadline Reminders

**Trigger:** Every 15 minutes
**Logic:** Check tasks due within next 2 hours, 1 hour, 30 minutes

**Anti-Spam System (v2.0.2):**
- Tracks which tasks reminded at each interval
- ONE reminder per task per interval
- Intervals: 2h, 1h, 30m before deadline
- Skips tasks already overdue
- Only posts to Discord at 1-hour mark

**Reminder Format (Telegram):**
```
⏰ Deadline Reminder

TASK-001: Fix login bug
Assignee: @John
Due in: 1 hour (5:00 PM)

Status: in_progress
Priority: High
```

**Reminder Format (Discord - 1h mark only):**
```
⏰ @John - Your task is due in 1 hour!

TASK-001: Fix login bug
Deadline: Jan 16, 2026 5:00 PM

[View Task Button]
```

**Deduplication:** `src/services/reminder_tracker.py` stores reminded task IDs per interval

---

#### Overdue Alerts

**Trigger:** 10:00 AM, 2:00 PM daily
**Target:** Telegram (boss) + Discord (team)

**Alert Format:**
```
🚨 Overdue Tasks Alert

3 tasks are past their deadline:

1. TASK-008: API integration
   Assignee: John
   Was due: Jan 15, 3:00 PM (1 day overdue)
   Status: in_progress

2. TASK-015: Email template
   Assignee: Sarah
   Was due: Jan 14, 11:00 AM (2 days overdue)
   Status: pending

3. TASK-022: Testing
   Assignee: Mayank
   Was due: Jan 13, 5:00 PM (3 days overdue)
   Status: blocked
   Reason: Waiting for API access

Please follow up with your team.
```

---

#### Proactive Check-ins (v2.0.5)

**Trigger:** Every hour
**Logic:** Find tasks with no updates in 4+ hours

**Check-in Message (Discord):**
```
👋 Hey @John! Just checking in...

TASK-001: Fix login bug
Last update: 6 hours ago
Status: in_progress

How's it going? Any blockers?
```

**Implementation:**
- `src/scheduler/jobs.py` (proactive_checkins job)
- Only sends if task is `in_progress` or `in_review`
- Friendly, non-pressuring tone
- Tracks last check-in time (doesn't spam)

---

#### Weekly Report

**Trigger:** Monday 10:00 AM
**Targets:** Google Sheets + Discord Report channel

**Report Sections:**
1. **Week Summary** (Jan 13-19, 2026)
2. **Tasks Created:** 25
3. **Tasks Completed:** 18
4. **Completion Rate:** 72%
5. **Priority Breakdown:** Urgent: 5, High: 12, Medium: 6, Low: 2
6. **Top Performer:** John (8 tasks completed)
7. **Overdue:** 3 tasks
8. **On-Time Rate:** 85%
9. **Highlights:** Key achievements (AI-generated)
10. **Blockers:** Main issues (AI-generated)

**Stored in:** Google Sheets "📅 Weekly Reports" sheet

---

#### Message Queue Processor (v2.0.5)

**Trigger:** Every 15 seconds
**Purpose:** Retry failed Discord/API messages

**Features:**
- Exponential backoff (1s, 2s, 4s, 8s, 16s)
- Max retries: 5
- Dead letter queue for permanent failures
- Background worker doesn't block main app

**Implementation:** `src/services/message_queue.py`

**Queued Message Types:**
- Discord posts
- Google Sheets updates
- Calendar events
- Telegram messages

**Monitoring:** Available in audit dashboard at `/audit`

---

## Data Systems

### Memory & Learning System

**Files:** `src/memory/`

#### Components

| Component | File | Purpose |
|-----------|------|---------|
| **Preferences** | `preferences.py` | User preferences (boss & team) |
| **Context** | `context.py` | Conversation context |
| **Learning** | `learning.py` | Learning from teachings |
| **Pattern Learning** | `pattern_learning.py` | Pattern recognition (v2.0.5) |
| **Task Context** | `task_context.py` | Recent task context |

---

#### Preferences System

**Storage:** PostgreSQL `ai_memory` table + Redis cache

**Preference Types:**

| Type | Example | Usage |
|------|---------|-------|
| **Deadline Rules** | "ASAP = 4 hours" | Auto-set deadlines |
| **Team Skills** | "John = React expert" | Smart assignment |
| **Priority Rules** | "Client X = high priority" | Auto-prioritization |
| **Default Assignees** | "bugs → John" | Auto-assignment |
| **Work Hours** | "9 AM - 5 PM" | Schedule tasks |
| **Communication Style** | "Brief updates" | Format responses |

**Teaching Flow:**
```
Boss: "When I say ASAP, deadline is 4 hours"

Bot: "✅ Got it! I'll remember that.

     Preference saved:
     - Keyword: 'ASAP'
     - Deadline: 4 hours from now

     Next time you say 'ASAP bug fix', I'll set deadline to 4 hours automatically."
```

**Implementation:**
```python
class PreferencesManager:
    def save_preference(user_id, key, value, category):
        # Save to database
        # Update Redis cache
        # Log for audit

    def get_preference(user_id, key):
        # Check Redis first
        # Fallback to database
        # Return default if not found
```

---

#### Pattern Learning (v2.0.5)

**File:** `src/memory/pattern_learning.py`
**Status:** ✅ Production

**What It Learns:**

1. **Staff Working Styles**
   - Typical task completion times
   - Preferred communication style
   - Common blockers

2. **Common Issues**
   - Recurring bugs
   - Frequent blockers
   - Dependency patterns

3. **Successful Resolutions**
   - What worked before
   - Effective approaches
   - Best practices

4. **Boss Preferences**
   - Approval patterns
   - Rejection reasons
   - Communication preferences

**Learning Process:**
```
Every interaction:
1. Extract: What happened?
2. Categorize: What type of interaction?
3. Store: Pattern in database
4. Aggregate: Update statistics
5. Use: Inform future AI responses
```

**Example Usage:**
```
Task assigned to John: "Fix dashboard bug"

Pattern Learner checks:
- John's past "dashboard" tasks → Average 4h completion
- John's typical blockers → Often needs design assets
- Boss's past approvals → Prefers screenshots + live demo

AI uses this context:
"Based on similar tasks, estimated 4h.
John, make sure to get design assets from Sarah first.
When submitting, include screenshots + live demo link (boss prefers this)."
```

**Storage:** PostgreSQL `pattern_memory` table

---

### Task Model

**File:** `src/database/models.py`
**Status:** ✅ Production

#### Task Schema (TaskDB)

**Database:** PostgreSQL

| Column | Type | Description | Nullable | Default |
|--------|------|-------------|----------|---------|
| `id` | String | TASK-001 format | No | Auto-gen |
| `title` | String(120) | Task title | No | - |
| `description` | Text | Full description | Yes | None |
| `assignee` | String | Team member name | Yes | None |
| `assignee_telegram_id` | BigInteger | Telegram user ID | Yes | None |
| `priority` | String | urgent/high/medium/low | No | "medium" |
| `status` | String | One of 14 statuses | No | "pending" |
| `type` | String | feature/bug/hotfix/etc | No | "task" |
| `deadline` | DateTime | ISO format | Yes | None |
| `created_at` | DateTime | Auto-set | No | Now |
| `updated_at` | DateTime | Auto-updated | No | Now |
| `created_by` | String | Creator name | Yes | "Boss" |
| `estimated_effort` | String | 2h30m, 1d, etc | Yes | None |
| `actual_effort` | Integer | Minutes logged | Yes | 0 |
| `progress` | Integer | 0-100 | No | 0 |
| `tags` | String | Comma-separated | Yes | None |
| `notes` | Text | Latest note | Yes | None |
| `blocked_by` | String | Task ID dependencies | Yes | None |
| `acceptance_criteria` | JSON | List of criteria | Yes | [] |
| `spec_sheet_url` | String | Discord forum URL | Yes | None |
| `discord_thread_id` | String | Discord thread ID | Yes | None |
| `is_deleted` | Boolean | Soft delete flag | No | False |

#### 14 Task Statuses

| Status | Description | Icon | Next Actions |
|--------|-------------|------|--------------|
| `pending` | Not started yet | 📋 | Start working |
| `in_progress` | Currently working | 🚧 | Continue or block |
| `in_review` | Submitted for review | 🔄 | Approve/reject |
| `awaiting_validation` | Waiting for boss approval | ⏳ | Boss reviews |
| `needs_revision` | Rejected, needs changes | 🔁 | Fix and resubmit |
| `completed` | Approved and done | ✅ | Archive |
| `cancelled` | Cancelled, won't do | 🚫 | Archive |
| `blocked` | Blocked by external factor | 🛑 | Resolve blocker |
| `delayed` | Postponed to later | ⏸️ | Resume when ready |
| `undone` | Was completed, now reopened | ↩️ | Fix issue |
| `on_hold` | Paused temporarily | ⏸️ | Resume later |
| `waiting` | Waiting for something | ⏳ | Check dependency |
| `needs_info` | Missing information | ❓ | Provide info |
| `overdue` | Past deadline | 🚨 | Urgent attention |

**Status Transitions:**
```
pending → in_progress → in_review → awaiting_validation → completed
                  ↓                         ↓
               blocked                needs_revision → in_progress
                  ↓
               on_hold → in_progress
```

---

#### Relationships

**1. Subtasks** (One-to-Many)
```python
class TaskDB:
    subtasks = relationship("SubtaskDB", back_populates="parent_task")

class SubtaskDB:
    id: String          # SUB-001
    task_id: String     # TASK-001 (foreign key)
    title: String
    completed: Boolean
    order: Integer      # Display order
```

**2. Time Entries** (One-to-Many)
```python
class TimeEntryDB:
    id: String          # TIME-001
    task_id: String     # TASK-001
    user_name: String
    duration: Integer   # Minutes
    started_at: DateTime
    ended_at: DateTime
    notes: String
```

**3. Task Dependencies** (Many-to-Many)
```python
class TaskDependencyDB:
    task_id: String         # TASK-002
    depends_on_task_id: String  # TASK-001
    # Means: TASK-002 depends on TASK-001
```

**4. Notes** (Embedded in Task)
```python
# Notes stored as JSON in notes column
notes: [
    {
        "timestamp": "2026-01-16T10:30:00",
        "author": "John",
        "type": "status_change",
        "content": "Started working on this",
        "pinned": false
    }
]
```

---

### Validation System

**File:** `src/bot/validation.py`
**Status:** ✅ Production

#### Validation Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    VALIDATION WORKFLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TEAM MEMBER                          BOSS                       │
│  ───────────                          ────                       │
│  1. "I finished the landing page"                               │
│     ↓                                                            │
│  2. Send screenshots/links                                       │
│     📸 Screenshot 1                                              │
│     📸 Screenshot 2                                              │
│     🔗 Live demo link                                            │
│     ↓                                                            │
│  3. "that's all"                                                │
│     ↓                                                            │
│  4. Add notes (optional)                                         │
│     "Fixed the login bug,                                        │
│      tested on Chrome/Safari"                                    │
│     ↓                                                            │
│  5. AUTO-REVIEW KICKS IN                                         │
│     ┌─────────────────────────┐                                 │
│     │ AI Reviewer scores:     │                                 │
│     │ • Proof: 85/100         │                                 │
│     │ • Notes: 60/100         │                                 │
│     │ • Criteria: 90/100      │                                 │
│     │ Total: 78/100           │                                 │
│     └─────────────────────────┘                                 │
│     ↓                                                            │
│  6a. IF SCORE ≥ 70:                                             │
│      "✅ Looks good! Send to boss?"                             │
│      ↓                                                           │
│      "yes" ──────────────────────▶ 7. Receives request          │
│                                         with all proof           │
│                                         ↓                        │
│                                      8. Reviews work             │
│                                         ↓                        │
│  ┌──────────────────────────────── 9a. "approved"               │
│  │                                      "Great work!"            │
│  ▼                                      ↓                        │
│  10a. 🎉 "TASK APPROVED!"           Task → COMPLETED             │
│                                                                  │
│  ─────── OR ───────                                             │
│                                                                  │
│  ┌──────────────────────────────── 9b. "no - fix footer"        │
│  │                                                               │
│  ▼                                      ↓                        │
│  10b. 🔄 "REVISION NEEDED"          Task → NEEDS_REVISION        │
│      Feedback displayed                                          │
│      ↓                                                           │
│  11. Make changes, submit again...                               │
│                                                                  │
│  ─────── OR (SCORE < 70) ───────                                │
│                                                                  │
│  6b. "⚠️ Your submission needs work:                            │
│       • Notes too brief (40/100)                                │
│       • Missing test details                                    │
│                                                                  │
│       Suggested: 'Completed landing page...                     │
│       Tested on Chrome, Safari...'                              │
│                                                                  │
│       Score: 55/100 (need 70+)                                  │
│                                                                  │
│       • 'yes' - Apply suggestions                               │
│       • 'no' - Send anyway                                      │
│       • 'edit' - Write your own"                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Validation States

**Database:** PostgreSQL `validation_requests` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | String | VAL-001 |
| `task_id` | String | TASK-001 |
| `submitter` | String | Team member name |
| `proof_items` | JSON | List of proof |
| `notes` | Text | Submission notes |
| `review_score` | Integer | 0-100 (auto-review) |
| `suggestions` | Text | AI suggestions |
| `status` | String | pending/approved/rejected |
| `boss_feedback` | Text | Boss's response |
| `submitted_at` | DateTime | When submitted |
| `reviewed_at` | DateTime | When boss reviewed |

#### Proof Item Types

| Type | Description | Validation |
|------|-------------|------------|
| **Screenshot** | Image file | Vision AI analyzes |
| **Link** | URL | Check accessibility |
| **File** | Document | Check format |
| **Git Commit** | Commit SHA | Verify exists |
| **Text Note** | Description | Check completeness |

#### Auto-Review Scoring

**File:** `src/ai/reviewer.py`

**Scoring Algorithm:**
```python
def calculate_score(proof_items, notes, acceptance_criteria):
    score = 0

    # 1. Proof Quality (40%)
    if len(proof_items) >= 2:
        score += 20
    if has_screenshots(proof_items):
        score += 10
    if has_links(proof_items):
        score += 10

    # 2. Notes Completeness (30%)
    if len(notes) > 50:
        score += 10
    if contains_testing_details(notes):
        score += 10
    if explains_what_was_done(notes):
        score += 10

    # 3. Acceptance Criteria (20%)
    for criterion in acceptance_criteria:
        if criterion_addressed(criterion, notes, proof_items):
            score += (20 / len(acceptance_criteria))

    # 4. Communication (10%)
    if professional_tone(notes):
        score += 5
    if clear_writing(notes):
        score += 5

    return score
```

**Stricter Validation (v2.0.5):**
- Staff must **explicitly address EACH** acceptance criterion
- Vague "done" statements rejected
- Must explain what they did for EACH criterion with proof/details
- Vision AI analysis validates screenshots match claims

---

## API & Technical

### API Endpoints

**File:** `src/main.py`
**Framework:** FastAPI
**Status:** ✅ Production

#### Public Endpoints

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/` | GET | API status | None |
| `/health` | GET | Health check | None |
| `/webhook/telegram` | POST | Telegram bot webhook | Telegram secret |
| `/onboard` | GET | Team onboarding form (v1.5.2) | None |
| `/onboard` | POST | Submit onboarding data | None |
| `/team` | GET | View team members | None |
| `/oauth/callback` | GET | Google OAuth callback (v1.5.2) | None |

#### Admin Endpoints

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/audit` | GET | Audit dashboard (v2.0.5) | Admin |
| `/api/audit/stats` | GET | JSON audit stats (v2.0.5) | Admin |
| `/api/tasks` | GET | List all tasks | API key |
| `/api/tasks/{id}` | GET | Get task details | API key |
| `/api/tasks` | POST | Create task | API key |
| `/api/tasks/{id}` | PUT | Update task | API key |
| `/api/tasks/{id}` | DELETE | Delete task | API key |
| `/api/team` | GET | List team members | API key |

#### Webhook Handler

**File:** `src/main.py` → `telegram_webhook()`

**Flow:**
```python
@app.post("/webhook/telegram")
async def telegram_webhook(update: dict, background_tasks: BackgroundTasks):
    """
    1. Validate Telegram secret token
    2. Parse update (message, callback, reaction)
    3. Add to background tasks (non-blocking)
    4. Return 200 OK immediately
    """

    background_tasks.add_task(process_telegram_update, update)
    return {"status": "ok"}

async def process_telegram_update(update):
    """
    1. Extract message/user info
    2. Route to appropriate handler
    3. Process with AI if needed
    4. Send response
    5. Update database/sheets
    6. Log for audit
    """
```

**Why Background Tasks:**
- Telegram webhooks timeout after 60s
- Some operations (AI, Sheets sync) take time
- Background processing prevents timeouts
- User gets immediate response

---

#### Onboarding Portal (v1.5.2)

**Endpoint:** `/onboard` (GET)

**Purpose:** Self-service team member registration

**Flow:**
```
1. Team member visits /onboard
2. Fills 4-step form:
   Step 1: Name, Role, Email
   Step 2: Telegram ID, Discord ID
   Step 3: Google OAuth (Calendar/Tasks)
   Step 4: Confirmation
3. Submits → Saves to PostgreSQL + Sheets
4. Redirects to confirmation page
```

**OAuth Integration:**
- User clicks "Connect Google"
- Popup opens for Google auth
- Grants Calendar + Tasks permissions
- Returns to form with credentials
- Calendar ID auto-set to email

**UI:** Dark minimalist design, mobile-responsive

---

#### Audit Dashboard (v2.0.5)

**Endpoint:** `/audit` (GET)

**Purpose:** Monitor system health and failed operations

**Displays:**
1. **Message Queue Status**
   - Pending messages count
   - Failed messages count
   - Retry attempts histogram

2. **Dead Letter Queue**
   - Permanently failed messages
   - Error details
   - Retry history

3. **Rate Limit Stats**
   - Requests per user
   - Throttled requests
   - Burst capacity used

4. **Recent Tasks**
   - Last 10 tasks created
   - Status distribution
   - Completion times

**JSON API:** `/api/audit/stats` returns same data as JSON

---

### Utility Modules

**Directory:** `src/utils/`
**Status:** ✅ Production (v1.5.3+)

#### datetime_utils.py

**Purpose:** Consistent timezone handling

| Function | Description |
|----------|-------------|
| `to_naive_local()` | Convert aware datetime to naive local |
| `parse_deadline()` | Parse natural deadline strings |
| `get_local_now()` | Get current time in configured timezone |
| `format_datetime()` | Format for display |

**Fixes:** PostgreSQL offset-naive/aware datetime errors

**Example:**
```python
from src.utils.datetime_utils import parse_deadline

deadline = parse_deadline("tomorrow at 5pm")
# Returns: datetime(2026, 1, 17, 17, 0, 0)

deadline = parse_deadline("next Friday")
# Returns: datetime(2026, 1, 24, 23, 59, 59)
```

---

#### team_utils.py

**Purpose:** Team member lookups with fallback

| Function | Description |
|----------|-------------|
| `get_assignee_info()` | Get full team member data |
| `lookup_team_member()` | 3-tier fallback lookup |
| `get_department_from_role()` | Role → Department mapping |

**3-Tier Fallback:**
```python
def lookup_team_member(name):
    # 1. Try PostgreSQL database
    member = db.get_team_member(name)
    if member:
        return member

    # 2. Try Google Sheets
    member = sheets.get_team_member(name)
    if member:
        return member

    # 3. Try config/team.py
    member = config.TEAM.get(name)
    if member:
        return member

    return None  # Not found
```

**Benefits:** Resilient to database/API failures

---

#### validation_utils.py

**Purpose:** Validate data before saving

| Function | Description |
|----------|-------------|
| `validate_task_data()` | Check task fields |
| `validate_team_data()` | Check team member fields |
| `validate_deadline()` | Ensure deadline is future |
| `validate_priority()` | Check valid priority value |

**Example:**
```python
from src.utils.validation_utils import validate_task_data

task = {
    "title": "Fix bug",
    "priority": "CRITICAL",  # Invalid
    "deadline": "2025-01-01"  # Past
}

errors, warnings = validate_task_data(task)

errors:
  - "Invalid priority: CRITICAL (must be urgent/high/medium/low)"
  - "Deadline is in the past"

warnings:
  - "No assignee specified"
  - "Estimated effort not provided"
```

**Benefits:** Catch errors before database save

---

### Configuration

**File:** `config/settings.py`
**Status:** ✅ Production

#### Environment Variables

**Required:**

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | `123456:ABC-DEF...` |
| `TELEGRAM_BOSS_CHAT_ID` | Boss's Telegram user ID | `987654321` |
| `DEEPSEEK_API_KEY` | DeepSeek AI API key | `sk-...` |
| `GOOGLE_CREDENTIALS_JSON` | Service account JSON (base64) | `eyJ0eXBlIjoi...` |
| `GOOGLE_SHEET_ID` | Google Sheet ID | `1BxiMVs0...` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql://user:pass@host/db` |

**Optional:**

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_BOT_TOKEN` | Discord bot token | None (v1.5.0+) |
| `DISCORD_DEV_FORUM` | Dev forum channel ID | None |
| `DISCORD_DEV_TASKS` | Dev tasks channel ID | None |
| `DISCORD_DEV_REPORT` | Dev report channel ID | None |
| `DISCORD_DEV_GENERAL` | Dev general channel ID | None |
| `OPENAI_API_KEY` | For Whisper transcription | None |
| `GOOGLE_CALENDAR_ID` | Default calendar ID | Boss's email |
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth client ID (v1.5.2) | None |
| `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth secret (v1.5.2) | None |
| `TIMEZONE` | System timezone | `America/New_York` |
| `MORNING_DIGEST_HOUR` | Morning email digest hour | `7` |
| `EVENING_DIGEST_HOUR` | Evening email digest hour | `20` |
| `SUBMISSION_REVIEW_THRESHOLD` | Auto-review pass score | `70` |
| `ENABLE_AUTO_REVIEW` | Enable/disable auto-review | `true` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379` |
| `LOG_LEVEL` | Logging level | `INFO` |

#### Team Configuration

**File:** `config/team.py`

**Purpose:** Code-defined team roster (source of truth)

**Example:**
```python
TEAM = {
    "John": {
        "name": "John Doe",
        "role": "Developer",
        "email": "john@example.com",
        "telegram_id": 123456789,
        "discord_id": "987654321098765432",
        "calendar_id": "john@example.com",
        "timezone": "America/New_York",
        "work_start": "09:00",
        "skills": ["React", "Python", "FastAPI"]
    },
    "Sarah": {
        "name": "Sarah Smith",
        "role": "Developer",
        "email": "sarah@example.com",
        "telegram_id": 234567890,
        "discord_id": "876543210987654321",
        "calendar_id": "sarah@example.com",
        "timezone": "America/Los_Angeles",
        "work_start": "09:00",
        "skills": ["Design", "Frontend", "UX"]
    },
    "Mayank": {
        "name": "Mayank Patel",
        "role": "Developer",
        "email": "mayank@example.com",
        "telegram_id": 345678901,
        "discord_id": "765432109876543210",
        "calendar_id": "mayank@example.com",
        "timezone": "Asia/Kolkata",
        "work_start": "10:00",
        "skills": ["Backend", "APIs", "Stripe"]
    },
    "Minty": {
        "name": "Minty Lee",
        "role": "Admin",
        "email": "sutima2543@gmail.com",
        "telegram_id": None,
        "discord_id": "834982814910775306",
        "calendar_id": "sutima2543@gmail.com",
        "timezone": "Asia/Bangkok",
        "work_start": "09:00",
        "skills": ["Admin", "Operations"]
    }
}

# Department → Roles mapping
DEPARTMENTS = {
    "Dev": ["Developer"],
    "Admin": ["Admin"],
    "Marketing": ["Marketing Manager", "Content Writer"],
    "Design": ["Designer", "UX Designer"]
}
```

**Sync Command:** `/syncteam` → Copies to PostgreSQL + Google Sheets

---

## Team Features

### Time Clock / Attendance System

**Status:** ✅ Production (v1.5.4+)
**Files:** `src/services/attendance.py`, `src/database/repositories/attendance.py`

#### Features

**1. Discord Check-in/Check-out**
   - Staff post "in", "out", "break" in attendance channels
   - Bot detects and records events
   - Adds reactions: ✅ (in), 👋 (out), ☕ (break on), 💪 (break off)

**2. Late Detection**
   - Compares check-in time to configured work start
   - Grace period: 15 minutes (configurable)
   - Adds ⏰ reaction if late
   - Timezone-aware calculations

**3. Break Toggle**
   - Single "break" message toggles break on/off
   - ☕ reaction = break started
   - 💪 reaction = break ended
   - Tracks break duration

**4. Google Sheets Sync**
   - Records sync to "⏰ Time Logs" sheet
   - Scheduled job every 15 minutes
   - Shows: Name, Date, Check In, Check Out, Break Duration, Total Hours, Status

**5. Weekly Reports**
   - Generated every Monday 10 AM
   - Saved to "📊 Time Reports" sheet
   - Shows: Weekly hours, Late count, Average hours/day

#### Discord Channels

| Department | Channel Name | Channel ID |
|------------|--------------|------------|
| **Dev** | dev-attendance | `1462451610184843449` |
| **Admin** | admin-attendance | `1462451782470078628` |

*Marketing and Design not yet configured*

#### Attendance Commands

**Team Members:**
- `"in"` - Check in
- `"out"` - Check out
- `"break"` - Toggle break (on/off)

**Boss:**
- `/timesheet` - View your timesheet
- `/timesheet @name` - View someone's timesheet
- `/timesheet team` - View full team timesheet
- `/timesheet week` - This week's summary

#### Database Schema

**Table:** `attendance_records`

| Column | Type | Description |
|--------|------|-------------|
| `id` | String | ATT-001 |
| `user_name` | String | Team member |
| `user_telegram_id` | BigInteger | Telegram ID |
| `user_discord_id` | String | Discord ID |
| `event_type` | String | check_in/check_out/break_start/break_end |
| `timestamp` | DateTime | When event occurred (timezone-aware) |
| `location` | String | Optional GPS |
| `notes` | String | Optional notes |
| `is_late` | Boolean | Late check-in? |
| `late_minutes` | Integer | How many min late |
| `date` | Date | For daily grouping |

#### Clock-out Reminder (v2.0.5)

**Feature:** When staff clocks out, system shows reminder of pending tasks

**Message:**
```
👋 You're clocking out for the day!

📋 Reminder - You still have these tasks:

🚧 In Progress:
  • TASK-001: Fix login bug (Due: Tomorrow)
  • TASK-008: API integration (Due: Jan 20)

📋 Pending:
  • TASK-015: Email template (Due: Jan 18)

Have a great evening! 🌙
```

**Implementation:** `src/services/attendance.py` (clock_out_reminder)

---

## Future Upgrades & Roadmap

### Completed Phases

#### ✅ Phase 1: Quick Wins (v1.1)
- Task Templates
- Discord Reaction Status Updates
- Task Search
- Bulk Status Updates
- Smart Dependencies

#### ✅ Phase 2: Medium Effort (v1.2)
- Recurring Tasks
- Time Tracking
- Subtasks
- Voice Commands (Whisper)

#### ✅ Phase 3: Major Features (v1.3+)
- PostgreSQL Backend
- AI Task Breakdown
- Image Vision Analysis
- Channel-Based Discord (v1.5.0)
- Time Clock/Attendance (v1.5.4)
- Advanced Automation (v2.0.5)

---

### Planned Features

#### 🔴 Priority 1: Team Member Bot Access

**Status:** Not Started
**Effort:** High
**Impact:** VERY HIGH

**Description:**
Multi-user Telegram bot access where team members interact directly

**Features:**
- Each member links Telegram to profile
- Members receive task assignments directly
- Members can `/done`, `/block`, `/note` their tasks
- Members submit proofs directly
- Boss sees all, members see only their tasks
- Permission system (boss vs team member)

**Implementation Plan:**
1. User authentication layer
2. Permission system (role-based)
3. Multi-user message routing
4. Privacy filters (members see only own tasks)
5. Task assignment notifications
6. Status update commands for members

**Database Changes:**
- Add `user_permissions` table
- Add `telegram_auth_tokens` table
- Update `team_members` with telegram linkage

**Why High Priority:**
- Unlocks true workflow automation
- Eliminates manual bottlenecks
- Real-time team collaboration
- Market differentiator

---

#### 🔴 Priority 2: Web Dashboard

**Status:** Not Started
**Effort:** High
**Impact:** VERY HIGH

**Description:**
React/Next.js dashboard for visual task management

**Features:**
- Kanban board view (drag & drop)
- Gantt chart for timelines
- Team workload visualization
- Burndown charts
- Real-time updates (WebSocket)
- Mobile-responsive
- Dark/light theme

**Pages:**
1. **Dashboard** - Overview metrics, charts
2. **Tasks** - Kanban board
3. **Timeline** - Gantt view
4. **Team** - Team performance
5. **Reports** - Analytics
6. **Calendar** - Calendar view
7. **Settings** - Configuration

**Tech Stack:**
- Frontend: Next.js 14, React, TailwindCSS
- State: Zustand or Jotai
- Real-time: Socket.IO
- Charts: Recharts or Chart.js
- Backend API: Existing FastAPI endpoints

**Authentication:**
- OAuth 2.0 with Google
- Role-based access (boss vs team)
- API key for programmatic access

---

#### 🔴 Priority 3: Smart Assignee Suggestion

**Status:** Not Started
**Effort:** Medium
**Impact:** Medium-High

**Description:**
AI suggests best person for each task based on skills, workload, performance

**Algorithm:**
```python
def suggest_assignee(task):
    candidates = []

    for member in team:
        score = 0

        # 1. Skills match (40%)
        if task_requires_skill(task, member.skills):
            score += 40

        # 2. Workload (30%)
        active_count = get_active_tasks(member)
        if active_count < 3:
            score += 30
        elif active_count < 5:
            score += 20
        else:
            score += 10

        # 3. Past performance (20%)
        completion_rate = get_completion_rate(member)
        score += completion_rate * 20

        # 4. Availability (10%)
        if member.status == "active":
            score += 10

        candidates.append((member, score))

    # Sort by score, return top 3
    return sorted(candidates, key=lambda x: x[1], reverse=True)[:3]
```

**UI:**
```
Boss: "Need someone to fix the React dashboard"

Bot: "Based on skills and workload, I suggest:

      1. ⭐ Sarah (Score: 95)
         • Skills: React, Frontend (perfect match)
         • Workload: 2 active tasks (light)
         • Completion rate: 92%

      2. John (Score: 75)
         • Skills: React, Backend (partial match)
         • Workload: 4 active tasks (moderate)
         • Completion rate: 88%

      3. Mike (Score: 60)
         • Skills: JavaScript (related)
         • Workload: 3 active tasks (moderate)
         • Completion rate: 85%

      Who should I assign? (reply with name or number)"
```

**Data Requirements:**
- Team skills (already in config/team.py)
- Active task counts (query database)
- Historical completion rates (calculate from database)
- Availability status (from Team sheet)

---

#### 🔴 Priority 4: Analytics & Intelligence

**Status:** Not Started
**Effort:** High
**Impact:** High (long-term)

**Features:**

**1. Velocity Tracking**
- Track story points or task counts per sprint/week
- Calculate team velocity
- Capacity planning

**2. Burndown Charts**
- Visual progress toward sprint goals
- Ideal vs actual burndown
- Predict completion date

**3. Prediction Engine**
- ML model trained on past tasks
- "Based on history, this will take 3 days"
- Factors: task type, assignee, complexity

**4. Bottleneck Detection**
- Identify where tasks get stuck
- Suggest process improvements
- "Tasks in 'in_review' status take 2x longer on average"

**5. Auto-Prioritization**
- Dynamically adjust priority based on:
  - Deadline proximity
  - Dependencies
  - Business value
  - Risk

**ML Models:**
- Task duration prediction (regression)
- Priority recommendation (classification)
- Bottleneck detection (anomaly detection)

**Implementation:**
- Collect data: 3-6 months of task history
- Train models: scikit-learn or XGBoost
- API endpoints: `/predict/duration`, `/predict/priority`
- Dashboard: Analytics tab

---

#### 🔴 Priority 5: Slack Integration

**Status:** Not Started
**Effort:** Medium
**Impact:** Medium

**Description:**
Mirror Discord functionality to Slack

**Features:**
- Task embeds in Slack channels
- Slash commands (`/task`, `/status`)
- Reaction-based status updates
- Thread-based task discussions
- Slack OAuth for team members

**Slack Workspace Structure:**
```
#dev-tasks (simple tasks)
#dev-specs (detailed specs, threads)
#dev-report (standup, weekly)
#admin-tasks
#admin-report
...
```

**Commands:**
- `/task [description]` - Create task
- `/status` - View tasks
- `/submit [task-id]` - Submit work

**Implementation:**
- Slack SDK for Python
- Webhook endpoints for events
- OAuth 2.0 for authentication
- Mirror `src/integrations/discord.py` structure

---

### Implementation Priority Matrix

| Priority | Feature | Effort | Impact | Status | Start Date |
|----------|---------|--------|--------|--------|------------|
| 1 | Task Templates | Low | High | ✅ Done | - |
| 2 | Discord Reactions | Low | High | ✅ Done | - |
| 3 | Task Search | Low | Medium | ✅ Done | - |
| 4 | Bulk Updates | Low | Medium | ✅ Done | - |
| 5 | Smart Dependencies | Medium | High | ✅ Done | - |
| 6 | Recurring Tasks | Medium | High | ✅ Done | - |
| 7 | Time Tracking | Medium | Medium | ✅ Done | - |
| 8 | **Team Bot Access** | High | **Very High** | 🔴 Planned | Q1 2026 |
| 9 | PostgreSQL | High | High | ✅ Done | - |
| 10 | Subtasks Commands | Medium | Medium | ✅ Done | - |
| 11 | Voice Commands | Medium | Medium | ✅ Done | - |
| 12 | **Web Dashboard** | High | **Very High** | 🔴 Planned | Q2 2026 |
| 13 | AI Task Breakdown | Medium | High | ✅ Done | - |
| 14 | Smart Assignee | Medium | Medium-High | 🔴 Planned | Q2 2026 |
| 15 | Analytics Engine | High | High | 🔴 Planned | Q3 2026 |
| 16 | Slack Integration | Medium | Medium | 🔴 Planned | Q3 2026 |

---

## Version History

### Latest Versions

| Version | Date | Key Changes |
|---------|------|-------------|
| **2.2.0** | 2026-01-23 | **🧠 SMART AI v2.2:** Complexity detection (1-10 score), role-aware routing (Mayank→DEV, Zea→ADMIN), keyword-based role inference, intelligent self-answering. **🔧 COMPREHENSIVE TASK OPS:** 13 new intents for natural language task modifications |
| **2.0.5** | 2026-01-21 | **🚀 ADVANCED AUTOMATION:** Proactive check-ins, stricter validation, clock-out reminders, pattern learning, message retry queue, rate limiting, audit dashboard |
| **2.0.2** | 2026-01-21 | Fixed deadline reminder spam with deduplication system |
| **2.0.1** | 2026-01-21 | AI reformulation for team messages, better Discord ID lookup |
| **2.0.0** | 2026-01-20 | **🧠 AI-FIRST INTENT:** Complete rewrite - AI classifies ALL natural language, no more regex |
| **1.8.3** | 2026-01-20 | Direct team communication via Discord (ASK_TEAM_MEMBER intent) |
| **1.8.2** | 2026-01-20 | Preserve task details, better deadline parsing |
| **1.8.0** | 2026-01-20 | Major architecture rewrite with TaskProcessor (4-step flow) |
| **1.7.6** | 2026-01-20 | Anti-hallucination system with validation |
| **1.7.5** | 2026-01-20 | Single-assignee multi-task support with ordinal patterns |
| **1.7.2** | 2026-01-20 | Mandatory self-answering AI loop |
| **1.7.1** | 2026-01-20 | "No questions" override, Discord error feedback |
| **1.7.0** | 2026-01-20 | Intelligent self-answering AI loop |
| **1.6.6** | 2026-01-20 | Skip questions when details already provided |
| **1.5.4** | 2026-01-18 | Time Clock/Attendance system with late detection |
| **1.5.2** | 2026-01-18 | Web onboarding portal with Google OAuth |
| **1.5.0** | 2026-01-18 | **MAJOR:** Channel-based Discord with Bot API (not webhooks) |
| **1.4.0** | 2026-01-18 | Discord forum, sequential multi-task, SPECSHEETS mode |
| **1.3.1** | 2026-01-17 | Image vision analysis with DeepSeek VL |
| **1.3.0** | 2026-01-17 | AI task breakdown |
| **1.2.1** | 2026-01-17 | Discord bot reaction listener |
| **1.2.0** | 2026-01-17 | Recurring tasks, time tracking, subtasks, voice commands |
| **1.1.0** | 2026-01-17 | PostgreSQL, templates, search, bulk ops, smart dependencies |
| **1.0.0** | 2026-01-17 | Initial release |

For complete version history, see lines 2137-2182 in this document.

---

## Quick Start Checklist

**For New Team Members:**

- [ ] Read this FEATURES.md (you are here!)
- [ ] Read CLAUDE.md for plugin workflows
- [ ] Check `.env.example` for required env vars
- [ ] Run `python -m src.main` to start locally
- [ ] Test with `/help` in Telegram
- [ ] Visit `/onboard` to register your profile
- [ ] Check Discord channels are configured
- [ ] Run `python test_all.py` to verify tests pass

**For New Features:**

- [ ] Check this file to avoid duplication
- [ ] Update CLAUDE.md if adding new workflows
- [ ] Write tests in `test_*.py`
- [ ] Update this FEATURES.md (LAST step!)
- [ ] Increment version number
- [ ] Add to Version History section

---

## Documentation Standards

### When Adding Features

**1. Update This File**
- Add to appropriate section
- Include code examples
- Document all parameters
- Add to Quick Reference if commonly used
- Update Version History

**2. Code Documentation**
```python
def new_feature(param1: str, param2: int) -> dict:
    """
    Brief one-line description.

    Detailed explanation of what this does, why it exists,
    and how it fits into the system.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        dict: Description of return value

    Raises:
        ValueError: When param1 is invalid

    Example:
        >>> result = new_feature("test", 42)
        >>> print(result)
        {'success': True}

    Note:
        Added in v2.1.0
    """
```

**3. Test Coverage**
- Unit tests for core logic
- Integration tests for workflows
- Document test cases in docstrings

---

## Support & Troubleshooting

### Common Issues

**Issue:** Telegram bot not responding
**Solution:** Check `TELEGRAM_BOT_TOKEN` and webhook setup

**Issue:** Google Sheets not syncing
**Solution:** Verify `GOOGLE_CREDENTIALS_JSON` and Sheet ID

**Issue:** Discord embeds not posting
**Solution:** Check Discord channel IDs and bot permissions

**Issue:** AI responses are off
**Solution:** Check `DEEPSEEK_API_KEY` balance and rate limits

**Issue:** Tasks not archiving
**Solution:** Check scheduler is running (`scheduler/jobs.py`)

### Debug Mode

**Enable verbose logging:**
```bash
export LOG_LEVEL=DEBUG
python -m src.main
```

**Check logs:**
```bash
# Railway
railway logs -s boss-workflow

# Local
tail -f logs/boss-workflow.log
```

---

## Repository Info

**GitHub:** https://github.com/outwareai/boss-workflow
**Deployment:** Railway (auto-deploy on push to main)
**License:** MIT

---

*This document is automatically referenced by Claude Code. Always read this file first when working on the project, and update it last after making changes.*

**Last Major Revision:** 2026-01-21 (v2.0.5)
**Next Planned Update:** Team Bot Access implementation (Q1 2026)
