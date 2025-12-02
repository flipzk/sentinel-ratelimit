from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
import structlog

from sentinel.core.strategies.base import RateLimitStrategy, RateLimitStatus
from sentinel.core.quota import QuotaManager

logger = structlog.get_logger()

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, 
        app, 
        strategy: RateLimitStrategy, 
        quota_manager: QuotaManager
    ):
        super().__init__(app)
        self.strategy = strategy
        self.quota_manager = quota_manager

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        api_key = request.headers.get("X-API-Key")
        client_ip = request.client.host if request.client else "unknown"
        client_id = f"api:{api_key}" if api_key else f"ip:{client_ip}"
        
        # Contextual Logging
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            client_id=client_id,
            path=request.url.path,
            method=request.method
        )

        quota = self.quota_manager.get_quota(api_key)
        result = await self.strategy.check(client_id, quota.limit, quota.window)

        logger.info(
            "rate_limit_check",
            status=result.status,
            remaining=result.remaining,
            limit=quota.limit,
            tier=self.quota_manager._resolve_tier(api_key)
        )

        headers = {
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(int(result.reset_at)),
            "X-User-Tier": self.quota_manager._resolve_tier(api_key),
        }

        if result.status == RateLimitStatus.DENIED:
            headers["Retry-After"] = str(int(result.retry_after or 1))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Quota exceeded",
                    "tier": headers["X-User-Tier"],
                    "retry_after": result.retry_after,
                },
                headers=headers,
            )

        response = await call_next(request)
        
        for key, value in headers.items():
            response.headers[key] = value

        return response