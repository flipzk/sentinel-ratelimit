import time
from sentinel.core.storage.redis import RedisBackend
from sentinel.core.strategies.base import RateLimitStrategy, RateLimitResult, RateLimitStatus

class SlidingWindowStrategy(RateLimitStrategy):
    """
    Sliding Window Log algorithm.
    Precise but more expensive than Token Bucket (stores one entry per request).
    Uses Redis ZSET to track timestamps of recent requests.
    """

    # LUA SCRIPT LOGIC:
    # 1. Remove timestamps older than (now - window)
    # 2. Count remaining timestamps (current usage)
    # 3. If count < limit: Add current timestamp, Allow.
    # 4. Else: Deny.
    _LUA_SCRIPT = """
    local key = KEYS[1]
    local limit = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    
    local window_start = now - window

    -- 1. Cleanup old requests
    redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

    -- 2. Check current usage
    local current_count = redis.call('ZCARD', key)

    if current_count < limit then
        -- 3. Allow: Add unique member (timestamp + microsecond to avoid collision)
        redis.call('ZADD', key, now, now) 
        redis.call('EXPIRE', key, window)
        return {1, limit - (current_count + 1)}
    end

    -- 4. Deny
    return {0, 0}
    """

    def __init__(self, backend: RedisBackend):
        self.backend = backend

    async def check(self, key: str, limit: int, window: int) -> RateLimitResult:
        now = time.time()
        redis_key = f"sentinel:sw:{key}"

        # Atomic execution via Lua
        result = await self.backend.eval_script(
            self._LUA_SCRIPT,
            keys=[redis_key],
            args=[limit, window, now]
        )

        is_allowed = bool(result[0])
        remaining = int(result[1])

        return RateLimitResult(
            status=RateLimitStatus.ALLOWED if is_allowed else RateLimitStatus.DENIED,
            limit=limit,
            remaining=remaining,
            reset_at=now + window, # Approximate reset
            retry_after=None # Complex to calc precisely in SW, defaulting to None
        )