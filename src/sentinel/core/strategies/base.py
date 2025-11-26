"""
Abstract base classes for rate limiting strategies.

This module defines the contract that all rate limiting algorithms must follow.
Using the Strategy Pattern allows swapping algorithms at runtime without
changing the client code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class RateLimitResult(Enum):
    """
    Possible outcomes of a rate limit check.

    ALLOWED: Request is within limits and should proceed.
    DENIED: Request exceeds limits and should be rejected (HTTP 429).
    """

    ALLOWED = "allowed"
    DENIED = "denied"


@dataclass(frozen=True)
class RateLimitResponse:
    """
    Immutable response from a rate limit check.

    This object contains all information needed to:
    1. Decide whether to allow/deny the request
    2. Populate rate limit headers in the HTTP response
    3. Tell the client when they can retry (if denied)

    Attributes:
        result: Whether the request is ALLOWED or DENIED.
        limit: Maximum number of requests allowed in the window.
        remaining: Number of requests remaining in current window.
        reset_at: Unix timestamp when the limit resets.
        retry_after: Seconds until the client can retry (only if denied).

    Example headers this maps to:
        X-RateLimit-Limit: {limit}
        X-RateLimit-Remaining: {remaining}
        X-RateLimit-Reset: {reset_at}
        Retry-After: {retry_after}  (only on 429 responses)
    """

    result: RateLimitResult
    limit: int
    remaining: int
    reset_at: float
    retry_after: float | None = None

    @property
    def is_allowed(self) -> bool:
        """Convenience property to check if request should proceed."""
        return self.result == RateLimitResult.ALLOWED


class RateLimitStrategy(ABC):
    """
    Abstract base class for rate limiting algorithms.

    All rate limiting strategies must implement the `check` and `reset` methods.
    This allows different algorithms (fixed window, sliding window, token bucket, etc.)
    to be used interchangeably.
    """

    @abstractmethod
    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResponse:
        """
        Check if a request should be allowed.

        This method is called for every incoming request that needs
        rate limiting. It must be fast and handle concurrent calls.

        Args:
            key: Unique identifier for the rate limit bucket.
                 Examples: "user:123", "ip:192.168.1.1", "api_key:abc123"
            limit: Maximum number of requests allowed within the window.
            window_seconds: Duration of the time window in seconds.

        Returns:
            RateLimitResponse with the decision and metadata.

        """
        pass

    @abstractmethod
    async def reset(self, key: str) -> None:
        """
        Reset rate limit state for a specific key.


        Args:
            key: The rate limit key to reset.
        """
        pass