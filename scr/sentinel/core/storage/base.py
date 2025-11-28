import json
from typing import Any
from redis.asyncio import Redis
from sentinel.core.storage.base import StorageBackend

class RedisBackend(StorageBackend):
    def __init__(self, redis: Redis):
        self._redis = redis

    async def get(self, key: str) -> dict[str, Any] | None:
        val = await self._redis.get(key)
        return json.loads(val) if val else None

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        async with self._redis.pipeline() as pipe:
            await pipe.set(key, json.dumps(value))
            await pipe.expire(key, ttl)
            await pipe.execute()

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    # Required for Sliding Window (implementing interface contract)
    async def zadd(self, key: str, score: float, member: str) -> None:
        await self._redis.zadd(key, {member: score})

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        return await self._redis.zremrangebyscore(key, min_score, max_score)

    async def zcard(self, key: str) -> int:
        return await self._redis.zcard(key)

    async def zrange(self, key: str, start: int, stop: int) -> list[str]:
        return [
            m.decode() if isinstance(m, bytes) else m 
            for m in await self._redis.zrange(key, start, stop)
        ]

    async def expire(self, key: str, seconds: int) -> None:
        await self._redis.expire(key, seconds)

    # Helper for atomic Lua execution
    async def eval_script(self, script: str, keys: list[str], args: list[str | int | float]):
        return await self._redis.eval(script, len(keys), *keys, *args)