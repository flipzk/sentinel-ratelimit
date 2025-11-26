"""
Token Bucket rate limiting algorithm implementation.

The Token Bucket is one of the most widely used rate limiting algorithms,
especially in financial APIs. It provides a good balance between strictness
and flexibility by allowing controlled bursts.

How it works:
1. Each user/key has a "bucket" with a maximum capacity (the limit)
2. The bucket starts full
3. Each request consumes 1 token
4. Tokens refill at a constant rate over time
5. If no tokens available, request is denied

Example with limit=10, window=60s:
- Bucket capacity: 10 tokens
- Refill rate: 10/60 = 0.166 tokens per second
- User can burst 10 requests instantly, then must wait for refill
"""

import time

from sentinel.core.backends.base import StorageBackend
from sentinel.core.strategies.base import (
    RateLimitResponse,
    RateLimitResult,
    RateLimitStrategy,
)


class TokenBucketStrategy(RateLimitStrategy):
    """
    Token Bucket algorithm for rate limiting.

    Characteristics:
    - Allows bursts up to bucket capacity
    - Smooth token refill over time
    - Memory efficient (only stores 2 values per key)
    - Simple and predictable behavior

    Trade-offs:
    - Pro: Handles traffic bursts gracefully
    - Pro: Low memory footprint
    - Pro: Fast O(1) operations
    - Con: Less precise than sliding window for exact counts

    Best for:
    - General API rate limiting
    - Endpoints where occasional bursts are acceptable
    - High-throughput systems needing efficiency

    Storage format:
        Key: "tb:{identifier}"
        Value: {"tokens": float, "last_refill": float}

    Example:
        >>> backend = InMemoryBackend()
        >>> strategy = TokenBucketStrategy(backend)
        >>> response = await strategy.check("user:123", limit=100, window_seconds=60)
        >>> print(response.is_allowed)  # True
        >>> print(response.remaining)   # 99
    """

    # Prefix for storage keys to avoid collisions
    KEY_PREFIX = "tb"

    def __init__(self, backend: StorageBackend) -> None:
        """
        Initialize Token Bucket strategy with a storage backend.

        Args:
            backend: Storage backend for persisting bucket state.
        """
        self._backend = backend

    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResponse:
        """
        Check if a request should be allowed under Token Bucket rules.

        Algorithm:
        1. Calculate refill rate (tokens per second)
        2. Get current bucket state (or create new full bucket)
        3. Calculate tokens to add based on elapsed time
        4. If tokens >= 1: consume one, allow request
        5. If tokens < 1: deny request, calculate retry time

        Args:
            key: Unique identifier for the rate limit bucket.
            limit: Maximum tokens (requests) in the bucket.
            window_seconds: Time for bucket to fully refill.

        Returns:
            RateLimitResponse with decision and metadata.
        """
        now = time.time()
        storage_key = f"{self.KEY_PREFIX}:{key}"

        # How many tokens we add per second
        # Example: limit=60, window=60s → 1 token/second
        refill_rate = limit / window_seconds

        # Get current state or create full bucket
        state = await self._get_state(storage_key)

        if state is None:
            # New bucket: start with full capacity
            current_tokens = float(limit)
            last_refill = now
        else:
            # Existing bucket: calculate token refill
            current_tokens = state["tokens"]
            last_refill = state["last_refill"]

            # Add tokens based on elapsed time
            elapsed = now - last_refill
            tokens_to_add = elapsed * refill_rate

            # Cap at maximum capacity
            current_tokens = min(limit, current_tokens + tokens_to_add)

        # Attempt to consume one token
        if current_tokens >= 1:
            # Consume token and allow request
            new_tokens = current_tokens - 1

            await self._save_state(
                storage_key,
                tokens=new_tokens,
                last_refill=now,
                ttl=window_seconds * 2,  # Keep state longer than window
            )

            return RateLimitResponse(
                result=RateLimitResult.ALLOWED,
                limit=limit,
                remaining=int(new_tokens),
                reset_at=now + window_seconds,
            )
        else:
            # Not enough tokens, deny request
            # Calculate how long until 1 token is available
            tokens_needed = 1 - current_tokens
            retry_after = tokens_needed / refill_rate

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

        Removes the bucket state, so next request gets a full bucket.

        Args:
            key: The rate limit key to reset.
        """
        storage_key = f"{self.KEY_PREFIX}:{key}"
        await self._backend.delete(storage_key)

    async def _get_state(self, storage_key: str) -> dict | None:
        """
        Retrieve bucket state from storage.

        Args:
            storage_key: The full storage key (with prefix).

        Returns:
            Dict with "tokens" and "last_refill", or None if not found.
        """
        return await self._backend.get(storage_key)

    async def _save_state(
        self,
        storage_key: str,
        tokens: float,
        last_refill: float,
        ttl: int,
    ) -> None:
        """
        Persist bucket state to storage.

        Args:
            storage_key: The full storage key (with prefix).
            tokens: Current token count.
            last_refill: Timestamp of this update.
            ttl: Time-to-live for automatic cleanup.
        """
        await self._backend.set(
            storage_key,
            {"tokens": tokens, "last_refill": last_refill},
            ttl=ttl,
        )