import json
import logging
from typing import Optional, Dict, Any, List, Tuple
import redis.asyncio as aioredis
from app.cache.base import BaseCacheBackend
from app.config import settings

logger = logging.getLogger("redis_backend")

# Lua script for atomic Rate Limiting (INCR + EXPIRE in one round-trip)
RATE_LIMIT_LUA = """
local current = redis.call('INCR', KEYS[1])
if tonumber(current) == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

class RedisCacheBackend(BaseCacheBackend):
    def __init__(self, url: str = settings.REDIS_URL):
        self.url = url
        self.client: Optional[aioredis.Redis] = None
        self._rate_limit_script = None

    async def connect(self):
        if self.client is None:
            self.client = aioredis.from_url(
                self.url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
            )
            self._rate_limit_script = self.client.register_script(RATE_LIMIT_LUA)
            logger.info("Connected to Redis at %s", self.url)

    async def disconnect(self):
        if self.client:
            await self.client.aclose()
            self.client = None

    async def _ensure_client(self) -> aioredis.Redis:
        if self.client is None:
            await self.connect()
        return self.client

    # 1. Product Metadata Caching
    async def get_product(self, product_id: int) -> Optional[Dict[str, Any]]:
        client = await self._ensure_client()
        key = f"product:{product_id}"
        val = await client.get(key)
        if val:
            return json.loads(val)
        return None

    async def set_product(self, product_id: int, data: Dict[str, Any], ttl: int = settings.PRODUCT_CACHE_TTL) -> bool:
        client = await self._ensure_client()
        key = f"product:{product_id}"
        await client.set(key, json.dumps(data), ex=ttl)
        return True

    # Invalidation with PUBLISH
    async def invalidate_product(self, product_id: int) -> bool:
        client = await self._ensure_client()
        key = f"product:{product_id}"
        await client.delete(key)
        # Core requirement: Redis uses PUBLISH to notify other application instances
        await client.publish("product_invalidation", json.dumps({"product_id": product_id, "action": "invalidate"}))
        return True

    # 2. Leaderboard with ZINCRBY and ZREVRANGE
    async def increment_product_view(self, product_id: int, use_lock: bool = True) -> int:
        client = await self._ensure_client()
        key = "leaderboard:views"
        # Core requirement: Use ZINCRBY to update view counts atomically
        new_score = await client.zincrby(key, 1, str(product_id))
        return int(new_score)

    async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        client = await self._ensure_client()
        key = "leaderboard:views"
        # Core requirement: Use ZREVRANGE with WITHSCORES to retrieve the top 10
        raw_items = await client.zrevrange(key, 0, limit - 1, withscores=True)
        results = []
        for pid, score in raw_items:
            results.append({"product_id": int(pid), "views": int(score)})
        return results

    # 3. Distributed Rate Limiting using Lua script (atomic INCR + EXPIRE)
    async def check_rate_limit(self, user_id: str, limit: int = 100, window: int = 60) -> Tuple[bool, int]:
        client = await self._ensure_client()
        key = f"ratelimit:{user_id}"
        if self._rate_limit_script is None:
            self._rate_limit_script = client.register_script(RATE_LIMIT_LUA)
        current = await self._rate_limit_script(keys=[key], args=[window])
        current_count = int(current)
        is_allowed = current_count <= limit
        return is_allowed, current_count

    # 4. Session Storage using Redis Hashes (HSET/HGETALL)
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        client = await self._ensure_client()
        key = f"session:{session_id}"
        data = await client.hgetall(key)
        if not data:
            return None
        # Parse nested json fields if any
        if "cart_count" in data:
            data["cart_count"] = int(data["cart_count"])
        if "preferences" in data and isinstance(data["preferences"], str):
            try:
                data["preferences"] = json.loads(data["preferences"])
            except Exception:
                pass
        return data

    async def set_session(self, session_id: str, data: Dict[str, Any], ttl: int = settings.SESSION_CACHE_TTL) -> bool:
        client = await self._ensure_client()
        key = f"session:{session_id}"
        # Flatten dictionary for HSET
        flat = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                flat[k] = json.dumps(v)
            else:
                flat[k] = str(v)
        async with client.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            pipe.hset(key, mapping=flat)
            pipe.expire(key, ttl)
            await pipe.execute()
        return True

    async def update_session_field(self, session_id: str, field: str, value: Any) -> bool:
        client = await self._ensure_client()
        key = f"session:{session_id}"
        val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        # Update only this single field in Redis Hash!
        await client.hset(key, field, val_str)
        return True

    async def health_check(self) -> bool:
        try:
            client = await self._ensure_client()
            return await client.ping()
        except Exception as e:
            logger.error("Redis health check failed: %s", e)
            return False
