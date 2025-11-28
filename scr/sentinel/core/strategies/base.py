from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

class RateLimitStatus(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"

@dataclass(frozen=True)
class RateLimitResult:
    status: RateLimitStatus
    limit: int
    remaining: int
    reset_at: float
    retry_after: float | None = None

class RateLimitStrategy(ABC):
    @abstractmethod
    async def check(self, key: str, limit: int, window: int) -> RateLimitResult:
        """Atomically checks if request is allowed."""
        ...