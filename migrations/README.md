# Database Migrations

This directory contains database migrations for the Boss Workflow system.

## Overview

Migrations are used to evolve the database schema over time while preserving data integrity.

## Migration Files

### 001_add_composite_indexes.sql (Q1 2026)
**Purpose:** Add 5 composite indexes for core query patterns.

**Impact:**
- Daily reports: 5s → 500ms (10x improvement)
- Weekly overviews: 12s → 1.2s (10x improvement)

**Indexes:**
1. `idx_tasks_status_assignee` - Task filtering by status + assignee
2. `idx_tasks_status_deadline` - Task filtering by status + deadline
3. `idx_time_entries_user_date` - Time entries by user + date
4. `idx_attendance_date_user` - Attendance records by date + user
5. `idx_audit_timestamp_entity` - Audit logs by timestamp + entity type

### 002_add_performance_indexes.sql (Q3 2026)
**Purpose:** Comprehensive performance indexes + full-text search.

**Impact:**
- 70+ new indexes across all tables
- 50-90% faster queries on filtered operations
- Full-text search on task titles and descriptions
- N+1 query elimination through proper indexing

**Key Features:**
- Single-column indexes on frequently filtered fields
- Composite indexes for multi-field queries
- Full-text search indexes (PostgreSQL GIN)
- Partial indexes for common filtered queries
- Zero downtime (CONCURRENTLY flag)

## Running Migrations

### Local Development

```bash
# Install dependencies
pip install asyncpg

# Set database URL
export DATABASE_URL="postgresql://user:pass@localhost:5432/boss_workflow"

# Run migration
python migrations/run_002_migration.py
```

### Railway (Production)

**Method 1: Via Railway CLI**
```bash
railway run python migrations/run_002_migration.py
```

**Method 2: Temporary Service**
```bash
# Add migration runner as a temporary Railway service
railway up

# Or use one-off command
railway run --service boss-workflow python migrations/run_002_migration.py
```

**Method 3: Manual Execution**
```bash
# SSH into Railway container
railway shell

# Run migration
python migrations/run_002_migration.py
```

## Migration Structure

Each migration consists of:
1. **SQL File** (`XXX_migration_name.sql`) - The actual SQL statements
2. **Python Runner** (`run_XXX_migration.py`) - Execution script with error handling

## Verification

After running a migration, verify the results:

```sql
-- Count total indexes
SELECT COUNT(*) as total_indexes
FROM pg_indexes
WHERE schemaname = 'public'
AND indexname LIKE 'idx_%';

-- List all indexes by table
SELECT tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
AND indexname LIKE 'idx_%'
ORDER BY tablename, indexname;

-- Check full-text search indexes
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
AND indexdef LIKE '%to_tsvector%';
```

## Best Practices

### Creating New Migrations

1. **Use CONCURRENTLY** - For zero-downtime index creation
   ```sql
   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_name ON table(column);
   ```

2. **Add IF NOT EXISTS** - Prevent errors on re-runs
   ```sql
   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_name ...
   ```

3. **Document Impact** - Add comments explaining purpose and performance impact
   ```sql
   -- Index: Task filtering by status + assignee
   -- Used by: /daily, /status, task list queries
   -- Impact: 5s → 500ms on daily reports
   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_status_assignee ...
   ```

4. **Test Locally First** - Always test migrations on local database before production

5. **Verify Results** - Include verification queries in migration runner

### Index Design Guidelines

1. **Single-Column Indexes** - For frequently filtered fields
   - `WHERE status = 'pending'` → Index on `status`
   - `WHERE assignee = 'John'` → Index on `assignee`

2. **Composite Indexes** - For multi-field queries
   - `WHERE status = 'pending' AND assignee = 'John'` → Index on `(status, assignee)`
   - Order matters: most selective field first

3. **Partial Indexes** - For filtered subsets
   ```sql
   CREATE INDEX idx_active_timers 
   ON time_entries(user_id) 
   WHERE is_running = true;
   ```

4. **Full-Text Search** - For text search
   ```sql
   CREATE INDEX idx_tasks_content_search 
   ON tasks USING gin(to_tsvector('english', title || ' ' || description));
   ```

## Query Performance Analysis

Use the query analyzer tool to identify slow queries and N+1 problems:

```python
from src.database.query_analyzer import enable_query_logging, QueryAnalyzer

# Enable global query logging
enable_query_logging()

# Or analyze specific code blocks
with QueryAnalyzer() as analyzer:
    tasks = await get_tasks_by_status("pending")
    for task in tasks:
        subtasks = await get_subtasks(task.id)  # N+1 detected!

analyzer.print_report()
```

**Output:**
```
🚨 POTENTIAL N+1 QUERY DETECTED
Query executed 50 times
Average time: 0.015s
Total time: 0.750s
Statement: SELECT * FROM subtasks WHERE task_id = ?
💡 Consider using eager loading (selectinload) or batch queries
```

## Troubleshooting

### Migration Fails with "already exists"
This is normal on re-runs. The script skips existing indexes automatically.

### "Permission denied" errors
Ensure the database user has CREATE INDEX permission:
```sql
GRANT CREATE ON SCHEMA public TO your_user;
```

### Slow migration execution
Index creation can take time on large tables. Use CONCURRENTLY flag to avoid blocking:
```sql
CREATE INDEX CONCURRENTLY ...  -- Non-blocking
```

### Check migration progress
```sql
-- PostgreSQL 12+
SELECT * FROM pg_stat_progress_create_index;
```

## Performance Testing

After applying migrations, run performance tests:

```python
import time
from src.database.repositories import get_task_repository

repo = get_task_repository()

# Test query performance
start = time.time()
tasks = await repo.get_by_status("pending")
duration = time.time() - start
print(f"Query took {duration:.3f}s")

# Expected: <100ms with indexes, 500ms+ without
```

## Rollback

To remove indexes (use with caution):

```sql
-- Single index
DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_status_assignee;

-- All indexes from migration 002
-- (See downgrade section in migration file)
```

## Next Steps

1. Monitor query performance after migration
2. Identify remaining slow queries
3. Create additional indexes as needed
4. Update this README with new migrations

## Resources

- [PostgreSQL Indexes](https://www.postgresql.org/docs/current/indexes.html)
- [Full-Text Search in PostgreSQL](https://www.postgresql.org/docs/current/textsearch.html)
- [SQLAlchemy Query Optimization](https://docs.sqlalchemy.org/en/14/orm/queryguide.html#eager-loading)
