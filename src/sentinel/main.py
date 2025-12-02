from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from redis.asyncio import from_url

from sentinel.config import settings, StrategyType # <--- Import Enum
from sentinel.api.middleware import RateLimitMiddleware
from sentinel.api.routes import router
from sentinel.core.storage.redis import RedisBackend
from sentinel.core.strategies.token_bucket import TokenBucketStrategy
from sentinel.core.strategies.sliding_window import SlidingWindowStrategy
from sentinel.core.quota import QuotaManager 

resources = {}

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    
    redis_client = from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    backend = RedisBackend(redis_client)
    quota_manager = QuotaManager() 
    
    if settings.rate_limit_strategy == StrategyType.SLIDING_WINDOW:
        strategy = SlidingWindowStrategy(backend)
        print(" Logic: Sliding Window Log (Precise)")
    else:
        strategy = TokenBucketStrategy(backend)
        print(" Logic: Token Bucket (Efficient)")
    
    resources["redis"] = redis_client
    
    app.add_middleware(
        RateLimitMiddleware,
        strategy=strategy,
        quota_manager=quota_manager
    )
    
    yield
    
    await redis_client.close()

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)