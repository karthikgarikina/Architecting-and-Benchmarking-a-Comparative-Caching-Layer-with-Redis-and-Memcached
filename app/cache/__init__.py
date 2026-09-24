import logging
from typing import Optional
from fastapi import Header
from app.config import settings
from app.cache.base import BaseCacheBackend
from app.cache.redis_backend import RedisCacheBackend
from app.cache.memcached_backend import MemcachedCacheBackend

logger = logging.getLogger("cache_factory")

redis_backend = RedisCacheBackend(settings.REDIS_URL)
memcached_backend = MemcachedCacheBackend(settings.MEMCACHED_URL)

async def init_cache_backends():
    await redis_backend.connect()
    await memcached_backend.connect()

async def close_cache_backends():
    await redis_backend.disconnect()
    await memcached_backend.disconnect()

def get_cache_backend(
    x_cache_backend: Optional[str] = Header(None, alias="X-Cache-Backend")
) -> BaseCacheBackend:
    """
    Selects cache backend according to X-Cache-Backend header.
    Defaults to settings.DEFAULT_CACHE_BACKEND if header is omitted.
    """
    backend_choice = (x_cache_backend or settings.DEFAULT_CACHE_BACKEND).lower().strip()
    if backend_choice == "memcached":
        return memcached_backend
    return redis_backend

def get_backend_name(
    x_cache_backend: Optional[str] = Header(None, alias="X-Cache-Backend")
) -> str:
    backend_choice = (x_cache_backend or settings.DEFAULT_CACHE_BACKEND).lower().strip()
    if backend_choice == "memcached":
        return "memcached"
    return "redis"
