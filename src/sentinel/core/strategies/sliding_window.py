"""
Sliding Window Log rate limiting algorithm implementation.

The Sliding Window algorithm provides precise request counting by
storing the timestamp of each request. It's more accurate than
Token Bucket but uses more memory.

How it works:
1. Store timestamp of each request in a sorted set
2. Remove timestamps older than the window
3. Count remaining timestamps
4. If count < limit: allow and add new timestamp
5. If count >= limit: deny

"""

import time

from sentinel.core.backends.base import StorageBackend
from sentinel.core.strategies.base import (
    RateLimitResponse,
    RateLimitResult,
    RateLimitStrategy,
)


class SlidingWindowStrategy(RateLimitStrategy):
    """
    Sliding Window Log algorithm for rate limiting.

    Tracks exact timestamps of each request within the window.
    Most accurate algorithm but with higher memory usage.

    Characteristics:
    - Precise request counting (no approximation)
    - No burst allowance beyond limit
    - Higher memory usage (stores all request timestamps)
    - Strict enforcement of limits

    Trade-offs vs Token Bucket:
    - Pro: Exact limit enforcement
    - Pro: Better for compliance requirements
    - Con: More storage per key (O(n) where n = requests in window)
    - Con: Cleanup overhead on each check

    Best for:
    - Financial endpoints where exact limits matter
    - Withdrawal limits, transfer limits
    - Compliance-sensitive operations
    - Any endpoint where bursts are not acceptable

    Storage format:
        Key: "sw:{identifier}"
        Value: Sorted set of timestamps (score = timestamp, member = timestamp string)

    Example:
        >>> backend = InMemoryBackend()
        >>> strategy = SlidingWindowStrategy(backend)
        >>> response = await strategy.check("user:123", limit=10, window_seconds=60)
        >>> print(response.is_allowed)  # True
        >>> print(response.remaining)   # 9
    """

    # Prefix for storage keys to avoid collisions
    KEY_PREFIX = "sw"

    def __init__(self, backend: StorageBackend) -> None:
        """
        Initialize Sliding Window strategy with a storage backend.

        Args:
            backend: Storage backend for persisting request timestamps.
        """
        self._backend = backend

    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResponse:
        """
        Check if a request should be allowed under Sliding Window rules.

        Algorithm:
        1. Calculate window start time (now - window_seconds)
        2. Remove all timestamps before window start
        3. Count remaining timestamps
        4. If count < limit: add new timestamp, allow
        5. If count >= limit: deny, calculate retry time

        Args:
            key: Unique identifier for the rate limit bucket.
            limit: Maximum requests allowed in the window.
            window_seconds: Duration of the sliding window.

        Returns:
            RateLimitResponse with decision and metadata.
        """
        now = time.time()
        storage_key = f"{self.KEY_PREFIX}:{key}"
        window_start = now - window_seconds

        # Step 1: Remove expired timestamps (outside the window)
        await self._backend.zremrangebyscore(
            storage_key,
            min_score=0,
            max_score=window_start,
        )

        # Step 2: Count current requests in window
        request_count = await self._backend.zcard(storage_key)

        if request_count < limit:
            # Step 3a: Under limit - add timestamp and allow
            # Use timestamp as both score and member for uniqueness
            timestamp_str = f"{now}"
            await self._backend.zadd(storage_key, score=now, member=timestamp_str)

            # Set TTL to auto-cleanup old keys
            await self._backend.expire(storage_key, window_seconds)

            return RateLimitResponse(
                result=RateLimitResult.ALLOWED,
                limit=limit,
                remaining=limit - request_count - 1,
                reset_at=now + window_seconds,
            )
        else:
            # Step 3b: At or over limit - deny
            # Calculate when the oldest request will expire
            retry_after = await self._calculate_retry_after(
                storage_key,
                window_seconds,
                now,
            )

            return RateLimitResponse(
                result=RateLimitResult.DENIED,
                limit=limit,
                remaining=0,
                reset_at=now + retry_after,
                retry_after=retry_after,
            )

    async def reset(self, key: str) -> None:
        """
        Reset rate limit state for a key.

        Removes all request timestamps, so next request starts fresh.

        Args:
            key: The rate limit key to reset.
        """
        storage_key = f"{self.KEY_PREFIX}:{key}"
        await self._backend.delete(storage_key)

    async def _calculate_retry_after(
        self,
        storage_key: str,
        window_seconds: int,
        now: float,
    ) -> float:
        """
        Calculate seconds until the client can retry.

        Finds the oldest timestamp and calculates when it will
        fall outside the window.

        Args:
            storage_key: The full storage key.
            window_seconds: Duration of the sliding window.
            now: Current timestamp.

        Returns:
            Seconds until one slot opens up.
        """
        oldest_timestamps = await self._backend.zrange(storage_key, 0, 0)

        if oldest_timestamps:
            oldest = float(oldest_timestamps[0])
            retry_after = (oldest + window_seconds) - now
            return max(0.1, retry_after)

        return float(window_seconds)