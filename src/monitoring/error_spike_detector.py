"""Error spike detection and alerting.

Q3 2026: Production hardening with proactive error monitoring.

Detects sudden increases in error rates and sends alerts
when errors spike above baseline levels.
"""
import logging
from datetime import datetime, timedelta
from collections import deque
from .alerts import alert_manager, AlertSeverity

logger = logging.getLogger(__name__)


class ErrorSpikeDetector:
    """Detect sudden error rate increases and alert."""

    def __init__(self, window_minutes: int = 5, spike_threshold: float = 2.0):
        """
        Initialize error spike detector.

        Args:
            window_minutes: Time window for error rate calculation (default: 5)
            spike_threshold: Multiplier for spike detection (default: 2.0x baseline)
        """
        self.window_minutes = window_minutes
        self.spike_threshold = spike_threshold
        self.error_timestamps = deque(maxlen=1000)
        self.baseline_rate = 0.0
        self.last_alert_time = None
        self.min_baseline_errors = 5  # Need at least 5 errors to establish baseline

    async def record_error(self):
        """Record an error occurrence and check for spikes."""
        now = datetime.utcnow()
        self.error_timestamps.append(now)

        # Update baseline (rolling average)
        current_rate = self._calculate_rate()

        # Only establish baseline after minimum errors
        if len(self.error_timestamps) >= self.min_baseline_errors:
            if self.baseline_rate == 0:
                self.baseline_rate = current_rate
            else:
                # Exponential moving average (0.9 keeps history, 0.1 adds new data)
                self.baseline_rate = 0.9 * self.baseline_rate + 0.1 * current_rate

            # Check for spike (only after baseline established)
            if current_rate > self.baseline_rate * self.spike_threshold:
                await self._send_spike_alert(current_rate)

    def _calculate_rate(self) -> float:
        """
        Calculate errors per minute in the current window.

        Returns:
            Error rate in errors per minute
        """
        cutoff = datetime.utcnow() - timedelta(minutes=self.window_minutes)
        recent_errors = [t for t in self.error_timestamps if t > cutoff]
        return len(recent_errors) / self.window_minutes if self.window_minutes > 0 else 0

    async def _send_spike_alert(self, current_rate: float):
        """
        Send alert for error spike.

        Rate limits to max 1 alert per hour to prevent alert fatigue.

        Args:
            current_rate: Current error rate in errors per minute
        """
        now = datetime.utcnow()

        # Rate limit alerts (max 1 per hour)
        if self.last_alert_time:
            time_since_last = (now - self.last_alert_time).total_seconds()
            if time_since_last < 3600:  # 1 hour
                logger.debug(
                    f"Error spike alert suppressed (last sent {time_since_last}s ago)"
                )
                return

        self.last_alert_time = now

        spike_factor = (
            current_rate / max(self.baseline_rate, 0.1)
            if current_rate > 0
            else 1.0
        )

        await alert_manager.send_alert(
            title="Error Rate Spike Detected",
            message=f"Error rate increased {spike_factor:.1f}x above baseline",
            severity=AlertSeverity.CRITICAL,
            metrics={
                "current_rate": f"{current_rate:.2f}/min",
                "baseline_rate": f"{self.baseline_rate:.2f}/min",
                "spike_factor": f"{spike_factor:.1f}x",
                "window_minutes": str(self.window_minutes),
            },
        )

        logger.warning(
            f"Error spike alert sent: {current_rate:.2f}/min "
            f"({spike_factor:.1f}x baseline)"
        )

    def get_current_metrics(self) -> dict:
        """
        Get current error metrics for diagnostics.

        Returns:
            Dictionary with current metrics
        """
        current_rate = self._calculate_rate()
        recent_count = len(
            [
                t
                for t in self.error_timestamps
                if t > datetime.utcnow() - timedelta(minutes=self.window_minutes)
            ]
        )

        return {
            "current_rate": round(current_rate, 3),
            "baseline_rate": round(self.baseline_rate, 3),
            "recent_error_count": recent_count,
            "total_errors_tracked": len(self.error_timestamps),
            "baseline_established": self.baseline_rate > 0,
            "time_since_last_alert": (
                round(
                    (datetime.utcnow() - self.last_alert_time).total_seconds()
                )
                if self.last_alert_time
                else None
            ),
        }


# Global detector instance
detector = ErrorSpikeDetector()
