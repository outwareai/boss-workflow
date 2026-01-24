# Monitoring & Observability Guide

This guide covers monitoring, logging, and observability practices for the Boss Workflow system.

## Table of Contents

- [Logging Strategy](#logging-strategy)
- [Error Tracking](#error-tracking)
- [Performance Monitoring](#performance-monitoring)
- [Health Checks](#health-checks)
- [Alerting](#alerting)
- [Testing & Validation](#testing--validation)

## Logging Strategy

### Log Levels

The system uses Python's standard logging levels:

```python
import logging

logger = logging.getLogger(__name__)

# CRITICAL (50) - System failure, immediate action required
logger.critical("Database connection lost - system halted")

# ERROR (40) - Error occurred but system continues
logger.error(f"Failed to send Discord notification: {error}")

# WARNING (30) - Something unexpected but handled
logger.warning(f"Retry attempt {retry_count}/3 for DeepSeek API")

# INFO (20) - Normal operations, important events
logger.info(f"Task TASK-001 created successfully")

# DEBUG (10) - Detailed diagnostic information
logger.debug(f"Processing intent: {intent_data}")
```

### Logging Best Practices

**DO:**
```python
# Use f-strings with context
logger.info(f"User {user_id} created task {task_id}")

# Log exceptions with stack trace
try:
    result = await risky_operation()
except Exception as e:
    logger.error(f"Operation failed: {e}", exc_info=True)

# Structure log messages
logger.info(f"[TASK_CREATE] user={user_id} assignee={assignee} priority={priority}")
```

**DON'T:**
```python
# Don't log sensitive data
logger.info(f"Token: {oauth_token}")  # ❌ NEVER

# Don't use print statements
print("Debug message")  # ❌ Use logger.debug()

# Don't log in tight loops without throttling
for item in million_items:
    logger.info(f"Processing {item}")  # ❌ Performance impact
```

### Log Configuration

Configure logging in `src/config/settings.py`:

```python
import logging
from config.settings import settings

logging.basicConfig(
    level=logging.INFO if settings.ENVIRONMENT == "production" else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set third-party library log levels
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.INFO)
```

## Error Tracking

### Railway Logs

View production logs in Railway:

```bash
# Via Railway CLI
railway logs -s boss-workflow

# Filter by level
railway logs -s boss-workflow | grep ERROR

# Follow logs in real-time
railway logs -s boss-workflow --follow

# Get last 200 lines
railway logs -s boss-workflow --tail 200
```

### Error Patterns

**Background Task Errors:**
```python
# src/scheduler/jobs.py sends notifications on error
async def send_daily_standup():
    try:
        # Job logic
        pass
    except Exception as e:
        logger.error(f"Daily standup failed: {e}", exc_info=True)
        await notify_admin(f"❌ Standup job failed: {e}")
```

**Repository Errors:**
```python
# src/database/repositories/ have comprehensive exception handling
async def create_task(self, task_data):
    try:
        task = TaskDB(**task_data)
        self.db.add(task)
        await self.db.commit()
        return task
    except IntegrityError as e:
        logger.error(f"Task creation integrity error: {e}")
        await self.db.rollback()
        raise TaskCreationError("Task ID already exists")
    except SQLAlchemyError as e:
        logger.error(f"Database error creating task: {e}", exc_info=True)
        await self.db.rollback()
        raise
```

### Telegram Error Notifications

Errors are sent to boss via Telegram when configured:

```python
# Set in .env
TELEGRAM_ERROR_NOTIFICATIONS=true
TELEGRAM_BOSS_CHAT_ID=123456789

# Errors automatically sent for:
# - Scheduler job failures
# - Background task failures
# - Critical system errors
```

## Performance Monitoring

### Request Timing

Track API request times:

```python
import time
from functools import wraps

def timing_decorator(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start
            logger.info(f"{func.__name__} completed in {duration:.2f}s")
            return result
        except Exception as e:
            duration = time.time() - start
            logger.error(f"{func.__name__} failed after {duration:.2f}s: {e}")
            raise
    return wrapper
```

### Database Query Performance

Monitor slow queries:

```python
# Add to database session config
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault('query_start_time', []).append(time.time())

@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.time() - conn.info['query_start_time'].pop(-1)
    if total > 1.0:  # Log queries taking > 1 second
        logger.warning(f"Slow query ({total:.2f}s): {statement[:200]}")
```

### Rate Limiting Metrics

Track rate limit hits with slowapi:

```python
# src/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=lambda: "global")

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    logger.warning(f"Rate limit exceeded: {request.url}")
    return _rate_limit_exceeded_handler(request, exc)
```

## Health Checks

### System Health Endpoint

Check overall system health:

```bash
# GET /health
curl https://boss-workflow-production.up.railway.app/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2026-01-25T10:30:00Z",
  "version": "2.5.0",
  "components": {
    "database": "connected",
    "redis": "connected",
    "telegram": "active",
    "deepseek": "active"
  }
}
```

### Component Health Checks

**Database:**
```python
async def check_database():
    try:
        await db.execute("SELECT 1")
        return {"status": "connected"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "error", "message": str(e)}
```

**Redis:**
```python
async def check_redis():
    try:
        await redis_client.ping()
        return {"status": "connected"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "error", "message": str(e)}
```

**External APIs:**
```python
async def check_telegram():
    try:
        me = await telegram_bot.get_me()
        return {"status": "active", "bot_username": me.username}
    except Exception as e:
        logger.error(f"Telegram health check failed: {e}")
        return {"status": "error", "message": str(e)}
```

### Scheduled Health Checks

Run health checks periodically:

```python
# src/scheduler/jobs.py
@scheduler.scheduled_job('cron', minute='*/5')  # Every 5 minutes
async def system_health_check():
    """Check system health and alert if issues detected."""
    health = {
        "database": await check_database(),
        "redis": await check_redis(),
        "telegram": await check_telegram(),
        "deepseek": await check_deepseek()
    }

    unhealthy = [k for k, v in health.items() if v["status"] != "connected" and v["status"] != "active"]

    if unhealthy:
        logger.error(f"Unhealthy components: {unhealthy}")
        await notify_admin(f"⚠️ System health issue: {', '.join(unhealthy)}")
```

## Alerting

### Alert Channels

**Telegram (Primary):**
- Boss notifications for critical errors
- Task approval requests
- Daily summaries

**Discord (Secondary):**
- Team notifications
- Task updates
- System status

**Railway Logs (Diagnostic):**
- All application logs
- Debug information
- Performance metrics

### Alert Severity Levels

**Critical (🔴):**
- Database connection lost
- Unable to process any requests
- Security breach detected

**High (🟠):**
- Scheduler job failures
- External API timeouts
- Data sync failures

**Medium (🟡):**
- Rate limit exceeded
- Slow query detected
- Retry exhausted

**Low (🔵):**
- Unusual activity
- Configuration warnings
- Performance degradation

### Alert Configuration

Configure alerts in `.env`:

```bash
# Telegram alerts
TELEGRAM_ERROR_NOTIFICATIONS=true
TELEGRAM_BOSS_CHAT_ID=123456789

# Discord alerts
DISCORD_ERROR_WEBHOOK=https://discord.com/api/webhooks/xxx/xxx

# Alert thresholds
SLOW_QUERY_THRESHOLD_SECONDS=1.0
ERROR_RATE_ALERT_THRESHOLD=10  # errors per minute
```

### Alert Examples

**Critical Alert:**
```python
async def alert_critical(title: str, message: str):
    """Send critical alert via all channels."""
    logger.critical(f"{title}: {message}")

    # Telegram
    await telegram_bot.send_message(
        chat_id=settings.TELEGRAM_BOSS_CHAT_ID,
        text=f"🔴 CRITICAL: {title}\n\n{message}"
    )

    # Discord
    await discord_webhook.send({
        "content": f"@everyone 🔴 CRITICAL: {title}",
        "embeds": [{"description": message, "color": 0xFF0000}]
    })
```

**Error Rate Alert:**
```python
error_count = 0
last_alert = None

async def track_error():
    global error_count, last_alert
    error_count += 1

    # Alert if > 10 errors in last minute
    if error_count >= 10 and (not last_alert or time.time() - last_alert > 300):
        await alert_high("High Error Rate", f"{error_count} errors in the last minute")
        last_alert = time.time()
        error_count = 0
```

## Testing & Validation

### Test Monitoring

Run tests with verbose logging:

```bash
# Run all tests with logging
pytest tests/ -v --log-cli-level=INFO

# Run specific test suite
pytest tests/unit/test_api_routes.py -v

# Run with coverage and HTML report
pytest tests/ -v --cov=src --cov-report=html

# Open coverage report
open htmlcov/index.html
```

### Integration Test Monitoring

Use `test_full_loop.py` for end-to-end testing:

```bash
# Full integration test
python test_full_loop.py test-all

# Read Railway logs
python test_full_loop.py check-logs

# Verify deployment health
python test_full_loop.py verify-deploy
```

### Load Testing

Monitor performance under load:

```python
# tests/load/scenarios.py
import asyncio
import time
from locust import HttpUser, task, between

class BossWorkflowUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def create_task(self):
        start = time.time()
        response = self.client.post("/api/tasks", json={
            "task_id": f"TASK-{int(time.time())}",
            "title": "Load test task",
            "assignee": "test_user"
        })
        duration = time.time() - start

        if duration > 2.0:
            logger.warning(f"Slow request: {duration:.2f}s")
```

Run load test:
```bash
locust -f tests/load/scenarios.py --host=https://boss-workflow-production.up.railway.app
```

## Monitoring Checklist

### Daily
- [ ] Check Railway logs for errors
- [ ] Review Telegram error notifications
- [ ] Verify scheduler jobs ran successfully

### Weekly
- [ ] Run full integration test suite
- [ ] Check test coverage (target: 70%+)
- [ ] Review slow query logs
- [ ] Verify health check status

### Monthly
- [ ] Security audit (CVE scan)
- [ ] Dependency updates
- [ ] Performance benchmarking
- [ ] Load testing
- [ ] Backup verification

## Useful Commands

### Railway Monitoring

```bash
# View logs
railway logs -s boss-workflow --tail 200

# Follow logs in real-time
railway logs -s boss-workflow --follow

# Check deployment status
railway status -s boss-workflow

# View environment variables
railway variables -s boss-workflow
```

### Database Monitoring

```bash
# Connect to production database
railway connect postgres -s boss-workflow

# Check table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

# Check slow queries (if pg_stat_statements enabled)
SELECT
    query,
    calls,
    mean_exec_time,
    max_exec_time
FROM pg_stat_statements
WHERE mean_exec_time > 1000  -- > 1 second
ORDER BY mean_exec_time DESC
LIMIT 10;
```

### Test Monitoring

```bash
# Run tests with timing
pytest tests/ -v --durations=10

# Run tests with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_api_routes.py -v

# Run integration tests
python test_full_loop.py test-all
```

## Future Monitoring Enhancements

### Phase 1: Metrics Collection
- [ ] Add Prometheus metrics export
- [ ] Track request rates, error rates, response times
- [ ] Monitor database connection pool usage
- [ ] Track cache hit/miss rates

### Phase 2: Dashboards
- [ ] Create Grafana dashboards
- [ ] Real-time system health visualization
- [ ] Performance trend analysis
- [ ] Alert history and trends

### Phase 3: Advanced Alerting
- [ ] Anomaly detection with ML
- [ ] Predictive alerting
- [ ] Auto-remediation for common issues
- [ ] PagerDuty/Opsgenie integration

### Phase 4: Distributed Tracing
- [ ] Add OpenTelemetry instrumentation
- [ ] Trace requests across services
- [ ] Identify performance bottlenecks
- [ ] Correlation of logs, metrics, traces

---

**Last Updated:** 2026-01-25
**System Version:** 2.5.0
**Health Status:** 9.5/10 ⭐
