import json
import logging
from typing import Optional, Dict, Any
import asyncpg
from app.config import settings

logger = logging.getLogger("database")

pool: Optional[asyncpg.Pool] = None

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    category VARCHAR(100) NOT NULL,
    sku VARCHAR(64) UNIQUE NOT NULL,
    stock INTEGER NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    specifications JSONB NOT NULL DEFAULT '{}'::jsonb,
    reviews_summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
"""

async def init_db() -> asyncpg.Pool:
    global pool
    if pool is None:
        logger.info("Initializing asyncpg database pool...")
        pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=5,
            max_size=30,
            command_timeout=10,
        )
        async with pool.acquire() as conn:
            await conn.execute(CREATE_TABLES_SQL)
        logger.info("Database pool initialized and tables ensured.")
    return pool

async def close_db():
    global pool
    if pool is not None:
        await pool.close()
        pool = None
        logger.info("Database pool closed.")

async def get_db_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        await init_db()
    return pool

async def get_product_by_id(product_id: int) -> Optional[Dict[str, Any]]:
    p = await get_db_pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name, description, price, category, sku, stock,
                   attributes, specifications, reviews_summary,
                   created_at, updated_at
            FROM products WHERE id = $1
            """,
            product_id,
        )
        if not row:
            return None
        res = dict(row)
        res["price"] = float(res["price"])
        if isinstance(res.get("attributes"), str):
            res["attributes"] = json.loads(res["attributes"])
        if isinstance(res.get("specifications"), str):
            res["specifications"] = json.loads(res["specifications"])
        if res.get("created_at"):
            res["created_at"] = res["created_at"].isoformat()
        if res.get("updated_at"):
            res["updated_at"] = res["updated_at"].isoformat()
        return res

async def update_product_by_id(product_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    p = await get_db_pool()
    valid_fields = ["name", "description", "price", "category", "stock", "attributes", "specifications", "reviews_summary"]
    set_clauses = []
    values = []
    idx = 1
    for k, v in updates.items():
        if k in valid_fields and v is not None:
            if k in ("attributes", "specifications") and isinstance(v, dict):
                set_clauses.append(f"{k} = ${idx}::jsonb")
                values.append(json.dumps(v))
            else:
                set_clauses.append(f"{k} = ${idx}")
                values.append(v)
            idx += 1
    if not set_clauses:
        return await get_product_by_id(product_id)

    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    values.append(product_id)
    query = f"""
        UPDATE products
        SET {', '.join(set_clauses)}
        WHERE id = ${idx}
        RETURNING id, name, description, price, category, sku, stock,
                  attributes, specifications, reviews_summary,
                  created_at, updated_at
    """
    async with p.acquire() as conn:
        row = await conn.fetchrow(query, *values)
        if not row:
            return None
        res = dict(row)
        res["price"] = float(res["price"])
        if isinstance(res.get("attributes"), str):
            res["attributes"] = json.loads(res["attributes"])
        if isinstance(res.get("specifications"), str):
            res["specifications"] = json.loads(res["specifications"])
        if res.get("created_at"):
            res["created_at"] = res["created_at"].isoformat()
        if res.get("updated_at"):
            res["updated_at"] = res["updated_at"].isoformat()
        return res

async def get_product_count() -> int:
    p = await get_db_pool()
    async with p.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM products")
        return int(count)
