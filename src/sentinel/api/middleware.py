from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

from sentinel.core.strategies.base import RateLimitStrategy, RateLimitResult


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, strategy: RateLimitStrategy, limit: int, window: int):
        super().__init__(app)
        self.strategy = strategy
        self.limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next) -> Response:
        client_key = self._get_client_key(request)
        result = await self.strategy.check(client_key, self.limit, self.window)

        headers = {
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(int(result.reset_at)),
        }

        if result.result == RateLimitResult.DENIED:
            headers["Retry-After"] = str(int(result.retry_after or 1))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests",
                    "retry_after": result.retry_after,
                },
                headers=headers,
            )

        response = await call_next(request)
        for key, value in headers.items():
            response.headers[key] = value

        return response

    def _get_client_key(self, request: Request) -> str:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"api:{api_key}"

        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        return f"ip:{client_ip}"