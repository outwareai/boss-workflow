"""
Scheduled health checks with alerting.

Q3 2026: Production hardening with proactive monitoring.
"""
import logging
from src.monitoring.alerts import alert_manager, AlertSeverity

logger = logging.getLogger(__name__)


async def check_system_health():
    """
    Run system health checks and send alerts if needed.

    Scheduled to run every 5 minutes.
    Checks:
    - Error rate
    - Database pool usage
    - Cache hit rate
    """
    logger.info("Running system health checks...")

    try:
        # Check DB pool
        from src.database.connection import get_pool_status
        try:
            pool_status = await get_pool_status()
            await alert_manager.check_db_pool(pool_status)
        except Exception as e:
            logger.warning(f"Could not check DB pool: {e}")

        # Check cache hit rate (if Redis is configured)
        try:
            from config.settings import get_settings
            settings = get_settings()

            if settings.redis_url:
                # TODO: Implement cache stats when Redis monitoring is added
                # For now, skip cache checks
                pass
        except Exception as e:
            logger.debug(f"Cache check skipped: {e}")

        logger.debug("System health checks completed")

    except Exception as e:
        logger.error(f"Error in system health check: {e}", exc_info=True)


async def check_critical_services():
    """
    Check if critical services are responsive.

    Scheduled to run every minute.
    Checks:
    - Database connectivity
    - Discord bot connectivity
    - Google Sheets API
    """
    logger.debug("Running critical services check...")

    services_down = []

    # Check database
    try:
        from src.database.connection import get_session
        async with get_session() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        logger.debug("Database: OK")
    except Exception as e:
        services_down.append(f"Database: {str(e)[:100]}")
        logger.error(f"Database check failed: {e}")

    # Check Discord bot
    try:
        from src.integrations.discord_bot import get_discord_bot
        discord_bot = get_discord_bot()
        if discord_bot and discord_bot.is_ready():
            logger.debug("Discord Bot: OK")
        else:
            services_down.append("Discord Bot: Not ready")
    except Exception as e:
        logger.debug(f"Discord bot check skipped: {e}")

    # Check Google Sheets
    try:
        from src.integrations.sheets import get_sheets_integration
        sheets = get_sheets_integration()
        if sheets and sheets._initialized:
            logger.debug("Google Sheets: OK")
        else:
            services_down.append("Google Sheets: Not initialized")
    except Exception as e:
        logger.debug(f"Sheets check skipped: {e}")

    # Send alert if any critical services are down
    if services_down:
        await alert_manager.send_alert(
            title="Critical Services Down",
            message="The following services are not responding:",
            severity=AlertSeverity.CRITICAL,
            metrics={"services": ", ".join(services_down)}
        )

    logger.debug("Critical services check completed")


async def check_scheduled_jobs():
    """
    Check that scheduled jobs are running as expected.

    Scheduled to run every 30 minutes.
    Verifies that scheduler is active and jobs are scheduled.
    """
    logger.debug("Running scheduled jobs check...")

    try:
        from src.scheduler.jobs import get_scheduler_manager
        scheduler_manager = get_scheduler_manager()

        if not scheduler_manager.scheduler:
            await alert_manager.send_alert(
                title="Scheduler Not Running",
                message="The background job scheduler is not active",
                severity=AlertSeverity.CRITICAL,
                metrics={"scheduler_status": "stopped"}
            )
            return

        if not scheduler_manager.scheduler.running:
            await alert_manager.send_alert(
                title="Scheduler Not Running",
                message="The background job scheduler is not running",
                severity=AlertSeverity.CRITICAL,
                metrics={"scheduler_status": "not_running"}
            )
            return

        # Get job count
        jobs = scheduler_manager.scheduler.get_jobs()
        if len(jobs) < 5:  # Should have at least 5 core jobs
            await alert_manager.send_alert(
                title="Scheduler Missing Jobs",
                message=f"Only {len(jobs)} jobs scheduled, expected at least 5",
                severity=AlertSeverity.WARNING,
                metrics={
                    "jobs_count": len(jobs),
                    "expected_min": 5
                }
            )

        logger.debug(f"Scheduler check: {len(jobs)} jobs scheduled")

    except Exception as e:
        logger.error(f"Error checking scheduled jobs: {e}", exc_info=True)
        await alert_manager.send_alert(
            title="Scheduler Health Check Failed",
            message=f"Could not verify scheduler status: {str(e)[:100]}",
            severity=AlertSeverity.WARNING,
            metrics={"error": str(e)[:100]}
        )
