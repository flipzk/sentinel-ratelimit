"""
Unit tests for Sliding Window rate limiting strategy.

These tests verify the correctness of the Sliding Window algorithm
without any external dependencies (using InMemoryBackend).

Test categories:
- Basic allow/deny behavior
- Request counting accuracy
- Window expiration behavior
- Key isolation (different users don't affect each other)
- Edge cases and boundary conditions
- Reset functionality

Run tests:
    pytest tests/unit/test_sliding_window.py -v
"""

import asyncio

import pytest

from sentinel.core.backends.memory import InMemoryBackend
from sentinel.core.strategies.base import RateLimitResult
from sentinel.core.strategies.sliding_window import SlidingWindowStrategy


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def backend() -> InMemoryBackend:
    """Create a fresh in-memory backend for each test."""
    return InMemoryBackend()


@pytest.fixture
def strategy(backend: InMemoryBackend) -> SlidingWindowStrategy:
    """Create a Sliding Window strategy with the test backend."""
    return SlidingWindowStrategy(backend)


# =============================================================================
# Basic Behavior Tests
# =============================================================================


class TestBasicBehavior:
    """Tests for fundamental allow/deny functionality."""

    @pytest.mark.asyncio
    async def test_first_request_is_allowed(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """First request should always be allowed."""
        result = await strategy.check("user:1", limit=10, window_seconds=60)

        assert result.is_allowed
        assert result.result == RateLimitResult.ALLOWED

    @pytest.mark.asyncio
    async def test_requests_within_limit_are_allowed(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """All requests within the limit should be allowed."""
        limit = 5
        key = "user:2"

        for i in range(limit):
            result = await strategy.check(key, limit=limit, window_seconds=60)
            assert result.is_allowed, f"Request {i + 1} should be allowed"

    @pytest.mark.asyncio
    async def test_request_exceeding_limit_is_denied(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Request beyond the limit should be denied."""
        limit = 3
        key = "user:3"

        # Use all slots
        for _ in range(limit):
            await strategy.check(key, limit=limit, window_seconds=60)

        # Next request should be denied
        result = await strategy.check(key, limit=limit, window_seconds=60)

        assert not result.is_allowed
        assert result.result == RateLimitResult.DENIED


# =============================================================================
# Request Counting Tests
# =============================================================================


class TestRequestCounting:
    """Tests for accurate request counting."""

    @pytest.mark.asyncio
    async def test_remaining_decreases_with_each_request(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Remaining count should decrease by 1 per request."""
        limit = 10
        key = "user:4"

        for i in range(limit):
            result = await strategy.check(key, limit=limit, window_seconds=60)
            expected_remaining = limit - i - 1
            assert result.remaining == expected_remaining, (
                f"After request {i + 1}, remaining should be {expected_remaining}"
            )

    @pytest.mark.asyncio
    async def test_remaining_is_zero_when_denied(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Denied requests should show 0 remaining."""
        limit = 2
        key = "user:5"

        # Use all slots
        await strategy.check(key, limit=limit, window_seconds=60)
        await strategy.check(key, limit=limit, window_seconds=60)

        # Check denied request
        result = await strategy.check(key, limit=limit, window_seconds=60)

        assert not result.is_allowed
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_limit_is_always_returned_correctly(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Response should always contain the correct limit value."""
        limit = 100
        key = "user:6"

        result = await strategy.check(key, limit=limit, window_seconds=60)

        assert result.limit == limit

    @pytest.mark.asyncio
    async def test_exact_count_at_limit_boundary(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Sliding window should have exact counting at the limit."""
        limit = 5
        key = "user:exact"

        # Make exactly 'limit' requests
        for i in range(limit):
            result = await strategy.check(key, limit=limit, window_seconds=60)
            assert result.is_allowed
            assert result.remaining == limit - i - 1

        # The very next request should be denied
        result = await strategy.check(key, limit=limit, window_seconds=60)
        assert not result.is_allowed
        assert result.remaining == 0


# =============================================================================
# Window Expiration Tests
# =============================================================================


class TestWindowExpiration:
    """Tests for window expiration behavior."""

    @pytest.mark.asyncio
    async def test_requests_allowed_after_window_expires(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """After window expires, requests should be allowed again."""
        limit = 2
        window_seconds = 1  # Short window for testing
        key = "user:7"

        # Use all slots
        await strategy.check(key, limit=limit, window_seconds=window_seconds)
        await strategy.check(key, limit=limit, window_seconds=window_seconds)

        # Should be denied
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        assert not result.is_allowed

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Should be allowed again
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        assert result.is_allowed

    @pytest.mark.asyncio
    async def test_partial_window_expiration(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Only expired requests should be removed from window."""
        limit = 3
        window_seconds = 2
        key = "user:8"

        # Make first request
        await strategy.check(key, limit=limit, window_seconds=window_seconds)

        # Wait half the window
        await asyncio.sleep(1.1)

        # Make second request
        await strategy.check(key, limit=limit, window_seconds=window_seconds)

        # Make third request
        await strategy.check(key, limit=limit, window_seconds=window_seconds)

        # Should be denied (3 requests in window)
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        assert not result.is_allowed

        # Wait for first request to expire (but not second and third)
        await asyncio.sleep(1.0)

        # Now should be allowed (first request expired)
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        assert result.is_allowed

    @pytest.mark.asyncio
    async def test_retry_after_is_provided_when_denied(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Denied response should include retry_after value."""
        limit = 1
        window_seconds = 10
        key = "user:9"

        # Use the only slot
        await strategy.check(key, limit=limit, window_seconds=window_seconds)

        # Next request denied
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)

        assert not result.is_allowed
        assert result.retry_after is not None
        assert result.retry_after > 0
        # Should be approximately window_seconds (time until first request expires)
        assert result.retry_after <= window_seconds

    @pytest.mark.asyncio
    async def test_retry_after_decreases_over_time(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """retry_after should decrease as time passes."""
        limit = 1
        window_seconds = 3
        key = "user:retry"

        # Use the only slot
        await strategy.check(key, limit=limit, window_seconds=window_seconds)

        # Get first retry_after
        result1 = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        retry1 = result1.retry_after

        # Wait a bit
        await asyncio.sleep(1.0)

        # Get second retry_after
        result2 = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        retry2 = result2.retry_after

        # Second retry_after should be less than first
        assert retry2 < retry1


# =============================================================================
# Key Isolation Tests
# =============================================================================


class TestKeyIsolation:
    """Tests for isolation between different rate limit keys."""

    @pytest.mark.asyncio
    async def test_different_keys_have_independent_limits(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Each key should have its own window."""
        limit = 2

        # Use all slots for user A
        await strategy.check("user:A", limit=limit, window_seconds=60)
        await strategy.check("user:A", limit=limit, window_seconds=60)

        # User A should be denied
        result_a = await strategy.check("user:A", limit=limit, window_seconds=60)
        assert not result_a.is_allowed

        # User B should still have all slots
        result_b = await strategy.check("user:B", limit=limit, window_seconds=60)
        assert result_b.is_allowed
        assert result_b.remaining == limit - 1

    @pytest.mark.asyncio
    async def test_many_users_independent_limits(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Multiple users should have completely independent limits."""
        limit = 3
        num_users = 5

        # Each user makes 'limit' requests
        for user_id in range(num_users):
            key = f"user:{user_id}"
            for _ in range(limit):
                result = await strategy.check(key, limit=limit, window_seconds=60)
                assert result.is_allowed

            # One more should be denied
            result = await strategy.check(key, limit=limit, window_seconds=60)
            assert not result.is_allowed


# =============================================================================
# Reset Tests
# =============================================================================


class TestReset:
    """Tests for the reset functionality."""

    @pytest.mark.asyncio
    async def test_reset_clears_all_requests(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Reset should remove all recorded requests."""
        limit = 3
        key = "user:reset"

        # Use all slots
        for _ in range(limit):
            await strategy.check(key, limit=limit, window_seconds=60)

        # Should be denied
        result = await strategy.check(key, limit=limit, window_seconds=60)
        assert not result.is_allowed

        # Reset
        await strategy.reset(key)

        # Should have all slots again
        result = await strategy.check(key, limit=limit, window_seconds=60)
        assert result.is_allowed
        assert result.remaining == limit - 1

    @pytest.mark.asyncio
    async def test_reset_nonexistent_key_does_not_error(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Resetting a key that doesn't exist should not raise."""
        # Should not raise
        await strategy.reset("nonexistent:key")

    @pytest.mark.asyncio
    async def test_reset_only_affects_target_key(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Reset should not affect other keys."""
        limit = 2

        # Use all slots for both users
        await strategy.check("user:X", limit=limit, window_seconds=60)
        await strategy.check("user:X", limit=limit, window_seconds=60)

        await strategy.check("user:Y", limit=limit, window_seconds=60)
        await strategy.check("user:Y", limit=limit, window_seconds=60)

        # Reset only user X
        await strategy.reset("user:X")

        # User X should have full capacity
        result_x = await strategy.check("user:X", limit=limit, window_seconds=60)
        assert result_x.is_allowed
        assert result_x.remaining == limit - 1

        # User Y should still be at limit
        result_y = await strategy.check("user:Y", limit=limit, window_seconds=60)
        assert not result_y.is_allowed


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for boundary conditions and edge cases."""

    @pytest.mark.asyncio
    async def test_limit_of_one(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Should work correctly with limit of 1."""
        limit = 1
        key = "user:limit1"

        # First request allowed
        result = await strategy.check(key, limit=limit, window_seconds=60)
        assert result.is_allowed
        assert result.remaining == 0

        # Second immediately denied
        result = await strategy.check(key, limit=limit, window_seconds=60)
        assert not result.is_allowed

    @pytest.mark.asyncio
    async def test_very_short_window(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Should work with very short time windows."""
        limit = 5
        window_seconds = 1
        key = "user:shortwindow"

        # Use all slots
        for _ in range(limit):
            await strategy.check(key, limit=limit, window_seconds=window_seconds)

        # Should be denied
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        assert not result.is_allowed

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Should be allowed
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        assert result.is_allowed

    @pytest.mark.asyncio
    async def test_large_limit(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Should work with large limits."""
        limit = 10000
        key = "user:largelimit"

        result = await strategy.check(key, limit=limit, window_seconds=3600)

        assert result.is_allowed
        assert result.remaining == limit - 1
        assert result.limit == limit

    @pytest.mark.asyncio
    async def test_reset_at_is_in_the_future(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """reset_at should always be a future timestamp."""
        import time

        limit = 5
        key = "user:resetat"

        result = await strategy.check(key, limit=limit, window_seconds=60)

        assert result.reset_at > time.time()

    @pytest.mark.asyncio
    async def test_special_characters_in_key(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Keys with special characters should work correctly."""
        limit = 5
        special_keys = [
            "user:email@example.com",
            "ip:192.168.1.1",
            "api:key-with-dashes",
            "user:名前",  # Unicode
        ]

        for key in special_keys:
            result = await strategy.check(key, limit=limit, window_seconds=60)
            assert result.is_allowed, f"Key '{key}' should be allowed"

    @pytest.mark.asyncio
    async def test_rapid_requests_all_counted(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Rapid successive requests should all be counted."""
        limit = 5
        key = "user:rapid"

        # Make rapid requests (no sleep between them)
        results = []
        for _ in range(limit + 2):
            result = await strategy.check(key, limit=limit, window_seconds=60)
            results.append(result.is_allowed)

        # First 'limit' should be allowed, rest denied
        assert results[:limit] == [True] * limit
        assert results[limit:] == [False] * 2


# =============================================================================
# Comparison with Token Bucket Behavior
# =============================================================================


class TestSlidingWindowSpecificBehavior:
    """Tests that highlight Sliding Window's unique characteristics."""

    @pytest.mark.asyncio
    async def test_no_burst_allowance(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """
        Sliding Window should NOT allow bursts beyond limit.
        
        Unlike Token Bucket, even if you wait, you can't
        accumulate extra capacity beyond the limit.
        """
        limit = 3
        window_seconds = 2
        key = "user:noburst"

        # Wait a long time (would accumulate tokens in Token Bucket)
        await asyncio.sleep(0.5)

        # Try to make more than 'limit' requests quickly
        allowed_count = 0
        for _ in range(limit + 2):
            result = await strategy.check(key, limit=limit, window_seconds=window_seconds)
            if result.is_allowed:
                allowed_count += 1

        # Should allow exactly 'limit' requests, no more
        assert allowed_count == limit

    @pytest.mark.asyncio
    async def test_strict_limit_enforcement(
        self,
        strategy: SlidingWindowStrategy,
    ) -> None:
        """Sliding Window enforces exact limits, not approximate."""
        limit = 10
        key = "user:strict"

        # Make exactly 'limit' requests
        for i in range(limit):
            result = await strategy.check(key, limit=limit, window_seconds=60)
            assert result.is_allowed, f"Request {i + 1} should be allowed"
            assert result.remaining == limit - i - 1

        # Request limit + 1 must be denied
        result = await strategy.check(key, limit=limit, window_seconds=60)
        assert not result.is_allowed
        assert result.remaining == 0