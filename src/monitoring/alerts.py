"""
Production alerting system.

Q3 2026: Production hardening with proactive monitoring.
"""
import logging
from enum import Enum
from datetime import datetime
from typing import Optional
import aiohttp
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertManager:
    """
    Manage production alerts.

    Sends alerts to configured channels (Slack, Discord) when
    system health thresholds are exceeded.
    """

    def __init__(self):
        self.slack_webhook = settings.slack_alert_webhook
        self.discord_webhook = settings.discord_alert_webhook
        self.alert_threshold = {
            "error_rate": settings.alert_error_rate_threshold,
            "response_time_p95": settings.alert_response_time_threshold,
            "db_pool_usage": 0.8,  # 80% pool usage
            "cache_hit_rate": 0.6,  # 60% minimum
        }

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        metrics: Optional[dict] = None
    ):
        """
        Send alert to configured channels.

        Args:
            title: Alert title
            message: Alert message body
            severity: Alert severity (critical, warning, info)
            metrics: Optional metrics dictionary to include
        """

        # Skip if alerting is disabled
        if not settings.enable_alerting:
            logger.debug(f"Alerting disabled, skipping: {title}")
            return

        # Format message
        color_map = {
            AlertSeverity.CRITICAL: "#FF0000",  # Red
            AlertSeverity.WARNING: "#FFA500",   # Orange
            AlertSeverity.INFO: "#0000FF",      # Blue
        }

        alert_data = {
            "title": f"[{severity.value.upper()}] {title}",
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "severity": severity.value,
            "metrics": metrics or {}
        }

        # Send to Slack
        if self.slack_webhook:
            try:
                await self._send_to_slack(alert_data, color_map[severity])
            except Exception as e:
                logger.error(f"Failed to send Slack alert: {e}")

        # Send to Discord
        if self.discord_webhook:
            try:
                await self._send_to_discord(alert_data, color_map[severity])
            except Exception as e:
                logger.error(f"Failed to send Discord alert: {e}")

        logger.warning(f"Alert sent: {title} ({severity})")

    async def _send_to_slack(self, alert: dict, color: str):
        """Send alert to Slack."""
        payload = {
            "attachments": [{
                "color": color,
                "title": alert["title"],
                "text": alert["message"],
                "fields": [
                    {"title": k, "value": str(v), "short": True}
                    for k, v in alert["metrics"].items()
                ],
                "footer": "Boss Workflow Alerts",
                "ts": int(datetime.utcnow().timestamp())
            }]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.slack_webhook, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Slack webhook returned {response.status}")

    async def _send_to_discord(self, alert: dict, color: str):
        """Send alert to Discord."""
        # Convert hex color to int
        color_int = int(color.replace("#", ""), 16)

        payload = {
            "embeds": [{
                "title": alert["title"],
                "description": alert["message"],
                "color": color_int,
                "fields": [
                    {"name": k, "value": str(v), "inline": True}
                    for k, v in alert["metrics"].items()
                ],
                "timestamp": alert["timestamp"],
                "footer": {"text": "Boss Workflow Alerts"}
            }]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.discord_webhook, json=payload) as response:
                if response.status not in (200, 204):
                    logger.error(f"Discord webhook returned {response.status}")

    async def check_error_rate(self, error_count: int, total_requests: int):
        """
        Check if error rate exceeds threshold.

        Args:
            error_count: Number of errors in period
            total_requests: Total requests in period
        """
        if total_requests == 0:
            return

        error_rate = error_count / total_requests

        if error_rate > self.alert_threshold["error_rate"]:
            await self.send_alert(
                title="High Error Rate Detected",
                message=f"Error rate is {error_rate:.1%}, above threshold of {self.alert_threshold['error_rate']:.1%}",
                severity=AlertSeverity.CRITICAL,
                metrics={
                    "error_rate": f"{error_rate:.1%}",
                    "errors": error_count,
                    "total_requests": total_requests
                }
            )

    async def check_response_time(self, p95_time: float):
        """
        Check if response time exceeds threshold.

        Args:
            p95_time: P95 response time in seconds
        """
        if p95_time > self.alert_threshold["response_time_p95"]:
            await self.send_alert(
                title="Slow Response Time",
                message=f"P95 response time is {p95_time:.2f}s, above threshold of {self.alert_threshold['response_time_p95']:.2f}s",
                severity=AlertSeverity.WARNING,
                metrics={
                    "p95_time": f"{p95_time:.2f}s",
                    "threshold": f"{self.alert_threshold['response_time_p95']:.2f}s"
                }
            )

    async def check_db_pool(self, pool_status: dict):
        """
        Check database pool health.

        Args:
            pool_status: Dict with keys 'checked_out' and 'total'
        """
        utilization = pool_status.get("checked_out", 0) / max(pool_status.get("total", 1), 1)

        if utilization > self.alert_threshold["db_pool_usage"]:
            await self.send_alert(
                title="High Database Pool Usage",
                message=f"DB pool at {utilization:.1%} capacity, may need scaling",
                severity=AlertSeverity.WARNING,
                metrics={
                    "utilization": f"{utilization:.1%}",
                    "checked_out": pool_status.get("checked_out", 0),
                    "total": pool_status.get("total", 0)
                }
            )

    async def check_cache_hit_rate(self, hits: int, total: int):
        """
        Check cache hit rate.

        Args:
            hits: Cache hits in period
            total: Total cache requests in period
        """
        if total == 0:
            return

        hit_rate = hits / total

        if hit_rate < self.alert_threshold["cache_hit_rate"]:
            await self.send_alert(
                title="Low Cache Hit Rate",
                message=f"Cache hit rate is {hit_rate:.1%}, below threshold of {self.alert_threshold['cache_hit_rate']:.1%}",
                severity=AlertSeverity.WARNING,
                metrics={
                    "hit_rate": f"{hit_rate:.1%}",
                    "hits": hits,
                    "total": total
                }
            )


# Global alert manager
alert_manager = AlertManager()
