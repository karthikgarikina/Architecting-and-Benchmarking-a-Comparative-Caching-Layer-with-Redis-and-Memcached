import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_PORT: int = 8000
    REDIS_URL: str = "redis://redis:6379/0"
    MEMCACHED_URL: str = "memcached:11211"
    DATABASE_URL: str = "postgresql://catalog_user:catalog_pass@db:5432/catalog_db"
    DEFAULT_CACHE_BACKEND: str = "redis"
    RATE_LIMIT_MAX_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    PRODUCT_CACHE_TTL: int = 300
    SESSION_CACHE_TTL: int = 86400

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
