"""
Google API utilities with timeout protection.

Provides helper functions to wrap Google API calls with timeout protection
to prevent hanging requests from blocking the application.
"""

import asyncio
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class GoogleAPITimeoutError(Exception):
    """Raised when a Google API call exceeds the timeout."""
    pass


async def execute_with_timeout(
    api_call: Callable,
    timeout: float = 10.0,
    operation: str = "Google API call"
) -> Any:
    """
    Execute Google API call with timeout protection.

    This function wraps Google API `.execute()` calls with asyncio.wait_for
    to prevent hanging requests. It uses asyncio.to_thread to run the
    synchronous Google API call in a separate thread.

    Args:
        api_call: Lambda that calls .execute() on a Google API request
                 Example: lambda: service.events().list(...).execute()
        timeout: Timeout in seconds (default: 10.0)
        operation: Description for logging (e.g., "Calendar.events.list")

    Returns:
        The API response (dict or list depending on the API call)

    Raises:
        GoogleAPITimeoutError: If call exceeds timeout
        Exception: If API call fails for other reasons

    Examples:
        # List calendar events with 10 second timeout
        result = await execute_with_timeout(
            lambda: service.events().list(calendarId='primary').execute(),
            timeout=10.0,
            operation="Calendar.events.list"
        )

        # Create calendar event with 15 second timeout
        result = await execute_with_timeout(
            lambda: service.events().insert(calendarId='primary', body=event).execute(),
            timeout=15.0,
            operation="Calendar.events.insert"
        )
    """
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(api_call),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        error_msg = f"{operation} timed out after {timeout}s"
        logger.error(error_msg)
        raise GoogleAPITimeoutError(error_msg)
    except Exception as e:
        logger.error(f"{operation} failed: {e}")
        raise


# Timeout constants for different operation types
TIMEOUT_READ = 10.0      # Read operations (list, get)
TIMEOUT_WRITE = 15.0     # Write operations (insert, update, delete)
TIMEOUT_BATCH = 30.0     # Batch operations (batchUpdate)
