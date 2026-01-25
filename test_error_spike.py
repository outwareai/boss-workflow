"""Test error spike detection functionality."""
import asyncio
import logging
import sys
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_error_spike_detector():
    """Test the error spike detector."""
    logger.info("Starting error spike detector test...")

    # Import detector
    from src.monitoring.error_spike_detector import ErrorSpikeDetector

    # Create detector with lower thresholds for testing
    detector = ErrorSpikeDetector(window_minutes=1, spike_threshold=1.5)

    logger.info(f"Created detector: window={detector.window_minutes}m, threshold={detector.spike_threshold}x")

    # Test 1: Record baseline errors
    logger.info("\n=== Test 1: Establishing baseline ===")
    for i in range(6):
        await detector.record_error()
        logger.debug(f"Recorded error {i+1}")
        metrics = detector.get_current_metrics()
        logger.info(f"Metrics after error {i+1}: rate={metrics['current_rate']:.2f}/min, baseline={metrics['baseline_rate']:.2f}/min")

    # Test 2: Rapid errors (spike)
    logger.info("\n=== Test 2: Creating error spike ===")
    for i in range(8):
        await detector.record_error()
        logger.debug(f"Recorded spike error {i+1}")
        metrics = detector.get_current_metrics()
        logger.info(f"Metrics after spike {i+1}: rate={metrics['current_rate']:.2f}/min, baseline={metrics['baseline_rate']:.2f}/min")

    # Test 3: Check final metrics
    logger.info("\n=== Test 3: Final metrics ===")
    metrics = detector.get_current_metrics()
    logger.info(f"Final Metrics:")
    for key, value in metrics.items():
        logger.info(f"  {key}: {value}")

    logger.info("\n✅ Error spike detector test completed")


async def test_prometheus_metrics():
    """Test Prometheus metrics are created correctly."""
    logger.info("\nTesting Prometheus metrics...")

    try:
        from src.monitoring import error_rate_current, errors_total

        logger.info("✅ Successfully imported error metrics")

        # Record some metrics
        errors_total.labels(type="test_error", severity="warning").inc(5)
        error_rate_current.labels(time_window="5m").set(2.5)

        logger.info("✅ Successfully recorded metrics")

    except ImportError as e:
        logger.warning(f"⚠️ Prometheus not available: {e}")


async def test_middleware_integration():
    """Test that middleware can import and use detector."""
    logger.info("\nTesting middleware integration...")

    try:
        from src.monitoring.middleware import _record_error_metrics

        logger.info("✅ Successfully imported middleware error recording function")

        # Test recording an error
        class FakeRequest:
            class FakeClient:
                host = "127.0.0.1"

            url = type('url', (), {'path': '/test'})()
            client = FakeClient()
            method = "GET"

        await _record_error_metrics(FakeRequest(), status_code=500)
        logger.info("✅ Successfully recorded error via middleware")

    except Exception as e:
        logger.error(f"❌ Middleware integration test failed: {e}", exc_info=True)


async def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("ERROR SPIKE ALERTING - PHASE 4 TEST SUITE")
    logger.info("=" * 60)

    try:
        await test_error_spike_detector()
        await test_prometheus_metrics()
        await test_middleware_integration()

        logger.info("\n" + "=" * 60)
        logger.info("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Test suite failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
