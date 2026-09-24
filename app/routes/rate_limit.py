from fastapi import APIRouter, Depends, Header, HTTPException, Response
from typing import Optional
from app.cache import get_cache_backend, get_backend_name
from app.cache.base import BaseCacheBackend
from app.config import settings

router = APIRouter(tags=["Rate Limit"])

@router.get("/rate-limit-test")
async def rate_limit_endpoint(
    response: Response,
    x_user_id: Optional[str] = Header("anonymous-user", alias="X-User-ID"),
    cache: BaseCacheBackend = Depends(get_cache_backend),
    backend_name: str = Depends(get_backend_name),
):
    """
    Direct test endpoint for distributed rate limiter.
    Limits to 100 req/min per user ID.
    Returns HTTP 200 for requests 1-100, and HTTP 429 for subsequent requests.
    """
    response.headers["X-Cache-Backend"] = backend_name
    allowed, current = await cache.check_rate_limit(
        user_id=x_user_id,
        limit=settings.RATE_LIMIT_MAX_REQUESTS,
        window=settings.RATE_LIMIT_WINDOW_SECONDS
    )
    response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_MAX_REQUESTS)
    response.headers["X-RateLimit-Remaining"] = str(max(0, settings.RATE_LIMIT_MAX_REQUESTS - current))
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {settings.RATE_LIMIT_MAX_REQUESTS} requests per minute.",
            headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)}
        )
    
    return {
        "status": "ok",
        "user_id": x_user_id,
        "request_count": current,
        "backend": backend_name
    }
