# Redis Caching Layer Implementation

**Version:** Q3 2026 - Priority 2
**Status:** ✅ Implemented
**Date:** 2026-01-25

## Overview

Redis caching layer to reduce database load and improve response times. The implementation is fully optional - if Redis is not configured, the application continues to work normally without caching.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                    │
├─────────────────────────────────────────────────────────┤
│                  Cached Repositories                    │
│  (CachedTaskRepository with @cached decorators)         │
├─────────────────────────────────────────────────────────┤
│                    Cache Decorators                     │
│  (@cached, @cache_invalidate, @cached_property_async)  │
├─────────────────────────────────────────────────────────┤
│                    Redis Client                         │
│  (Connection pooling, async operations)                 │
├─────────────────────────────────────────────────────────┤
│                      Redis Server                       │
│  (Railway Redis or external Redis instance)            │
└─────────────────────────────────────────────────────────┘
```

## Components

### 1. Redis Client (`src/cache/redis_client.py`)

- **Connection Management**: Async Redis client with connection pooling (50 connections max)
- **Graceful Degradation**: Returns `None` if Redis is not configured/available
- **Connection Timeout**: 5 seconds to prevent hanging
- **Global Instance**: Singleton pattern for efficient connection reuse

**Core Methods:**
- `get_redis()` - Get or create Redis client
- `close_redis()` - Close Redis connection
- `CacheClient.get(key)` - Get cached value
- `CacheClient.set(key, value, ttl)` - Set cached value with TTL
- `CacheClient.delete(key)` - Delete cached value
- `CacheClient.invalidate_pattern(pattern)` - Delete keys matching pattern
- `CacheClient.exists(key)` - Check if key exists
- `CacheClient.ttl(key)` - Get remaining TTL
- `CacheClient.increment(key, amount)` - Increment counter

### 2. Cache Decorators (`src/cache/decorators.py`)

#### `@cached(ttl=300, key_prefix="", skip_none=True)`

Cache function result in Redis.

**Features:**
- Automatic cache key generation from function name and arguments
- Handles instance methods (skips `self`/`cls` in key)
- Configurable TTL (default: 5 minutes)
- Optional key prefix for namespacing
- Skip caching `None` results

**Example:**
```python
@cached(ttl=600, key_prefix="user")
async def get_user(user_id: str):
    return await db.fetch_user(user_id)
```

#### `@cache_invalidate(key_prefix)`

Invalidate cache after function execution.

**Example:**
```python
@cache_invalidate("user:*")
async def update_user(user_id: str, data: dict):
    return await db.update_user(user_id, data)
```

#### `@cached_property_async(ttl=300)`

Cached property for async methods.

**Example:**
```python
class MyClass:
    @cached_property_async(ttl=600)
    async def expensive_property(self):
        return await expensive_computation()
```

### 3. Statistics Tracking (`src/cache/stats.py`)

**Application-Level Stats:**
- Hit/Miss counting
- Hit rate calculation
- Summary reporting

**Redis Server Stats:**
- Redis version
- Connected clients
- Memory usage
- Commands processed
- Keyspace hits/misses
- Persistence info

**Methods:**
- `stats.record_hit()` - Record cache hit
- `stats.record_miss()` - Record cache miss
- `stats.get_rate()` - Get hit rate (0.0-1.0)
- `stats.get_summary()` - Get app stats summary
- `stats.get_redis_stats()` - Get Redis server stats
- `stats.get_full_stats()` - Get combined stats

### 4. Cached Repository (`src/database/repositories/tasks_cached.py`)

**CachedTaskRepository** - Wrapper around TaskRepository with caching.

**Cached Read Methods (with TTL):**
- `get_by_id(task_id)` - 5 minutes
- `get_by_status(status)` - 1 minute
- `get_by_assignee(assignee)` - 1 minute
- `get_overdue()` - 2 minutes
- `get_due_soon(hours)` - 2 minutes
- `get_by_project(project_id)` - 3 minutes
- `get_daily_stats()` - 5 minutes
- `get_subtasks(task_id)` - 3 minutes
- `get_blocking_tasks(task_id)` - 3 minutes
- `get_blocked_tasks(task_id)` - 3 minutes

**Write Methods with Automatic Invalidation:**
- `create()` - Invalidates list caches
- `update()` - Invalidates specific task and list caches
- `delete()` - Invalidates specific task and list caches
- `change_status()` - Invalidates status-based caches
- `add_subtask()` - Invalidates subtask caches
- `complete_subtask()` - Invalidates subtask caches
- `add_dependency()` - Invalidates dependency caches
- `remove_dependency()` - Invalidates dependency caches
- `assign_to_project()` - Invalidates project caches
- `remove_from_project()` - Invalidates project caches

## Cache Key Patterns

All cache keys are prefixed with `boss-workflow:` to avoid collisions.

**Task Caches:**
- `task:{task_id}` - Individual task
- `tasks:status:{status}:{limit}:{offset}` - Tasks by status
- `tasks:assignee:{assignee}:{limit}:{offset}` - Tasks by assignee
- `tasks:overdue` - Overdue tasks
- `tasks:due_soon:{hours}` - Tasks due soon
- `tasks:project:{project_id}` - Tasks in project
- `tasks:daily_stats` - Daily statistics

**Relationship Caches:**
- `task:subtasks:{task_id}` - Task subtasks
- `task:blocking:{task_id}` - Tasks blocking this task
- `task:blocked:{task_id}` - Tasks blocked by this task

## Admin API Endpoints

### GET /api/admin/cache/stats

Get cache statistics.

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2026-01-25T10:30:00",
  "application": {
    "hits": 150,
    "misses": 50,
    "total": 200,
    "hit_rate": 0.75,
    "hit_rate_percent": "75.00%"
  },
  "redis": {
    "redis_version": "7.0.0",
    "connected_clients": 5,
    "used_memory_human": "1.5M",
    "total_commands_processed": 1000,
    "keyspace_hits": 180,
    "keyspace_misses": 20
  },
  "redis_hit_rate": 0.9,
  "redis_hit_rate_percent": "90.00%",
  "redis_available": true
}
```

### POST /api/admin/cache/clear?pattern=*

Clear cache entries matching pattern.

**Parameters:**
- `pattern` (query) - Pattern to match (default: `*`)

**Examples:**
- `/api/admin/cache/clear?pattern=*` - Clear all cache
- `/api/admin/cache/clear?pattern=tasks:*` - Clear all task list caches
- `/api/admin/cache/clear?pattern=task:TASK-*` - Clear specific task caches

**Response:**
```json
{
  "status": "ok",
  "pattern": "tasks:*",
  "deleted": 25,
  "timestamp": "2026-01-25T10:30:00"
}
```

### POST /api/admin/cache/reset-stats

Reset cache hit/miss statistics.

**Response:**
```json
{
  "status": "ok",
  "message": "Cache statistics reset",
  "timestamp": "2026-01-25T10:30:00"
}
```

## Environment Configuration

### Railway Environment Variables

```env
# Redis URL (provided by Railway Redis plugin)
REDIS_URL=redis://default:password@redis.railway.internal:6379
```

If `REDIS_URL` is not set or empty, caching is disabled and the application works normally.

## Usage Examples

### Using Cached Repository

```python
from src.database.repositories import get_cached_task_repository

# Use cached version instead of regular repository
task_repo = get_cached_task_repository()

# This call is cached for 5 minutes
task = await task_repo.get_by_id("TASK-202601-001")

# This call is also cached (1 minute)
pending_tasks = await task_repo.get_by_status("pending")

# Write operations automatically invalidate caches
await task_repo.update("TASK-202601-001", {"status": "completed"})
# Cache for TASK-202601-001 is now invalidated
# List caches are also invalidated
```

### Direct Cache Usage

```python
from src.cache.redis_client import cache

# Set value
await cache.set("my_key", {"data": "value"}, ttl=300)

# Get value
value = await cache.get("my_key")

# Check existence
exists = await cache.exists("my_key")

# Get TTL
ttl = await cache.ttl("my_key")

# Delete
await cache.delete("my_key")

# Pattern invalidation
deleted = await cache.invalidate_pattern("my_*")
```

### Using Decorator

```python
from src.cache.decorators import cached

@cached(ttl=600, key_prefix="expensive")
async def expensive_operation(param1: str, param2: int):
    # This function result is cached for 10 minutes
    result = await some_expensive_computation(param1, param2)
    return result

# First call - executes function
result1 = await expensive_operation("test", 123)

# Second call with same params - uses cache
result2 = await expensive_operation("test", 123)

# Different params - executes function
result3 = await expensive_operation("other", 456)
```

## Performance Impact

**Expected Improvements:**
- **Database Load**: 40-60% reduction in read queries
- **Response Time**: 30-50% faster for cached reads
- **Hit Rate Target**: >70% after warm-up

**Measured Metrics:**
- Application hit rate (tracked per request)
- Redis server hit rate (from INFO stats)
- Cache memory usage
- Average query duration savings

## Graceful Degradation

The caching layer is designed to fail gracefully:

1. **Redis Not Configured**: Returns `None`, application works normally
2. **Redis Connection Failed**: Logs warning, continues without cache
3. **Redis Timeout**: 5-second timeout prevents hanging
4. **Cache Get Failure**: Logs error, executes query normally
5. **Cache Set Failure**: Logs error, query still succeeds

**No application failures due to Redis issues.**

## Testing

Run cache tests:
```bash
python test_cache.py
```

**Test Coverage:**
1. Redis connection test
2. Cache operations (get/set/delete/pattern)
3. Cache decorator functionality
4. Statistics tracking
5. Graceful degradation

## Future Enhancements

**Q4 2026:**
- Cache warm-up on startup
- Predictive cache preloading
- Cache compression for large values
- Multi-tier caching (L1: memory, L2: Redis)

**Q1 2027:**
- Cache analytics dashboard
- Automatic cache TTL optimization
- Cache versioning for schema changes
- Distributed cache invalidation events

## Monitoring

**Key Metrics to Track:**
- Cache hit rate (application & Redis)
- Memory usage trends
- Average TTL before expiry
- Most frequently cached keys
- Cache invalidation patterns

**Alerts:**
- Hit rate < 50% (cache not effective)
- Memory usage > 80% (need scaling)
- Connection failures (Redis down)

## Migration Guide

### Switching from Regular to Cached Repository

**Before:**
```python
from src.database.repositories import get_task_repository
task_repo = get_task_repository()
```

**After:**
```python
from src.database.repositories import get_cached_task_repository
task_repo = get_cached_task_repository()
```

**All methods remain the same** - caching is transparent.

---

**Implementation Date:** 2026-01-25
**Author:** Claude (Automated Implementation)
**Status:** ✅ Complete and Tested
