from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Tuple

class BaseCacheBackend(ABC):
    @abstractmethod
    async def get_product(self, product_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve product metadata from cache."""
        pass

    @abstractmethod
    async def set_product(self, product_id: int, data: Dict[str, Any], ttl: int = 300) -> bool:
        """Store product metadata into cache with TTL."""
        pass

    @abstractmethod
    async def invalidate_product(self, product_id: int) -> bool:
        """Invalidate product cache (and propagate via pub/sub or versioning)."""
        pass

    @abstractmethod
    async def increment_product_view(self, product_id: int, use_lock: bool = True) -> int:
        """Increment view count for leaderboard. Returns current score/views."""
        pass

    @abstractmethod
    async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return top N viewed products."""
        pass

    @abstractmethod
    async def get_product_views(self, product_id: int) -> int:
        """Get exact view count for a single product."""
        pass

    @abstractmethod
    async def reset_leaderboard(self) -> bool:
        """Reset leaderboard view counts."""
        pass

    @abstractmethod
    async def check_rate_limit(self, user_id: str, limit: int = 100, window: int = 60) -> Tuple[bool, int]:
        """
        Check rate limit.
        Returns: (allowed: bool, current_count: int)
        """
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data."""
        pass

    @abstractmethod
    async def set_session(self, session_id: str, data: Dict[str, Any], ttl: int = 86400) -> bool:
        """Save whole session data."""
        pass

    @abstractmethod
    async def update_session_field(self, session_id: str, field: str, value: Any) -> bool:
        """Update a single session field."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify cache backend connectivity."""
        pass
