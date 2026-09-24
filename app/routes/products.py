from fastapi import APIRouter, Depends, HTTPException, Response, Header
from typing import Optional
from app.models import Product, ProductUpdate
from app.database import get_product_by_id, update_product_by_id
from app.cache import get_cache_backend, get_backend_name
from app.cache.base import BaseCacheBackend

router = APIRouter(prefix="/products", tags=["Products"])

@router.get("/{product_id}", response_model=Product)
async def get_product(
    product_id: int,
    response: Response,
    cache: BaseCacheBackend = Depends(get_cache_backend),
    backend_name: str = Depends(get_backend_name),
):
    """
    Get product by ID.
    Checks active cache backend first (Redis or Memcached).
    On miss, retrieves from PostgreSQL, populates cache with 300s TTL, and returns.
    """
    response.headers["X-Cache-Backend"] = backend_name
    cached = await cache.get_product(product_id)
    if cached:
        response.headers["X-Cache"] = "HIT"
        return cached

    # Cache Miss: Fetch from DB
    product = await get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    response.headers["X-Cache"] = "MISS"
    await cache.set_product(product_id, product, ttl=300)
    return product

@router.post("/{product_id}", response_model=Product)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    response: Response,
    cache: BaseCacheBackend = Depends(get_cache_backend),
    backend_name: str = Depends(get_backend_name),
):
    """
    Update product by ID.
    Updates DB record, then invalidates cache (Pub/Sub for Redis, Cache Versioning for Memcached).
    """
    response.headers["X-Cache-Backend"] = backend_name
    updates = payload.model_dump(exclude_unset=True)
    updated = await update_product_by_id(product_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Product not found")

    # Invalidate cache
    await cache.invalidate_product(product_id)
    response.headers["X-Cache-Invalidated"] = "true"
    return updated
