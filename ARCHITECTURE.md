# Boss Workflow Architecture

**Version:** 2.5.0
**Last Updated:** 2026-01-24
**Status:** Production

---

## System Overview

Boss Workflow is a Telegram-based task management system with AI-powered natural language processing, PostgreSQL persistence, and multi-platform integrations.

### Core Components

```
┌────────────────────────────────────────────────────────┐
│                   USER INTERFACES                       │
├────────────────────────────────────────────────────────┤
│  • Telegram Bot (Primary)    • Web Onboarding Portal   │
│  • Discord Notifications     • Audit Dashboard         │
└────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────┐
│              FASTAPI APPLICATION SERVER                │
│  (src/main.py - Webhook handlers, API endpoints)      │
└────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────┐
│                    HANDLER LAYER                        │
│  • CommandHandler (slash commands)                     │
│  • ApprovalHandler (confirmations)                     │
│  • ValidationHandler (proof submission)                │
│  • QueryHandler (status queries)                       │
│  • ModificationHandler (task edits)                    │
│  • RoutingHandler (dispatcher + AI fallback)           │
└────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────┐
│                    AI SERVICES LAYER                    │
│  • Intent Detection (AI-powered routing)               │
│  • Task Generation (task spec creation)                │
│  • Clarification (smart question generation)           │
│  • Validation (proof/notes quality scoring)            │
└────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────┐
│                  DATA PERSISTENCE LAYER                 │
│  • PostgreSQL (source of truth)                        │
│  • Redis (sessions, caching)                           │
│  • Google Sheets (boss dashboard)                      │
│  • Google Calendar (deadlines)                         │
└────────────────────────────────────────────────────────┘
```

---

## Handler Flow & Priority

The handler architecture uses a priority-based matching system where the first matching handler processes the message.

### Request Flow Diagram

```
User Message (Telegram)
        ↓
   TelegramBot Client
   (telegram_simple.py)
        ↓
   FastAPI Webhook
   (POST /webhook/telegram)
        ↓
  process_telegram_update()
        ↓
  RoutingHandler.route()
        ↓
   ┌────┴────┬────────┬──────────┬──────────┬──────────┐
   ↓         ↓        ↓          ↓          ↓          ↓
  /cmd     "yes"  submission  "status"  "update"  unknown
   ↓         ↓        ↓          ↓          ↓          ↓
Command   Approval Validation  Query  Modification  AI Intent
Handler   Handler   Handler   Handler   Handler      (fallback)
   ↓         ↓        ↓          ↓          ↓          ↓
 Handler Execution
(can_handle() → handle())
   ↓
SessionManager
(store state, retrieve context)
   ↓
Database/External APIs
(update tasks, Discord, Sheets)
   ↓
Response to User
(Telegram message)
```

### Handler Priority (First Match Wins)

1. **CommandHandler** - Slash commands with `/` prefix
   ```
   Examples: /task, /status, /help, /team, /daily, /weekly
   Matching: Exact prefix match "/"
   ```

2. **ApprovalHandler** - Dangerous action confirmations
   ```
   Examples: "yes", "no", "confirm", "approved", "rejected"
   Matching: Exact string match (case-insensitive)
   Checks: Active session for approval context
   ```

3. **ValidationHandler** - Task submission & proof workflows
   ```
   Examples: Submit proof, photos, links, notes
   Matching: Checks active validation session
   Context: SUBMISSION stage in task workflow
   ```

4. **QueryHandler** - Status queries and reports
   ```
   Examples: "status", "what's pending", "show overdue", "report"
   Matching: Regex patterns for query keywords
   Fallback: Contains "status", "pending", "report", etc.
   ```

5. **ModificationHandler** - Task updates and edits
   ```
   Examples: "update TASK-001", "mark as done", "change deadline"
   Matching: Regex patterns for modification keywords
   Fallback: Contains "update", "change", "modify", "mark", "done"
   ```

6. **RoutingHandler** - Catch-all with AI intent detection
   ```
   Examples: Natural language task creation, delegation, etc.
   Matching: Falls through all other handlers
   Fallback: Uses DeepSeek AI for intent classification
   ```

---

## Handler Architecture Details

### BaseHandler (Abstract Base Class)

All handlers inherit from `BaseHandler`:

```python
from abc import ABC, abstractmethod

class BaseHandler(ABC):
    """Abstract base class for all message handlers."""

    async def can_handle(self, update: dict) -> bool:
        """
        Check if this handler should process the message.

        Args:
            update: Telegram update dict

        Returns:
            bool: True if handler can process, False otherwise
        """
        raise NotImplementedError

    async def handle(self, update: dict) -> dict:
        """
        Process the message and return response.

        Args:
            update: Telegram update dict

        Returns:
            dict: Response with status, message, etc.
        """
        raise NotImplementedError

    async def log_execution(self, update: dict, result: dict):
        """
        Log handler execution for audit trail.

        Args:
            update: Original Telegram update
            result: Handler result
        """
        pass
```

### Handler Implementations

#### 1. CommandHandler

**File:** `src/bot/handlers/command_handler.py`
**Purpose:** Process slash commands
**Test Coverage:** 14 tests

```python
class CommandHandler(BaseHandler):
    """Handles slash commands like /task, /status, /help."""

    async def can_handle(self, update: dict) -> bool:
        """Check if message starts with /"""
        text = update.get("message", {}).get("text", "")
        return text.startswith("/")

    async def handle(self, update: dict) -> dict:
        """Route to specific command handler"""
        text = update["message"]["text"]
        command = text.split()[0].strip("/")

        if command == "task":
            return await self._handle_task_command(update)
        elif command == "status":
            return await self._handle_status_command(update)
        # ... more commands
```

**Supported Commands:**
- `/task [description]` - Create new task
- `/urgent [description]` - Create urgent task
- `/status` - Show task overview
- `/daily` - Today's tasks
- `/weekly` - Weekly summary
- `/team` - View team members
- `/help` - Show help

#### 2. ApprovalHandler

**File:** `src/bot/handlers/approval_handler.py`
**Purpose:** Handle dangerous action confirmations
**Test Coverage:** 12 tests

```python
class ApprovalHandler(BaseHandler):
    """Handles confirmations for dangerous actions."""

    async def can_handle(self, update: dict) -> bool:
        """Check for exact approval keywords"""
        text = update.get("message", {}).get("text", "").lower().strip()
        return text in ["yes", "no", "confirm", "approved", "rejected"]

    async def handle(self, update: dict) -> dict:
        """Process approval/rejection"""
        text = update["message"]["text"].lower()
        chat_id = update["message"]["chat"]["id"]

        # Get pending approval from session
        session = await SessionManager.get_session(chat_id, "pending_approval")
        if not session:
            return {"status": "error", "message": "No pending approval"}

        if text == "yes" or text == "approved":
            return await self._approve(session)
        else:
            return await self._reject(session)
```

**Handled Actions:**
- Approving/rejecting task submissions
- Confirming dangerous deletions
- Validating submission quality

#### 3. ValidationHandler

**File:** `src/bot/handlers/validation_handler.py`
**Purpose:** Handle task submission workflows
**Test Coverage:** 9 tests

```python
class ValidationHandler(BaseHandler):
    """Handles task submission and proof workflows."""

    async def can_handle(self, update: dict) -> bool:
        """Check if in validation session"""
        chat_id = update["message"]["chat"]["id"]
        stage = await SessionManager.get_session(chat_id, "task_stage")
        return stage == "VALIDATION"

    async def handle(self, update: dict) -> dict:
        """Process submission"""
        chat_id = update["message"]["chat"]["id"]

        # 1. Collect proof (photos, links, notes)
        # 2. Quality check with AI
        # 3. Ask for approval or improvements
        # 4. Store submission
        # 5. Notify boss
```

**Workflow Stages:**
- SUBMISSION - Receiving proof
- QUALITY_CHECK - AI validation
- APPROVAL_REQUEST - Awaiting response
- COMPLETION - Task marked done

#### 4. QueryHandler

**File:** `src/bot/handlers/query_handler.py`
**Purpose:** Handle status queries
**Test Coverage:** 7 tests

```python
class QueryHandler(BaseHandler):
    """Handles status queries and reports."""

    async def can_handle(self, update: dict) -> bool:
        """Check for query keywords"""
        text = update.get("message", {}).get("text", "").lower()
        query_keywords = ["status", "pending", "overdue", "report", "show"]
        return any(keyword in text for keyword in query_keywords)

    async def handle(self, update: dict) -> dict:
        """Execute query"""
        text = update["message"]["text"]

        if "pending" in text.lower():
            return await self._get_pending_tasks()
        elif "overdue" in text.lower():
            return await self._get_overdue_tasks()
        elif "report" in text.lower():
            return await self._generate_report()
        # ... more queries
```

**Query Types:**
- Status overview
- Pending tasks
- Overdue tasks
- Weekly reports
- Team performance

#### 5. ModificationHandler

**File:** `src/bot/handlers/modification_handler.py`
**Purpose:** Handle task edits and updates
**Test Coverage:** 8 tests

```python
class ModificationHandler(BaseHandler):
    """Handles task updates and edits."""

    async def can_handle(self, update: dict) -> bool:
        """Check for modification keywords"""
        text = update.get("message", {}).get("text", "").lower()
        mod_keywords = ["update", "change", "modify", "mark", "done"]
        return any(keyword in text for keyword in mod_keywords)

    async def handle(self, update: dict) -> dict:
        """Process modification"""
        text = update["message"]["text"]

        if "mark" in text.lower() and "done" in text.lower():
            return await self._mark_done(update)
        elif "update" in text.lower():
            return await self._update_task(update)
        elif "deadline" in text.lower():
            return await self._update_deadline(update)
        # ... more modifications
```

**Modification Types:**
- Mark as done
- Update status
- Change deadline
- Add notes
- Update priority

#### 6. RoutingHandler

**File:** `src/bot/handlers/routing_handler.py`
**Purpose:** Route messages and AI-powered fallback
**Test Coverage:** 7 tests

```python
class RoutingHandler(BaseHandler):
    """Central dispatcher and AI-powered fallback."""

    def __init__(self, handlers: List[BaseHandler]):
        self.handlers = handlers

    async def route(self, update: dict) -> dict:
        """Route to first matching handler."""
        for handler in self.handlers:
            if await handler.can_handle(update):
                return await handler.handle(update)

        # No handler matched, use AI intent
        return await self._ai_intent_fallback(update)

    async def _ai_intent_fallback(self, update: dict) -> dict:
        """Use DeepSeek AI for intent classification."""
        text = update["message"]["text"]

        intent = await DeepSeekAI.classify_intent(text)

        if intent == "TASK_CREATION":
            return await self._handle_task_creation(update, text)
        elif intent == "DELEGATION":
            return await self._handle_delegation(update, text)
        # ... more intents
```

### Session Management

Handlers use centralized session management:

```python
from src.memory.sessions import SessionManager

# Store session state (TTL: 1 hour default)
await SessionManager.set_session(
    chat_id=update["message"]["chat"]["id"],
    key="active_handler",
    value="validation",
    ttl=3600
)

# Retrieve session state
active = await SessionManager.get_session(chat_id, "active_handler")

# Clear session
await SessionManager.delete_session(chat_id, "active_handler")
```

**Session Keys:**
- `active_handler` - Current active handler
- `task_stage` - Current stage in task workflow
- `pending_approval` - Pending action waiting approval
- `conversation_context` - Conversation history

---

## Database Architecture

### Data Flow

```
Telegram Update
    ↓
Handler Processing
    ↓
Repository Layer (CRUD)
    ↓
PostgreSQL Database
    ↓
Cache (Redis)
    ↓
External Sync (Google Sheets/Calendar)
```

### Core Tables

```sql
-- Tasks (primary entity)
tasks (
    id, task_id, title, description, assignee, status,
    deadline, priority, created_at, updated_at, ...
)

-- Subtasks and dependencies
subtasks (id, task_id, title, status, ...)
task_dependencies (id, from_task, to_task, type, ...)

-- Audit trail
audit_logs (id, entity_type, entity_id, action, timestamp, ...)

-- Conversations
conversations (id, chat_id, task_id, created_at, ...)
messages (id, conversation_id, sender, text, timestamp, ...)

-- Team and access
team_members (id, user_id, name, role, telegram_id, ...)
oauth_tokens (id, user_id, service, token_encrypted, ...)

-- User preferences
ai_memory (id, user_id, key, value, created_at, ...)
```

### Repository Pattern

Each entity has a repository for database operations:

```python
from src.database.repositories import (
    get_task_repository,
    get_team_repository,
    get_audit_repository
)

task_repo = get_task_repository()

# CRUD operations
task = await task_repo.create({...})
task = await task_repo.get_by_id(task_id)
tasks = await task_repo.list()
updated = await task_repo.update(task_id, {...})
deleted = await task_repo.delete(task_id)

# Relationships
subtask = await task_repo.add_subtask(task_id, "...")
dep = await task_repo.add_dependency(from_task, to_task, "blocked_by")

# Queries
pending = await task_repo.get_by_status("pending")
overdue = await task_repo.get_overdue()
```

---

## External Integrations

### Telegram Bot

**File:** `src/bot/telegram_simple.py`

```
User Types Message → Telegram Server → Webhook → FastAPI
                                         ↓
                                    Handler Processing
                                         ↓
                                    Response → Telegram
```

**Webhook Setup:**
```python
# Auto-registers on startup
async def startup_event():
    await setup_telegram_webhook(
        url=f"{WEBHOOK_BASE_URL}/webhook/telegram",
        secret_token=TELEGRAM_WEBHOOK_SECRET
    )
```

### Discord Integration

**File:** `src/integrations/discord.py`

**Channels:**
- Main: All task activity
- Tasks: New tasks
- Standup: Daily reports
- Reports: Weekly/monthly

**Notifications:**
```
Task Created → Embed to #tasks
Task Completed → Reaction + Embed to #main
Daily Standup → Summary to #standup
Weekly Report → Chart to #reports
```

### Google Sheets Sync

**File:** `src/integrations/sheets.py`

**Sync Flow:**
```
Database Change Event
    ↓
Sync Job (every 5 minutes)
    ↓
Query Latest Changes
    ↓
Update Google Sheets
    ↓
Push Notifications
```

### Google Calendar Integration

**File:** `src/integrations/calendar.py`

**Features:**
- Deadline reminders
- Overdue alerts
- Calendar event creation
- Automatic deadline updates

---

## Deployment Architecture

### Local Development

```bash
python -m uvicorn src.main:app --reload
```

**Services:**
- FastAPI (port 8000)
- PostgreSQL (local or cloud)
- Redis (optional, local or cloud)

### Production (Railway)

**Services:**
- FastAPI on Railway (auto-scales)
- PostgreSQL on Railway
- Redis on Railway (optional)
- Telegram webhook (auto-configured)

**Environment Variables:**
```
TELEGRAM_BOT_TOKEN=xxx
DEEPSEEK_API_KEY=xxx
DISCORD_WEBHOOK_URL=xxx
GOOGLE_CREDENTIALS_JSON={...}
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
```

---

## Error Handling & Resilience

### Handler Error Handling

```python
async def handle(self, update: dict) -> dict:
    try:
        # Main logic
        return await process()
    except ValidationError as e:
        await self.log_execution(update, {"error": str(e)})
        return {"status": "error", "message": str(e)}
    except Exception as e:
        await logger.error(f"Handler error: {e}")
        await self._send_error_notification(update, e)
        return {"status": "error", "message": "Internal error"}
```

### Retry Logic

**Message Retry Queue:**
```python
# Automatic retries for failed messages
# Exponential backoff: 1s, 2s, 4s, 8s, 16s
# Max retries: 5
```

### Dead Letter Queue

```python
# Messages that fail after all retries
# Stored in PostgreSQL for manual review
# Available in /audit dashboard
```

---

## Security

### Token Encryption

All OAuth tokens encrypted with Fernet AES-128:

```python
from src.database.models import OAuth  # Auto-encrypts tokens
```

### Rate Limiting

```
Public: 20 req/min
Authenticated: 100 req/min
Admin: 200 req/min
```

### Audit Logging

All operations logged:
```
CREATE task_id=TASK-001, user=john
UPDATE status=completed, task_id=TASK-001
DELETE task_id=TASK-001
```

---

## Performance Optimization

### Database Performance

- 5 composite indexes (10x faster queries)
- 7 N+1 query fixes
- Connection pooling (30 concurrent connections)
- Query eager loading

### Caching

- Redis session storage
- Task status cache (5-minute TTL)
- Team member cache (hourly)

### Async Processing

- Background task queue
- Webhook non-blocking
- Parallel handler execution

---

## Testing Architecture

### Unit Tests

- Handler tests (57+ tests)
- Repository tests (129+ tests)
- Service tests
- Model tests

### Integration Tests

- Full workflow tests
- Multi-handler scenarios
- External integration tests

### Test Coverage

**Target:** 70%+
**Current:** ~65%

---

## Future Architecture Improvements

### Phase 2: (Q2 2026)

- Multi-user team bot access
- Web dashboard (React/Next.js)
- WebSocket real-time updates

### Phase 3: (Q3 2026)

- Analytics engine
- Machine learning for better routing
- Slack integration

---

## Troubleshooting Guide

### Handler Not Matching

**Problem:** Message goes to wrong handler
**Solution:** Check `can_handle()` logic in handler priority

### Database Connection Issues

**Problem:** "Connection timeout" errors
**Solution:** Check connection pool settings in `src/database/engine.py`

### Telegram Webhook Not Registered

**Problem:** Bot not receiving messages
**Solution:** Check `WEBHOOK_BASE_URL` and `TELEGRAM_BOT_TOKEN` in startup logs

### Discord Embeds Not Posting

**Problem:** Tasks don't appear in Discord
**Solution:** Check webhook URLs and channel IDs in Discord integration

---

*Last Updated: 2026-01-24*
*Maintained by: Boss Workflow Team*
