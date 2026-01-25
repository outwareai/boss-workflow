"""
Boss Workflow Automation - Main Application Entry Point

FastAPI application with webhook endpoints and background scheduler.
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

import asyncio

from config import settings
from .models.api_validation import (
    SubtaskCreate,
    DependencyCreate,
    TaskFilter,
    AdminAuthRequest,
    TeachingRequest,
    ProjectCreate,
    TelegramUpdate,
)
from .bot.telegram_simple import get_telegram_bot_simple
from .scheduler.jobs import get_scheduler_manager
from .memory.preferences import get_preferences_manager
from .memory.context import get_conversation_context
from .integrations.sheets import get_sheets_integration
from .integrations.discord import get_discord_integration
from .integrations.calendar import get_calendar_integration
from .integrations.discord_bot import (
    get_discord_bot,
    start_discord_bot,
    stop_discord_bot,
    setup_status_callback,
    setup_attendance_callback,
    setup_task_submission_callback,
)
from .database import init_database, close_database, get_database
from .database.sync import get_sheets_sync

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # Startup
    logger.info("Starting Boss Workflow Automation...")

    # Initialize PostgreSQL database
    try:
        if await init_database():
            logger.info("PostgreSQL database initialized")
        else:
            logger.warning("PostgreSQL not configured or failed to initialize")
    except Exception as e:
        logger.warning(f"PostgreSQL init failed: {e}")

    # Initialize services with error handling
    try:
        telegram_bot = get_telegram_bot_simple()
        await telegram_bot.initialize()
        logger.info("Telegram bot initialized")

        # Set webhook if URL is configured
        if settings.webhook_base_url:
            await telegram_bot.set_webhook()
            logger.info("Telegram webhook set")
    except Exception as e:
        logger.error(f"Telegram init failed (will retry on first message): {e}")

    # Initialize integrations (optional - don't fail startup)
    try:
        sheets = get_sheets_integration()
        await sheets.initialize()
        logger.info("Google Sheets initialized")
    except Exception as e:
        logger.warning(f"Google Sheets init failed: {e}")

    try:
        calendar = get_calendar_integration()
        await calendar.initialize()
        logger.info("Google Calendar initialized")
    except Exception as e:
        logger.warning(f"Google Calendar init failed: {e}")

    # Connect to Redis (optional)
    try:
        prefs = get_preferences_manager()
        await prefs.connect()
    except Exception as e:
        logger.warning(f"Preferences Redis failed: {e}")

    try:
        context = get_conversation_context()
        await context.connect()
    except Exception as e:
        logger.warning(f"Context Redis failed: {e}")

    # Q3 2026: Initialize Redis cache
    try:
        from .cache.redis_client import get_redis
        redis_client = await get_redis()
        if redis_client:
            logger.info("Redis cache initialized")
        else:
            logger.warning("Redis cache not configured (REDIS_URL not set)")
    except Exception as e:
        logger.warning(f"Redis cache init failed: {e}")

    # Start scheduler
    try:
        scheduler = get_scheduler_manager()
        scheduler.start()
        logger.info("Scheduler started")
    except Exception as e:
        logger.warning(f"Scheduler failed: {e}")

    # Start Discord bot for reactions
    discord_bot_task = None
    try:
        if settings.discord_bot_token:
            # Set up status update callback
            async def handle_status_update(task_id: str, new_status: str, changed_by: str, source: str):
                """Handle status update from Discord reaction."""
                logger.info(f"Discord reaction status update: {task_id} -> {new_status} by {changed_by}")
                try:
                    # Update in PostgreSQL
                    from .database.repositories import get_task_repository, get_audit_repository
                    task_repo = get_task_repository()
                    audit_repo = get_audit_repository()

                    task = await task_repo.get_by_id(task_id)
                    if task:
                        old_status = task.status
                        await task_repo.update(task_id, {"status": new_status})

                        # Log audit
                        await audit_repo.log_change(
                            task_id=task_id,
                            action="status_change",
                            field_changed="status",
                            old_value=old_status,
                            new_value=new_status,
                            changed_by=changed_by,
                            reason=f"Via {source}"
                        )
                        logger.info(f"Task {task_id} status updated to {new_status} in database")

                    # Update in Google Sheets
                    sheets = get_sheets_integration()
                    await sheets.update_task_status(task_id, new_status)
                    logger.info(f"Task {task_id} status updated to {new_status} in sheets")

                except Exception as e:
                    logger.error(f"Error updating task status from Discord: {e}")

            async def handle_priority_update(task_id: str, new_priority: str, changed_by: str, source: str):
                """Handle priority update from Discord reaction."""
                logger.info(f"Discord reaction priority update: {task_id} -> {new_priority} by {changed_by}")
                try:
                    from .database.repositories import get_task_repository
                    task_repo = get_task_repository()
                    await task_repo.update(task_id, {"priority": new_priority})
                    logger.info(f"Task {task_id} priority updated to {new_priority}")
                except Exception as e:
                    logger.error(f"Error updating task priority from Discord: {e}")

            setup_status_callback(handle_status_update)
            from .integrations.discord_bot import setup_priority_callback
            setup_priority_callback(handle_priority_update)

            # Set up attendance callback
            async def handle_attendance(user_id: str, user_name: str, event_type: str, channel_id: str, channel_name: str):
                """Handle attendance events from Discord."""
                logger.info(f"Attendance event: {user_name} ({user_id}) - {event_type} in {channel_name}")
                try:
                    from .services.attendance import get_attendance_service
                    service = get_attendance_service()
                    result = await service.process_event(
                        user_id=user_id,
                        user_name=user_name,
                        event_type=event_type,
                        channel_id=channel_id,
                        channel_name=channel_name,
                    )
                    logger.info(f"Attendance result: {result.get('message', 'Success')}")
                    return result
                except Exception as e:
                    logger.error(f"Error processing attendance: {e}")
                    return {
                        "success": False,
                        "emoji": "⚠️",
                        "message": f"Error: {e}",
                    }

            setup_attendance_callback(handle_attendance)

            # Set up task submission callback (staff completing tasks)
            async def handle_task_submission(
                user_id: str,
                user_name: str,
                task_ids: list,
                message_content: str,
                attachment_urls: list,
                channel_id: str,
                channel_name: str,
                message_url: str,
            ):
                """Handle task submission from Discord staff."""
                logger.info(f"Task submission from {user_name}: {task_ids}")
                try:
                    import aiohttp

                    # Build notification message for boss
                    task_list = ", ".join(task_ids)
                    proof_info = f"\n📎 {len(attachment_urls)} attachment(s)" if attachment_urls else ""

                    notification = f"""📨 *Task Submission from Discord*

👤 *From:* {user_name}
📋 *Task(s):* {task_list}
💬 *Message:* {message_content[:300]}{'...' if len(message_content) > 300 else ''}{proof_info}

🔗 [View on Discord]({message_url})

Reply with `/approve {task_ids[0]}` or `/reject {task_ids[0]} [reason]`"""

                    # Send to boss via Telegram API directly
                    telegram_api = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
                    timeout = aiohttp.ClientTimeout(total=30.0)  # 30 second timeout for Telegram API
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        await session.post(
                            telegram_api,
                            json={
                                "chat_id": settings.telegram_boss_chat_id,
                                "text": notification,
                                "parse_mode": "Markdown",
                                "disable_web_page_preview": True,
                            }
                        )

                    # Update task status to in_review
                    from .database.repositories import get_task_repository
                    task_repo = get_task_repository()
                    for task_id in task_ids:
                        try:
                            await task_repo.update(task_id, {
                                "status": "in_review",
                                "updated_at": datetime.now(),
                            })
                            logger.info(f"Task {task_id} status updated to in_review")
                        except Exception as e:
                            logger.warning(f"Could not update task {task_id} status: {e}")

                    return {
                        "success": True,
                        "message": f"Submission received for {len(task_ids)} task(s)",
                        "reply_message": f"📨 Submission received! Boss has been notified about: {task_list}",
                    }

                except Exception as e:
                    logger.error(f"Error handling task submission: {e}")
                    return {
                        "success": False,
                        "message": f"Error: {e}",
                    }

            setup_task_submission_callback(handle_task_submission)

            # Set up staff message callback (AI assistant for staff)
            async def handle_staff_message(
                user_id: str,
                user_name: str,
                message: str,
                channel_id: str,
                channel_name: str,
                message_url: str = None,
                attachments: list = None,
                thread_id: str = None,
            ):
                """Handle staff messages for AI assistant conversations."""
                logger.info(f"Staff message from {user_name} in {channel_name}: {message[:50]}...")
                try:
                    from .bot.staff_handler import get_staff_handler
                    handler = get_staff_handler()
                    result = await handler.handle_staff_message(
                        user_id=user_id,
                        user_name=user_name,
                        message=message,
                        channel_id=channel_id,
                        channel_name=channel_name,
                        message_url=message_url,
                        attachments=attachments or [],
                        thread_id=thread_id,
                    )
                    logger.info(f"Staff message handled: action={result.get('action')}")
                    return result
                except Exception as e:
                    logger.error(f"Error handling staff message: {e}", exc_info=True)
                    return {
                        "success": False,
                        "response": f"Sorry, I encountered an error. Please try again.",
                        "error": str(e),
                    }

            from .integrations.discord_bot import setup_staff_message_callback
            setup_staff_message_callback(handle_staff_message)

            # Enable AI assistant in general/tasks channels
            bot = get_discord_bot()
            if bot:
                # Enable for dev general channel (and any other channels you want)
                if settings.discord_dev_general_channel_id:
                    bot.enable_ai_assistant_for_channel(int(settings.discord_dev_general_channel_id))
                if settings.discord_dev_tasks_channel_id:
                    bot.enable_ai_assistant_for_channel(int(settings.discord_dev_tasks_channel_id))
                # AI assistant also responds in threads automatically

            # Start bot in background
            # PHASE 2 FIX: Safe background task for Discord bot
            from .utils.background_tasks import create_safe_task
            discord_bot_task = create_safe_task(start_discord_bot(), "discord-bot-startup")
            logger.info("Discord bot starting in background (with AI assistant)...")
        else:
            logger.info("Discord bot token not configured, skipping bot startup")
    except Exception as e:
        logger.warning(f"Discord bot failed to start: {e}")

    # Start message queue worker for retry handling
    message_queue_worker = None
    try:
        from .services.message_queue import get_message_queue, MessageType

        queue = get_message_queue()

        # Register Discord handler for retrying failed requests
        async def handle_discord_retry(payload: dict) -> bool:
            """Handler for retrying Discord Bot API requests."""
            try:
                discord = get_discord_integration()
                endpoint = payload.get("endpoint", "")
                json_data = payload.get("json_data", {})

                if not endpoint:
                    return False

                # Make the request without re-queueing on failure
                status, data = await discord._api_request("POST", endpoint, json_data, queue_on_failure=False)
                return status in [200, 201, 204]
            except Exception as e:
                logger.error(f"Discord retry failed: {e}")
                return False

        queue.register_handler(MessageType.DISCORD_BOT, handle_discord_retry)

        # Start the worker
        await queue.start_worker()
        logger.info("Message queue worker started")

    except Exception as e:
        logger.warning(f"Message queue worker failed to start: {e}")

    logger.info("Boss Workflow Automation started successfully!")

    yield

    # Shutdown
    logger.info("Shutting down Boss Workflow Automation...")

    # Stop Discord bot
    try:
        await stop_discord_bot()
        if discord_bot_task:
            discord_bot_task.cancel()
            try:
                await discord_bot_task
            except asyncio.CancelledError:
                pass
        logger.info("Discord bot stopped")
    except Exception as e:
        logger.warning(f"Error stopping Discord bot: {e}")

    try:
        scheduler = get_scheduler_manager()
        scheduler.stop()
    except Exception as e:
        logger.warning(f"Failed to stop scheduler during shutdown: {e}")

    # Stop message queue worker
    try:
        from .services.message_queue import get_message_queue
        queue = get_message_queue()
        await queue.stop_worker()
        logger.info("Message queue worker stopped")
    except Exception as e:
        logger.warning(f"Failed to stop message queue worker during shutdown: {e}")

    try:
        prefs = get_preferences_manager()
        await prefs.disconnect()
    except Exception as e:
        logger.warning(f"Failed to disconnect preferences manager during shutdown: {e}")

    try:
        context = get_conversation_context()
        await context.disconnect()
    except Exception as e:
        logger.warning(f"Failed to disconnect conversation context during shutdown: {e}")

    # Q3 2026: Close Redis cache connection
    try:
        from .cache.redis_client import close_redis
        await close_redis()
        logger.info("Redis cache connection closed")
    except Exception as e:
        logger.warning(f"Failed to close Redis cache during shutdown: {e}")

    try:
        await close_database()
    except Exception as e:
        logger.warning(f"Failed to close database during shutdown: {e}")

    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Boss Workflow Automation",
    description="Conversational task management system with AI-powered clarification",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware (Q1 2026 Security - Hybrid approach with feature flag)
try:
    if settings.use_slowapi_rate_limiting:
        # Use slowapi implementation
        from .middleware.slowapi_limiter import setup_rate_limiting
        from slowapi.errors import RateLimitExceeded

        limiter = setup_rate_limiting(app, settings.redis_url)
        logger.info("Slowapi rate limiting enabled (via feature flag)")

        # Import monitoring metrics
        from .monitoring import rate_limit_violations_total

        # Add custom exception handler for slowapi rate limit exceeded
        @app.exception_handler(RateLimitExceeded)
        async def slowapi_rate_limit_handler(request: Request, exc: RateLimitExceeded):
            """Handle slowapi rate limit exceeded with custom response."""
            endpoint = request.url.path
            client_ip = request.client.host if request.client else 'unknown'

            logger.warning(
                f"Rate limit exceeded: {client_ip} "
                f"on {endpoint}"
            )

            # Record metric
            try:
                rate_limit_violations_total.labels(
                    endpoint=endpoint,
                    limiter="slowapi",
                    client_type="api"
                ).inc()
            except Exception as me:
                logger.warning(f"Failed to record rate limit metric: {me}")

            # Extract retry_after from exception if available
            retry_after = getattr(exc, 'retry_after', None)

            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(int(retry_after)) if retry_after else "60"},
                content={
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": retry_after or 60,
                    "rate_limit": {
                        "authenticated": settings.rate_limit_authenticated,
                        "public": settings.rate_limit_public,
                    }
                }
            )
    else:
        # Use existing custom middleware (default)
        from .middleware.rate_limit import RateLimitMiddleware
        from .memory.preferences import get_redis_client

        redis_client = get_redis_client()
        app.add_middleware(RateLimitMiddleware, redis_client=redis_client)
        logger.info("Custom rate limiting middleware enabled (default)")
except Exception as e:
    logger.warning(f"Rate limiting middleware disabled: {e}")

# Q3 2026: Add Prometheus metrics middleware and endpoint
try:
    from prometheus_client import make_asgi_app
    from prometheus_fastapi_instrumentator import Instrumentator
    from .monitoring.middleware import metrics_middleware

    # Add custom metrics middleware
    app.middleware("http")(metrics_middleware)

    # Mount Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # Instrument FastAPI with default metrics
    Instrumentator().instrument(app).expose(app, endpoint="/metrics/default")

    logger.info("Prometheus metrics enabled at /metrics")
except ImportError as e:
    logger.warning(f"Prometheus metrics disabled: {e}")

# Register web routes (onboarding, OAuth, team management)
from .web.routes import router as web_router
app.include_router(web_router)


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "status": "healthy",
        "service": "Boss Workflow Automation",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Detailed health check endpoint."""
    # Check database health
    db_health = {"status": "not_configured"}
    try:
        db = get_database()
        db_health = await db.health_check()
    except Exception as e:
        db_health = {"status": "error", "error": str(e)}

    # Check Discord bot status
    discord_bot = get_discord_bot()
    discord_bot_status = "not_configured"
    if discord_bot:
        discord_bot_status = "connected" if not discord_bot.is_closed() else "disconnected"

    return {
        "status": "healthy",
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "services": {
            "telegram": bool(settings.telegram_bot_token),
            "deepseek": bool(settings.deepseek_api_key),
            "discord_webhook": bool(settings.discord_webhook_url),
            "discord_bot": discord_bot_status,
            "sheets": bool(settings.google_sheet_id),
            "redis": bool(settings.redis_url),
            "database": db_health.get("status", "unknown"),
        }
    }


@app.get("/health/db")
async def db_health():
    """Database connection pool health check."""
    from .database.connection import get_pool_status

    try:
        db = get_database()

        # Check if database is initialized
        if not db._initialized:
            return {
                "status": "not_initialized",
                "error": "Database not yet initialized"
            }

        # Get pool status using new helper
        pool_status = await get_pool_status()

        # Q3 2026: Update Prometheus metrics for DB pool
        try:
            from .monitoring.prometheus import update_db_pool_metrics
            if db.engine and db.engine.pool:
                update_db_pool_metrics(db.engine.pool)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to update DB pool metrics: {e}")

        return {
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            **pool_status
        }

    except Exception as e:
        logger.error(f"Error checking database health: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }


@app.get("/api/admin/pool-status")
async def get_admin_pool_status():
    """
    Get detailed database connection pool status with health checks.

    Q3 2026: Pool monitoring and leak detection endpoint.
    """
    from .database.health import get_detailed_health_report

    try:
        report = await get_detailed_health_report()
        return report

    except Exception as e:
        logger.error(f"Error getting pool status: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }


@app.post("/admin/run-migration-simple")
async def run_migration_simple(auth: AdminAuthRequest):
    """
    Run Q1 2026 composite indexes migration (hardcoded - guaranteed to work).

    Q1 2026 Security: Moved secret from query param to body, using constant-time comparison.
    Q3 2026: Added Pydantic validation for admin secret.
    """
    try:
        import secrets as sec_module

        # Security check - constant-time comparison
        admin_secret = settings.admin_secret if hasattr(settings, 'admin_secret') else None

        if not admin_secret or not sec_module.compare_digest(auth.secret, admin_secret):
            raise HTTPException(status_code=403, detail="Unauthorized")

        db = get_database()
        import asyncpg

        # Get database URL in asyncpg format
        db_url = db.engine.url.render_as_string(hide_password=False).replace("postgresql+asyncpg://", "postgresql://")

        # 5 composite indexes from Q1 2026 migration
        indexes = [
            ("idx_tasks_status_assignee", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_status_assignee ON tasks(status, assignee)"),
            ("idx_tasks_status_deadline", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_status_deadline ON tasks(status, deadline)"),
            ("idx_time_entries_user_date", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_time_entries_user_date ON time_entries(user_id, started_at)"),
            ("idx_attendance_date_user", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_attendance_date_user ON attendance_records(CAST(event_time AS DATE), user_id)"),
            ("idx_audit_timestamp_entity", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_timestamp_entity ON audit_logs(timestamp DESC, entity_type)")
        ]

        conn = await asyncpg.connect(db_url)
        results = []

        try:
            for name, sql in indexes:
                try:
                    await conn.execute(sql)
                    results.append(f"✅ Created: {name}")
                except Exception as e:
                    if 'already exists' in str(e):
                        results.append(f"⚠️  Already exists: {name}")
                    else:
                        results.append(f"❌ Error on {name}: {str(e)[:100]}")

            # Verify
            verify = await conn.fetch("""
                SELECT indexname, tablename
                FROM pg_indexes
                WHERE schemaname = 'public'
                AND indexname IN ('idx_tasks_status_assignee', 'idx_tasks_status_deadline',
                                  'idx_time_entries_user_date', 'idx_attendance_date_user',
                                  'idx_audit_timestamp_entity')
            """)

            return {
                "status": "success",
                "timestamp": __import__('datetime').datetime.now().isoformat(),
                "results": results,
                "verified": len(verify),
                "indexes": [{"name": row["indexname"], "table": row["tablename"]} for row in verify]
            }

        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Migration error: {e}")
        return {"status": "error", "error": str(e)}


@app.post("/admin/run-migration")
async def run_migration(auth: AdminAuthRequest):
    """
    Run database migrations (admin only).
    Requires ADMIN_SECRET environment variable in request body.

    Q1 2026 Security: Moved secret from query param to body, using constant-time comparison.
    Q3 2026: Added Pydantic validation for admin secret.
    """
    try:
        import secrets as sec_module

        # Security: Require admin secret - constant-time comparison
        admin_secret = settings.admin_secret if hasattr(settings, 'admin_secret') else None

        if not admin_secret or not sec_module.compare_digest(auth.secret, admin_secret):
            raise HTTPException(status_code=403, detail="Unauthorized - Invalid admin secret")

        db = get_database()

        # Read migration SQL
        import pathlib
        migration_path = pathlib.Path(__file__).parent.parent / "migrations" / "001_add_composite_indexes.sql"

        if not migration_path.exists():
            return {
                "status": "error",
                "error": f"Migration file not found: {migration_path}"
            }

        migration_sql = migration_path.read_text(encoding="utf-8")

        # Split into individual statements
        statements = [s.strip() for s in migration_sql.split(';') if s.strip() and not s.strip().startswith('--')]

        results = []

        # CREATE INDEX CONCURRENTLY cannot run in a transaction, so use raw connection
        import asyncpg
        # Convert SQLAlchemy URL to asyncpg-compatible format
        db_url = db.engine.url.render_as_string(hide_password=False)
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(db_url)

        try:
            for statement in statements:
                if not statement or statement.startswith('--'):
                    continue

                try:
                    # Execute statement (autocommit mode by default in asyncpg)
                    await conn.execute(statement)

                    # Extract index name
                    if 'idx_' in statement:
                        index_name = statement.split('idx_')[1].split()[0]
                        results.append(f"✅ Created index: idx_{index_name}")
                    else:
                        results.append("✅ Statement executed")

                except Exception as e:
                    if 'already exists' in str(e):
                        if 'idx_' in statement:
                            index_name = statement.split('idx_')[1].split()[0]
                            results.append(f"⚠️  Index already exists: idx_{index_name}")
                        else:
                            results.append("⚠️  Already exists (skipped)")
                    else:
                        results.append(f"❌ Error: {str(e)[:100]}")

            # Verify indexes
            indexes = await conn.fetch("""
                SELECT schemaname, tablename, indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                AND indexname LIKE 'idx_%'
                ORDER BY tablename, indexname
            """)

            return {
                "status": "success",
                "timestamp": __import__('datetime').datetime.now().isoformat(),
                "results": results,
                "indexes_found": len(indexes),
                "indexes": [{"table": idx["tablename"], "name": idx["indexname"]} for idx in indexes]
            }

        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Error running migration: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }


@app.post("/admin/seed-test-team")
async def seed_test_team(auth: AdminAuthRequest):
    """
    Seed test team members (Mayank/Zea) for routing tests.
    Requires ADMIN_SECRET environment variable in request body.

    Q1 2026 Security: Moved secret from query param to body, using constant-time comparison.
    Q3 2026: Added Pydantic validation for admin secret.
    """
    try:
        import secrets as sec_module

        # Security check - use constant-time comparison to prevent timing attacks
        admin_secret = settings.admin_secret if hasattr(settings, 'admin_secret') else None

        if not admin_secret or not sec_module.compare_digest(auth.secret, admin_secret):
            raise HTTPException(status_code=403, detail="Unauthorized")

        from .database.repositories import get_team_repository
        team_repo = get_team_repository()

        test_members = [
            {
                "name": "Mayank",
                "role": "Developer",  # Maps to DEV
                "telegram_id": "123456789",
                "discord_id": "987654321",
                "skills": ["Python", "FastAPI", "PostgreSQL"],
                "is_active": True
            },
            {
                "name": "Zea",
                "role": "Admin",  # Maps to ADMIN
                "telegram_id": "111111111",
                "discord_id": "222222222",
                "skills": ["Management", "Coordination"],
                "is_active": True
            }
        ]

        results = []
        for member_data in test_members:
            try:
                existing = await team_repo.find_member(member_data["name"])
                if existing:
                    results.append(f"⚠️  {member_data['name']} exists with role: {existing.role}")
                    if existing.role != member_data["role"]:
                        await team_repo.update(existing.id, {"role": member_data["role"]})
                        results.append(f"✅ Updated {member_data['name']} role to: {member_data['role']}")
                else:
                    # Unpack dict into create method parameters
                    created = await team_repo.create(
                        name=member_data["name"],
                        role=member_data["role"],
                        telegram_id=member_data.get("telegram_id"),
                        discord_id=member_data.get("discord_id"),
                        skills=member_data.get("skills")
                    )
                    if created:
                        results.append(f"✅ Created {member_data['name']} (ID: {created.id}) with role: {member_data['role']}")
                    else:
                        results.append(f"❌ Failed to create {member_data['name']}")
            except Exception as e:
                results.append(f"❌ Error with {member_data['name']}: {str(e)[:100]}")

        # Verify
        all_members = await team_repo.get_all()
        member_list = [{"name": m.name, "role": m.role} for m in all_members]

        return {
            "status": "success",
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "results": results,
            "total_members": len(all_members),
            "members": member_list
        }

    except Exception as e:
        logger.error(f"Error seeding team: {e}")
        return {"status": "error", "error": str(e)}


@app.post("/admin/clear-conversations")
async def clear_all_conversations(auth: AdminAuthRequest):
    """
    Clear all active conversations (useful for testing).

    Q1 2026: Clears all active conversation state from Redis/memory.
    Useful for test cleanup and debugging conversation issues.

    Usage: POST /admin/clear-conversations with {"secret": "your_secret"}
    """
    try:
        import secrets as sec_module

        # Security check
        if not settings.admin_secret or not sec_module.compare_digest(auth.secret, settings.admin_secret):
            raise HTTPException(status_code=403, detail="Unauthorized")

        # Use the singleton context instance (already connected)
        context = get_conversation_context()

        # Get all active conversation keys
        active_keys = await context._store_scan("active_conversation:*")
        cleared = []

        for key in active_keys:
            user_id = key.split(":")[-1]
            success = await context.clear_active_conversation(user_id)
            if success:
                cleared.append(user_id)

        return {
            "status": "success",
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "cleared_count": len(cleared),
            "user_ids": cleared
        }

    except Exception as e:
        logger.error(f"Error clearing conversations: {e}")
        return {"status": "error", "error": str(e)}


@app.post("/api/admin/test-alert")
async def test_alert(severity: str = "warning"):
    """
    Test alerting system.

    Q3 2026: Send a test alert to configured channels (Slack/Discord).

    Usage:
        POST /api/admin/test-alert?severity=critical
        POST /api/admin/test-alert?severity=warning
        POST /api/admin/test-alert?severity=info
    """
    try:
        from .monitoring.alerts import alert_manager, AlertSeverity

        # Validate severity
        try:
            alert_severity = AlertSeverity(severity)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid severity. Must be one of: critical, warning, info"
            )

        await alert_manager.send_alert(
            title="Test Alert",
            message="This is a test alert from the admin panel",
            severity=alert_severity,
            metrics={
                "test": "value",
                "timestamp": datetime.utcnow().isoformat(),
                "environment": settings.environment
            }
        )

        return {
            "status": "success",
            "message": f"Test alert sent with severity: {severity}",
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error sending test alert: {e}")
        return {"status": "error", "error": str(e)}


@app.post("/api/admin/synthetic-tests")
async def run_synthetic_tests_now():
    """
    Run synthetic monitoring tests immediately.

    Q3 2026 Phase 2: Manually trigger synthetic health checks.
    Tests intent classification, help command, and status command.

    Usage:
        POST /api/admin/synthetic-tests

    Returns:
        JSON with test results and pass/fail status
    """
    try:
        from .monitoring.synthetic_tests import run_synthetic_tests

        results = await run_synthetic_tests()

        return {
            "status": results["status"],
            "timestamp": results["timestamp"],
            "checks": results["checks"],
            "failed_checks": results.get("failed_checks", 0),
            "passed_checks": sum(1 for c in results["checks"] if c["passed"]),
            "total_checks": len(results["checks"])
        }

    except Exception as e:
        logger.error(f"Error running synthetic tests: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@app.post("/api/admin/backup-oauth-tokens")
async def backup_oauth_tokens_api():
    """
    Backup all OAuth tokens to JSON file (Railway-internal execution).

    This endpoint runs the backup script within Railway's environment,
    avoiding database connection issues from external machines.

    Returns:
        JSON with backup filename, token count, and timestamp
    """
    try:
        from pathlib import Path
        import json
        from datetime import datetime
        from sqlalchemy import select
        from .database.models import OAuthTokenDB

        logger.info("[BACKUP] Starting OAuth token backup via API...")

        # Get database connection
        db = get_database()
        async with db.session() as session:
            # Fetch all tokens
            stmt = select(OAuthTokenDB)
            result = await session.execute(stmt)
            tokens = result.scalars().all()

            if not tokens:
                logger.warning("[BACKUP] No tokens found in database")
                return {
                    "status": "warning",
                    "message": "No tokens found",
                    "token_count": 0
                }

            logger.info(f"[BACKUP] Found {len(tokens)} token(s)")

            # Create backup structure
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_data = {
                "backup_timestamp": timestamp,
                "backup_date": datetime.now().isoformat(),
                "token_count": len(tokens),
                "tokens": []
            }

            # Export token data
            for token in tokens:
                backup_data["tokens"].append({
                    "email": token.email,
                    "service": token.service,
                    "access_token": token.access_token,
                    "refresh_token": token.refresh_token,
                    "token_type": token.token_type,
                    "expires_at": token.expires_at.isoformat() if token.expires_at else None,
                    "scopes": token.scopes,
                    "created_at": token.created_at.isoformat() if token.created_at else None,
                    "updated_at": token.updated_at.isoformat() if token.updated_at else None
                })

            # SECURITY FIX: Save encrypted backup to file instead of returning in response
            backup_dir = Path("backups")
            backup_dir.mkdir(exist_ok=True)

            backup_filename = f"oauth_backup_{timestamp}.json.enc"
            backup_path = backup_dir / backup_filename

            # Convert backup data to JSON string
            backup_json = json.dumps(backup_data, indent=2)

            # Encrypt the backup data
            from .utils.encryption import get_token_encryption
            encryption = get_token_encryption()
            encrypted_backup = encryption.encrypt(backup_json)

            # Write encrypted backup to file
            with open(backup_path, 'w') as f:
                f.write(encrypted_backup)

            logger.info(f"[SUCCESS] Encrypted backup saved to: {backup_path}")
            logger.info(f"[CRITICAL] Backup file is encrypted - use decryption key to restore")
            logger.warning(f"[SECURITY] Backup data NOT included in API response (stored securely in file)")

            # SECURITY FIX: Return only metadata - NO sensitive data
            return {
                "status": "success",
                "backup_file": backup_filename,
                "backup_path": str(backup_path),
                "token_count": len(tokens),
                "timestamp": timestamp,
                "message": "Tokens backed up securely to encrypted file (not exposed in response)"
            }

    except Exception as e:
        logger.error(f"[ERROR] Backup failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@app.post("/api/admin/encrypt-oauth-tokens")
async def encrypt_oauth_tokens_api(mode: str = "gradual"):
    """
    Encrypt all OAuth tokens in production database.

    This endpoint runs the encryption migration within Railway's environment,
    avoiding database connection issues from external machines.

    Args:
        mode: "gradual" (batch by batch) or "all" (all at once)

    Returns:
        JSON with encryption statistics and coverage
    """
    try:
        from sqlalchemy import select
        from .database.models import OAuthTokenDB
        from .database.repositories.oauth import get_oauth_repository

        logger.info(f"[ENCRYPTION] Starting OAuth token encryption (mode={mode})...")

        repo = get_oauth_repository()
        db = get_database()

        # Get all tokens
        async with db.session() as session:
            stmt = select(OAuthTokenDB)
            result = await session.execute(stmt)
            tokens = result.scalars().all()

            if not tokens:
                logger.warning("[ENCRYPTION] No tokens found in database")
                return {
                    "status": "warning",
                    "message": "No tokens found",
                    "stats": {"total": 0, "encrypted": 0, "plaintext": 0}
                }

            logger.info(f"[ENCRYPTION] Found {len(tokens)} token(s)")

            # Collect plaintext tokens
            plaintext_tokens = []
            already_encrypted = 0

            for token in tokens:
                # Check if already encrypted (Fernet tokens start with "gAAAAA")
                if token.refresh_token and token.refresh_token.startswith("gAAAAA"):
                    already_encrypted += 1
                else:
                    plaintext_tokens.append((token.email, token.service))

            logger.info(f"[STATS] Already encrypted: {already_encrypted}")
            logger.info(f"[STATS] Plaintext: {len(plaintext_tokens)}")

            if not plaintext_tokens:
                logger.info("[SUCCESS] All tokens already encrypted!")
                return {
                    "status": "success",
                    "mode": mode,
                    "message": "All tokens already encrypted",
                    "stats": {
                        "total": len(tokens),
                        "already_encrypted": already_encrypted,
                        "encrypted": 0,
                        "failed": 0,
                        "plaintext": 0
                    }
                }

            # Encrypt plaintext tokens
            results = {
                "success": 0,
                "failed": 0,
                "errors": []
            }

            for email, service in plaintext_tokens:
                try:
                    # Get current token
                    current = await repo.get_token(email, service)

                    if not current:
                        logger.warning(f"[WARNING] Token disappeared: {email}/{service}")
                        continue

                    # Calculate expires_in from expires_at if present
                    expires_in = None
                    if current.get("expires_at"):
                        from datetime import datetime
                        expires_at = current["expires_at"]
                        if isinstance(expires_at, str):
                            expires_at = datetime.fromisoformat(expires_at)
                        now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
                        delta = expires_at - now
                        expires_in = int(delta.total_seconds())

                    # Re-save (will auto-encrypt via repository)
                    await repo.store_token(
                        email=email,
                        service=service,
                        refresh_token=current["refresh_token"],
                        access_token=current.get("access_token", ""),
                        expires_in=expires_in
                    )

                    results["success"] += 1
                    logger.info(f"[SUCCESS] Encrypted: {email}/{service}")

                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append(f"{email}/{service}: {str(e)}")
                    logger.error(f"[ERROR] Failed: {email}/{service} - {e}")

            # Calculate final stats
            remaining_plaintext = len(plaintext_tokens) - results["success"]

            final_stats = {
                "total": len(tokens),
                "already_encrypted": already_encrypted,
                "encrypted": results["success"],
                "failed": results["failed"],
                "plaintext": remaining_plaintext
            }

            logger.info(f"[COMPLETE] Encryption migration finished")
            logger.info(f"[STATS] {final_stats}")

            return {
                "status": "success",
                "mode": mode,
                "message": "Encryption migration complete",
                "stats": final_stats,
                "errors": results["errors"] if results["errors"] else None
            }

    except Exception as e:
        logger.error(f"[ERROR] Encryption migration failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/api/admin/verify-oauth-encryption")
async def verify_oauth_encryption_api():
    """
    Verify OAuth token encryption coverage.

    Checks all tokens in database to ensure they are encrypted
    (Fernet tokens start with "gAAAAA").

    Returns:
        JSON with encryption statistics and list of plaintext tokens
    """
    try:
        from sqlalchemy import select
        from .database.models import OAuthTokenDB

        logger.info("[VERIFY] Checking OAuth token encryption coverage...")

        db = get_database()

        stats = {
            "total": 0,
            "encrypted": 0,
            "plaintext": 0
        }
        plaintext_tokens = []

        async with db.session() as session:
            stmt = select(OAuthTokenDB)
            result = await session.execute(stmt)
            tokens = result.scalars().all()

            for token in tokens:
                stats["total"] += 1

                # Check if encrypted (Fernet tokens start with "gAAAAA")
                if token.refresh_token and token.refresh_token.startswith("gAAAAA"):
                    stats["encrypted"] += 1
                else:
                    stats["plaintext"] += 1
                    plaintext_tokens.append(f"{token.email}/{token.service}")

            coverage = (stats["encrypted"] / stats["total"] * 100) if stats["total"] > 0 else 0

            logger.info(f"[VERIFY] Coverage: {coverage:.1f}% ({stats['encrypted']}/{stats['total']})")

            return {
                "status": "success",
                "coverage_percent": coverage,
                "stats": stats,
                "plaintext_tokens": plaintext_tokens if plaintext_tokens else None,
                "message": "100% encrypted" if coverage >= 100 else f"{stats['plaintext']} tokens remain plaintext"
            }

    except Exception as e:
        logger.error(f"[ERROR] Verification failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


# ==================== CACHE ADMIN ENDPOINTS (Q3 2026) ====================

@app.get("/api/admin/cache/stats")
async def get_cache_stats():
    """
    Get cache statistics and Redis server info.

    Q3 2026: Redis caching performance monitoring endpoint.

    Returns:
        JSON with application hit rate, Redis stats, and health info
    """
    try:
        from .cache.stats import stats

        full_stats = await stats.get_full_stats()

        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            **full_stats
        }

    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@app.post("/api/admin/cache/clear")
async def clear_cache(pattern: str = "*"):
    """
    Clear cache entries matching pattern.

    Q3 2026: Cache invalidation endpoint for admins.

    Args:
        pattern: Pattern to match (e.g., "tasks:*", "task:TASK-*")

    Returns:
        JSON with number of entries cleared
    """
    try:
        from .cache.redis_client import cache

        deleted = await cache.invalidate_pattern(pattern)

        logger.info(f"Admin cleared {deleted} cache entries matching {pattern}")

        return {
            "status": "ok",
            "pattern": pattern,
            "deleted": deleted,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/cache/reset-stats")
async def reset_cache_stats():
    """
    Reset cache hit/miss statistics.

    Q3 2026: Reset application-level cache statistics counters.

    Returns:
        JSON confirmation
    """
    try:
        from .cache.stats import stats

        stats.reset()

        logger.info("Admin reset cache statistics")

        return {
            "status": "ok",
            "message": "Cache statistics reset",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error resetting cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/check-consistency")
async def check_data_consistency():
    """
    Check data consistency across Sheets, DB, and Discord.

    Q3 2026: Automated data consistency checker.

    Returns:
        JSON with detected issues:
        - orphaned_db_tasks: Tasks in DB but not in Sheets
        - orphaned_sheet_tasks: Tasks in Sheets but not in DB
        - orphaned_discord_threads: Discord threads with no matching task
        - missing_discord_threads: Active tasks without Discord threads
        - status_mismatches: Tasks with different status in DB vs Sheets
    """
    try:
        from .utils.data_consistency import run_consistency_check

        issues = await run_consistency_check()

        total_issues = sum(len(v) if isinstance(v, list) else 0 for v in issues.values())

        logger.info(f"Data consistency check complete. Found {total_issues} issues.")

        return {
            "status": "healthy" if total_issues == 0 else "issues_found",
            "total_issues": total_issues,
            "issues": issues,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error checking data consistency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/fix-orphans")
async def fix_orphaned_data_endpoint():
    """
    Auto-fix orphaned data where safe.

    Q3 2026: Automated orphan cleanup.

    Safe fixes:
    - Delete orphaned Discord threads (no matching task)
    - Sync status mismatches (DB is source of truth)

    Unsafe fixes require manual intervention:
    - Orphaned DB tasks
    - Orphaned Sheet tasks

    Returns:
        JSON with count of fixes applied
    """
    try:
        from .utils.data_consistency import run_consistency_check, fix_orphaned_data

        # First check what needs fixing
        issues = await run_consistency_check()

        # Apply fixes
        fixed_count = await fix_orphaned_data(issues)

        logger.info(f"Auto-fix complete. Fixed {fixed_count} issues.")

        return {
            "status": "fixed",
            "fixed_count": fixed_count,
            "details": {
                "discord_threads_deleted": len(issues["orphaned_discord_threads"]),
                "status_mismatches_synced": len(issues["status_mismatches"])
            },
            "remaining_issues": {
                "orphaned_db_tasks": len(issues["orphaned_db_tasks"]),
                "orphaned_sheet_tasks": len(issues["orphaned_sheet_tasks"]),
                "missing_discord_threads": len(issues["missing_discord_threads"])
            },
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error fixing orphaned data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Track processed update IDs to prevent duplicate processing from Telegram retries
_processed_updates: set = set()
_max_processed_updates = 1000


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Telegram webhook endpoint.

    Receives updates from Telegram and processes them in background
    to avoid Telegram's 60-second timeout causing duplicate requests.

    Q3 2026: Added Pydantic validation (lenient due to Telegram's complex update structure).
    Q1 2027: Added webhook signature validation for security.
    """
    try:
        # SECURITY FIX: Verify webhook signature (Secret Token Method)
        if settings.telegram_webhook_secret:
            import secrets
            received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not secrets.compare_digest(received_secret, settings.telegram_webhook_secret):
                logger.warning(f"Invalid Telegram webhook signature - rejecting request")
                return JSONResponse(
                    status_code=403,
                    content={"ok": False, "error": "Invalid signature"}
                )

        # Parse and validate basic structure
        update_data = await request.json()

        # Basic validation of required fields
        if not isinstance(update_data, dict):
            logger.warning("Invalid Telegram update: not a dict")
            return JSONResponse(
                status_code=200,  # Return 200 to prevent Telegram retries
                content={"ok": False, "error": "Invalid update format"}
            )

        update_id = update_data.get('update_id')
        if not update_id or not isinstance(update_id, int) or update_id <= 0:
            logger.warning(f"Invalid update_id: {update_id}")
            return JSONResponse(
                status_code=200,
                content={"ok": False, "error": "Invalid update_id"}
            )

        logger.debug(f"Received Telegram update: {update_id}")

        # Deduplicate - Telegram resends if we're slow (>60s)
        if update_id in _processed_updates:
            logger.info(f"[WEBHOOK] Skipping duplicate update {update_id}")
            return {"ok": True}

        # Mark as processed immediately
        _processed_updates.add(update_id)
        logger.info(f"[WEBHOOK] Processing new update {update_id}, total processed: {len(_processed_updates)}")

        # Cleanup old update IDs to prevent memory leak
        if len(_processed_updates) > _max_processed_updates:
            sorted_ids = sorted(_processed_updates)
            for old_id in sorted_ids[:len(sorted_ids)//2]:
                _processed_updates.discard(old_id)
            logger.debug(f"[WEBHOOK] Cleaned up old update IDs, new total: {len(_processed_updates)}")

        # Process in background - don't await, return immediately
        async def process_in_background():
            try:
                logger.info(f"[WEBHOOK-BG] Starting background processing for update {update_id}")
                telegram_bot = get_telegram_bot_simple()
                await telegram_bot.process_webhook(update_data)
                logger.info(f"[WEBHOOK-BG] Completed background processing for update {update_id}")
            except Exception as e:
                logger.error(f"[WEBHOOK-BG] Background processing error for update {update_id}: {e}", exc_info=True)

        # PHASE 2 FIX: Safe background task with error handling
        from .utils.background_tasks import create_safe_task
        create_safe_task(
            process_in_background(),
            f"webhook-telegram-{update_id}"
        )
        logger.debug(f"[WEBHOOK] Safe background task created for update {update_id}, returning OK")

        # Return immediately to prevent Telegram timeout
        return {"ok": True}

    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}")
        return JSONResponse(
            status_code=200,  # Return 200 to prevent Telegram retries
            content={"ok": False, "error": str(e)}
        )


@app.post("/webhook/discord")
async def discord_webhook(request: Request):
    """
    Discord webhook endpoint for reaction tracking.

    This would be used if using a Discord bot for reaction-based status updates.
    """
    try:
        data = await request.json()
        logger.debug(f"Received Discord webhook: {data}")

        # Process reaction events for status updates
        # This is optional - requires Discord bot setup
        # For now, just acknowledge

        return {"ok": True}

    except Exception as e:
        logger.error(f"Error processing Discord webhook: {e}")
        return JSONResponse(
            status_code=200,
            content={"ok": False, "error": str(e)}
        )


@app.get("/api/status")
async def get_status():
    """Get current system status and statistics."""
    try:
        sheets = get_sheets_integration()
        daily_tasks = await sheets.get_daily_tasks()
        overdue_tasks = await sheets.get_overdue_tasks()

        scheduler = get_scheduler_manager()
        jobs = scheduler.get_job_status()

        return {
            "tasks": {
                "today": len(daily_tasks),
                "overdue": len(overdue_tasks),
                "completed": sum(1 for t in daily_tasks if t.get('Status') == 'completed')
            },
            "scheduler": {
                "jobs": jobs
            }
        }

    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trigger-job/{job_id}")
async def trigger_job(job_id: str):
    """Manually trigger a scheduled job."""
    scheduler = get_scheduler_manager()

    if scheduler.trigger_job(job_id):
        return {"ok": True, "message": f"Job {job_id} triggered"}
    else:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


@app.post("/api/admin/send-smart-reminders")
async def send_smart_reminders_now():
    """
    Manually trigger smart deadline reminders.

    Phase 3 (Q1 2026): Send grouped reminders by assignee.
    """
    try:
        from .scheduler.smart_reminders import get_smart_reminder_system

        reminder_system = get_smart_reminder_system()
        count = await reminder_system.send_deadline_reminders()

        return {
            "status": "success",
            "reminders_sent": count,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error sending smart reminders: {e}")
        return {"status": "error", "error": str(e)}


@app.post("/api/admin/send-overdue-escalation")
async def send_overdue_escalation_now():
    """
    Manually trigger smart overdue escalation.

    Phase 3 (Q1 2026): Send categorized escalation alerts.
    """
    try:
        from .scheduler.smart_reminders import get_smart_reminder_system

        reminder_system = get_smart_reminder_system()
        count = await reminder_system.send_overdue_escalation()

        return {
            "status": "success",
            "escalations_sent": count,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error sending overdue escalation: {e}")
        return {"status": "error", "error": str(e)}


@app.post("/api/admin/send-reminder/{task_id}")
async def send_reminder_for_task(task_id: str):
    """
    Manually send a reminder for a specific task.

    Phase 3 (Q1 2026): On-demand reminders for urgent follow-ups.
    """
    try:
        from .scheduler.smart_reminders import get_smart_reminder_system

        reminder_system = get_smart_reminder_system()
        success = await reminder_system.send_manual_reminder(task_id)

        if success:
            return {
                "status": "success",
                "message": f"Reminder sent for {task_id}",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "status": "error",
                "message": f"Could not send reminder for {task_id}"
            }

    except Exception as e:
        logger.error(f"Error sending reminder: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/api/tasks/daily")
async def get_daily_tasks():
    """Get today's tasks."""
    try:
        sheets = get_sheets_integration()
        tasks = await sheets.get_daily_tasks()
        return {"tasks": tasks}

    except Exception as e:
        logger.error(f"Error getting daily tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks/overdue")
async def get_overdue_tasks():
    """Get overdue tasks."""
    try:
        sheets = get_sheets_integration()
        tasks = await sheets.get_overdue_tasks()
        return {"tasks": tasks}

    except Exception as e:
        logger.error(f"Error getting overdue tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/weekly-overview")
async def get_weekly_overview():
    """Get weekly statistics overview."""
    try:
        sheets = get_sheets_integration()
        overview = await sheets.generate_weekly_overview()
        return overview

    except Exception as e:
        logger.error(f"Error getting weekly overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/preferences/{user_id}/teach")
async def teach_preference(user_id: str, teaching: TeachingRequest):
    """
    Teach the bot a new preference.

    Q3 2026: Added Pydantic validation with XSS prevention and length limits.
    """
    try:
        from .memory.learning import get_learning_manager
        learning = get_learning_manager()

        success, response = await learning.process_teach_command(user_id, teaching.text)

        return {
            "success": success,
            "response": response
        }

    except Exception as e:
        logger.error(f"Error processing teach command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/preferences/{user_id}")
async def get_user_preferences(user_id: str):
    """Get user preferences."""
    try:
        prefs = get_preferences_manager()
        user_prefs = await prefs.get_preferences(user_id)
        return user_prefs.to_dict()

    except Exception as e:
        logger.error(f"Error getting preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== DATABASE API ENDPOINTS ====================

@app.get("/api/db/tasks")
async def get_db_tasks(filters: TaskFilter = Depends()):
    """
    Get tasks from PostgreSQL database with pagination.

    Q3 2026: Added pagination support (limit/offset) to prevent unbounded queries.
    """
    try:
        from .database.repositories import get_task_repository
        task_repo = get_task_repository()

        status = filters.status.value if filters.status else None
        assignee = filters.assignee
        limit = filters.limit
        offset = filters.offset

        if status:
            tasks = await task_repo.get_by_status(status, limit=limit, offset=offset)
        elif assignee:
            tasks = await task_repo.get_by_assignee(assignee, limit=limit, offset=offset)
        else:
            tasks = await task_repo.get_all(limit=limit, offset=offset)

        return {
            "tasks": [
                {
                    "id": t.task_id,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "assignee": t.assignee,
                    "deadline": t.deadline.isoformat() if t.deadline else None,
                    "created_at": t.created_at.isoformat(),
                }
                for t in tasks
            ],
            "count": len(tasks),
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": len(tasks) == limit  # If we got exactly limit results, there might be more
            }
        }

    except Exception as e:
        logger.error(f"Error getting tasks from DB: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/tasks/{task_id}")
async def get_db_task(task_id: str):
    """Get a single task with full details from PostgreSQL."""
    try:
        from .database.repositories import get_task_repository
        task_repo = get_task_repository()

        task = await task_repo.get_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # Get subtasks and dependencies
        subtasks = await task_repo.get_subtasks(task_id)
        blocking = await task_repo.get_blocking_tasks(task_id)
        blocked_by_this = await task_repo.get_blocked_tasks(task_id)

        return {
            "task": {
                "id": task.task_id,
                "title": task.title,
                "description": task.description,
                "status": task.status,
                "priority": task.priority,
                "assignee": task.assignee,
                "deadline": task.deadline.isoformat() if task.deadline else None,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat(),
                "progress": task.progress,
                "project_id": task.project_id,
            },
            "subtasks": [
                {"id": s.id, "title": s.title, "completed": s.completed}
                for s in subtasks
            ],
            "blocking_tasks": [t.task_id for t in blocking],
            "blocks_tasks": [t.task_id for t in blocked_by_this],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task from DB: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/tasks/{task_id}/subtasks")
async def add_subtask(task_id: str, subtask: SubtaskCreate):
    """Add a subtask to a task."""
    try:
        from .database.repositories import get_task_repository
        task_repo = get_task_repository()

        title = subtask.title
        description = subtask.description

        subtask_obj = await task_repo.add_subtask(
            task_id=task_id,
            title=title,
            description=description,
        )

        if not subtask_obj:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return {"ok": True, "subtask_id": subtask_obj.id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding subtask: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/tasks/{task_id}/dependencies")
async def add_dependency(task_id: str, dependency: DependencyCreate):
    """Add a dependency between tasks."""
    try:
        from .database.repositories import get_task_repository
        task_repo = get_task_repository()

        depends_on = dependency.depends_on
        dep_type = dependency.type.value

        dependency_obj = await task_repo.add_dependency(
            task_id=task_id,
            depends_on_task_id=depends_on,
            dependency_type=dep_type,
        )

        if not dependency_obj:
            raise HTTPException(status_code=400, detail="Could not create dependency (circular or task not found)")

        return {"ok": True, "dependency_id": dependency_obj.id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding dependency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/audit")
async def query_audit_logs(
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """
    Query audit logs with filters.
    
    Q2 2026: New endpoint for comprehensive audit trail querying.
    
    Args:
        action: Filter by action type (e.g., "task_delete", "oauth_token_access")
        user_id: Filter by user who performed action
        entity_type: Filter by entity type (e.g., "task", "team_member")
        level: Filter by severity (info, warning, critical)
        limit: Max results (default 100)
        offset: Pagination offset
    
    Returns:
        List of audit log entries with pagination
    """
    try:
        from .database.repositories import get_audit_repository
        audit_repo = get_audit_repository()

        # Build filters
        filters = {}
        if action:
            filters["action"] = action
        if user_id:
            filters["user_id"] = user_id
        if entity_type:
            filters["entity_type"] = entity_type
        if level:
            filters["level"] = level

        # Query audit logs
        logs = await audit_repo.query(filters=filters, limit=limit, offset=offset)
        total = await audit_repo.count(filters=filters)

        return {
            "logs": [
                {
                    "id": log.id,
                    "action": log.action,
                    "user_id": log.user_id,
                    "entity_type": log.entity_type,
                    "entity_id": log.entity_id,
                    "details": log.details,
                    "level": log.level,
                    "ip_address": log.ip_address,
                    "timestamp": log.timestamp.isoformat(),
                }
                for log in logs
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(f"Error querying audit logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/audit/{task_id}")
async def get_task_audit(task_id: str):
    """Get audit history for a task."""
    try:
        from .database.repositories import get_audit_repository
        audit_repo = get_audit_repository()

        logs = await audit_repo.get_task_history(task_id)

        return {
            "task_id": task_id,
            "history": [
                {
                    "action": log.action,
                    "field": log.field_changed,
                    "old_value": log.old_value,
                    "new_value": log.new_value,
                    "changed_by": log.changed_by,
                    "timestamp": log.timestamp.isoformat(),
                    "reason": log.reason,
                }
                for log in logs
            ],
            "count": len(logs),
        }

    except Exception as e:
        logger.error(f"Error getting audit logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/db/projects")
async def get_projects():
    """Get all projects with stats."""
    try:
        from .database.repositories import get_project_repository
        project_repo = get_project_repository()

        stats = await project_repo.get_all_stats()
        return {"projects": stats}

    except Exception as e:
        logger.error(f"Error getting projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/projects")
async def create_project(project_data: ProjectCreate):
    """
    Create a new project.

    Q3 2026: Added Pydantic validation with XSS prevention, length limits, and color format validation.
    """
    try:
        from .database.repositories import get_project_repository
        project_repo = get_project_repository()

        project = await project_repo.create(
            name=project_data.name,
            description=project_data.description,
            color=project_data.color,
        )

        return {"ok": True, "project_id": project.id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/sync")
async def trigger_sync():
    """Trigger a sync from PostgreSQL to Google Sheets."""
    try:
        sync = get_sheets_sync()
        result = await sync.sync_pending_tasks()
        return {"ok": True, **result}

    except Exception as e:
        logger.error(f"Error running sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Q1 2026: BATCH OPERATIONS API ====================

@app.post("/api/batch/complete")
async def batch_complete_tasks(
    assignee: str,
    dry_run: bool = False,
    user_id: str = "API"
):
    """Complete all tasks for a specific assignee."""
    try:
        from .operations.batch import batch_ops
        from .database.connection import get_session

        async with get_session() as session:
            result = await batch_ops.complete_all_for_assignee(
                session, assignee, dry_run, user_id
            )
            return {"ok": True, **result}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Batch complete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/batch/reassign")
async def batch_reassign_tasks(
    from_assignee: str,
    to_assignee: str,
    dry_run: bool = False,
    user_id: str = "API"
):
    """Reassign all tasks from one person to another."""
    try:
        from .operations.batch import batch_ops
        from .database.connection import get_session

        async with get_session() as session:
            result = await batch_ops.reassign_all(
                session, from_assignee, to_assignee, None, dry_run, user_id
            )
            return {"ok": True, **result}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Batch reassign error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/batch/status")
async def batch_status_change(
    task_ids: List[str],
    status: str,
    dry_run: bool = False,
    user_id: str = "API"
):
    """Bulk status change for multiple tasks."""
    try:
        from .operations.batch import batch_ops
        from .database.connection import get_session

        async with get_session() as session:
            result = await batch_ops.bulk_status_change(
                session, task_ids, status, dry_run, user_id
            )
            return {"ok": True, **result}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Batch status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/batch/delete")
async def batch_delete_tasks(
    task_ids: List[str],
    dry_run: bool = False,
    user_id: str = "API"
):
    """Bulk delete multiple tasks."""
    try:
        from .operations.batch import batch_ops
        from .database.connection import get_session

        async with get_session() as session:
            result = await batch_ops.bulk_delete(
                session, task_ids, dry_run, user_id
            )
            return {"ok": True, **result}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Batch delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/batch/tags")
async def batch_add_tags(
    task_ids: List[str],
    tags: List[str],
    dry_run: bool = False,
    user_id: str = "API"
):
    """Bulk add tags to multiple tasks."""
    try:
        from .operations.batch import batch_ops
        from .database.connection import get_session

        async with get_session() as session:
            result = await batch_ops.bulk_add_tags(
                session, task_ids, tags, dry_run, user_id
            )
            return {"ok": True, **result}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Batch add tags error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/batch/progress/{batch_id}")
async def get_batch_progress(batch_id: str):
    """Get progress of a running batch operation."""
    try:
        from .operations.batch import batch_ops

        progress = await batch_ops.get_batch_progress(batch_id)
        if progress:
            return {"ok": True, "progress": progress}
        else:
            raise HTTPException(status_code=404, detail="Batch operation not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get progress error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/batch/cancel/{batch_id}")
async def cancel_batch_operation(batch_id: str):
    """Cancel a running batch operation."""
    try:
        from .operations.batch import batch_ops

        cancelled = await batch_ops.cancel_batch(batch_id)
        return {"ok": True, "cancelled": cancelled}

    except Exception as e:
        logger.error(f"Cancel batch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== END BATCH OPERATIONS API ====================


# ==================== Q2 2026: UNDO/REDO API ====================

@app.get("/api/undo/history")
async def get_undo_history(user_id: str, limit: int = 10):
    """
    Get undo history for a user.

    Args:
        user_id: User ID (Telegram/Discord)
        limit: Number of records to return (default 10, max 50)

    Returns:
        List of undoable actions
    """
    try:
        from .operations.undo_manager import get_undo_manager

        if limit > 50:
            limit = 50

        undo_mgr = get_undo_manager()
        history = await undo_mgr.get_undo_history(user_id, limit)

        return {"ok": True, "history": history, "count": len(history)}

    except Exception as e:
        logger.error(f"Error getting undo history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/undo")
async def undo_action(user_id: str, action_id: Optional[int] = None):
    """
    Undo an action.

    Args:
        user_id: User performing the undo
        action_id: Specific action to undo (None = most recent)

    Returns:
        Undo result with success status
    """
    try:
        from .operations.undo_manager import get_undo_manager

        undo_mgr = get_undo_manager()
        result = await undo_mgr.undo_action(user_id, action_id)

        if result["success"]:
            return {"ok": True, **result}
        else:
            raise HTTPException(status_code=400, detail=result["message"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error performing undo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/redo")
async def redo_action(user_id: str, action_id: int):
    """
    Redo a previously undone action.

    Args:
        user_id: User performing the redo
        action_id: ID of action to redo

    Returns:
        Redo result with success status
    """
    try:
        from .operations.undo_manager import get_undo_manager

        undo_mgr = get_undo_manager()
        result = await undo_mgr.redo_action(user_id, action_id)

        if result["success"]:
            return {"ok": True, **result}
        else:
            raise HTTPException(status_code=400, detail=result["message"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error performing redo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== END UNDO/REDO API ====================


@app.get("/api/db/stats")
async def get_db_stats():
    """Get database statistics."""
    try:
        from .database.repositories import (
            get_task_repository,
            get_audit_repository,
            get_conversation_repository,
        )

        task_repo = get_task_repository()
        audit_repo = get_audit_repository()
        conv_repo = get_conversation_repository()

        task_stats = await task_repo.get_daily_stats()
        audit_stats = await audit_repo.get_activity_stats(days=7)
        conv_stats = await conv_repo.get_stats(days=7)

        return {
            "tasks": task_stats,
            "audit": audit_stats,
            "conversations": conv_stats,
        }

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Monitoring endpoints
@app.get("/api/monitoring/error-spike-metrics")
async def get_error_spike_metrics():
    """Get error spike detection metrics.

    Returns current error rate, baseline, and spike detection status.
    """
    try:
        from .monitoring.error_spike_detector import detector

        metrics = detector.get_current_metrics()

        return {
            "ok": True,
            "metrics": metrics,
            "spike_threshold": detector.spike_threshold,
            "window_minutes": detector.window_minutes,
        }

    except Exception as e:
        logger.error(f"Error getting error spike metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/performance/metrics")
async def get_performance_metrics():
    """Get performance metrics.

    Q3 2026 Phase 4: Response time tracking and slow query detection.

    Returns:
        JSON with slow queries and performance thresholds
    """
    try:
        from .monitoring.performance import perf_tracker
        from .database.slow_query_detector import slow_query_detector

        return {
            "slow_queries": slow_query_detector.get_slow_queries(),
            "slow_query_stats": slow_query_detector.get_stats(),
            "thresholds": {
                "slow_query_ms": slow_query_detector.threshold_ms,
                "slow_request_s": perf_tracker.slow_request_threshold
            }
        }

    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/performance/slow-queries")
async def get_slow_queries(limit: int = 20):
    """Get slow query report.

    Q3 2026 Phase 4: Detailed slow query analysis.

    Args:
        limit: Maximum number of queries to return (default 20)

    Returns:
        JSON with slow query details sorted by duration
    """
    try:
        from .database.slow_query_detector import slow_query_detector

        queries = slow_query_detector.get_slow_queries(limit=limit)
        stats = slow_query_detector.get_stats()

        return {
            "total": len(queries),
            "queries": queries,
            "statistics": stats,
            "threshold_ms": slow_query_detector.threshold_ms
        }

    except Exception as e:
        logger.error(f"Error getting slow queries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/performance/clear-slow-queries")
async def clear_slow_query_history():
    """Clear slow query history.

    Q3 2026 Phase 4: Reset slow query tracking.

    Returns:
        JSON confirmation
    """
    try:
        from .database.slow_query_detector import slow_query_detector

        slow_query_detector.clear_history()

        return {
            "status": "success",
            "message": "Slow query history cleared",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error clearing slow query history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Error handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle Pydantic validation errors with detailed feedback.

    Q3 2026: Custom validation error handler that returns clear, actionable error messages.
    """
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"],
        })

    logger.warning(f"Validation error on {request.url.path}: {errors}")

    return JSONResponse(
        status_code=400,
        content={
            "error": "Validation failed",
            "details": errors,
            "help": "Please check the input fields and ensure they meet the requirements."
        }
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """
    Handle direct Pydantic validation errors.

    Q3 2026: Catches validation errors raised within business logic.
    """
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"],
        })

    logger.warning(f"Pydantic validation error on {request.url.path}: {errors}")

    return JSONResponse(
        status_code=400,
        content={
            "error": "Validation failed",
            "details": errors,
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
