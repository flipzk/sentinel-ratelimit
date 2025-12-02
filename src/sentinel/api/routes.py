from fastapi import APIRouter, Request
from pydantic import BaseModel
from sentinel.config import settings

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    strategy: str

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
        "docs": "/docs"
    }

@router.get("/test")
async def test_endpoint(request: Request):
    """
    Protected endpoint to test token consumption.
    Check response headers for rate limit status.
    """
    return {
        "message": "Request allowed",
        "headers": {
            "limit": request.headers.get("X-RateLimit-Limit"),
            "remaining": request.headers.get("X-RateLimit-Remaining"),
            "reset": request.headers.get("X-RateLimit-Reset"),
        }
    }