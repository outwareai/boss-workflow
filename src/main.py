"""
Boss Workflow Automation - Main Application Entry Point

FastAPI application with webhook endpoints and background scheduler.
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import asyncio

from config import settings
from .models.api_validation import SubtaskCreate, DependencyCreate, TaskFilter
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
                    async with aiohttp.ClientSession() as session:
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
            discord_bot_task = asyncio.create_task(start_discord_bot())
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
    try:
        db = get_database()

        # Check if database is initialized
        if not db._initialized:
            return {
                "status": "not_initialized",
                "error": "Database not yet initialized"
            }

        # Get pool statistics
        engine = db.engine
        if engine:
            pool = engine.pool
            return {
                "status": "healthy",
                "timestamp": __import__('datetime').datetime.now().isoformat(),
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "total_connections": pool.size() + pool.overflow(),
                "max_connections": pool.size() + pool._max_overflow,
            }
        else:
            return {
                "status": "error",
                "error": "Engine not available"
            }

    except Exception as e:
        logger.error(f"Error checking database health: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }


@app.post("/admin/run-migration-simple")
async def run_migration_simple(auth: dict):
    """
    Run Q1 2026 composite indexes migration (hardcoded - guaranteed to work).

    Q1 2026 Security: Moved secret from query param to body, using constant-time comparison.
    """
    try:
        import secrets as sec_module

        # Security check - constant-time comparison
        admin_secret = settings.admin_secret if hasattr(settings, 'admin_secret') else None
        provided_secret = auth.get("secret", "") if isinstance(auth, dict) else ""

        if not admin_secret or not sec_module.compare_digest(provided_secret, admin_secret):
            return {"status": "error", "error": "Unauthorized"}

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
async def run_migration(auth: dict):
    """
    Run database migrations (admin only).
    Requires ADMIN_SECRET environment variable in request body.

    Q1 2026 Security: Moved secret from query param to body, using constant-time comparison.
    """
    try:
        import secrets as sec_module

        # Security: Require admin secret - constant-time comparison
        admin_secret = settings.admin_secret if hasattr(settings, 'admin_secret') else None
        provided_secret = auth.get("secret", "") if isinstance(auth, dict) else ""

        if not admin_secret or not sec_module.compare_digest(provided_secret, admin_secret):
            return {
                "status": "error",
                "error": "Unauthorized - Invalid admin secret"
            }

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
async def seed_test_team(auth: dict):
    """
    Seed test team members (Mayank/Zea) for routing tests.
    Requires ADMIN_SECRET environment variable in request body.

    Q1 2026 Security: Moved secret from query param to body, using constant-time comparison.
    """
    try:
        import secrets as sec_module

        # Security check - use constant-time comparison to prevent timing attacks
        admin_secret = settings.admin_secret if hasattr(settings, 'admin_secret') else None
        provided_secret = auth.get("secret", "") if isinstance(auth, dict) else ""

        if not admin_secret or not sec_module.compare_digest(provided_secret, admin_secret):
            return {"status": "error", "error": "Unauthorized"}

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
async def clear_all_conversations(auth: dict):
    """
    Clear all active conversations (useful for testing).

    Usage: POST /admin/clear-conversations with {"secret": "your_secret"}
    """
    try:
        import secrets as sec_module

        # Security check
        admin_secret = settings.admin_secret if hasattr(settings, 'admin_secret') else None
        provided_secret = auth.get("secret", "") if isinstance(auth, dict) else ""

        if not admin_secret or not sec_module.compare_digest(provided_secret, admin_secret):
            return {"status": "error", "error": "Unauthorized"}

        from .memory.context import ConversationContext
        context = ConversationContext()
        await context.connect()

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


# Track processed update IDs to prevent duplicate processing from Telegram retries
_processed_updates: set = set()
_max_processed_updates = 1000


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Telegram webhook endpoint.

    Receives updates from Telegram and processes them in background
    to avoid Telegram's 60-second timeout causing duplicate requests.
    """
    try:
        update_data = await request.json()
        update_id = update_data.get('update_id')
        logger.debug(f"Received Telegram update: {update_id}")

        # Deduplicate - Telegram resends if we're slow (>60s)
        if update_id in _processed_updates:
            logger.info(f"Skipping duplicate update {update_id}")
            return {"ok": True}

        # Mark as processed immediately
        _processed_updates.add(update_id)

        # Cleanup old update IDs to prevent memory leak
        if len(_processed_updates) > _max_processed_updates:
            sorted_ids = sorted(_processed_updates)
            for old_id in sorted_ids[:len(sorted_ids)//2]:
                _processed_updates.discard(old_id)

        # Process in background - don't await, return immediately
        async def process_in_background():
            try:
                telegram_bot = get_telegram_bot_simple()
                await telegram_bot.process_webhook(update_data)
            except Exception as e:
                logger.error(f"Background processing error for update {update_id}: {e}")

        # Fire and forget - process in background
        asyncio.create_task(process_in_background())

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
async def teach_preference(user_id: str, request: Request):
    """Teach the bot a new preference."""
    try:
        data = await request.json()
        teaching_text = data.get("text", "")

        from .memory.learning import get_learning_manager
        learning = get_learning_manager()

        success, response = await learning.process_teach_command(user_id, teaching_text)

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
    """Get tasks from PostgreSQL database."""
    try:
        from .database.repositories import get_task_repository
        task_repo = get_task_repository()

        status = filters.status.value if filters.status else None
        assignee = filters.assignee
        limit = filters.limit

        if status:
            tasks = await task_repo.get_by_status(status)
        elif assignee:
            tasks = await task_repo.get_by_assignee(assignee)
        else:
            tasks = await task_repo.get_all(limit=limit)

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
async def add_dependency(task_id: str, request: Request):
    """Add a dependency between tasks."""
    try:
        from .database.repositories import get_task_repository
        task_repo = get_task_repository()

        data = await request.json()
        depends_on = data.get("depends_on")
        dep_type = data.get("type", "depends_on")

        if not depends_on:
            raise HTTPException(status_code=400, detail="depends_on task ID required")

        dependency = await task_repo.add_dependency(
            task_id=task_id,
            depends_on_task_id=depends_on,
            dependency_type=dep_type,
        )

        if not dependency:
            raise HTTPException(status_code=400, detail="Could not create dependency (circular or task not found)")

        return {"ok": True, "dependency_id": dependency.id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding dependency: {e}")
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
async def create_project(request: Request):
    """Create a new project."""
    try:
        from .database.repositories import get_project_repository
        project_repo = get_project_repository()

        data = await request.json()
        name = data.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="Project name required")

        project = await project_repo.create(
            name=name,
            description=data.get("description"),
            color=data.get("color"),
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


# Error handlers
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
