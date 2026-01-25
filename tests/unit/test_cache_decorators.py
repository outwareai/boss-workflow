"""
Tests for src/cache/decorators.py

Tests caching decorators including @cached, @cache_invalidate,
and @cached_property_async, plus cache key generation.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.cache.decorators import (
    _generate_cache_key,
    cached,
    cache_invalidate,
    cached_property_async,
)


class TestGenerateCacheKey:
    """Tests for _generate_cache_key function."""

    def test_basic_cache_key_with_function_name(self):
        """Test generating cache key with just function name."""
        key = _generate_cache_key("my_func", (), {})
        assert key == "my_func"

    def test_cache_key_with_string_args(self):
        """Test cache key with string arguments."""
        key = _generate_cache_key("my_func", ("arg1", "arg2"), {})
        assert key == "my_func:arg1:arg2"

    def test_cache_key_with_int_args(self):
        """Test cache key with integer arguments."""
        key = _generate_cache_key("my_func", (123, 456), {})
        assert key == "my_func:123:456"

    def test_cache_key_with_kwargs(self):
        """Test cache key with keyword arguments."""
        key = _generate_cache_key("my_func", (), {"id": "123", "name": "test"})
        assert "id=123" in key
        assert "name=test" in key

    def test_cache_key_with_prefix(self):
        """Test cache key with custom prefix."""
        key = _generate_cache_key("my_func", ("arg1",), {}, key_prefix="custom")
        assert key.startswith("custom:")

    def test_cache_key_skip_first_arg(self):
        """Test skipping first argument (for instance methods)."""
        key = _generate_cache_key("method", ("self", "arg1"), {}, skip_first_arg=True)
        assert "self" not in key
        assert "arg1" in key

    def test_cache_key_with_list_arg_hashed(self):
        """Test that list arguments are hashed."""
        key = _generate_cache_key("my_func", ([1, 2, 3],), {})
        # Should contain a hash, not the full list
        assert ":" in key
        assert "[1, 2, 3]" not in key

    def test_cache_key_with_complex_object_hashed(self):
        """Test that complex objects are hashed."""
        class CustomObj:
            pass

        obj = CustomObj()
        key = _generate_cache_key("my_func", (obj,), {})
        # Should contain a hash
        assert "my_func:" in key

    def test_cache_key_deterministic(self):
        """Test that same inputs produce same key."""
        key1 = _generate_cache_key("func", ("a", "b"), {"x": 1})
        key2 = _generate_cache_key("func", ("a", "b"), {"x": 1})
        assert key1 == key2

    def test_cache_key_different_for_different_inputs(self):
        """Test that different inputs produce different keys."""
        key1 = _generate_cache_key("func", ("a",), {})
        key2 = _generate_cache_key("func", ("b",), {})
        assert key1 != key2


@pytest.mark.asyncio
class TestCachedDecorator:
    """Tests for @cached decorator."""

    @patch('src.cache.decorators.cache')
    @patch('src.cache.decorators.stats')
    async def test_cache_miss_calls_function(self, mock_stats, mock_cache):
        """Test that cache miss calls the original function."""
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()
        call_count = 0

        @cached(ttl=60)
        async def my_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result = await my_func(5)

        assert result == 10
        assert call_count == 1
        mock_stats.record_miss.assert_called_once()
        mock_cache.set.assert_called_once()

    @patch('src.cache.decorators.cache')
    @patch('src.cache.decorators.stats')
    async def test_cache_hit_skips_function(self, mock_stats, mock_cache):
        """Test that cache hit returns cached value without calling function."""
        mock_cache.get = AsyncMock(return_value=20)
        call_count = 0

        @cached(ttl=60)
        async def my_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result = await my_func(5)

        assert result == 20  # Cached value
        assert call_count == 0  # Function not called
        mock_stats.record_hit.assert_called_once()

    @patch('src.cache.decorators.cache')
    @patch('src.cache.decorators.stats')
    async def test_cache_stores_result_with_ttl(self, mock_stats, mock_cache):
        """Test that result is cached with correct TTL."""
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        @cached(ttl=300)
        async def my_func(x):
            return x * 2

        await my_func(5)

        # Verify set was called with correct TTL
        args = mock_cache.set.call_args
        assert args[0][2] == 300  # TTL argument

    @patch('src.cache.decorators.cache')
    @patch('src.cache.decorators.stats')
    async def test_cache_skip_none_by_default(self, mock_stats, mock_cache):
        """Test that None results are not cached by default."""
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        @cached(ttl=60)
        async def my_func(x):
            return None

        result = await my_func(5)

        assert result is None
        mock_cache.set.assert_not_called()

    @patch('src.cache.decorators.cache')
    @patch('src.cache.decorators.stats')
    async def test_cache_none_when_skip_none_false(self, mock_stats, mock_cache):
        """Test that None is cached when skip_none=False."""
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        @cached(ttl=60, skip_none=False)
        async def my_func(x):
            return None

        await my_func(5)

        mock_cache.set.assert_called_once()

    @patch('src.cache.decorators.cache')
    @patch('src.cache.decorators.stats')
    async def test_cache_with_custom_key_prefix(self, mock_stats, mock_cache):
        """Test caching with custom key prefix."""
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        @cached(ttl=60, key_prefix="custom")
        async def my_func(x):
            return x * 2

        await my_func(5)

        # Verify key starts with custom prefix
        key = mock_cache.set.call_args[0][0]
        assert key.startswith("custom:")

    @patch('src.cache.decorators.cache')
    @patch('src.cache.decorators.stats')
    async def test_cache_different_args_different_keys(self, mock_stats, mock_cache):
        """Test that different arguments produce different cache keys."""
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        @cached(ttl=60)
        async def my_func(x):
            return x * 2

        await my_func(5)
        key1 = mock_cache.set.call_args[0][0]

        await my_func(10)
        key2 = mock_cache.set.call_args[0][0]

        assert key1 != key2


@pytest.mark.asyncio
class TestCacheInvalidateDecorator:
    """Tests for @cache_invalidate decorator."""

    @patch('src.cache.decorators.cache')
    async def test_invalidate_calls_function_first(self, mock_cache):
        """Test that function is called before invalidation."""
        mock_cache.invalidate_pattern = AsyncMock(return_value=5)
        call_order = []

        @cache_invalidate("test:*")
        async def my_func():
            call_order.append("function")
            return "result"

        # Mock to track when invalidation happens
        async def track_invalidate(pattern):
            call_order.append("invalidate")
            return 5

        mock_cache.invalidate_pattern = track_invalidate

        result = await my_func()

        assert result == "result"
        assert call_order == ["function", "invalidate"]

    @patch('src.cache.decorators.cache')
    async def test_invalidate_pattern_called_with_correct_prefix(self, mock_cache):
        """Test that invalidate_pattern is called with correct prefix."""
        mock_cache.invalidate_pattern = AsyncMock(return_value=3)

        @cache_invalidate("user:*")
        async def my_func():
            return "done"

        await my_func()

        mock_cache.invalidate_pattern.assert_called_once_with("user:*")

    @patch('src.cache.decorators.cache')
    async def test_invalidate_returns_function_result(self, mock_cache):
        """Test that decorator returns function result."""
        mock_cache.invalidate_pattern = AsyncMock(return_value=0)

        @cache_invalidate("test:*")
        async def my_func(value):
            return value * 2

        result = await my_func(10)
        assert result == 20


@pytest.mark.asyncio
class TestCachedPropertyAsync:
    """Tests for @cached_property_async decorator."""

    @patch('src.cache.decorators.cache')
    async def test_cached_property_first_call(self, mock_cache):
        """Test first call to cached property."""
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        class MyClass:
            def __init__(self):
                self.compute_count = 0

            @cached_property_async(ttl=60)
            async def expensive_property(self):
                self.compute_count += 1
                return "computed"

        obj = MyClass()
        result = await obj.expensive_property()

        assert result == "computed"
        assert obj.compute_count == 1

    @patch('src.cache.decorators.cache')
    async def test_cached_property_uses_redis_cache(self, mock_cache):
        """Test that cached property uses Redis cache."""
        mock_cache.get = AsyncMock(return_value="cached_value")

        class MyClass:
            @cached_property_async(ttl=60)
            async def expensive_property(self):
                return "computed"

        obj = MyClass()
        result = await obj.expensive_property()

        assert result == "cached_value"

    @patch('src.cache.decorators.cache')
    async def test_cached_property_stores_in_instance(self, mock_cache):
        """Test that cached property stores value in instance."""
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        class MyClass:
            @cached_property_async(ttl=60)
            async def expensive_property(self):
                return "computed"

        obj = MyClass()
        await obj.expensive_property()

        # Second call should use instance cache
        mock_cache.get = AsyncMock(return_value=None)  # Clear Redis
        result = await obj.expensive_property()

        assert result == "computed"
        assert hasattr(obj, "_cached_expensive_property")

    @patch('src.cache.decorators.cache')
    async def test_cached_property_different_instances(self, mock_cache):
        """Test that different instances have separate caches."""
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        class MyClass:
            def __init__(self, value):
                self.value = value

            @cached_property_async(ttl=60)
            async def expensive_property(self):
                return self.value

        obj1 = MyClass("value1")
        obj2 = MyClass("value2")

        result1 = await obj1.expensive_property()
        result2 = await obj2.expensive_property()

        assert result1 == "value1"
        assert result2 == "value2"
