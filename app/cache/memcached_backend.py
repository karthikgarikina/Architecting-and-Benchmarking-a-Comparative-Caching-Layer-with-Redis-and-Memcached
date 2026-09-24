import asyncio
import json
import logging
import random
import time
from typing import Optional, Dict, Any, List, Tuple
import aiomcache
from app.cache.base import BaseCacheBackend
from app.config import settings

logger = logging.getLogger("memcached_backend")

class MemcachedCacheBackend(BaseCacheBackend):
    def __init__(self, url: str = settings.MEMCACHED_URL):
        # Format is host:port
        self.url = url
        if "://" in url:
            url = url.split("://")[-1]
        if ":" in url:
            parts = url.split(":")
            self.host = parts[0]
            self.port = int(parts[1])
        else:
            self.host = url
            self.port = 11211
        self.client: Optional[aiomcache.Client] = None

    async def connect(self):
        if self.client is None:
            self.client = aiomcache.Client(self.host, self.port)
            logger.info("Connected to Memcached at %s:%d", self.host, self.port)

    async def disconnect(self):
        if self.client:
            await self.client.close()
            self.client = None

    async def _ensure_client(self) -> aiomcache.Client:
        if self.client is None:
            await self.connect()
        return self.client

    # Versioning helper for Memcached Cache Invalidation
    async def get_current_version(self) -> int:
        client = await self._ensure_client()
        val = await client.get(b"global_product_version")
        if val is None:
            # Initialize version to 1
            await client.add(b"global_product_version", b"1")
            return 1
        try:
            return int(val.decode("utf-8"))
        except Exception:
            return 1

    # 1. Product Metadata Caching with Cache Versioning
    async def get_product(self, product_id: int) -> Optional[Dict[str, Any]]:
        client = await self._ensure_client()
        version = await self.get_current_version()
        key = f"v{version}:product:{product_id}".encode("utf-8")
        raw = await client.get(key)
        if raw:
            return json.loads(raw.decode("utf-8"))
        return None

    async def set_product(self, product_id: int, data: Dict[str, Any], ttl: int = settings.PRODUCT_CACHE_TTL) -> bool:
        client = await self._ensure_client()
        version = await self.get_current_version()
        key = f"v{version}:product:{product_id}".encode("utf-8")
        val = json.dumps(data).encode("utf-8")
        return await client.set(key, val, exptime=ttl)

    # Invalidation using generational Cache Versioning
    async def invalidate_product(self, product_id: int) -> bool:
        client = await self._ensure_client()
        # Invalidate specific product key if exists
        version = await self.get_current_version()
        key = f"v{version}:product:{product_id}".encode("utf-8")
        await client.delete(key)
        # Core requirement: Increment global version key to invalidate all current keys by prefix
        try:
            new_ver = await client.incr(b"global_product_version", 1)
            if new_ver is None:
                await client.set(b"global_product_version", b"2")
        except Exception:
            await client.set(b"global_product_version", str(version + 1).encode("utf-8"))
        return True

    # 2. Leaderboard: Serialized List with Distributed Lock (via `add`)
    async def acquire_lock(self, lock_key: str, ttl: int = 5, max_retries: int = 50, initial_delay: float = 0.01) -> bool:
        client = await self._ensure_client()
        key = lock_key.encode("utf-8")
        delay = initial_delay
        for _ in range(max_retries):
            # Memcached 'add' acts as atomic 'Set if Not Exists'
            acquired = await client.add(key, b"locked", exptime=ttl)
            if acquired:
                return True
            # Exponential backoff with jitter
            await asyncio.sleep(delay + random.uniform(0.001, 0.005))
            delay = min(delay * 1.5, 0.2)
        return False

    async def release_lock(self, lock_key: str):
        client = await self._ensure_client()
        try:
            await client.delete(lock_key.encode("utf-8"))
        except Exception:
            pass

    async def increment_product_view(self, product_id: int, use_lock: bool = True) -> int:
        client = await self._ensure_client()
        lb_key = b"leaderboard:views"
        lock_name = "lock:leaderboard:views"

        if use_lock:
            # Safely update using distributed lock
            locked = await self.acquire_lock(lock_name)
            if not locked:
                raise TimeoutError("Could not acquire Memcached distributed lock for leaderboard")
            try:
                raw = await client.get(lb_key)
                board: Dict[str, int] = {}
                if raw:
                    try:
                        board = json.loads(raw.decode("utf-8"))
                    except Exception:
                        board = {}
                current = board.get(str(product_id), 0) + 1
                board[str(product_id)] = current
                await client.set(lb_key, json.dumps(board).encode("utf-8"))
                return current
            finally:
                await self.release_lock(lock_name)
        else:
            # Naive No-Lock Implementation to demonstrate race condition & lost updates
            raw = await client.get(lb_key)
            board: Dict[str, int] = {}
            if raw:
                try:
                    board = json.loads(raw.decode("utf-8"))
                except Exception:
                    board = {}
            # Small yield to guarantee race condition under concurrent requests
            await asyncio.sleep(0.001)
            current = board.get(str(product_id), 0) + 1
            board[str(product_id)] = current
            await client.set(lb_key, json.dumps(board).encode("utf-8"))
            return current

    async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        client = await self._ensure_client()
        lb_key = b"leaderboard:views"
        raw = await client.get(lb_key)
        if not raw:
            return []
        try:
            board: Dict[str, int] = json.loads(raw.decode("utf-8"))
            # Sort descending by view count
            sorted_items = sorted(board.items(), key=lambda x: x[1], reverse=True)[:limit]
            return [{"product_id": int(pid), "views": int(cnt)} for pid, cnt in sorted_items]
        except Exception as e:
            logger.error("Error parsing Memcached leaderboard: %s", e)
            return []

    async def get_product_views(self, product_id: int) -> int:
        client = await self._ensure_client()
        lb_key = b"leaderboard:views"
        raw = await client.get(lb_key)
        if not raw:
            return 0
        try:
            board = json.loads(raw.decode("utf-8"))
            return int(board.get(str(product_id), 0))
        except Exception:
            return 0

    async def reset_leaderboard(self) -> bool:
        client = await self._ensure_client()
        await client.delete(b"leaderboard:views")
        await client.delete(b"lock:leaderboard:views")
        return True

    # 3. Distributed Rate Limiting using atomic `incr` and safe `add` initialization
    async def check_rate_limit(self, user_id: str, limit: int = 100, window: int = 60) -> Tuple[bool, int]:
        client = await self._ensure_client()
        # Current minute window
        window_bucket = int(time.time() // window)
        key = f"ratelimit:{user_id}:{window_bucket}".encode("utf-8")

        # In Memcached, incr fails if key does not exist
        try:
            current = await client.incr(key, 1)
        except Exception:
            current = None

        if current is None:
            # Key does not exist. Atomically initialize with add (Set if Not Exists)
            added = await client.add(key, b"1", exptime=window)
            if added:
                current = 1
            else:
                # Race condition: Another client created it simultaneously, so incr will now succeed
                try:
                    current = await client.incr(key, 1)
                    if current is None:
                        current = 2
                except Exception:
                    current = 2

        is_allowed = int(current) <= limit
        return is_allowed, int(current)

    # 4. Session Storage using Serialized JSON Strings (Full Re-serialization)
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        client = await self._ensure_client()
        key = f"session:{session_id}".encode("utf-8")
        raw = await client.get(key)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    async def set_session(self, session_id: str, data: Dict[str, Any], ttl: int = settings.SESSION_CACHE_TTL) -> bool:
        client = await self._ensure_client()
        key = f"session:{session_id}".encode("utf-8")
        # Store as full serialized JSON string
        val = json.dumps(data).encode("utf-8")
        return await client.set(key, val, exptime=ttl)

    async def update_session_field(self, session_id: str, field: str, value: Any) -> bool:
        # Full object fetch, modify, re-serialize, and save
        data = await self.get_session(session_id)
        if data is None:
            data = {"session_id": session_id}
        data[field] = value
        return await self.set_session(session_id, data)

    async def health_check(self) -> bool:
        try:
            client = await self._ensure_client()
            stats = await client.stats()
            return stats is not None and len(stats) > 0
        except Exception as e:
            logger.error("Memcached health check failed: %s", e)
            return False
