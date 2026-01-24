"""
Database health monitoring and connection leak detection.

Q3 2026: Pool health checks and leak detection.
"""
import logging
from typing import Dict, Any
from .connection import get_pool_status

logger = logging.getLogger(__name__)


async def check_pool_health() -> bool:
    """
    Check if connection pool is healthy.

    Returns:
        bool: True if pool is healthy, False if degraded/critical
    """
    status = await get_pool_status()

    # Handle different pool types
    if status.get("pool_type") == "NullPool":
        return True  # No pooling in test mode, always healthy

    # Check health status
    health = status.get("status")

    if health == "critical":
        logger.error(
            f"CRITICAL: Pool utilization > 90%: {status.get('utilization')} "
            f"({status.get('checked_out')}/{status.get('max_connections')})"
        )
        return False

    if health == "warning":
        logger.warning(
            f"WARNING: High pool utilization > 80%: {status.get('utilization')} "
            f"({status.get('checked_out')}/{status.get('max_connections')})"
        )
        return True  # Warning, but still operational

    if health == "error":
        logger.error(f"ERROR: Pool status check failed: {status.get('error')}")
        return False

    # Healthy
    return True


async def check_connection_leaks() -> Dict[str, Any]:
    """
    Check for potential connection leaks.

    A connection leak occurs when connections are checked out but never returned.
    This is indicated by:
    1. Overflow connections being used
    2. High number of checked out connections for extended periods

    Returns:
        dict: Leak detection results with warnings
    """
    status = await get_pool_status()

    # Handle NullPool
    if status.get("pool_type") == "NullPool":
        return {
            "has_leak": False,
            "message": "No pooling (test mode)"
        }

    # Handle errors
    if status.get("status") == "error":
        return {
            "has_leak": False,
            "error": status.get("error")
        }

    warnings = []
    has_leak = False

    # Check for overflow usage (potential leak indicator)
    overflow = status.get("overflow", 0)
    if overflow > 0:
        warnings.append(
            f"Overflow connections in use: {overflow} "
            f"(may indicate connection leak or need to increase pool_size)"
        )
        logger.warning(warnings[-1])
        has_leak = True

    # Check for high utilization
    checked_out = status.get("checked_out", 0)
    max_connections = status.get("max_connections", 1)
    utilization = checked_out / max(max_connections, 1)

    if utilization > 0.9:
        warnings.append(
            f"Very high utilization ({utilization:.1%}): "
            f"{checked_out}/{max_connections} connections in use"
        )
        logger.warning(warnings[-1])

    return {
        "has_leak": has_leak,
        "warnings": warnings,
        "overflow_connections": overflow,
        "checked_out": checked_out,
        "max_connections": max_connections,
        "utilization": f"{utilization:.1%}",
        "recommendation": (
            "Consider increasing DB_POOL_SIZE or DB_MAX_OVERFLOW if overflow persists"
            if has_leak
            else "Pool health is normal"
        )
    }


async def get_detailed_health_report() -> Dict[str, Any]:
    """
    Get a detailed health report for the connection pool.

    Returns:
        dict: Comprehensive health report
    """
    pool_status = await get_pool_status()
    pool_healthy = await check_pool_health()
    leak_check = await check_connection_leaks()

    return {
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "pool_status": pool_status,
        "is_healthy": pool_healthy,
        "leak_detection": leak_check,
        "overall_status": (
            "healthy" if pool_healthy and not leak_check.get("has_leak")
            else "degraded" if pool_healthy
            else "critical"
        )
    }
