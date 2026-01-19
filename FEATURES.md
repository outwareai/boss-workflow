# Boss Workflow Automation - Features Documentation

> **Last Updated:** 2026-01-19
> **Version:** 1.5.8

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
14. [Utility Modules](#utility-modules-new-in-v153)
15. [Time Clock / Attendance System](#time-clock--attendance-system-new-in-v154)
16. [Configuration](#configuration)
17. [Future Upgrades & Roadmap](#future-upgrades--roadmap)

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

### Multi-Task Handling (NEW in v1.4)

When you send multiple tasks in one message, the bot handles them **sequentially**:

```
You: "John fix the login bug, then Sarah update the homepage, and Mike review the API"

Bot: "📋 Task 1 of 3
      [Shows first task preview]

      yes = create & next | skip = skip & next | no = cancel all"

You: "yes"

Bot: "✅ Task 1 created!

      📋 Task 2 of 3
      [Shows second task preview]..."
```

**Separators detected:** "then", "and also", "another task", "next task", numbered lists

### SPECSHEETS Mode (NEW in v1.4)

Trigger detailed specification generation with keywords:

```
You: "SPECSHEETS detailed for: Build authentication system for John"
```

**Trigger keywords:** `specsheet`, `spec sheet`, `detailed spec`, `detailed for:`, `full spec`, `comprehensive`, `more developed`, `more detailed`, `with details`

**Generates:**
- Multi-paragraph description (3-5 paragraphs)
- 4-6 detailed acceptance criteria
- Comprehensive subtask breakdown with implementation details
- Technical considerations

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
| `/syncteam` | Sync team from config/team.py to Sheets + DB | `/syncteam` |
| `/syncteam --clear` | Clear mock data first, then sync | `/syncteam --clear` |
| `/clearteam` | Clear all data from Team sheet | `/clearteam` |
| `/teach [instruction]` | Teach bot preferences | `/teach When I say ASAP, deadline is 4 hours` |
| `/preferences` | View saved preferences | `/preferences` |

### Task Operations

| Command | Description | Example |
|---------|-------------|---------|
| `/note [task-id] [content]` | Add note to task | `/note TASK-001 Waiting for API docs` |
| `/delay [task-id] [deadline] [reason]` | Postpone task | `/delay TASK-001 tomorrow Client request` |
| `/templates` | View available task templates | `/templates` |

### Search & Filter (NEW in v1.1)

| Command | Description | Example |
|---------|-------------|---------|
| `/search [query]` | Search tasks by keyword | `/search login bug` |
| `/search @name` | Find tasks by assignee | `/search @John` |
| `/search #priority` | Filter by priority | `/search #urgent` |
| `/search status:X` | Filter by status | `/search status:blocked` |
| `/search due:X` | Filter by deadline | `/search due:today` |

### Bulk Operations (NEW in v1.1)

| Command | Description | Example |
|---------|-------------|---------|
| `/complete ID ID ID` | Mark multiple tasks done | `/complete TASK-001 TASK-002` |
| `/block ID ID [reason]` | Block multiple tasks | `/block TASK-001 TASK-002 API down` |
| `/assign @name ID ID` | Assign tasks to someone | `/assign @Sarah TASK-003 TASK-004` |

### Recurring Tasks (NEW in v1.2)

| Command | Description | Example |
|---------|-------------|---------|
| `/recurring "title" pattern time` | Create recurring task | `/recurring "Weekly standup" every:monday 9am` |
| `/recurring list` | List all recurring tasks | `/recurring list` |
| `/recurring pause REC-ID` | Pause a recurring task | `/recurring pause REC-001` |
| `/recurring resume REC-ID` | Resume paused recurring | `/recurring resume REC-001` |
| `/recurring delete REC-ID` | Delete recurring task | `/recurring delete REC-001` |

**Recurrence Patterns:**
- Daily: `every:day`
- Weekdays only: `every:weekday`
- Weekly: `every:monday`, `every:monday,wednesday,friday`
- Monthly: `every:1st`, `every:15th`, `every:last`
- Interval: `every:2weeks`, `every:3days`

### Time Tracking (NEW in v1.2)

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
- Hours and minutes: `2h30m`
- Hours with decimal: `1.5h`
- Minutes only: `45m`
- Days: `1d` (= 8 hours)

### Subtasks (NEW in v1.2)

| Command | Description | Example |
|---------|-------------|---------|
| `/subtask TASK-ID "title"` | Add subtask to a task | `/subtask TASK-001 "Design mockup"` |
| `/subtasks TASK-ID` | List subtasks for a task | `/subtasks TASK-001` |
| `/subdone TASK-ID #num` | Mark subtask complete | `/subdone TASK-001 1` |
| `/subdone TASK-ID all` | Mark all subtasks done | `/subdone TASK-001 all` |
| `/breakdown TASK-ID` | AI-powered task breakdown (NEW v1.3) | `/breakdown TASK-001` |

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
| `SEARCH_TASKS` | "What's John working on?" | Searches and filters tasks |
| `BULK_COMPLETE` | "Mark these 3 as done" | Bulk status update |
| `LIST_TEMPLATES` | "What templates are available?" | Shows task templates |
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
- **Task Template Detection** (NEW v1.1): Auto-detects keywords like "bug:", "hotfix:", "feature:" and applies template defaults
- **Smart Dependency Detection** (NEW v1.1): AI analyzes existing tasks to suggest potential dependencies before task creation

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

### Voice Transcription (NEW in v1.2) (`src/ai/transcriber.py`)

| Function | Description |
|----------|-------------|
| `transcribe()` | Convert audio to text using OpenAI Whisper |
| `transcribe_with_context()` | Transcribe with context prompt for better accuracy |
| `transcribe_voice_message()` | Convenience wrapper for Telegram voice messages |

**Features:**
- OpenAI Whisper API integration
- Task management context prompts ("assignments, deadlines, priorities")
- Automatic temp file handling
- Supports OGG, MP3, WAV, and other audio formats
- Requires `OPENAI_API_KEY` environment variable

**Usage:**
1. Send voice message in Telegram
2. Bot transcribes using Whisper
3. Shows transcription: `📝 "Create urgent task for John"`
4. Processes as normal text command

### Image Vision Analysis (NEW in v1.3) (`src/ai/vision.py`)

| Function | Description |
|----------|-------------|
| `analyze_image()` | Analyze image with custom prompt |
| `analyze_screenshot()` | Extract structured info from screenshots |
| `analyze_proof()` | Validate proof images for task completion |
| `extract_text()` | OCR text extraction from images |
| `describe_for_task()` | Analyze image in task creation context |

**Features:**
- DeepSeek VL (Vision-Language) model integration
- Automatic base64 encoding for API calls
- Context-aware analysis prompts
- Proof validation with relevance assessment
- Integration with auto-review system

**Usage:**
1. Send photo in Telegram
2. Bot shows: `🔍 Analyzing image...`
3. Vision AI describes what's in the image
4. Analysis is included in task context or proof review

**Proof Analysis:**
When submitting proof screenshots:
1. Send screenshot as proof
2. Vision AI analyzes what the screenshot shows
3. Analysis preview shown: `🔍 _AI Analysis: Shows completed login page..._`
4. Analysis included in boss notification
5. Auto-reviewer uses vision analysis for quality scoring

### AI Task Breakdown (NEW in v1.3) (`src/ai/deepseek.py`)

| Function | Description |
|----------|-------------|
| `breakdown_task()` | Analyze task and generate subtask suggestions |

**Features:**
- Analyzes task title, description, type, and acceptance criteria
- Generates 3-8 logical subtasks with effort estimates
- Detects if task is too simple for breakdown
- Shows dependencies between subtasks
- Confirms before creating subtasks

**Usage:**
```
/breakdown TASK-001
```

**Example Output:**
```
AI Task Breakdown: TASK-001
"Build user authentication system"

Analysis: This is a multi-step feature requiring backend, frontend, and testing work.

Suggested Subtasks:
1. Design auth flow diagram ~30min
2. Create database schema for users ~1h
3. Implement login/register API ~2h (after #2)
4. Build frontend login form ~2h (after #3)
5. Add password reset flow ~1h (after #3)
6. Write integration tests ~1h (after #4, #5)

Total Estimated Effort: 7h 30m

Create these subtasks? Reply yes or no.
```

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
| `search_tasks()` | Search with filters (query, assignee, status, priority, due) |
| `bulk_update_status()` | Update status for multiple tasks at once |
| `bulk_assign()` | Assign multiple tasks to a person |

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

### Channel-Based Bot API (NEW in v1.5.0)

**MAJOR CHANGE:** Discord integration now uses Bot API with Channel IDs instead of webhooks. This provides full permissions for message management, thread creation/deletion, and @mentions.

### Features (`src/integrations/discord.py`)

| Function | Description |
|----------|-------------|
| `send_message()` | Send message to any channel |
| `edit_message()` | Edit existing message |
| `delete_message()` | Delete message from channel |
| `create_forum_thread()` | Create forum post with embed |
| `delete_thread()` | Delete thread/forum post |
| `add_reaction()` | Add reaction to message |
| `get_channel_threads()` | List all threads in channel |
| `bulk_delete_threads()` | Delete threads matching prefix |
| `post_task()` | Smart task posting (forum or text) |
| `post_spec_sheet()` | Detailed spec as forum thread |
| `post_standup()` | Daily standup to report channel |
| `post_weekly_summary()` | Weekly report embed |
| `post_alert()` | Alerts to tasks channel |
| `post_general_message()` | Post to general channel |
| `post_help()` | Help message with reaction guide |
| `cleanup_task_channel()` | Clean all task threads |

### Channel Structure (Per Department)

Each department (Dev, Admin, Marketing, Design) has 4 dedicated channels:

| Channel Type | Purpose | Content |
|--------------|---------|---------|
| **Forum** | Detailed specs, creates threads per task | Spec sheets, complex tasks |
| **Tasks** | Regular tasks, status updates | Simple tasks, overdue alerts, cancellations |
| **Report** | Standup and reports | Daily standup, weekly summary |
| **General** | General messages | Help, announcements |

### Channel Configuration

**Dev Category (Primary - configured):**
```bash
DISCORD_DEV_FORUM_CHANNEL_ID=1459834094304104653
DISCORD_DEV_TASKS_CHANNEL_ID=1461760665873158349
DISCORD_DEV_REPORT_CHANNEL_ID=1461760697334632651
DISCORD_DEV_GENERAL_CHANNEL_ID=1461760791719182590
```

**Other Categories (Future - set when needed):**
- `DISCORD_ADMIN_*_CHANNEL_ID` - Admin department
- `DISCORD_MARKETING_*_CHANNEL_ID` - Marketing department
- `DISCORD_DESIGN_*_CHANNEL_ID` - Design department

### Role-Based Routing

Tasks are automatically routed to department channels based on assignee's role:

| Role Keywords | Target Category |
|---------------|-----------------|
| developer, backend, frontend, engineer, qa, devops | Dev |
| admin, administrator, manager, lead, director | Admin |
| marketing, content, social, growth, seo, ads | Marketing |
| designer, ui, ux, graphic, creative, artist | Design |

**How it works:**
1. Task created with assignee
2. System looks up assignee's role from database
3. Routes to matching department's channels
4. Falls back to Dev category if no match

### Content Routing

Within each department, content goes to appropriate channel:

| Content Type | Target Channel |
|--------------|----------------|
| Detailed specs, complex tasks | Forum (creates thread) |
| Simple tasks, overdue, cancelled | Tasks |
| Daily standup, weekly summary | Report |
| Help, announcements | General |

### Discord Bot Reaction Listener

The system includes a full Discord bot (`src/integrations/discord_bot.py`) that listens for reactions on task messages and automatically updates task status.

**Setup Requirements:**
- `DISCORD_BOT_TOKEN` - Bot token from Discord Developer Portal
- Bot needs `MESSAGE_CONTENT`, `GUILD_REACTIONS`, `GUILDS`, `GUILD_MEMBERS` intents enabled

**Reaction to Status Mapping:**

| Reaction | Status |
|----------|--------|
| ✅ | completed |
| 🚧 | in_progress |
| 🚫 | blocked |
| ⏸️ | on_hold |
| 🔄 | in_review |
| ❌ | cancelled |
| ⏳ | pending |
| 👀 | in_review |
| 🔴 | urgent (changes priority) |

### Embed Format

- Task ID and title
- Priority emoji (🟢🟡🟠🔴)
- Status with emoji
- Assignee with Discord @mention
- Deadline
- Estimated effort
- Acceptance criteria with checkmarks
- Pinned notes
- Delay reason if delayed

### @Mention Format

Team members must have numeric Discord user IDs in `config/team.py`:
```python
"discord_id": "392400310108291092",  # Numeric ID, not username
```
To get numeric ID: Discord Developer Mode → Right-click user → Copy ID

### Discord Cleanup Command

`/cleandiscord [channel_id]` - Delete all task threads from a channel

```
/cleandiscord                    # Uses default dev forum channel
/cleandiscord 1459834094304104653  # Specific channel
```

### Legacy Webhooks (Deprecated)

Webhooks are still supported for backward compatibility but not recommended:
- `DISCORD_WEBHOOK_URL`
- `DISCORD_TASKS_CHANNEL_WEBHOOK`
- `DISCORD_STANDUP_CHANNEL_WEBHOOK`
- `DISCORD_SPECS_CHANNEL_WEBHOOK`

---

## Google Calendar Integration

### Features (`src/integrations/calendar.py`)

| Function | Description |
|----------|-------------|
| `create_task_event()` | Add task deadline to assignee's personal calendar |
| `update_task_event()` | Modify event if deadline changes |
| `delete_task_event()` | Remove event if task cancelled |
| `get_events_today()` | Retrieve today's events |
| `get_upcoming_deadlines()` | Get tasks due within X hours |
| `create_reminder_event()` | Create standalone reminder |
| `get_daily_schedule()` | Get all events for a day |

### Per-User Calendar Support (NEW in v1.5.1)

Events are created directly on the assignee's personal Google Calendar when:
1. Staff member shares their calendar with the service account
2. Their Calendar ID is stored in the Team sheet

**Setup for Staff Members:**

1. **Share Calendar with Service Account:**
   - Open Google Calendar → Settings → Select your calendar
   - Under "Share with specific people", add:
     `tasking-boss-bot@tasking-boss-bot.iam.gserviceaccount.com`
   - Give "Make changes to events" permission

2. **Get Calendar ID:**
   - In Calendar Settings → "Integrate calendar"
   - Copy the Calendar ID (usually your email, or a long string ending in @group.calendar.google.com)

3. **Add to Team Sheet:**
   - Open the 👥 Team sheet
   - Add the Calendar ID in the "Calendar ID" column for that team member

**How It Works:**
```
Task Created for Minty →
  System looks up Minty's Calendar ID from Sheets →
  Creates event on Minty's personal calendar →
  Minty sees task deadline directly in her Google Calendar
```

**Fallback Behavior:**
- If no Calendar ID configured: Event created on default (primary) calendar
- If calendar not shared: Error logged, event creation fails gracefully
- Email invites still sent as attendees if email configured

### Event Properties

- Color-coded by priority (Green/Yellow/Orange/Red)
- Multi-step reminders based on priority:
  - Low: 1 hour before
  - Medium: 1 hour, 30 min before
  - High: 2 hours, 1 hour, 30 min before
  - Urgent: 4 hours, 2 hours, 1 hour, 30 min before
- Description includes: task description, assignee, acceptance criteria, task ID
- Status prefix in title: ⏰ DELAYED or 🚨 OVERDUE

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

## Web Onboarding Portal (NEW in v1.5.2)

### Staff Self-Service Onboarding

A web-based onboarding page for new team members to register themselves.

**URL:** `https://boss-workflow-production.up.railway.app/onboard`

### Features (`src/web/routes.py`)

| Endpoint | Description |
|----------|-------------|
| `/onboard` | Staff onboarding form (4-step wizard) |
| `/team` | View team members list |
| `/auth/google/calendar` | Google Calendar OAuth flow |
| `/auth/google/tasks` | Google Tasks OAuth flow |
| `/api/onboard` | Form submission API |

### Onboarding Flow

**Step 1: Basic Information**
- Full name
- Email address
- Role/Department (Developer, Admin, Marketing, Designer, etc.)

**Step 2: Discord Setup**
- Discord User ID (with instructions to get it)
- Optional Discord username

**Step 3: Google Integration**
- Connect Google Calendar (OAuth2)
- Connect Google Tasks (OAuth2)
- Both are optional

**Step 4: Confirmation**
- Review details
- Complete setup

### What Happens on Submit

1. Staff info saved to 👥 Team sheet
2. Staff info saved to PostgreSQL database
3. Google OAuth tokens stored (if connected)
4. Staff appears in system immediately

### Google OAuth Setup Required

To enable "Connect Google Calendar/Tasks" buttons:

1. Go to Google Cloud Console → APIs & Services → OAuth consent screen
2. Create consent screen (External type for personal accounts)
3. Add scopes: `calendar`, `tasks`
4. Create OAuth2 credentials (Web application)
5. Add redirect URI: `https://boss-workflow-production.up.railway.app/auth/google/callback`
6. Set environment variables:
   - `GOOGLE_OAUTH_CLIENT_ID`
   - `GOOGLE_OAUTH_CLIENT_SECRET`

### Design

Dark minimalist theme matching outsupplements.com:
- Dark background (#0a0a0a)
- Card style (#1a1a1a)
- Green accent (#4ade80)
- Inter font family
- Step indicator with progress
- Mobile responsive

---

## Scheduler & Automation

### Scheduled Jobs (`src/scheduler/jobs.py`)

| Job | Schedule | Description |
|-----|----------|-------------|
| `daily_standup_job` | 9 AM daily | Summary of today's tasks + comprehensive email digest (Telegram only) |
| `eod_reminder_job` | 6 PM daily | Pending/overdue tasks, tomorrow's priorities |
| `weekly_summary_job` | Friday 5 PM | Team performance, completed vs pending, trends |
| `monthly_report_job` | 1st of month 9 AM | Monthly analytics, productivity insights |
| `deadline_reminder` | 2 hours before | Reminder to assignee and boss |
| `overdue_alert` | Every 4 hours | Lists overdue tasks with days count |
| `conversation_cleanup` | Every 5 minutes | Auto-finalize timed-out conversations |
| `recurring_tasks_job` | Every 5 minutes | Create task instances from recurring templates (NEW v1.2) |
| `morning_digest` | 10 AM | Email summary for morning (Telegram only) |
| `evening_digest` | 9 PM | Email summary for evening (Telegram only) |
| `sync_attendance` | Every 15 minutes | Sync attendance records from PostgreSQL to Google Sheets (NEW v1.5.4) |
| `weekly_time_report` | Monday 10 AM | Generate weekly time/attendance report for all staff (NEW v1.5.4) |

### Email Digest in Daily Standup (NEW in v1.4.1)

After the daily standup message, a **separate comprehensive email summary** is automatically sent to Telegram (boss only, not Discord).

**Features:**
- Sent as separate message right after task standup
- Only goes to Telegram (boss) - not Discord
- Shows email overview (total, unread, important counts)
- AI-powered summary of key emails
- Extracted action items
- Priority emails highlighted
- List of latest 15 emails with status icons

**Requirements:**
- Set `ENABLE_EMAIL_DIGEST=true` in environment
- Gmail must be configured (run `python setup_gmail.py` first)

**Example Output:**
```
📧 Comprehensive Email Summary

📊 Overview
• Total: 12 emails
• Unread: 5 🔵
• Important: 2 ⭐

📝 AI Summary
[AI-generated summary of key emails...]

📌 Action Items
• Reply to client about proposal by EOD
• Review contract draft from legal

🚨 Priority Emails
• John Smith: Urgent - Production issue needs attention

📬 Latest Emails
1. 🔵 ⭐ John Smith: Urgent - Production issue
2. 🔵 Client Name: Re: Proposal feedback
3. Sarah: Weekly report ready for review
...
```

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

**Task Templates (NEW in v1.1):**

| Template | Auto-fills |
|----------|------------|
| `bug` | type=bug, priority=high, tags=["bugfix"] |
| `hotfix` | type=bug, priority=urgent, deadline=4 hours |
| `feature` | type=feature, effort="1 day", tags=["feature"] |
| `research` | type=research, priority=low |
| `meeting` | type=meeting, effort="1 hour" |
| `docs` | type=task, priority=low, tags=["documentation"] |
| `refactor` | type=task, priority=low, tags=["refactor", "tech-debt"] |
| `test` | type=task, priority=medium, tags=["testing"] |

Templates are auto-detected from natural language (e.g., "bug: login crashes" triggers bug template).

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
| `recurring_tasks` | Recurring task templates (NEW v1.2) | recurring_id, title, pattern, time, next_run, is_active, instances_created |
| `time_entries` | Time tracking log (NEW v1.2) | entry_id, task_id, user_id, started_at, ended_at, duration_minutes, entry_type |
| `active_timers` | Currently running timers (NEW v1.2) | user_id, time_entry_id, task_ref, started_at |

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

## Utility Modules (NEW in v1.5.3)

Centralized utilities for consistent behavior across the application.

### Datetime Utilities (`src/utils/datetime_utils.py`)

All datetime handling uses these functions to ensure timezone consistency:

```python
from src.utils import (
    get_local_tz,       # Get configured timezone
    get_local_now,      # Current time in local TZ (naive)
    to_naive_local,     # Convert any datetime to naive local
    to_aware_utc,       # Convert to timezone-aware UTC
    parse_deadline,     # Parse deadline strings ("tomorrow", "2026-01-20")
    format_deadline,    # Format for display ("Jan 20, 2026 5:00 PM")
    is_overdue,         # Check if deadline passed
    hours_until_deadline,  # Hours remaining (negative if overdue)
)

# Convert timezone-aware deadline to naive local for PostgreSQL
db_deadline = to_naive_local(task.deadline)

# Parse user input like "tomorrow" or "2026-01-20T18:00:00+07:00"
deadline = parse_deadline("tomorrow")  # Returns naive local datetime
```

### Team Utilities (`src/utils/team_utils.py`)

Centralized team member lookup across all data sources:

```python
from src.utils import (
    lookup_team_member,     # Find member by name (DB → Sheets → config)
    get_assignee_info,      # Get all IDs for notifications
    get_role_for_assignee,  # Get role for channel routing
    validate_discord_id,    # Validate numeric Discord ID format
)

# Get assignee info for task creation
info = await get_assignee_info("Mayank")
# Returns: {"discord_id": "123...", "email": "...", "telegram_id": "...", "role": "Developer"}

# Lookup searches in order:
# 1. PostgreSQL database (fastest)
# 2. Google Sheets Team tab (source of truth)
# 3. config/team.py (local fallback)
```

### Validation Utilities (`src/utils/validation.py`)

Task validation before database save:

```python
from src.utils import (
    validate_task_data,        # Full task validation
    validate_email,            # Email format check
    validate_task_id,          # Task ID format (TASK-YYYYMMDD-XXX)
    validate_priority,         # Priority value check
    validate_status,           # Status value check
    validate_status_transition,  # Transition validity check
)

# Validate before creating task
result = validate_task_data(
    title="Fix login bug",
    assignee="Mayank",
    assignee_discord_id="1234567890123456789",
    priority="high",
)

if not result.is_valid:
    print(f"Errors: {result.errors}")
else:
    if result.warnings:
        print(f"Warnings: {result.warnings}")
    # Proceed with task creation
```

**Validation Checks:**
- Title required (3-500 characters)
- Priority must be: low, medium, high, urgent
- Status must be valid (14 statuses)
- Discord ID format (17-19 digits)
- Email format validation
- Deadline in past (warning)
- Assignee without contact info (warning)

---

## Time Clock / Attendance System (NEW in v1.5.4)

A simple, Discord-based attendance tracking system where staff send messages like "in", "out", "break" in dedicated channels.

### Discord Channels for Attendance

| Department | Channel ID | Purpose |
|------------|------------|---------|
| Dev | 1462451610184843449 | Developer attendance |
| Admin | 1462451782470078628 | Admin attendance |

### Staff Commands (Discord Message)

Staff simply send a message in their department's attendance channel:

| Message | Action | Bot Reaction |
|---------|--------|--------------|
| `in` | Clock in for the day | ✅ (+ ⏰ if late) |
| `out` | Clock out for the day | 👋 |
| `break` | Toggle break on/off | ☕ (start) / 💪 (end) |

**Example:**
```
Staff sends: "in"
Bot reacts: ✅
(If late, also: ⏰)
```

### Late Detection

The system automatically detects late arrivals based on:

1. **Expected work start time**: Default 9:00 AM Thailand time
2. **Grace period**: Default 15 minutes
3. **Timezone support**: Each staff member can have their own timezone configured

**Late Detection Algorithm:**
```
1. User sends "in" → capture event_time (UTC)
2. Look up team member by Discord ID
3. Get their timezone from Team sheet (default: Asia/Bangkok)
4. Get their work_start from Team sheet (default: 09:00)
5. Convert work_start to UTC for comparison
6. Apply grace period (default: 15 min)
7. If event_time > (work_start + grace_period):
   - is_late = True
   - late_minutes = (event_time - work_start).minutes
   - React with ⏰ emoji
```

**Multi-Timezone Example:**
```
Staff: Mayank (India, UTC+5:30)
Thailand work start: 9:00 AM (UTC+7)

Expected start in Mayank's time:
  9:00 ICT = 7:30 IST (1.5 hours behind)

If Mayank clocks in at 8:00 AM IST:
  = 9:30 AM ICT → 30 min late! ⏰

If Mayank clocks in at 7:15 AM IST:
  = 8:45 AM ICT → Within grace period ✅
```

### Google Sheets Integration

Two new sheets are created:

**⏰ Time Logs** (compact, 8 columns):

| Column | Description |
|--------|-------------|
| Record ID | ATT-YYYYMMDD-XXX |
| Date | YYYY-MM-DD |
| Time | HH:MM |
| Name | Staff name |
| Event | in/out/break in/break out |
| Late | Yes/No/- |
| Late Min | Minutes late (0 if not) |
| Channel | dev/admin |

**📊 Time Reports** (weekly summary, 11 columns):

| Column | Description |
|--------|-------------|
| Week | Week number |
| Year | 2026 |
| Name | Staff name |
| Days Worked | Count |
| Total Hours | Sum |
| Avg Start | Average clock-in time |
| Avg End | Average clock-out time |
| Late Days | Count |
| Total Late | Minutes |
| Break Time | Total break duration |
| Notes | Manual notes |

**Updated 👥 Team sheet** - 2 new columns:

| Column | Description |
|--------|-------------|
| Timezone | e.g., Asia/Kolkata, Asia/Bangkok |
| Work Start | e.g., 09:00 (in Thailand time) |

### Database Model

```python
class AttendanceRecordDB:
    id: int
    record_id: str  # ATT-YYYYMMDD-XXX
    user_id: str    # Discord user ID
    user_name: str
    event_type: str  # clock_in, clock_out, break_start, break_end
    event_time: datetime  # Local time
    event_time_utc: datetime  # UTC for calculations
    channel_id: str
    channel_name: str  # dev/admin
    is_late: bool
    late_minutes: int
    expected_time: datetime (nullable)
    synced_to_sheets: bool
    created_at: datetime
```

### Service Layer (`src/services/attendance.py`)

| Function | Description |
|----------|-------------|
| `process_clock_in()` | Record clock-in, check for late, return reaction info |
| `process_clock_out()` | Record clock-out, auto-end break if needed |
| `process_break_toggle()` | Toggle break on/off state |
| `calculate_late_status()` | Compare clock-in vs expected time with timezone handling |
| `get_user_daily_summary()` | Get today's attendance for a user |

### Repository Layer (`src/database/repositories/attendance.py`)

| Function | Description |
|----------|-------------|
| `record_event()` | Save clock in/out/break event |
| `get_user_events_for_date()` | Daily log for a user |
| `get_user_last_event()` | For break toggle logic |
| `get_weekly_summary()` | Per-user weekly stats |
| `get_team_weekly_summary()` | All users weekly stats |
| `get_unsynced_records()` | For Sheets sync |
| `mark_synced()` | After Sheets sync |

### Scheduled Jobs

| Job | Schedule | Description |
|-----|----------|-------------|
| `sync_attendance` | Every 15 min | Sync PostgreSQL → Google Sheets |
| `weekly_time_report` | Monday 10 AM | Generate weekly summary, post to Discord/Telegram |

### Configuration

```bash
# Attendance channels (env vars or settings.py)
DISCORD_ATTENDANCE_DEV_CHANNEL_ID=1462451610184843449
DISCORD_ATTENDANCE_ADMIN_CHANNEL_ID=1462451782470078628

# Working hours (Thailand time)
DEFAULT_WORK_START_HOUR=9
DEFAULT_WORK_END_HOUR=18
DEFAULT_GRACE_PERIOD_MINUTES=15

# Sync interval
ATTENDANCE_SYNC_INTERVAL_MINUTES=15
```

### Setup

1. **Run setup_sheets.py** to create ⏰ Time Logs and 📊 Time Reports sheets
2. **Configure Discord channels** in settings (or use defaults)
3. **Update Team sheet** with Timezone and Work Start columns for each staff member
4. **Staff sends messages** in their attendance channel

### Boss Attendance Reporting (NEW in v1.5.7)

Allows the boss to report attendance events for team members via natural language in Telegram.

**Example Inputs:**
- "Mayank didn't come to the meeting today, count as absence"
- "Sarah was 30 minutes late this morning"
- "John left early yesterday at 3pm"
- "Mike is on sick leave today"

**Supported Attendance Types:**

| Status Type | Display | Example Input |
|-------------|---------|---------------|
| `absence_reported` | Absent | "didn't come today", "absent", "no show" |
| `late_reported` | Late (X min) | "was 30 minutes late", "came late" |
| `early_departure_reported` | Left Early | "left at 3pm", "left early" |
| `sick_leave_reported` | Sick Leave | "on sick leave", "called in sick" |
| `excused_absence_reported` | Excused | "day off", "WFH", "approved leave" |

**Flow:**
1. Boss sends natural language message about attendance
2. AI extracts: person, status type, date, reason, duration
3. Bot shows confirmation preview:
   ```
   📋 Attendance Report Preview

   👤 Person: Mayank
   📌 Status: Absent
   📅 Date: 2026-01-19
   📝 Reason: missed meeting

   Confirm this report? (yes/no)
   ```
4. On "yes" → Records to DB + syncs to Sheets + sends Discord notification
5. Confirmation sent to boss

**Database Fields Added to `AttendanceRecordDB`:**
```python
is_boss_reported: bool = False
reported_by: Optional[str] = None       # Boss name
reported_by_id: Optional[str] = None    # Boss ID
reason: Optional[str] = None            # Reason for absence
affected_date: Optional[date] = None    # Date being reported
duration_minutes: Optional[int] = None  # For late arrivals
notification_sent: bool = False         # Discord notification status
```

**New Event Types:**
```python
class AttendanceEventTypeEnum:
    # ... existing types ...
    ABSENCE_REPORTED = "absence_reported"
    LATE_REPORTED = "late_reported"
    EARLY_DEPARTURE_REPORTED = "early_departure_reported"
    SICK_LEAVE_REPORTED = "sick_leave_reported"
    EXCUSED_ABSENCE_REPORTED = "excused_absence_reported"
```

**Google Sheets Format:**
Boss-reported entries appear in ⏰ Time Logs with `[BR]` prefix:
```
[BR] Absent | Reported by Boss: missed meeting
[BR] Late (30min) | Reported by Boss: traffic
```

**Discord Notification:**
When boss reports attendance, the team member is always notified in their department's general channel:
```
📋 Attendance Report

The boss has recorded the following for @Mayank:

Status: Absent
Date: 2026-01-19
Reason: missed meeting
```

**Service Layer Functions:**
| Function | Description |
|----------|-------------|
| `record_boss_reported_attendance()` | Main entry point for recording boss-reported events |
| `_find_team_member_by_name()` | Lookup team member by name (partial match) |
| `_sync_boss_reported_to_sheets()` | Sync to Time Logs with [BR] prefix |
| `_send_attendance_notification()` | Send Discord notification to team member |

**Repository Function:**
| Function | Description |
|----------|-------------|
| `record_boss_reported_event()` | Create attendance record with boss-reported fields |

**Intent Detection:**
The `REPORT_ABSENCE` intent is triggered by keywords:
- absence, absent, didn't come, not coming, missed, no show
- late, came late, was late, arrived late, minutes late
- left early, leaving early, early departure, left at
- sick leave, sick day, on leave, day off, called in sick
- not present, count as absence, mark as absent

**Edge Cases Handled:**
1. **Team member not found** → Uses raw name, warns boss
2. **Relative dates** → Parses "yesterday", "this morning", "last Monday"
3. **Duplicate reports** → Future: Check for existing report same person/date/type
4. **Conflicting data** → Future: Warn if already clocked in

---

## Configuration

### Environment Variables (`.env`)

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot API token |
| `TELEGRAM_BOSS_CHAT_ID` | Boss's Telegram chat ID |
| `DEEPSEEK_API_KEY` | DeepSeek AI API key |
| `DEEPSEEK_BASE_URL` | DeepSeek API endpoint |
| `OPENAI_API_KEY` | OpenAI API key for Whisper voice transcription (NEW v1.2) |
| `DISCORD_BOT_TOKEN` | Discord bot token (REQUIRED for v1.5+) |
| `DISCORD_DEV_FORUM_CHANNEL_ID` | Dev forum channel for specs (NEW v1.5) |
| `DISCORD_DEV_TASKS_CHANNEL_ID` | Dev tasks channel for regular tasks (NEW v1.5) |
| `DISCORD_DEV_REPORT_CHANNEL_ID` | Dev report channel for standup (NEW v1.5) |
| `DISCORD_DEV_GENERAL_CHANNEL_ID` | Dev general channel (NEW v1.5) |
| `DISCORD_ADMIN_*_CHANNEL_ID` | Admin department channels (optional) |
| `DISCORD_MARKETING_*_CHANNEL_ID` | Marketing department channels (optional) |
| `DISCORD_DESIGN_*_CHANNEL_ID` | Design department channels (optional) |
| `DISCORD_WEBHOOK_URL` | Legacy webhook (deprecated) |
| `DISCORD_TASKS_CHANNEL_WEBHOOK` | Legacy webhook (deprecated) |
| `DISCORD_STANDUP_CHANNEL_WEBHOOK` | Legacy webhook (deprecated) |
| `GOOGLE_CREDENTIALS_JSON` | Service account JSON |
| `GOOGLE_SHEET_ID` | Google Sheets document ID |
| `GOOGLE_CALENDAR_ID` | Google Calendar ID |
| `WEBHOOK_BASE_URL` | Railway/deployment URL |
| `TIMEZONE` | Scheduler timezone |
| `GMAIL_USER_EMAIL` | Gmail for digests |
| `DATABASE_URL` | PostgreSQL connection string (auto-set by Railway) |
| `REDIS_URL` | Redis connection string (optional) |
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth2 client ID for user Google auth (NEW v1.5.2) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth2 client secret for user Google auth (NEW v1.5.2) |

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
│   │   ├── reviewer.py      # Auto-review
│   │   ├── transcriber.py   # Voice transcription (Whisper) [NEW v1.2]
│   │   └── vision.py        # Image analysis (DeepSeek VL) [NEW v1.3]
│   ├── web/                  # Web onboarding portal [NEW v1.5.2]
│   │   ├── __init__.py
│   │   ├── routes.py         # FastAPI routes for web pages
│   │   └── templates/
│   │       └── onboard.html  # Staff onboarding form
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
│   │   ├── discord_bot.py   # Discord bot for reactions [NEW v1.2]
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
│   │       ├── projects.py  # Project operations
│   │       ├── recurring.py # Recurring tasks [NEW v1.2]
│   │       └── time_tracking.py # Time tracking [NEW v1.2]
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

### Phase 1: Quick Wins - COMPLETED in v1.1 ✅

#### 1. Task Templates ✅
**Status:** ✅ Implemented (v1.1)
**Files:** `src/memory/preferences.py`, `src/ai/clarifier.py`, `src/bot/commands.py`

8 built-in templates with auto-detection: bug, hotfix, feature, research, meeting, docs, refactor, test.

**Usage:**
- Natural: "bug: Login page crashes" → Auto-applies bug template
- Command: `/templates` → View all templates

---

#### 2. Discord Reaction Status Updates ✅
**Status:** ✅ Implemented (v1.1)
**Files:** `src/integrations/discord.py`

All task embeds now include reaction guide in footer:
- ✅ = Done, 🚧 = Working, 🚫 = Blocked, ⏸️ = Paused, 🔄 = Review

Added `post_help()` method for Discord-side help.

---

#### 3. Task Search ✅
**Status:** ✅ Implemented (v1.1)
**Files:** `src/bot/commands.py`, `src/bot/handler.py`, `src/integrations/sheets.py`

Natural language + command support:
- "What's John working on?" → AI-parsed search
- `/search @John` → Tasks for John
- `/search #urgent status:blocked due:today` → Multiple filters

---

#### 4. Bulk Status Update ✅
**Status:** ✅ Implemented (v1.1)
**Files:** `src/bot/commands.py`, `src/integrations/sheets.py`

Commands:
- `/complete TASK-001 TASK-002` → Mark multiple done
- `/block TASK-001 TASK-002 reason` → Block with reason
- `/assign @Sarah TASK-003 TASK-004` → Bulk assign

Natural language: "Mark these 3 as done"

---

#### 5. Smart Dependencies ✅
**Status:** ✅ Implemented (v1.1)
**Files:** `src/ai/clarifier.py`, `src/bot/handler.py`

AI automatically:
- Scans active tasks for potential dependencies
- Shows "Potential Dependencies" in task preview
- Asks before final confirmation if dependencies found
- Suggests adding `blocked_by` relationship

---

### Phase 2: Medium Effort (High Value) - COMPLETED in v1.2 ✅

#### 6. Recurring Tasks ✅
**Status:** ✅ Implemented (v1.2)
**Files:** `src/database/models.py`, `src/database/repositories/recurring.py`, `src/bot/commands.py`, `src/scheduler/jobs.py`

Tasks that auto-recreate on schedule. Scheduler checks every 5 minutes for due recurring tasks.

**Commands:**
- `/recurring "title" pattern time` - Create recurring task
- `/recurring list` - View all recurring tasks
- `/recurring pause/resume ID` - Control recurring tasks
- `/recurring delete ID` - Remove recurring task

**Recurrence Patterns:**
- Daily: `every:day`
- Weekdays: `every:weekday`
- Weekly: `every:monday`, `every:monday,wednesday,friday`
- Monthly: `every:1st`, `every:15th`, `every:last`
- Interval: `every:2weeks`, `every:3days`

---

#### 7. Time Tracking ✅
**Status:** ✅ Implemented (v1.2)
**Files:** `src/database/models.py`, `src/database/repositories/time_tracking.py`, `src/bot/commands.py`

Full time tracking with timers and manual logging:

**Commands:**
- `/start TASK-ID` - Start timer
- `/stop` - Stop active timer
- `/log TASK-ID 2h30m` - Manual time entry
- `/time TASK-ID` - Show time on task
- `/timesheet` - Personal timesheet
- `/timesheet team` - Team timesheet

**Duration Parsing:**
- `2h30m` → 150 minutes
- `1.5h` → 90 minutes
- `45m` → 45 minutes
- `1d` → 480 minutes (8 hours)

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

---

#### 9. Subtasks ✅
**Status:** ✅ Implemented (v1.2)
**Files:** `src/database/models.py`, `src/database/repositories/tasks.py`, `src/bot/commands.py`

Break tasks into smaller items with progress tracking:

**Commands:**
- `/subtask TASK-ID "title"` - Add subtask
- `/subtasks TASK-ID` - List subtasks
- `/subdone TASK-ID 1` - Complete subtask #1
- `/subdone TASK-ID all` - Complete all subtasks

**Features:**
- Automatic ordering (order number auto-assigned)
- Parent task tracks completion percentage
- Mark complete by order number
- List shows checkbox status (☐/☑)

---

#### 10. Voice Commands (Whisper) ✅
**Status:** ✅ Implemented (v1.2)
**Files:** `src/ai/transcriber.py`, `src/bot/telegram_simple.py`

Hands-free task creation via voice messages:

1. Send voice message in Telegram
2. Bot transcribes using OpenAI Whisper API
3. Shows transcription: `📝 "Create task for John"`
4. Processes as normal text command

**Features:**
- OpenAI Whisper API integration
- Context-aware prompts for task management terms
- Supports OGG, MP3, WAV audio formats
- Requires `OPENAI_API_KEY` environment variable

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

#### 15. AI Task Breakdown ✅
**Status:** ✅ Implemented (v1.3)
**Files:** `src/ai/deepseek.py`, `src/ai/prompts.py`, `src/bot/commands.py`

AI-powered task breakdown into subtasks:

**Command:** `/breakdown TASK-001`

**Features:**
- Analyzes task complexity and suggests 3-8 subtasks
- Shows effort estimates and dependencies
- Detects if task is too simple for breakdown
- Confirms before creating subtasks
- Integrates with existing subtask system

**Example:**
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

| Priority | Feature | Effort | Impact | Status |
|----------|---------|--------|--------|--------|
| 1 | Task Templates | Low | High | ✅ Done |
| 2 | Discord Reactions | Low | High | ✅ Done |
| 3 | Task Search | Low | Medium | ✅ Done |
| 4 | Bulk Updates | Low | Medium | ✅ Done |
| 5 | Smart Dependencies | Medium | High | ✅ Done |
| 6 | Recurring Tasks | Medium | High | ✅ Done |
| 7 | Time Tracking | Medium | Medium | ✅ Done |
| 8 | Team Bot Access | High | Very High | 🔴 Planned |
| 9 | PostgreSQL | High | High | ✅ Done |
| 10 | Subtasks Commands | Medium | Medium | ✅ Done |
| 11 | Voice Commands | Medium | Medium | ✅ Done |
| 12 | Web Dashboard | High | Very High | 🔴 Planned |
| 13 | AI Task Breakdown | Medium | High | ✅ Done |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.5.8 | 2026-01-19 | **SPECSHEETS Handler Fix:** Handler now properly checks `detailed_mode` flag from intent detection. When SPECSHEETS/detailed mode detected: skips multi-task splitting, skips clarifier questions, goes directly to comprehensive spec generation. **Extended Trigger Keywords:** Added `more developed`, `more detailed`, `with details`, and `spec sheet` (without "for") as triggers. Previously the message was incorrectly split into multiple tasks. |
| 1.5.6 | 2026-01-19 | **SPECSHEETS Intent Detection Fix:** Messages with "SPECSHEETS", "spec sheet for", "detailed spec for" now properly trigger task creation with detailed_mode. **Direct Assignee Detection:** Messages starting with team member names (mayank, sarah, john, etc.) now trigger task creation. Previously these fell through to incorrect intents. |
| 1.5.5 | 2026-01-19 | **Attendance Sheets Sync Fix:** Clock in/out/break events now properly sync to Google Sheets ⏰ Time Logs sheet. Previously events were only saved to PostgreSQL database. |
| 1.5.4 | 2026-01-18 | **Time Clock / Attendance System:** Staff check-in/check-out via Discord messages ("in", "out", "break"). **Discord Channels:** Dev attendance (1462451610184843449), Admin attendance (1462451782470078628). **Late Detection:** Automatic late detection with ⏰ reaction, timezone-aware calculations, configurable grace period. **Break Toggle:** Single "break" message toggles break on/off (☕/💪 reactions). **New Sheets:** ⏰ Time Logs for attendance records, 📊 Time Reports for weekly summaries. **Team Sheet Update:** Added Timezone and Work Start columns. **Database Model:** AttendanceRecordDB with full event tracking. **Service Layer:** AttendanceService for business logic with timezone handling. **Repository:** AttendanceRepository with daily/weekly summary methods. **Scheduler Jobs:** sync_attendance (every 15 min), weekly_time_report (Monday 10 AM). **Settings:** New attendance config options (channel IDs, work hours, grace period). |
| 1.5.3 | 2026-01-18 | **Centralized Utility Modules:** New `src/utils/` package with datetime, team lookup, and validation utilities. **Datetime Utils:** `to_naive_local()`, `parse_deadline()`, `get_local_now()` for consistent timezone handling (fixes PostgreSQL offset-naive/aware datetime errors). **Team Utils:** `get_assignee_info()`, `lookup_team_member()` with 3-tier fallback (DB → Sheets → config). **Validation Utils:** `validate_task_data()` with field validation and warnings before database save. **Task Model Fix:** Added `spec_sheet_url`, `discord_thread_id` optional fields to prevent AttributeError on forum posting. **Improved Error Messages:** More descriptive error messages with error type hints. **ThreadWithMessage Fix:** Updated discord_bot.py to handle discord.py 2.0+ `ThreadWithMessage` object (has `.thread`/`.message` attributes, not tuple). |
| 1.5.2 | 2026-01-18 | **Web Onboarding Portal:** Staff self-service registration page at `/onboard` with dark minimalist design. 4-step wizard: Basic Info → Discord Setup → Google Integration → Confirmation. Saves to Sheets + PostgreSQL. **Google OAuth2:** User-level authentication for Calendar & Tasks with popup flow. Includes embedded screenshot showing Google's "unverified app" warning with click-through instructions. **Auto Calendar ID:** Form automatically sets Calendar ID to user's email. Existing users backfilled. **Route Fix:** OAuth callback route ordering fixed to prevent "Invalid service" error. New env vars: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`. **Team View:** `/team` endpoint shows all team members. |
| 1.5.1 | 2026-01-18 | **Admin Department Setup:** Added Admin category Discord channels - Forum `1462370539858432145`, Report `1462370845908402268`, General `1462370950627725362`. **Team Member Minty:** Added (Discord: 834982814910775306, Role: Admin, Email: sutima2543@gmail.com). **Fallback Routing:** Tasks for departments without a tasks channel automatically post to forum. **Post to All Departments:** Added `post_standup_to_all()` for multi-department reports. **Per-User Google Calendar:** Events now created directly on assignee's personal calendar (if shared with service account). Team sheet has Calendar ID column. System looks up from Sheets, falls back to config/team.py. |
| 1.5.0 | 2026-01-18 | **MAJOR: Channel-Based Discord Integration:** Complete rewrite from webhooks to Bot API with channel IDs. Full permissions for message/thread management. **4 Channels Per Department:** Forum (specs), Tasks (regular tasks), Report (standup), General. **Dev Category Configured:** Forum `1459834094304104653`, Tasks `1461760665873158349`, Report `1461760697334632651`, General `1461760791719182590`. **Smart Content Routing:** Specs→Forum, tasks→Tasks channel, standup→Report, help→General. **Role-Based Department Routing:** Tasks route to matching department's channels based on assignee role. |
| 1.4.3 | 2026-01-18 | **Role-Based Discord Routing:** Tasks automatically route to department-specific Discord channels based on assignee role (Dev, Admin, Marketing, Design). **Team Sync Commands:** `/syncteam` syncs team from config/team.py to Sheets + DB. `/clearteam` removes mock data. **Team Config:** config/team.py defines team with roles for channel routing. |
| 1.4.2 | 2026-01-18 | **True Task Deletion:** Clearing tasks now permanently deletes from Google Sheets, Discord (messages + threads), and PostgreSQL database. Previously only marked as "cancelled". Supports single task deletion and bulk deletion with confirmation. |
| 1.4.1 | 2026-01-18 | **Email Digest in Standup:** Daily standup now sends comprehensive email summary as separate Telegram message (boss only, not Discord). All email digests are now Telegram-only for privacy. Includes AI summary, action items, priority emails, and latest 15 emails with status icons. |
| 1.4.0 | 2026-01-18 | **Discord Forum Channels:** Tasks posted as organized forum threads with auto-tagging. **Sequential Multi-Task Handling:** Multiple tasks processed one-by-one with yes/skip/no flow. **SPECSHEETS Mode:** Trigger detailed specs with keywords. **Proper @mentions:** Numeric Discord user IDs for mentions. **Background Processing:** Prevents Telegram webhook timeouts. **Thread Creation:** Auto-creates discussion threads on task messages. |
| 1.3.1 | 2026-01-17 | Image Vision Analysis: DeepSeek VL integration for photo analysis, proof screenshot validation, OCR text extraction. Vision analysis integrated with auto-review and boss notifications. |
| 1.3.0 | 2026-01-17 | AI Task Breakdown: `/breakdown TASK-ID` analyzes tasks and suggests subtasks with effort estimates |
| 1.2.1 | 2026-01-17 | Discord Bot Reaction Listener: Full bot integration that listens for emoji reactions and auto-updates task status in PostgreSQL + Sheets |
| 1.2.0 | 2026-01-17 | Phase 2 features: Recurring Tasks (auto-schedule), Time Tracking (timers + timesheets), Subtasks Commands, Voice Commands (OpenAI Whisper) |
| 1.1.0 | 2026-01-17 | PostgreSQL database with full relationships, Quick Wins: Task Templates (8 built-in), Search (NL + command), Bulk Updates, Smart Dependencies, Discord Reaction Guide |
| 1.0.0 | 2026-01-17 | Initial release with full feature set |

---

*This document is automatically referenced by Claude Code. Always read this file first when working on the project, and update it last after making changes.*
