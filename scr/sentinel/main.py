from contextlib import asynccontextmanager
from fastapi import FastAPI
from redis.asyncio import from_url

from sentinel.config import settings
from sentinel.api.routes import router
from sentinel.api.middleware import RateLimitMiddleware
from sentinel.core.storage.redis import RedisBackend
from sentinel.core.strategies.token_bucket import TokenBucketStrategy

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize infrastructure
    redis_client = from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    backend = RedisBackend(redis_client)
    
    # Initialize Core Logic
    strategy = TokenBucketStrategy(backend)
    
    # Add Middleware dynamically to inject dependencies
    app.add_middleware(
        RateLimitMiddleware,
        strategy=strategy,
        limit=settings.rate_limit_default,
        window=settings.rate_limit_window
    )
    
    yield
    
    await redis_client.close()

app = FastAPI(lifespan=lifespan)
app.include_router(router)