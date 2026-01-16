# Boss Workflow Automation System

A conversational task management system that integrates Telegram, DeepSeek AI, Discord, Google Sheets, and Google Calendar.

## Features

- **Conversational Task Creation**: Natural language task input with AI-powered clarifying questions
- **Smart Learning**: Bot learns your preferences and team knowledge over time
- **Multi-Platform Integration**:
  - **Telegram**: Input interface with voice support
  - **Discord**: Rich task embeds and team notifications
  - **Google Sheets**: Comprehensive tracking and reporting
  - **Google Calendar**: Deadline management with reminders
- **Automated Scheduling**:
  - Daily standup summaries
  - End-of-day reminders
  - Weekly reports
  - Deadline and overdue alerts
- **Extended Task Status**: pending, in_progress, completed, delayed, undone, blocked, on_hold, waiting, needs_info, overdue
- **Notes System**: Add notes to tasks with pinning support
- **Status History**: Full tracking of status changes with reasons

## Architecture

```
┌─────────┐    ┌──────────────────────┐    ┌──────────┐
│ TELEGRAM│◀──▶│     DEEPSEEK AI      │───▶│ DISCORD  │
│   BOT   │    │ (Conversation + Spec)│    │  EMBEDS  │
└─────────┘    └──────────────────────┘    └────┬─────┘
     │                   │                      │
     │                   ▼                      ▼
     │         ┌──────────────────┐    ┌──────────────────┐
     │         │  MEMORY/CONTEXT  │    │  GOOGLE SHEETS   │
     │         │   (Preferences)  │    │    TRACKING      │
     │         └──────────────────┘    └──────────────────┘
     │                                          │
     │         ┌────────────────────────────────┘
     │         ▼
     │    ┌──────────────────┐
     └───▶│    SCHEDULER     │
          │ + GOOGLE CALENDAR│
          └──────────────────┘
```

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Redis (for conversation state)
- PostgreSQL (for persistence) - optional with Railway

### 2. Get API Keys

| Service | Where to Get |
|---------|--------------|
| Telegram Bot | @BotFather on Telegram |
| DeepSeek AI | platform.deepseek.com |
| Discord Webhooks | Server Settings → Integrations → Webhooks |
| Google Service Account | Google Cloud Console → IAM → Service Accounts |

### 3. Setup

```bash
# Clone and enter directory
cd boss-workflow

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run locally
python -m uvicorn src.main:app --reload
```

### 4. Deploy to Railway

1. Push to GitHub
2. Connect Railway to your repo
3. Add Redis and Postgres services
4. Set environment variables
5. Deploy!

## Commands

### Task Creation
- `/task [description]` - Start task creation
- `/urgent [description]` - Create high-priority task
- `/skip` - Skip current question, use defaults
- `/done` - Finalize immediately
- `/cancel` - Cancel task creation

### Task Management
- `/status` - Current task overview
- `/note [task-id] [note]` - Add note to task
- `/delay [task-id] [deadline] [reason]` - Delay a task

### Reports
- `/weekly` - Weekly summary
- `/daily` - Today's tasks
- `/overdue` - Overdue tasks

### Settings
- `/preferences` - View preferences
- `/teach` - Teach the bot something new
- `/team` - View team members

## Teaching the Bot

```
/teach When I say ASAP, deadline is 4 hours
/teach John is our backend expert
/teach Always ask about deadline
/teach My default priority is medium
```

## Project Structure

```
boss-workflow/
├── src/
│   ├── main.py              # FastAPI app entry
│   ├── bot/
│   │   ├── telegram.py      # Telegram bot handlers
│   │   ├── commands.py      # Command processing
│   │   └── conversation.py  # Conversation state machine
│   ├── ai/
│   │   ├── deepseek.py      # DeepSeek integration
│   │   ├── prompts.py       # Prompt templates
│   │   └── clarifier.py     # Smart question generation
│   ├── memory/
│   │   ├── preferences.py   # User preferences
│   │   ├── context.py       # Conversation context
│   │   └── learning.py      # /teach handler
│   ├── integrations/
│   │   ├── discord.py       # Discord webhooks
│   │   ├── sheets.py        # Google Sheets
│   │   └── calendar.py      # Google Calendar
│   ├── scheduler/
│   │   ├── jobs.py          # Scheduled tasks
│   │   └── reminders.py     # Reminder logic
│   └── models/
│       ├── task.py          # Task model
│       └── conversation.py  # Conversation model
├── config/
│   └── settings.py          # Configuration
├── requirements.txt
├── Dockerfile
└── railway.toml
```

## Cost Estimate

| Service | Monthly Cost |
|---------|-------------|
| Railway Hosting | ~$5 |
| Redis (Railway) | ~$1-2 |
| DeepSeek API | ~$2-5 |
| Discord | Free |
| Telegram | Free |
| Google APIs | Free |
| **Total** | **~$8-12** |

## License

MIT
