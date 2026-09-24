from fastapi import APIRouter, Depends, Query, Response
from typing import Optional, List
from app.models import LeaderboardResponse, LeaderboardItem
from app.cache import get_cache_backend, get_backend_name
from app.cache.base import BaseCacheBackend

router = APIRouter(tags=["Leaderboard"])

@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    response: Response,
    limit: int = Query(10, ge=1, le=100),
    cache: BaseCacheBackend = Depends(get_cache_backend),
    backend_name: str = Depends(get_backend_name),
):
    """
    Returns the top viewed products.
    Redis: Uses ZREVRANGE with WITHSCORES.
    Memcached: Deserializes leaderboard array, sorts, returns top items.
    """
    response.headers["X-Cache-Backend"] = backend_name
    items = await cache.get_leaderboard(limit=limit)
    return LeaderboardResponse(
        backend=backend_name,
        top_products=[LeaderboardItem(**item) for item in items]
    )

@router.get("/products/{product_id}/views")
async def get_product_views(
    product_id: int,
    response: Response,
    cache: BaseCacheBackend = Depends(get_cache_backend),
    backend_name: str = Depends(get_backend_name),
):
    """
    Get exact view count for a specific product.
    """
    response.headers["X-Cache-Backend"] = backend_name
    views = await cache.get_product_views(product_id)
    return {
        "product_id": product_id,
        "views": views,
        "backend": backend_name
    }

@router.post("/leaderboard/reset")
async def reset_leaderboard(
    response: Response,
    cache: BaseCacheBackend = Depends(get_cache_backend),
    backend_name: str = Depends(get_backend_name),
):
    """
    Reset leaderboard data for testing and benchmarks.
    """
    response.headers["X-Cache-Backend"] = backend_name
    await cache.reset_leaderboard()
    return {"status": "reset", "backend": backend_name}

@router.post("/products/{product_id}/view")
async def increment_product_view(
    product_id: int,
    response: Response,
    no_lock: bool = Query(False, description="Disable distributed lock for Memcached race experiment"),
    cache: BaseCacheBackend = Depends(get_cache_backend),
    backend_name: str = Depends(get_backend_name),
):
    """
    Increments view count for a product on the leaderboard.
    Redis: Uses atomic ZINCRBY.
    Memcached: Uses distributed lock with `add` (or skips lock if no_lock=True).
    """
    response.headers["X-Cache-Backend"] = backend_name
    use_lock = not no_lock
    new_views = await cache.increment_product_view(product_id, use_lock=use_lock)
    return {
        "product_id": product_id,
        "views": new_views,
        "backend": backend_name,
        "lock_used": use_lock
    }
