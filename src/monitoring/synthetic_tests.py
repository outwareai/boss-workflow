"""
Synthetic Monitoring - Health checks via pinging bot with test messages.

Q3 2026: Phase 2 Low Effort - Hourly synthetic tests to verify bot is operational.
Catches failures early before real users are impacted.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class SyntheticMonitor:
    """Run synthetic tests against bot to verify health."""

    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all synthetic checks and return results."""
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "checks": []
        }

        # Check 1: Intent classification
        results["checks"].append(await self._check_intent_classification())

        # Check 2: Help command
        results["checks"].append(await self._check_help_command())

        # Check 3: Status command
        results["checks"].append(await self._check_status_command())

        # Check for failures
        failures = [c for c in results["checks"] if not c["passed"]]

        if failures:
            await self._send_failure_alert(failures)
            results["status"] = "failed"
            results["failed_checks"] = len(failures)
        else:
            results["status"] = "healthy"
            results["failed_checks"] = 0

        return results

    async def _check_intent_classification(self) -> Dict[str, Any]:
        """Test intent classification works."""
        try:
            from ..ai.intent import classify_intent

            result = await classify_intent("Create task for test: Synthetic check")
            passed = result.get("intent") == "create_task"

            return {
                "name": "Intent Classification",
                "passed": passed,
                "intent": result.get("intent"),
                "details": result if not passed else None
            }
        except Exception as e:
            logger.error(f"Intent classification check failed: {e}")
            return {
                "name": "Intent Classification",
                "passed": False,
                "error": str(e)
            }

    async def _check_help_command(self) -> Dict[str, Any]:
        """Test /help command."""
        try:
            from ..ai.intent import classify_intent

            result = await classify_intent("/help")
            passed = result.get("intent") == "help"

            return {
                "name": "Help Command",
                "passed": passed,
                "intent": result.get("intent"),
                "details": result if not passed else None
            }
        except Exception as e:
            logger.error(f"Help command check failed: {e}")
            return {
                "name": "Help Command",
                "passed": False,
                "error": str(e)
            }

    async def _check_status_command(self) -> Dict[str, Any]:
        """Test /status command."""
        try:
            from ..ai.intent import classify_intent

            result = await classify_intent("/status")
            passed = result.get("intent") == "check_status"

            return {
                "name": "Status Command",
                "passed": passed,
                "intent": result.get("intent"),
                "details": result if not passed else None
            }
        except Exception as e:
            logger.error(f"Status command check failed: {e}")
            return {
                "name": "Status Command",
                "passed": False,
                "error": str(e)
            }

    async def _send_failure_alert(self, failures: List[Dict[str, Any]]):
        """Send alert for synthetic test failures."""
        try:
            from .alerts import alert_manager, AlertSeverity

            failed_names = [f["name"] for f in failures]
            errors = [f.get("error", "Unknown error") for f in failures]

            await alert_manager.send_alert(
                title="Synthetic Test Failures",
                message=f"{len(failures)} synthetic checks failed:\n" + "\n".join(failed_names),
                severity=AlertSeverity.CRITICAL,
                metrics={
                    "failed_checks": len(failures),
                    "check_names": ", ".join(failed_names),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

            logger.error(f"Synthetic test failures detected: {failed_names}")

        except Exception as e:
            logger.error(f"Failed to send synthetic test alert: {e}")


# Global monitor instance
_monitor = None


def get_synthetic_monitor() -> SyntheticMonitor:
    """Get the synthetic monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = SyntheticMonitor()
    return _monitor


async def run_synthetic_tests() -> Dict[str, Any]:
    """Run synthetic tests and log results."""
    monitor = get_synthetic_monitor()
    results = await monitor.run_all_checks()

    passed = sum(1 for c in results["checks"] if c["passed"])
    total = len(results["checks"])

    logger.info(f"Synthetic tests: {passed}/{total} passed - {results['status']}")

    return results
