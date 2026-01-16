"""
Boss Workflow Automation - Main Application Entry Point

FastAPI application with webhook endpoints and background scheduler.
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from .bot.telegram_simple import get_telegram_bot_simple
from .scheduler.jobs import get_scheduler_manager
from .memory.preferences import get_preferences_manager
from .memory.context import get_conversation_context
from .integrations.sheets import get_sheets_integration
from .integrations.discord import get_discord_integration
from .integrations.calendar import get_calendar_integration

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

    logger.info("Boss Workflow Automation started successfully!")

    yield

    # Shutdown
    logger.info("Shutting down Boss Workflow Automation...")

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
    return {
        "status": "healthy",
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "services": {
            "telegram": bool(settings.telegram_bot_token),
            "deepseek": bool(settings.deepseek_api_key),
            "discord": bool(settings.discord_webhook_url),
            "sheets": bool(settings.google_sheet_id),
            "redis": bool(settings.redis_url)
        }
    }


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Telegram webhook endpoint.

    Receives updates from Telegram and processes them.
    """
    try:
        update_data = await request.json()
        logger.debug(f"Received Telegram update: {update_data.get('update_id')}")

        telegram_bot = get_telegram_bot_simple()
        await telegram_bot.process_webhook(update_data)

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
