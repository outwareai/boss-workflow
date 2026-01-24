"""
Caching decorators for easy integration.

Q3 2026: Performance optimization with Redis caching.
"""
import functools
import hashlib
import logging
from typing import Callable, Any, Optional
from .redis_client import cache
from .stats import stats

logger = logging.getLogger(__name__)


def _generate_cache_key(
    func_name: str,
    args: tuple,
    kwargs: dict,
    key_prefix: str = "",
    skip_first_arg: bool = False
) -> str:
    """
    Generate cache key from function name and arguments.

    Args:
        func_name: Function name
        args: Positional arguments
        kwargs: Keyword arguments
        key_prefix: Optional prefix for the key
        skip_first_arg: Skip first arg (for instance methods - skip self)

    Returns:
        Cache key string
    """
    key_parts = [key_prefix or func_name]

    # Add args to key (skip self for methods)
    start_idx = 1 if skip_first_arg and args else 0
    for arg in args[start_idx:]:
        # Convert to string, handle common types
        if isinstance(arg, (str, int, float, bool)):
            key_parts.append(str(arg))
        elif isinstance(arg, (list, tuple)):
            # Hash complex types
            key_parts.append(hashlib.md5(str(arg).encode()).hexdigest()[:8])
        else:
            # For objects, use repr hash
            key_parts.append(hashlib.md5(repr(arg).encode()).hexdigest()[:8])

    # Add kwargs to key
    for k, v in sorted(kwargs.items()):
        if isinstance(v, (str, int, float, bool)):
            key_parts.append(f"{k}={v}")
        else:
            key_parts.append(f"{k}={hashlib.md5(str(v).encode()).hexdigest()[:8]}")

    return ":".join(key_parts)


def cached(
    ttl: int = 300,
    key_prefix: str = "",
    skip_none: bool = True
):
    """
    Cache function result in Redis.

    Args:
        ttl: Time to live in seconds (default: 5 minutes)
        key_prefix: Prefix for cache key (default: function name)
        skip_none: Don't cache None results (default: True)

    Usage:
        @cached(ttl=600, key_prefix="user")
        async def get_user(user_id: str):
            return await fetch_user(user_id)
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            # Check if this is a method (has self/cls as first arg)
            skip_first = args and hasattr(args[0].__class__, func.__name__)

            cache_key = _generate_cache_key(
                func.__name__,
                args,
                kwargs,
                key_prefix,
                skip_first_arg=skip_first
            )

            # Try cache first
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                stats.record_hit()
                logger.debug(f"Cache HIT: {cache_key}")
                return cached_value

            # Cache miss - call function
            stats.record_miss()
            logger.debug(f"Cache MISS: {cache_key}")
            result = await func(*args, **kwargs)

            # Store in cache (unless None and skip_none)
            if result is not None or not skip_none:
                await cache.set(cache_key, result, ttl)
                logger.debug(f"Cache SET: {cache_key} (TTL: {ttl}s)")

            return result

        # Add helper methods to wrapper
        wrapper._cache_key_func = lambda *args, **kwargs: _generate_cache_key(
            func.__name__,
            args,
            kwargs,
            key_prefix,
            skip_first_arg=args and hasattr(args[0].__class__, func.__name__)
        )

        return wrapper

    return decorator


def cache_invalidate(key_prefix: str):
    """
    Decorator to invalidate cache after function execution.

    Useful for update/delete operations that modify cached data.

    Args:
        key_prefix: Pattern to invalidate (e.g., "tasks:*")

    Usage:
        @cache_invalidate("user:*")
        async def update_user(user_id: str, data: dict):
            return await db.update_user(user_id, data)
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Execute function first
            result = await func(*args, **kwargs)

            # Then invalidate cache
            deleted = await cache.invalidate_pattern(key_prefix)
            logger.info(f"Invalidated {deleted} cache entries matching {key_prefix}")

            return result

        return wrapper

    return decorator


def cached_property_async(ttl: int = 300):
    """
    Cached property for async methods (like @property but async).

    Args:
        ttl: Time to live in seconds

    Usage:
        class MyClass:
            @cached_property_async(ttl=600)
            async def expensive_property(self):
                return await expensive_computation()
    """
    def decorator(func: Callable):
        cache_attr = f"_cached_{func.__name__}"

        @functools.wraps(func)
        async def wrapper(self):
            # Check instance cache first
            if hasattr(self, cache_attr):
                return getattr(self, cache_attr)

            # Generate cache key from class and instance
            cache_key = f"{self.__class__.__name__}:{id(self)}:{func.__name__}"

            # Try Redis cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                # Store in instance for next access
                setattr(self, cache_attr, cached_value)
                return cached_value

            # Compute value
            result = await func(self)

            # Cache in Redis
            await cache.set(cache_key, result, ttl)

            # Cache in instance
            setattr(self, cache_attr, result)

            return result

        return wrapper

    return decorator
