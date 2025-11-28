"""
In-memory storage backend for testing and development.

This backend stores all data in Python dictionaries, making it:
- Fast: No network calls, no serialization
- Simple: No external dependencies
- Isolated: Each instance is independent

WARNING: Not suitable for production!
- No persistence (data lost on restart)
- No distribution (single process only)
- No concurrent process support

Use RedisBackend for production deployments.
"""

import time
from typing import Any

from sentinel.core.backends.base import StorageBackend


class InMemoryBackend(StorageBackend):
    """
    In-memory implementation of StorageBackend.

    Stores data in dictionaries with manual TTL checking.
    Designed for unit tests and local development only.

    Features:
    - Full StorageBackend interface support
    - TTL expiration (checked on access)
    - Sorted set operations via list + sort

    Example:
        >>> backend = InMemoryBackend()
        >>> await backend.set("key", {"value": 42}, ttl=60)
        >>> data = await backend.get("key")
        >>> print(data)  # {"value": 42}

    Thread Safety:
        This implementation is NOT thread-safe. For concurrent
        testing, use separate instances or add locking.
    """

    def __init__(self) -> None:
        """Initialize empty storage containers."""
        # Key-value storage: key -> value dict
        self._data: dict[str, dict[str, Any]] = {}

        # Sorted sets: key -> list of (score, member) tuples
        self._sorted_sets: dict[str, list[tuple[float, str]]] = {}

        # Expiration times: key -> unix timestamp when key expires
        self._expiry: dict[str, float] = {}

    def _is_expired(self, key: str) -> bool:
        """
        Check if a key has expired.

        Args:
            key: The key to check.

        Returns:
            True if key exists in expiry dict and current time > expiry time.
        """
        if key in self._expiry:
            return time.time() > self._expiry[key]
        return False

    def _cleanup_if_expired(self, key: str) -> bool:
        """
        Remove key if expired.

        Args:
            key: The key to check and potentially remove.

        Returns:
            True if key was expired and removed, False otherwise.
        """
        if self._is_expired(key):
            self._data.pop(key, None)
            self._sorted_sets.pop(key, None)
            self._expiry.pop(key, None)
            return True
        return False

    # =========================================================================
    # Key-Value Operations
    # =========================================================================

    async def get(self, key: str) -> dict[str, Any] | None:
        """
        Retrieve a value by key.

        Checks expiration before returning. If expired, returns None
        and cleans up the key.

        Args:
            key: The key to retrieve.

        Returns:
            The stored dictionary, or None if not found/expired.
        """
        if self._cleanup_if_expired(key):
            return None

        return self._data.get(key)

    async def set(
        self,
        key: str,
        value: dict[str, Any],
        ttl: int,
    ) -> None:
        """
        Store a value with TTL.

        Args:
            key: The key to store under.
            value: Dictionary to store.
            ttl: Seconds until expiration.
        """
        self._data[key] = value
        self._expiry[key] = time.time() + ttl

    async def delete(self, key: str) -> None:
        """
        Delete a key from all storage containers.

        Args:
            key: The key to delete.
        """
        self._data.pop(key, None)
        self._sorted_sets.pop(key, None)
        self._expiry.pop(key, None)

    # =========================================================================
    # Sorted Set Operations
    # =========================================================================

    async def zadd(self, key: str, score: float, member: str) -> None:
        """
        Add member to sorted set with score.

        If member exists, updates its score. Maintains sorted order.

        Args:
            key: The sorted set key.
            score: Numeric score (usually timestamp).
            member: The member string.
        """
        if self._cleanup_if_expired(key):
            pass  # Key was expired, will create fresh

        if key not in self._sorted_sets:
            self._sorted_sets[key] = []

        # Remove existing member if present (to update score)
        self._sorted_sets[key] = [
            (s, m) for s, m in self._sorted_sets[key] if m != member
        ]

        # Add with new score
        self._sorted_sets[key].append((score, member))

        # Keep sorted by score (ascending)
        self._sorted_sets[key].sort(key=lambda x: x[0])

    async def zremrangebyscore(
        self,
        key: str,
        min_score: float,
        max_score: float,
    ) -> int:
        """
        Remove members with scores between min and max (inclusive).

        Args:
            key: The sorted set key.
            min_score: Minimum score to remove.
            max_score: Maximum score to remove.

        Returns:
            Number of members removed.
        """
        if self._cleanup_if_expired(key):
            return 0

        if key not in self._sorted_sets:
            return 0

        original_count = len(self._sorted_sets[key])

        # Keep only members outside the removal range
        self._sorted_sets[key] = [
            (score, member)
            for score, member in self._sorted_sets[key]
            if not (min_score <= score <= max_score)
        ]

        removed_count = original_count - len(self._sorted_sets[key])
        return removed_count

    async def zcard(self, key: str) -> int:
        """
        Count members in sorted set.

        Args:
            key: The sorted set key.

        Returns:
            Number of members, or 0 if key doesn't exist.
        """
        if self._cleanup_if_expired(key):
            return 0

        return len(self._sorted_sets.get(key, []))

    async def zrange(
        self,
        key: str,
        start: int,
        stop: int,
    ) -> list[str]:
        """
        Get members by index range.

        Follows Redis convention: stop is inclusive.

        Args:
            key: The sorted set key.
            start: Start index (0-based).
            stop: Stop index (inclusive, -1 for last).

        Returns:
            List of member strings in the range.
        """
        if self._cleanup_if_expired(key):
            return []

        items = self._sorted_sets.get(key, [])

        if not items:
            return []

        # Handle negative indices like Redis
        length = len(items)
        if start < 0:
            start = max(0, length + start)
        if stop < 0:
            stop = length + stop

        # Redis stop is inclusive, Python slice is exclusive
        # So we add 1 to stop
        end = stop + 1

        # Extract just the members (not scores)
        return [member for _, member in items[start:end]]

    async def expire(self, key: str, seconds: int) -> None:
        """
        Set expiration time on a key.

        Works for both key-value and sorted set keys.

        Args:
            key: The key to set expiration on.
            seconds: Seconds until expiration.
        """
        # Only set expiry if key exists
        if key in self._data or key in self._sorted_sets:
            self._expiry[key] = time.time() + seconds

    # =========================================================================
    # Utility Methods (not part of interface, useful for testing)
    # =========================================================================

    def clear(self) -> None:
        """
        Clear all stored data.

        Useful for resetting state between tests.
        """
        self._data.clear()
        self._sorted_sets.clear()
        self._expiry.clear()

    def keys(self) -> list[str]:
        """
        Get all non-expired keys.

        Returns:
            List of all valid keys across both storage types.
        """
        all_keys = set(self._data.keys()) | set(self._sorted_sets.keys())
        return [k for k in all_keys if not self._is_expired(k)]
