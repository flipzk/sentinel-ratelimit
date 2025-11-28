"""
Abstract base class for storage backends.

This module defines the contract that all storage backends must follow.
Separating storage from algorithms allows:
- Testing with in-memory backend (no Redis needed)
- Swapping Redis for Memcached, DynamoDB, etc.
- Running locally without external dependencies

The interface includes both key-value operations (for Token Bucket)
and sorted set operations (for Sliding Window algorithm).
"""

from abc import ABC, abstractmethod
from typing import Any


class StorageBackend(ABC):
    """
    Abstract base class for rate limit state storage.

    Implementations must handle:
    - Key-value storage with TTL (for Token Bucket)
    - Sorted sets with score-based operations (for Sliding Window)
    - Concurrent access from multiple requests

    Available implementations:
    - InMemoryBackend: For testing and development (no persistence)
    - RedisBackend: For production (distributed, persistent)

    Why abstract?
    -------------
    1. Testability: Unit tests use InMemoryBackend (fast, no setup)
    2. Flexibility: Swap storage without changing algorithms
    3. Local development: Run without Redis installed
    4. Dependency Inversion: Algorithms depend on abstraction, not Redis

    Example:
        >>> backend = InMemoryBackend()  # for testing
        >>> strategy = TokenBucketStrategy(backend)

        >>> backend = RedisBackend(redis_url)  # for production
        >>> strategy = TokenBucketStrategy(backend)
    """

    # =========================================================================
    # Key-Value Operations (used by Token Bucket)
    # =========================================================================

    @abstractmethod
    async def get(self, key: str) -> dict[str, Any] | None:
        """
        Retrieve a value by key.

        Args:
            key: The key to retrieve.

        Returns:
            The stored dictionary, or None if key doesn't exist or expired.

        Example:
            >>> await backend.get("tb:user:123")
            {"tokens": 5.0, "last_refill": 1699900000.0}
        """
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        value: dict[str, Any],
        ttl: int,
    ) -> None:
        """
        Store a value with expiration time.

        Args:
            key: The key to store under.
            value: Dictionary to store (must be JSON-serializable).
            ttl: Time-to-live in seconds. Key auto-deletes after this.

        Example:
            >>> await backend.set(
            ...     "tb:user:123",
            ...     {"tokens": 5.0, "last_refill": 1699900000.0},
            ...     ttl=120
            ... )
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """
        Delete a key from storage.

        Args:
            key: The key to delete. No error if key doesn't exist.

        Example:
            >>> await backend.delete("tb:user:123")
        """
        pass

    @abstractmethod
    async def zadd(self, key: str, score: float, member: str) -> None:
        """
        Add a member to a sorted set with a score.

        If member already exists, its score is updated.

        Args:
            key: The sorted set key.
            score: Numeric score for sorting (usually a timestamp).
            member: The member to add (must be unique in the set).

        Example:
            >>> # Store request timestamp
            >>> await backend.zadd("sw:user:123", 1699900000.0, "1699900000.0")
        """
        pass

    @abstractmethod
    async def zremrangebyscore(
        self,
        key: str,
        min_score: float,
        max_score: float,
    ) -> int:
        """
        Remove members with scores in the given range.

        Used to clean up old requests outside the sliding window.

        Args:
            key: The sorted set key.
            min_score: Minimum score (inclusive).
            max_score: Maximum score (inclusive).

        Returns:
            Number of members removed.

        Example:
            >>> # Remove all requests older than window_start
            >>> removed = await backend.zremrangebyscore(
            ...     "sw:user:123",
            ...     min_score=0,
            ...     max_score=window_start
            ... )
        """
        pass

    @abstractmethod
    async def zcard(self, key: str) -> int:
        """
        Count members in a sorted set.

        Used to count requests in the current window.

        Args:
            key: The sorted set key.

        Returns:
            Number of members in the set, or 0 if key doesn't exist.

        Example:
            >>> count = await backend.zcard("sw:user:123")
            >>> if count >= limit:
            ...     deny_request()
        """
        pass

    @abstractmethod
    async def zrange(
        self,
        key: str,
        start: int,
        stop: int,
    ) -> list[str]:
        """
        Get members by index range (sorted by score ascending).

        Args:
            key: The sorted set key.
            start: Start index (0-based, inclusive).
            stop: Stop index (inclusive, use -1 for last element).

        Returns:
            List of members in the range.

        Example:
            >>> # Get the oldest request timestamp
            >>> oldest = await backend.zrange("sw:user:123", 0, 0)
            >>> if oldest:
            ...     oldest_timestamp = float(oldest[0])
        """
        pass

    @abstractmethod
    async def expire(self, key: str, seconds: int) -> None:
        """
        Set a timeout on a key.

        After the timeout, the key is automatically deleted.
        Useful for cleanup of sliding window sets.

        Args:
            key: The key to set expiration on.
            seconds: Time-to-live in seconds.

        Example:
            >>> await backend.zadd("sw:user:123", now, str(now))
            >>> await backend.expire("sw:user:123", window_seconds)
        """
        pass
