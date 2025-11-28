from abc import ABC, abstractmethod
from typing import Any

class StorageBackend(ABC):
    @abstractmethod
    async def get(self, key: str) -> dict[str, Any] | None:
        pass

    @abstractmethod
    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        pass

    @abstractmethod
    async def zadd(self, key: str, score: float, member: str) -> None:
        pass

    @abstractmethod
    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        pass

    @abstractmethod
    async def zcard(self, key: str) -> int:
        pass

    @abstractmethod
    async def zrange(self, key: str, start: int, stop: int) -> list[str]:
        pass

    @abstractmethod
    async def expire(self, key: str, seconds: int) -> None:
        pass