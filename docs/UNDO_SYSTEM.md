# Enterprise Undo/Redo System

**Version:** 2.0
**Created:** 2026-01-25
**Status:** Production Ready

## Overview

The enterprise undo/redo system provides multi-level undo/redo capabilities with full audit trail integration, allowing users to reverse any reversible operation within a 7-day window.

## Features

### Core Capabilities

- **Multi-level Undo**: Support for up to 10 undo operations per user
- **Redo Support**: Redo previously undone actions
- **Full Audit Trail**: Complete integration with existing audit log system
- **Redis Caching**: Fast access to recent undo history
- **Automatic Cleanup**: Removes undo history older than 7 days
- **User Isolation**: Each user has their own undo history

### Supported Actions

The following actions can be undone:

1. **Task Deletion** (`delete_task`)
   - Restores deleted task with all metadata
   - Undo function: `restore_task`

2. **Status Changes** (`change_status`)
   - Reverts task to previous status
   - Undo function: `restore_status`

3. **Reassignments** (`reassign`)
   - Restores previous assignee
   - Undo function: `restore_assignee`

4. **Priority Changes** (`change_priority`)
   - Reverts to previous priority
   - Undo function: `restore_priority`

5. **Deadline Changes** (`change_deadline`)
   - Restores previous deadline
   - Undo function: `restore_deadline`

## Architecture

### Database Schema

```sql
CREATE TABLE undo_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    action_data JSONB NOT NULL,
    undo_function VARCHAR(100) NOT NULL,
    undo_data JSONB NOT NULL,
    description TEXT,
    metadata JSONB,
    is_undone BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    undo_timestamp TIMESTAMP
);
```

### Indexes

- `idx_undo_history_user` - Fast user lookups
- `idx_undo_history_timestamp` - Chronological ordering
- `idx_undo_history_user_time` - Combined user + time lookup
- `idx_undo_history_action_type` - Action type filtering

### Data Flow

```
Action Performed
      ↓
Record Undo Data
      ↓
Store in PostgreSQL + Redis Cache
      ↓
User Requests Undo
      ↓
Fetch from Cache (or DB)
      ↓
Execute Undo Function
      ↓
Mark as Undone
      ↓
Clear Cache
```

## Usage

### Bot Commands

**Undo Last Action:**
```
/undo
```

**Undo Specific Action:**
```
/undo [action_id]
```

**View Undo History:**
```
/undo_list
```

**Redo Undone Action:**
```
/redo [action_id]
```

### API Endpoints

**Get Undo History:**
```http
GET /api/undo/history?user_id=123&limit=10
```

Response:
```json
{
  "ok": true,
  "history": [
    {
      "id": 1,
      "action_type": "delete_task",
      "description": "Deleted task TASK-001: Fix login bug",
      "timestamp": "2026-01-25T10:30:00Z",
      "metadata": {}
    }
  ],
  "count": 1
}
```

**Undo Action:**
```http
POST /api/undo?user_id=123&action_id=1
```

Response:
```json
{
  "ok": true,
  "success": true,
  "action_type": "delete_task",
  "description": "Deleted task TASK-001: Fix login bug",
  "result": {
    "task_id": "TASK-001",
    "restored": true
  }
}
```

**Redo Action:**
```http
POST /api/redo?user_id=123&action_id=1
```

Response:
```json
{
  "ok": true,
  "success": true,
  "action_type": "delete_task",
  "description": "Deleted task TASK-001: Fix login bug",
  "result": {
    "task_id": "TASK-001",
    "deleted": true
  }
}
```

### Programmatic Usage

```python
from src.operations.undo_manager import get_undo_manager

undo_mgr = get_undo_manager()

# Record an action
await undo_mgr.record_action(
    user_id="123",
    action_type="delete_task",
    action_data={"task_id": "TASK-001"},
    undo_function="restore_task",
    undo_data={"task_data": task_dict},
    description="Deleted task TASK-001"
)

# Get history
history = await undo_mgr.get_undo_history("123", limit=10)

# Undo most recent
result = await undo_mgr.undo_action("123")

# Undo specific action
result = await undo_mgr.undo_action("123", action_id=1)

# Redo action
result = await undo_mgr.redo_action("123", action_id=1)

# Cleanup old history
count = await undo_mgr.cleanup_old_history()
```

## Integration Guide

### Recording Undoable Actions

When implementing a new undoable operation:

1. **Capture the current state** before the operation
2. **Perform the operation**
3. **Record the undo action** with complete context

Example:
```python
from src.operations.undo_manager import get_undo_manager
from src.database.repositories import get_task_repository

async def delete_task_with_undo(task_id: str, user_id: str):
    repo = get_task_repository()
    undo_mgr = get_undo_manager()

    # Get current task state
    task = await repo.get_by_id(task_id)
    if not task:
        return False

    # Store complete task data for restoration
    task_data = {
        "task_id": task.task_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "assignee": task.assignee,
        # ... all other fields
    }

    # Record undo action BEFORE deletion
    await undo_mgr.record_action(
        user_id=user_id,
        action_type="delete_task",
        action_data={"task_id": task_id},
        undo_function="restore_task",
        undo_data={"task_data": task_data},
        description=f"Deleted task {task_id}: {task.title}"
    )

    # Perform deletion
    await repo.delete(task_id)

    return True
```

## Scheduled Maintenance

**Cleanup Job:**
- **Schedule:** Daily at 2:00 AM
- **Function:** `_cleanup_undo_history_job()`
- **Action:** Removes undo history older than 7 days
- **Notification:** Boss notified on failure

## Performance Considerations

### Caching Strategy

- Last 10 actions per user cached in Redis
- TTL: 1 hour
- Cache invalidated on undo/redo operations

### Database Optimization

- JSONB indexes for efficient querying
- Partial index on `is_undone = FALSE` for active records
- Regular cleanup prevents table bloat

## Security & Privacy

- User isolation: Users can only undo their own actions
- Boss override: Boss can undo any action (future enhancement)
- Audit trail: All undo/redo operations logged
- Data retention: 7-day maximum for GDPR compliance

## Limitations

### Not Undoable

The following operations CANNOT be undone:

- Bulk operations affecting multiple tasks
- External API calls (Discord, Sheets, Calendar)
- Email notifications sent
- Audit log entries
- System configuration changes

### Known Issues

- Undo history does not cascade to related entities (subtasks, dependencies)
- No undo grouping (batch operations counted separately)
- Cannot undo actions performed by other users (except boss)

## Future Enhancements

### Planned Features (Q3 2026)

1. **Undo Grouping**: Batch operations as single undo action
2. **Boss Override**: Allow boss to undo any user's actions
3. **Undo Preview**: Show what will be restored before undoing
4. **Extended History**: Configurable retention period per user
5. **Cascade Undo**: Undo related operations automatically
6. **Undo Notifications**: Notify affected users of undos

## Migration

### Running the Migration

**Local/Development:**
```bash
python migrations/run_003_migration.py
```

**Production (Railway):**
```bash
railway run python migrations/run_003_migration.py
```

### Rollback

To rollback the migration:
```sql
DROP TABLE IF EXISTS undo_history CASCADE;
```

## Testing

### Unit Tests

```bash
pytest tests/unit/test_undo_manager.py -v
```

### Integration Tests

```bash
python test_full_loop.py send "create task for John"
python test_full_loop.py send "/undo"
```

## Monitoring

### Key Metrics

- Undo actions per user per day
- Redo rate (% of undos that get redone)
- Average undo history size per user
- Cache hit rate for undo history
- Cleanup job success rate

### Alerts

- Failed undo/redo operations
- Cleanup job failures
- Unusual undo patterns (potential abuse)
- Cache failures

## Support

For issues or questions:
- Check logs: `/api/undo/history?user_id=<id>`
- Test undo: `/undo_list` in Telegram
- Trigger cleanup: Manual job trigger available
- Report bugs: Create issue with full context

---

**Last Updated:** 2026-01-25
**Maintained By:** Development Team
**Version:** 2.0
