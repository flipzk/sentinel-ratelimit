from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from sentinel.core.strategies.base import RateLimitStrategy, RateLimitStatus

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, strategy: RateLimitStrategy, limit: int, window: int):
        super().__init__(app)
        self.strategy = strategy
        self.limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next):
        # Identify client (IP or API Key)
        client_id = request.headers.get("X-API-Key") or request.client.host or "anon"
        
        result = await self.strategy.check(client_id, self.limit, self.window)

        headers = {
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(int(result.reset_at)),
        }

        if result.status == RateLimitStatus.DENIED:
            headers["Retry-After"] = str(int(result.retry_after or 1))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded", 
                    "retry_after": result.retry_after
                },
                headers=headers
            )

        response = await call_next(request)
        
        # Inject headers into response
        for k, v in headers.items():
            response.headers[k] = v
            
        return response