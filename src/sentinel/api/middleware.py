from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from sentinel.core.strategies.base import RateLimitStrategy, RateLimitStatus

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Global middleware that intercepts requests to enforce rate limits.
    It injects standard X-RateLimit-* headers into responses.
    """
    
    def __init__(self, app, strategy: RateLimitStrategy, limit: int, window: int):
        super().__init__(app)
        self.strategy = strategy
        self.limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 1. Identify Client (Priority: API Key > Forwarded Header > IP)
        client_key = self._get_client_key(request)
        
        # 2. Check Limit (Atomic operation via Strategy)
        result = await self.strategy.check(client_key, self.limit, self.window)

        # 3. Prepare Standard Headers (RFC 6585)
        headers = {
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(int(result.reset_at)),
        }

        # 4. Deny Logic
        if result.status == RateLimitStatus.DENIED:
            headers["Retry-After"] = str(int(result.retry_after or 1))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please slow down.",
                    "retry_after": result.retry_after,
                },
                headers=headers,
            )

        # 5. Allow Logic (Process Request)
        response = await call_next(request)
        
        # 6. Inject Headers into Success Response
        for key, value in headers.items():
            response.headers[key] = value

        return response

    def _get_client_key(self, request: Request) -> str:
        """Extracts unique client identifier."""
        if api_key := request.headers.get("X-API-Key"):
            return f"api:{api_key}"
        
        # Support for load balancers/proxies
        if forwarded := request.headers.get("X-Forwarded-For"):
            return f"ip:{forwarded.split(',')[0]}"
            
        return f"ip:{request.client.host if request.client else 'unknown'}"