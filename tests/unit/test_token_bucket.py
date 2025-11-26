"""
Unit tests for Token Bucket rate limiting strategy.

These tests verify the correctness of the Token Bucket algorithm
without any external dependencies (using InMemoryBackend).

Test categories:
- Basic allow/deny behavior
- Token consumption tracking
- Token refill over time
- Key isolation (different users don't affect each other)
- Edge cases and boundary conditions
- Reset functionality

Run tests:
    pytest tests/unit/test_token_bucket.py -v
"""

import asyncio

import pytest

from sentinel.core.backends.memory import InMemoryBackend
from sentinel.core.strategies.base import RateLimitResult
from sentinel.core.strategies.token_bucket import TokenBucketStrategy


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def backend() -> InMemoryBackend:
    """Create a fresh in-memory backend for each test."""
    return InMemoryBackend()


@pytest.fixture
def strategy(backend: InMemoryBackend) -> TokenBucketStrategy:
    """Create a Token Bucket strategy with the test backend."""
    return TokenBucketStrategy(backend)


# =============================================================================
# Basic Behavior Tests
# =============================================================================


class TestBasicBehavior:
    """Tests for fundamental allow/deny functionality."""

    @pytest.mark.asyncio
    async def test_first_request_is_allowed(
        self,
        strategy: TokenBucketStrategy,
    ) -> None:
        """First request should always be allowed (bucket starts full)."""
        result = await strategy.check("user:1", limit=10, window_seconds=60)

        assert result.is_allowed
        assert result.result == RateLimitResult.ALLOWED

    @pytest.mark.asyncio
    async def test_requests_within_limit_are_allowed(
        self,
        strategy: TokenBucketStrategy,
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
        strategy: TokenBucketStrategy,
    ) -> None:
        """Request beyond the limit should be denied."""
        limit = 3
        key = "user:3"

        # Exhaust all tokens
        for _ in range(limit):
            await strategy.check(key, limit=limit, window_seconds=60)

        # Next request should be denied
        result = await strategy.check(key, limit=limit, window_seconds=60)

        assert not result.is_allowed
        assert result.result == RateLimitResult.DENIED


# =============================================================================
# Token Tracking Tests
# =============================================================================


class TestTokenTracking:
    """Tests for correct token counting and remaining calculation."""

    @pytest.mark.asyncio
    async def test_remaining_decreases_with_each_request(
        self,
        strategy: TokenBucketStrategy,
    ) -> None:
        """Remaining tokens should decrease by 1 per request."""
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
        strategy: TokenBucketStrategy,
    ) -> None:
        """Denied requests should show 0 remaining tokens."""
        limit = 2
        key = "user:5"

        # Exhaust tokens
        await strategy.check(key, limit=limit, window_seconds=60)
        await strategy.check(key, limit=limit, window_seconds=60)

        # Check denied request
        result = await strategy.check(key, limit=limit, window_seconds=60)

        assert not result.is_allowed
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_limit_is_always_returned_correctly(
        self,
        strategy: TokenBucketStrategy,
    ) -> None:
        """Response should always contain the correct limit value."""
        limit = 100
        key = "user:6"

        result = await strategy.check(key, limit=limit, window_seconds=60)

        assert result.limit == limit


# =============================================================================
# Token Refill Tests
# =============================================================================


class TestTokenRefill:
    """Tests for token refill behavior over time."""

    @pytest.mark.asyncio
    async def test_tokens_refill_after_time_passes(
        self,
        strategy: TokenBucketStrategy,
    ) -> None:
        """Tokens should refill based on elapsed time."""
        limit = 2
        window_seconds = 2  # 1 token per second refill rate
        key = "user:7"

        # Use all tokens
        await strategy.check(key, limit=limit, window_seconds=window_seconds)
        await strategy.check(key, limit=limit, window_seconds=window_seconds)

        # Should be denied now
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        assert not result.is_allowed

        # Wait for 1 token to refill (slightly more than 1 second)
        await asyncio.sleep(1.1)

        # Should be allowed now
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        assert result.is_allowed

    @pytest.mark.asyncio
    async def test_tokens_do_not_exceed_limit_after_long_wait(
        self,
        strategy: TokenBucketStrategy,
    ) -> None:
        """Tokens should cap at limit even after long idle period."""
        limit = 5
        key = "user:8"

        # Make one request to initialize bucket
        await strategy.check(key, limit=limit, window_seconds=60)

        # Wait a bit (simulating idle time)
        await asyncio.sleep(0.5)

        # Make another request - remaining should not exceed limit - 1
        result = await strategy.check(key, limit=limit, window_seconds=60)

        # Even with refill, can't exceed limit
        assert result.remaining <= limit - 1

    @pytest.mark.asyncio
    async def test_retry_after_is_provided_when_denied(
        self,
        strategy: TokenBucketStrategy,
    ) -> None:
        """Denied response should include retry_after value."""
        limit = 1
        window_seconds = 10  # 0.1 tokens per second
        key = "user:9"

        # Use the only token
        await strategy.check(key, limit=limit, window_seconds=window_seconds)

        # Next request denied
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)

        assert not result.is_allowed
        assert result.retry_after is not None
        assert result.retry_after > 0
        # Should be approximately 10 seconds (time for 1 token)
        assert result.retry_after <= window_seconds


# =============================================================================
# Key Isolation Tests
# =============================================================================


class TestKeyIsolation:
    """Tests for isolation between different rate limit keys."""

    @pytest.mark.asyncio
    async def test_different_keys_have_independent_limits(
        self,
        strategy: TokenBucketStrategy,
    ) -> None:
        """Each key should have its own token bucket."""
        limit = 2

        # Exhaust tokens for user A
        await strategy.check("user:A", limit=limit, window_seconds=60)
        await strategy.check("user:A", limit=limit, window_seconds=60)

        # User A should be denied
        result_a = await strategy.check("user:A", limit=limit, window_seconds=60)
        assert not result_a.is_allowed

        # User B should still have full bucket
        result_b = await strategy.check("user:B", limit=limit, window_seconds=60)
        assert result_b.is_allowed
        assert result_b.remaining == limit - 1

    @pytest.mark.asyncio
    async def test_many_users_can_make_requests_simultaneously(
        self,
        strategy: TokenBucketStrategy,
    ) -> None:
        """Multiple users should be able to use their limits independently."""
        limit = 5
        num_users = 10

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
    async def test_reset_restores_full_bucket(
        self,
        strategy: TokenBucketStrategy,
    ) -> None:
        """Reset should allow a fresh start with full tokens."""
        limit = 3
        key = "user:reset"

        # Use some tokens
        await strategy.check(key, limit=limit, window_seconds=60)
        await strategy.check(key, limit=limit, window_seconds=60)

        # Reset the bucket
        await strategy.reset(key)

        # Should have full capacity again
        result = await strategy.check(key, limit=limit, window_seconds=60)
        assert result.is_allowed
        assert result.remaining == limit - 1

    @pytest.mark.asyncio
    async def test_reset_nonexistent_key_does_not_error(
        self,
        strategy: TokenBucketStrategy,
    ) -> None:
        """Resetting a key that doesn't exist should not raise an error."""
        # Should not raise
        await strategy.reset("nonexistent:key")

    @pytest.mark.asyncio
    async def test_reset_only_affects_target_key(
        self,
        strategy: TokenBucketStrategy,
    ) -> None:
        """Reset should not affect other keys."""
        limit = 2

        # Use tokens for both users
        await strategy.check("user:X", limit=limit, window_seconds=60)
        await strategy.check("user:X", limit=limit, window_seconds=60)

        await strategy.check("user:Y", limit=limit, window_seconds=60)
        await strategy.check("user:Y", limit=limit, window_seconds=60)

        # Reset only user X
        await strategy.reset("user:X")

        # User X should have full bucket
        result_x = await strategy.check("user:X", limit=limit, window_seconds=60)
        assert result_x.is_allowed
        assert result_x.remaining == limit - 1

        # User Y should still be exhausted
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
        strategy: TokenBucketStrategy,
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
        strategy: TokenBucketStrategy,
    ) -> None:
        """Should work with very short time windows."""
        limit = 10
        window_seconds = 1  # 10 tokens per second
        key = "user:shortwindow"

        # Exhaust tokens
        for _ in range(limit):
            await strategy.check(key, limit=limit, window_seconds=window_seconds)

        # Should be denied
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        assert not result.is_allowed

        # Wait for full refill
        await asyncio.sleep(1.1)

        # Should be allowed again
        result = await strategy.check(key, limit=limit, window_seconds=window_seconds)
        assert result.is_allowed

    @pytest.mark.asyncio
    async def test_large_limit(
        self,
        strategy: TokenBucketStrategy,
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
        strategy: TokenBucketStrategy,
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
        strategy: TokenBucketStrategy,
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