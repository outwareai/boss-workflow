# Boss Workflow Automation System

A conversational task management system that integrates Telegram, DeepSeek AI, Discord, Google Sheets, and Google Calendar.

## Recent Updates (Q1-Q3 2026)

### Architecture & Testing
- ⚡ **Handler Refactoring:** Extracted 7 specialized handlers from monolithic UnifiedHandler
- ✅ **470+ Tests:** Comprehensive unit and integration test coverage (65%+)
- 🔒 **Zero CVEs:** All security vulnerabilities resolved
- 🏗️ **Clean Architecture:** SOLID principles, separation of concerns

### Security Enhancements
- 🔐 **OAuth Encryption:** AES-256-GCM token encryption with PBKDF2
- 🛡️ **Rate Limiting:** Slowapi protection enabled
- ⏱️ **Timeout Protection:** All external API calls protected
- 🚨 **Error Handling:** Comprehensive exception handling across all layers

### Production Hardening
- 📊 **Integration Tests:** 130+ tests for Discord, Sheets, Calendar, DeepSeek
- 🔄 **Scheduler Tests:** 65+ tests for jobs, digests, reports, reminders
- 🌐 **API Tests:** 47+ tests for routes, validation, auth, rate limiting
- 📈 **System Health:** 9.5/10 (up from 6.0/10)

See [Q3_COMPLETION_REPORT.md](Q3_COMPLETION_REPORT.md) for complete details.

---

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
- **Extended Task Status**: pending, in_progress, awaiting_validation, needs_revision, completed, delayed, undone, blocked, on_hold, waiting, needs_info, overdue
- **Notes System**: Add notes to tasks with pinning support
- **Status History**: Full tracking of status changes with reasons
- **Validation Workflow**: Team member submits proof → Boss reviews → Approve or reject with feedback

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

## How It Works

**No commands needed!** Just talk naturally.

### Creating Tasks
```
"John needs to fix the login bug"
"Sarah should build the checkout page by Friday"
"Fix mobile menu - urgent"
```

The bot asks clarifying questions if needed, then creates the task.

### Marking Tasks Done
```
"I finished the landing page"
→ Bot: "Send me proof (screenshots, links)"
[send screenshots/links]
"that's all"
→ Bot: "Any notes?"
"Tested on Chrome and Safari"
→ Bot: "Send to boss? (yes/no)"
"yes"
```

### Auto-Review (Before Boss Sees It)
The bot automatically reviews submissions before they reach you:

```
Developer: "I finished the landing page"
→ sends screenshots
→ "that's all"
→ "tested it quickly"

Bot: "⚠️ Your submission needs some work:
      • Notes are too brief
      • Missing details about what was tested

      Suggested notes: 'Completed landing page redesign.
      Tested on Chrome and Safari. All responsive
      breakpoints working.'

      Score: 55/100 (need 70+)

      Reply:
      • 'yes' - Apply my suggestions
      • 'no' - Send to boss anyway
      • 'edit' - Type better notes yourself"

Developer: "yes"

Bot: "✨ Applied! Ready to send to boss? (yes/no)"
```

### Boss Validation
When submission passes review (or developer insists), boss receives notification with proof.
- Reply "yes" or "approved" → Task approved, person notified
- Reply "no - [feedback]" → Feedback sent, revision requested

### Checking Status
```
"What's pending?"
"Anything overdue?"
"Status"
```

### Teaching the Bot
```
"John is our backend dev"
"When I say ASAP, deadline is 4 hours"
"When I mention client X, priority is high"
```

### Email Digests
Automatic morning and evening email summaries sent to your Telegram:

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
─────────────────
```

Configure times in your `.env`:
- `MORNING_DIGEST_HOUR=7` (7 AM)
- `EVENING_DIGEST_HOUR=20` (8 PM)
- Uses your configured `TIMEZONE`


## Validation Workflow

The system includes a complete task validation workflow for proof of work:

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
│  5. "yes" (confirm) ──────────────────▶ 6. Receives request     │
│                                             with all proof       │
│                                             ↓                    │
│                                          7. Reviews work         │
│                                             ↓                    │
│  ┌──────────────────────────────────── 8a. "approved"           │
│  │                                          "Great work!"        │
│  ▼                                          ↓                    │
│  9a. 🎉 "TASK APPROVED!"                Task → COMPLETED         │
│                                                                  │
│  ─────── OR ───────                                             │
│                                                                  │
│  ┌──────────────────────────────────── 8b. "no - fix footer"    │
│  │                                                               │
│  ▼                                          ↓                    │
│  9b. 🔄 "REVISION NEEDED"               Task → NEEDS_REVISION    │
│      Feedback displayed                                          │
│      ↓                                                           │
│  10. Make changes, submit again...                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Proof Types Supported
- 📸 **Screenshots** - Send photos directly in Telegram
- 🔗 **Links** - URLs to live demos, PRs, deployments
- 📄 **Documents** - Attached files
- 📝 **Notes** - Text descriptions
- 💻 **Code commits** - Git commit references

## Project Structure

```
boss-workflow/
├── src/
│   ├── main.py              # FastAPI app entry
│   ├── bot/
│   │   ├── telegram_simple.py  # Simplified bot (no commands)
│   │   ├── handler.py       # Unified message handler
│   │   ├── conversation.py  # Conversation state machine
│   │   └── validation.py    # Validation workflow
│   ├── ai/
│   │   ├── deepseek.py      # DeepSeek integration
│   │   ├── intent.py        # Intent detection (NLU)
│   │   ├── prompts.py       # Prompt templates
│   │   └── clarifier.py     # Smart question generation
│   ├── memory/
│   │   ├── preferences.py   # User preferences
│   │   ├── context.py       # Conversation context
│   │   └── learning.py      # Learning from user teachings
│   ├── integrations/
│   │   ├── discord.py       # Discord webhooks
│   │   ├── sheets.py        # Google Sheets
│   │   └── calendar.py      # Google Calendar
│   ├── scheduler/
│   │   ├── jobs.py          # Scheduled tasks
│   │   └── reminders.py     # Reminder logic
│   └── models/
│       ├── task.py          # Task model with notes
│       ├── conversation.py  # Conversation model
│       └── validation.py    # Validation models
├── config/
│   └── settings.py          # Configuration
├── requirements.txt
├── Dockerfile
└── railway.toml
```

## Testing

### Unit Tests

Run all handler and repository tests:

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run all handler tests
pytest tests/unit/test_*_handler.py -v

# Run all repository tests
pytest tests/unit/repositories/ -v

# Run all tests with coverage report
pytest tests/unit/ -v --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_command_handler.py -v

# Run tests matching pattern
pytest -k "test_handle" -v
```

### Integration Tests

Test the complete workflow:

```bash
# Run comprehensive test
python test_full_loop.py test-all

# Test simple task creation
python test_full_loop.py test-simple

# Test complex task with questions
python test_full_loop.py test-complex

# Test routing to specific channels
python test_full_loop.py test-routing
```

### Coverage Report

Generate and view coverage statistics:

```bash
# Generate coverage report
pytest tests/unit/ --cov=src --cov-report=html

# Open report in browser
open htmlcov/index.html
```

**Target Coverage:** 70%+
**Current Coverage:** ~65% (handler + repository tests)

### Test Structure

```
tests/
├── unit/
│   ├── test_command_handler.py       # 14 tests
│   ├── test_approval_handler.py      # 12 tests
│   ├── test_validation_handler.py    # 9 tests
│   ├── test_query_handler.py         # 7 tests
│   ├── test_modification_handler.py  # 8 tests
│   ├── test_routing_handler.py       # 7 tests
│   ├── test_base_handler.py          # 6 tests
│   └── repositories/
│       ├── test_task_repository.py          # 29 tests
│       ├── test_oauth_repository.py         # 38 tests
│       ├── test_ai_memory_repository.py     # 22 tests
│       ├── test_audit_repository.py         # 18 tests
│       └── test_team_repository.py          # 22 tests
└── integration/
    └── test_full_loop.py             # Complete workflows
```

**Total Tests:** 200+
**Handler Tests:** 57+
**Repository Tests:** 129+

---

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
# Trigger redeploy
