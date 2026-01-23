"""
Retry logic with exponential backoff.

Q2 2026: Make external API calls resilient to transient failures.
Supports: Google APIs, Discord, Telegram, DeepSeek, etc.
"""

import logging
import asyncio
import functools
from typing import Callable, Type, Tuple, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class RetryExhausted(Exception):
    """Raised when all retry attempts are exhausted."""
    pass


async def retry_with_backoff(
    func: Callable,
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retry_on: Tuple[Type[Exception], ...] = (Exception,),
    skip_on: Tuple[Type[Exception], ...] = (),
    **kwargs
) -> Any:
    """
    Execute a function with exponential backoff retry logic.

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        exponential_base: Base for exponential calculation (default: 2.0)
        jitter: Add random jitter to delays to prevent thundering herd (default: True)
        retry_on: Tuple of exception types to retry on (default: all exceptions)
        skip_on: Tuple of exception types to never retry (raises immediately)
        **kwargs: Keyword arguments for func

    Returns:
        Result of func execution

    Raises:
        RetryExhausted: If all retries are exhausted
        Exception: If exception is in skip_on list

    Example:
        result = await retry_with_backoff(
            api_call,
            param1="value",
            max_retries=5,
            base_delay=2.0,
            retry_on=(ConnectionError, TimeoutError),
            skip_on=(ValueError, KeyError)
        )
    """
    import random

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # Success! Log if there were previous attempts
            if attempt > 0:
                logger.info(
                    f"✅ Retry successful on attempt {attempt + 1}/{max_retries + 1} "
                    f"for {func.__name__}"
                )

            return result

        except skip_on as e:
            # Don't retry these exceptions
            logger.warning(f"❌ Skipping retry for {func.__name__}: {type(e).__name__}: {e}")
            raise

        except retry_on as e:
            last_exception = e

            # If this was the last attempt, raise
            if attempt == max_retries:
                logger.error(
                    f"❌ All {max_retries + 1} retry attempts exhausted for {func.__name__}"
                )
                raise RetryExhausted(
                    f"Failed after {max_retries + 1} attempts: {type(e).__name__}: {e}"
                ) from e

            # Calculate delay with exponential backoff
            delay = min(base_delay * (exponential_base ** attempt), max_delay)

            # Add jitter to prevent thundering herd
            if jitter:
                delay = delay * (0.5 + random.random())

            logger.warning(
                f"⚠️  Retry attempt {attempt + 1}/{max_retries + 1} for {func.__name__} "
                f"after {type(e).__name__}: {e}. Retrying in {delay:.2f}s..."
            )

            # Wait before retrying
            await asyncio.sleep(delay)

        except Exception as e:
            # Unexpected exception not in retry_on list
            logger.error(
                f"❌ Unexpected exception in {func.__name__}: {type(e).__name__}: {e}"
            )
            raise

    # Should never reach here, but just in case
    raise RetryExhausted(f"Failed after {max_retries + 1} attempts") from last_exception


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retry_on: Tuple[Type[Exception], ...] = (Exception,),
    skip_on: Tuple[Type[Exception], ...] = ()
):
    """
    Decorator to add retry logic with exponential backoff to async functions.

    Usage:
        @with_retry(max_retries=5, base_delay=2.0, retry_on=(ConnectionError,))
        async def fetch_data(url: str):
            response = await httpx.get(url)
            return response.json()

    Args:
        Same as retry_with_backoff()

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_with_backoff(
                func,
                *args,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                exponential_base=exponential_base,
                jitter=jitter,
                retry_on=retry_on,
                skip_on=skip_on,
                **kwargs
            )
        return wrapper
    return decorator


# Common retry configurations for different services
GOOGLE_API_RETRY = {
    "max_retries": 5,
    "base_delay": 2.0,
    "max_delay": 60.0,
    "retry_on": (ConnectionError, TimeoutError, OSError),
}

DISCORD_RETRY = {
    "max_retries": 3,
    "base_delay": 1.0,
    "max_delay": 30.0,
    "retry_on": (ConnectionError, TimeoutError),
}

TELEGRAM_RETRY = {
    "max_retries": 4,
    "base_delay": 1.5,
    "max_delay": 45.0,
    "retry_on": (ConnectionError, TimeoutError),
}

DEEPSEEK_RETRY = {
    "max_retries": 5,
    "base_delay": 3.0,
    "max_delay": 120.0,
    "retry_on": (ConnectionError, TimeoutError),
}

DATABASE_RETRY = {
    "max_retries": 3,
    "base_delay": 0.5,
    "max_delay": 10.0,
    "retry_on": (ConnectionError, TimeoutError),
}


# Convenience decorators with pre-configured settings
def with_google_api_retry(func: Callable):
    """Decorator with Google API retry configuration."""
    return with_retry(**GOOGLE_API_RETRY)(func)


def with_discord_retry(func: Callable):
    """Decorator with Discord API retry configuration."""
    return with_retry(**DISCORD_RETRY)(func)


def with_telegram_retry(func: Callable):
    """Decorator with Telegram API retry configuration."""
    return with_retry(**TELEGRAM_RETRY)(func)


def with_deepseek_retry(func: Callable):
    """Decorator with DeepSeek API retry configuration."""
    return with_retry(**DEEPSEEK_RETRY)(func)


def with_database_retry(func: Callable):
    """Decorator with database retry configuration."""
    return with_retry(**DATABASE_RETRY)(func)
