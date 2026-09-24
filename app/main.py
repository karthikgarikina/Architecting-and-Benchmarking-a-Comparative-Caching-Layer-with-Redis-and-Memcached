import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db, close_db, get_product_count
from app.cache import init_cache_backends, close_cache_backends, redis_backend, memcached_backend, get_cache_backend
from app.routes.products import router as products_router
from app.routes.leaderboard import router as leaderboard_router
from app.routes.sessions import router as sessions_router
from app.routes.rate_limit import router as rate_limit_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Product Catalog API...")
    await init_db()
    await init_cache_backends()
    yield
    logger.info("Shutting down Product Catalog API...")
    await close_cache_backends()
    await close_db()

app = FastAPI(
    title="Comparative Caching Layer API (Redis 7 vs Memcached 1.6)",
    description="High-performance Product Catalog API demonstrating complex caching patterns with Redis and Memcached.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Rate Limiting Middleware when X-User-ID is passed
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    user_id = request.headers.get("X-User-ID")
    # Exempt health, docs, and direct rate-limit-test route (which handles its own explicit check)
    path = request.url.path
    if user_id and not (path.startswith("/docs") or path.startswith("/openapi") or path.startswith("/health") or path.startswith("/rate-limit-test")):
        cache = get_cache_backend(request.headers.get("X-Cache-Backend"))
        allowed, current = await cache.check_rate_limit(
            user_id=user_id,
            limit=settings.RATE_LIMIT_MAX_REQUESTS,
            window=settings.RATE_LIMIT_WINDOW_SECONDS
        )
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded. Maximum {settings.RATE_LIMIT_MAX_REQUESTS} requests per minute."},
                headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS), "X-RateLimit-Current": str(current)}
            )
    response = await call_next(request)
    return response

@app.get("/health", tags=["Health"])
async def health():
    db_ok = False
    prod_count = 0
    try:
        prod_count = await get_product_count()
        db_ok = True
    except Exception as e:
        logger.error("Health check DB failed: %s", e)

    redis_ok = await redis_backend.health_check()
    memcached_ok = await memcached_backend.health_check()

    status = "healthy" if (db_ok and redis_ok and memcached_ok and prod_count >= 100000) else "degraded"
    return {
        "status": status,
        "database": {"connected": db_ok, "product_count": prod_count},
        "redis": {"connected": redis_ok},
        "memcached": {"connected": memcached_ok},
    }

@app.get("/", tags=["Info"])
async def root():
    return {
        "service": "Product Catalog Comparative Caching Layer",
        "supported_backends": ["redis", "memcached"],
        "default_backend": settings.DEFAULT_CACHE_BACKEND,
        "endpoints": {
            "get_product": "GET /products/{id}",
            "update_product": "POST /products/{id}",
            "get_leaderboard": "GET /leaderboard",
            "view_product": "POST /products/{id}/view",
            "get_session": "GET /session/{id}",
            "patch_session": "PATCH /session/{id}",
            "rate_limit_test": "GET /rate-limit-test",
            "health": "GET /health"
        }
    }

app.include_router(products_router)
app.include_router(leaderboard_router)
app.include_router(sessions_router)
app.include_router(rate_limit_router)
