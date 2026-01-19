"""
Boss Workflow Automation - Main Application Entry Point

FastAPI application with webhook endpoints and background scheduler.
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import asyncio

from config import settings
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

            # Start bot in background
            discord_bot_task = asyncio.create_task(start_discord_bot())
            logger.info("Discord bot starting in background...")
        else:
            logger.info("Discord bot token not configured, skipping bot startup")
    except Exception as e:
        logger.warning(f"Discord bot failed to start: {e}")

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
    except:
        pass

    try:
        prefs = get_preferences_manager()
        await prefs.disconnect()
    except:
        pass

    try:
        context = get_conversation_context()
        await context.disconnect()
    except:
        pass

    try:
        await close_database()
    except:
        pass

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
async def get_db_tasks(status: str = None, assignee: str = None, limit: int = 50):
    """Get tasks from PostgreSQL database."""
    try:
        from .database.repositories import get_task_repository
        task_repo = get_task_repository()

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
async def add_subtask(task_id: str, request: Request):
    """Add a subtask to a task."""
    try:
        from .database.repositories import get_task_repository
        task_repo = get_task_repository()

        data = await request.json()
        title = data.get("title")
        if not title:
            raise HTTPException(status_code=400, detail="Subtask title required")

        subtask = await task_repo.add_subtask(
            task_id=task_id,
            title=title,
            description=data.get("description"),
        )

        if not subtask:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return {"ok": True, "subtask_id": subtask.id}

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
