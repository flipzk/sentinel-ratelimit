from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from redis.asyncio import from_url

from sentinel.config import settings
from sentinel.api.middleware import RateLimitMiddleware
from sentinel.api.routes import router
from sentinel.core.storage.redis import RedisBackend
from sentinel.core.strategies.token_bucket import TokenBucketStrategy

# Global resource container for cleanup
resources = {}

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle manager.
    Handles Redis connection startup and graceful shutdown.
    """
    # 1. Initialize Infrastructure
    redis_client = from_url(
        settings.redis_url, 
        encoding="utf-8", 
        decode_responses=True
    )
    
    # 2. Initialize Core Logic (Dependency Injection)
    backend = RedisBackend(redis_client)
    strategy = TokenBucketStrategy(backend)
    
    # Store reference to close later
    resources["redis"] = redis_client
    
    # 3. Inject Middleware
    # We add it here to ensure 'strategy' is fully initialized
    app.add_middleware(
        RateLimitMiddleware,
        strategy=strategy,
        limit=settings.rate_limit_default,
        window=settings.rate_limit_window
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