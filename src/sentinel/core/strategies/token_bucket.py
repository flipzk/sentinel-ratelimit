import time
from sentinel.core.storage.redis import RedisBackend
from sentinel.core.strategies.base import RateLimitStrategy, RateLimitResult, RateLimitStatus

class TokenBucketStrategy(RateLimitStrategy):
    """
    Lazy Token Bucket implementation using Lua for atomicity.
    Tokens are refilled only when the key is accessed.
    """

    _LUA_SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local window = tonumber(ARGV[4])

    -- Fetch current state
    local data = redis.call("hmget", key, "tokens", "last_refill")
    local tokens = tonumber(data[1])
    local last_refill = tonumber(data[2])

    -- Initialize if missing
    if tokens == nil then
        tokens = capacity
        last_refill = now
    else
        -- Lazy refill: calculate tokens gained since last visit
        local delta = math.max(0, now - last_refill)
        local refill = delta * rate
        tokens = math.min(capacity, tokens + refill)
        last_refill = now
    end

    local allowed = 0
    if tokens >= 1.0 then
        allowed = 1
        tokens = tokens - 1.0
    end

    -- Update state
    redis.call("hmset", key, "tokens", tokens, "last_refill", last_refill)
    redis.call("expire", key, window * 2) 

    return {allowed, tokens}
    """

    def __init__(self, backend: RedisBackend):
        self.backend = backend

    async def check(self, key: str, limit: int, window: int) -> RateLimitResult:
        now = time.time()
        rate = limit / window
        redis_key = f"sentinel:tb:{key}"

        # Atomic execution
        # Returns: [is_allowed (1/0), remaining_tokens (float)]
        result = await self.backend.eval_script(
            self._LUA_SCRIPT,
            keys=[redis_key],
            args=[limit, rate, now, window]
        )

        is_allowed = bool(result[0])
        remaining = max(0, int(result[1]))
        
        # Calculate Retry-After if denied
        retry_after = None
        if not is_allowed:
            tokens_needed = 1.0 - float(result[1])
            retry_after = tokens_needed / rate

        return RateLimitResult(
            status=RateLimitStatus.ALLOWED if is_allowed else RateLimitStatus.DENIED,
            limit=limit,
            remaining=remaining,
            reset_at=now + window, 
            retry_after=retry_after
        )