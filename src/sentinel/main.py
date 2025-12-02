from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from redis.asyncio import from_url

from sentinel.config import settings
from sentinel.api.middleware import RateLimitMiddleware
from sentinel.api.routes import router
from sentinel.core.storage.redis import RedisBackend
from sentinel.core.strategies.token_bucket import TokenBucketStrategy
from sentinel.core.quota import QuotaManager 

resources = {}

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # 1. Redis Connection
    redis_client = from_url(
        settings.redis_url, 
        encoding="utf-8", 
        decode_responses=True
    )
    
    # 2. Initialize Core Components
    backend = RedisBackend(redis_client)
    strategy = TokenBucketStrategy(backend)
    quota_manager = QuotaManager() 
    
    resources["redis"] = redis_client
    
    # 3. Inject Middleware
    app.add_middleware(
        RateLimitMiddleware,
        strategy=strategy,
        quota_manager=quota_manager
    )
    
    print(f"🚀 Sentinel started. Strategy: {settings.rate_limit_strategy}")
    yield
    
    # 4. Cleanup
    await redis_client.close()
    print(" Sentinel stopped")

app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan
)

app.include_router(router)