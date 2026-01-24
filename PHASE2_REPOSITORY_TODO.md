# PHASE 2 - REPOSITORY EXCEPTION HANDLING TODO

## Status: ⏳ IN PROGRESS

**Completed:** Background tasks (9) + Scheduler jobs (14)
**Remaining:** Repository exception handling (47 methods across 12 files)

---

## ✅ What's Been Done

### 1. Background Task Error Handling (COMPLETE)
- ✅ Created `src/utils/background_tasks.py` with `safe_background_task()` wrapper
- ✅ Updated 9 `asyncio.create_task()` calls across 4 files:
  - `src/main.py`: 2 tasks (webhook, Discord bot)
  - `src/memory/task_context.py`: 5 tasks (DB operations)
  - `src/services/message_queue.py`: 1 task (worker)
  - `src/utils/audit_logger.py`: 2 tasks (audit logs)

### 2. Scheduler Job Notifications (COMPLETE)
- ✅ Added `_notify_boss_of_failure()` helper to `src/scheduler/jobs.py`
- ✅ Updated all 14 scheduled jobs:
  1. Daily Standup
  2. EOD Reminder
  3. Weekly Summary
  4. Monthly Report
  5. Deadline Reminder
  6. Overdue Alert
  7. Conversation Timeout
  8. Archive Tasks
  9. Recurring Tasks
  10. Morning Email Digest
  11. Evening Email Digest
  12. Attendance Sync
  13. Weekly Time Report
  14. Proactive Check-in

### 3. Custom Exceptions (COMPLETE)
- ✅ Created `src/database/exceptions.py` with hierarchy:
  - `DatabaseError` (base)
  - `DatabaseConnectionError`
  - `DatabaseConstraintError`
  - `DatabaseOperationError`
  - `EntityNotFoundError`
  - `ValidationError`

---

## ⏳ What Remains: Repository Exception Handling

### Problem
47 repository methods currently return `None` on error instead of raising exceptions. This causes:
- Boss receives "success" messages when DB writes fail
- Silent failures that are hard to debug
- No way for callers to distinguish between "not found" and "error"

### Solution Pattern

**BEFORE (BAD):**
```python
async def create(self, task_data: Dict) -> Optional[TaskDB]:
    async with self.db.session() as session:
        try:
            task = TaskDB(...)
            session.add(task)
            await session.flush()
            return task
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return None  # ❌ Silent failure!
```

**AFTER (GOOD):**
```python
from ..exceptions import DatabaseConstraintError, DatabaseOperationError
from sqlalchemy.exc import IntegrityError

async def create(self, task_data: Dict) -> TaskDB:  # ✅ No Optional!
    async with self.db.session() as session:
        try:
            task = TaskDB(...)
            session.add(task)
            await session.flush()
            return task

        except IntegrityError as e:
            logger.error(f"Constraint violation creating task: {e}")
            raise DatabaseConstraintError(
                f"Cannot create task {task_data.get('id')}: {e}"
            )

        except Exception as e:
            logger.error(f"CRITICAL: Task creation failed: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to create task: {e}")
```

---

## Files to Update (12 repositories, 47 methods total)

### 1. `src/database/repositories/tasks.py` (~15 methods)
**Methods to fix:**
- `create()` - Line 35 - Raise DatabaseConstraintError for duplicates
- `update()` - Line 95 - Raise EntityNotFoundError if not found
- `delete()` - Line 114 - Raise EntityNotFoundError if not found
- Other methods that return None on error

**Pattern:**
- CREATE: Raise `DatabaseConstraintError` (duplicates) or `DatabaseOperationError` (other)
- UPDATE: Raise `EntityNotFoundError` (not found) or `DatabaseOperationError` (failure)
- DELETE: Raise `EntityNotFoundError` (not found)
- GET: Keep returning `None` for "not found" (this is expected behavior)

**Add imports:**
```python
from ..exceptions import (
    DatabaseConstraintError,
    DatabaseOperationError,
    EntityNotFoundError,
    ValidationError
)
from sqlalchemy.exc import IntegrityError
```

---

### 2. `src/database/repositories/audit.py` (~5 methods)
**Methods to fix:**
- `create_audit_entry()` - Return audit entry or raise
- `get_recent_audits()` - Raise on DB error, return empty list if none found
- `get_task_history()` - Raise on DB error

---

### 3. `src/database/repositories/conversations.py` (~4 methods)
**Methods to fix:**
- `create()` - Raise on duplicate or error
- `update()` - Raise EntityNotFoundError if not found
- `add_message()` - Raise on error
- `close()` - Raise EntityNotFoundError if not found

---

### 4. `src/database/repositories/attendance.py` (~5 methods)
**Methods to fix:**
- `create_record()` - Raise on duplicate or error
- `update_record()` - Raise EntityNotFoundError if not found
- `mark_synced()` - Raise on error
- `get_unsynced()` - Raise on DB error (not on empty)

---

### 5. `src/database/repositories/oauth.py` (~3 methods)
**Methods to fix:**
- `save_token()` - Raise on error
- `get_token()` - Keep None for "not found", raise on DB error
- `delete_token()` - Raise EntityNotFoundError if not found

---

### 6. `src/database/repositories/recurring.py` (~6 methods)
**Methods to fix:**
- `create()` - Raise DatabaseConstraintError for duplicates
- `update()` - Raise EntityNotFoundError if not found
- `delete()` - Raise EntityNotFoundError if not found
- `update_after_run()` - Raise EntityNotFoundError if not found
- `get_due_tasks()` - Raise on DB error (not on empty)

---

### 7. `src/database/repositories/team.py` (~3 methods)
**Methods to fix:**
- `create()` - Raise DatabaseConstraintError for duplicates
- `update()` - Raise EntityNotFoundError if not found
- `find_member()` - Keep None for "not found", raise on DB error

---

### 8. `src/database/repositories/time_tracking.py` (~3 methods)
**Methods to fix:**
- `create_entry()` - Raise on error
- `stop_entry()` - Raise EntityNotFoundError if not found
- `get_active_entry()` - Keep None for "not found", raise on DB error

---

### 9. `src/database/repositories/projects.py` (~2 methods)
**Methods to fix:**
- `create()` - Raise DatabaseConstraintError for duplicates
- `update()` - Raise EntityNotFoundError if not found

---

### 10. `src/database/repositories/staff_context.py` (~1 method)
**Methods to fix:**
- `save_context()` - Raise on error

---

### 11. `src/database/repositories/ai_memory.py` (~0 methods)
**NO CHANGES NEEDED** - This repository returns defaults by design (not errors)

---

### 12. Update `src/database/repositories/__init__.py`
**Add exception exports:**
```python
from ..exceptions import (
    DatabaseError,
    DatabaseConnectionError,
    DatabaseConstraintError,
    DatabaseOperationError,
    EntityNotFoundError,
    ValidationError,
)

__all__ = [
    # ... existing exports ...
    # Exceptions
    "DatabaseError",
    "DatabaseConnectionError",
    "DatabaseConstraintError",
    "DatabaseOperationError",
    "EntityNotFoundError",
    "ValidationError",
]
```

---

## Implementation Checklist

### For EACH repository file:

- [ ] Add exception imports at top
- [ ] Add `from sqlalchemy.exc import IntegrityError` import
- [ ] Update return type hints (remove `Optional` where appropriate)
- [ ] Replace `return None` with specific exceptions
- [ ] Keep `return None` for GET operations (expected "not found")
- [ ] Add `exc_info=True` to critical error logs
- [ ] Test locally with `python test_full_loop.py test-all`

---

## Testing Strategy

After updating each repository:

```bash
# Test basic operations
python test_full_loop.py send "create task for testing exceptions"

# Check logs for exception handling
python test_full_loop.py check-logs | grep "CRITICAL"

# Verify Railway deployment
python test_full_loop.py verify-deploy

# Run full test suite
python test_full_loop.py test-all
```

---

## Deployment Steps

1. Update repositories locally (batch 3-4 files at a time)
2. Commit: `git commit -m "feat(phase2): Repository exception handling - batch X"`
3. Push: `git push origin master`
4. Wait for Railway auto-deploy (~60s)
5. Verify: `python test_full_loop.py verify-deploy`
6. Test: `python test_full_loop.py test-all`
7. Repeat for next batch

---

## Estimated Effort

- **Per repository file:** ~10-15 minutes (read + update + test)
- **12 files total:** ~2-3 hours
- **Recommended:** Work in batches of 3-4 files, test after each batch

---

## Success Criteria

✅ All 47 repository methods raise specific exceptions instead of returning None
✅ Get operations still return None for "not found" (expected behavior)
✅ Full error context preserved in exceptions
✅ Return type hints updated (Optional removed where appropriate)
✅ All tests pass: `python test_full_loop.py test-all`
✅ Railway deployment successful
✅ No silent failures in production logs

---

**Last Updated:** 2026-01-24
**Status:** Phase 2 - Staged Integration - Steps 4-6 completed, repository work remaining
