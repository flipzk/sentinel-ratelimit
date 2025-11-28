from fastapi import FastAPI

from sentinel.api.middleware import RateLimitMiddleware
from sentinel.api.routes import router
from sentinel.config import StrategyType, settings
from sentinel.core.backends.memory import InMemoryBackend
from sentinel.core.strategies.sliding_window import SlidingWindowStrategy
from sentinel.core.strategies.token_bucket import TokenBucketStrategy


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Adaptive rate limiting for APIs",
        version="0.1.0",
    )

    backend = InMemoryBackend()

    if settings.rate_limit_strategy == StrategyType.TOKEN_BUCKET:
        strategy = TokenBucketStrategy(backend)
    else:
        strategy = SlidingWindowStrategy(backend)

    app.add_middleware(
        RateLimitMiddleware,
        strategy=strategy,
        limit=settings.rate_limit_default,
        window=settings.rate_limit_window,
    )

    app.include_router(router)

    return app


app = create_app()
