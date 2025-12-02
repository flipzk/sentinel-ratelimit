from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from sentinel.core.strategies.base import RateLimitStrategy, RateLimitStatus
from sentinel.core.quota import QuotaManager

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
        # 1. Identify Client
        api_key = request.headers.get("X-API-Key")
        client_id = f"api:{api_key}" if api_key else f"ip:{request.client.host}"
        
        # 2. DYNAMIC STEP: Get quota based on client identity
        # The limit is no longer hardcoded!
        quota = self.quota_manager.get_quota(api_key)
        
        # 3. Check Rate Limit using the dynamic quota
        result = await self.strategy.check(client_id, quota.limit, quota.window)

        headers = {
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(int(result.reset_at)),
            "X-User-Tier": self.quota_manager._resolve_tier(api_key), # Just for debugging
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