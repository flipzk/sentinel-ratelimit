from fastapi import APIRouter, Request
from pydantic import BaseModel

from sentinel.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    strategy: str


class RateLimitInfo(BaseModel):
    limit: int
    remaining: int
    reset_at: int


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        strategy=settings.rate_limit_strategy.value,
    )


@router.get("/")
async def root():
    return {
        "service": settings.app_name,
        "message": "Rate limiting service is running",
    }


@router.get("/test")
async def test_endpoint(request: Request):
    return {
        "message": "Request allowed",
        "client": request.headers.get("X-API-Key", request.client.host),
        "rate_limit": {
            "limit": request.headers.get("X-RateLimit-Limit"),
            "remaining": request.headers.get("X-RateLimit-Remaining"),
        },
    }
