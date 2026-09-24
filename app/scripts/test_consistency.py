import asyncio
import json
import logging
import os
import sys
import time
from typing import Dict, Any
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("consistency_test")

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
RESULTS_DIR = os.getenv("RESULTS_DIR", "results")

async def run_concurrent_increments(
    client: httpx.AsyncClient,
    product_id: int,
    backend: str,
    no_lock: bool,
    num_workers: int = 10,
    increments_per_worker: int = 100
) -> int:
    headers = {"X-Cache-Backend": backend}
    params = {"no_lock": "true"} if no_lock else {}

    async def worker():
        for _ in range(increments_per_worker):
            try:
                resp = await client.post(
                    f"{BASE_URL}/products/{product_id}/view",
                    headers=headers,
                    params=params,
                    timeout=30.0
                )
                resp.raise_for_status()
            except Exception as e:
                logger.error("Request failed: %s", e)

    tasks = [asyncio.create_task(worker()) for _ in range(num_workers)]
    await asyncio.gather(*tasks)

    # Fetch leaderboard to check final count
    resp = await client.get(f"{BASE_URL}/leaderboard?limit=100", headers=headers, timeout=10.0)
    data = resp.json()
    for item in data.get("top_products", []):
        if item["product_id"] == product_id:
            return item["views"]
    return 0

async def test_rate_limiter(client: httpx.AsyncClient, backend: str, user_id: str, total_requests: int = 105):
    logger.info("Testing Rate Limiter for %s with %d rapid requests...", backend, total_requests)
    headers = {
        "X-Cache-Backend": backend,
        "X-User-ID": user_id
    }
    status_counts = {}
    for i in range(total_requests):
        try:
            resp = await client.get(f"{BASE_URL}/rate-limit-test", headers=headers, timeout=10.0)
            status_counts[resp.status_code] = status_counts.get(resp.status_code, 0) + 1
        except Exception as e:
            logger.error("Rate limit request %d failed: %s", i, e)

    logger.info("Rate Limiter results for %s: %s", backend, status_counts)
    return status_counts

async def main():
    logger.info("Starting consistency verification against %s...", BASE_URL)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    async with httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=50, max_connections=100)) as client:
        # Wait for API to be healthy
        logger.info("Checking API health...")
        for _ in range(30):
            try:
                h = await client.get(f"{BASE_URL}/health", timeout=5.0)
                if h.status_code == 200 and h.json().get("status") in ["healthy", "degraded"]:
                    logger.info("API is ready: %s", h.json())
                    break
            except Exception:
                await asyncio.sleep(2)
        else:
            logger.error("API is not available!")
            sys.exit(1)

        total_expected = 1000
        num_workers = 10
        inc_per_worker = 100

        # Test 1: Redis Leaderboard Atomic Increments
        logger.info("--- Test 1: Redis Leaderboard Concurrent Increments (10 workers x 100 increments) ---")
        redis_product_id = 99901
        redis_final = await run_concurrent_increments(
            client=client,
            product_id=redis_product_id,
            backend="redis",
            no_lock=False,
            num_workers=num_workers,
            increments_per_worker=inc_per_worker
        )
        redis_lost = total_expected - redis_final
        logger.info("Redis: Expected = %d, Final = %d, Lost = %d", total_expected, redis_final, redis_lost)
        assert redis_final == total_expected, f"Redis failed consistency: {redis_final} != {total_expected}"

        # Test 2: Memcached Leaderboard WITH Distributed Lock
        logger.info("--- Test 2: Memcached Leaderboard WITH Distributed Lock (10 workers x 100 increments) ---")
        memcached_locked_product_id = 99902
        memcached_locked_final = await run_concurrent_increments(
            client=client,
            product_id=memcached_locked_product_id,
            backend="memcached",
            no_lock=False,
            num_workers=num_workers,
            increments_per_worker=inc_per_worker
        )
        memcached_lost_with_lock = total_expected - memcached_locked_final
        logger.info("Memcached (With Lock): Expected = %d, Final = %d, Lost = %d", total_expected, memcached_locked_final, memcached_lost_with_lock)
        assert memcached_locked_final == total_expected, f"Memcached with lock failed: {memcached_locked_final} != {total_expected}"

        # Test 3: Memcached Leaderboard WITHOUT Distributed Lock
        logger.info("--- Test 3: Memcached Leaderboard WITHOUT Lock (Naive Get-Modify-Set Race Condition) ---")
        memcached_nolock_product_id = 99903
        memcached_nolock_final = await run_concurrent_increments(
            client=client,
            product_id=memcached_nolock_product_id,
            backend="memcached",
            no_lock=True,
            num_workers=num_workers,
            increments_per_worker=inc_per_worker
        )
        memcached_lost_no_lock = total_expected - memcached_nolock_final
        logger.info("Memcached (No Lock): Expected = %d, Final = %d, Lost = %d (Race Deficit demonstrated!)",
                    total_expected, memcached_nolock_final, memcached_lost_no_lock)
        assert memcached_lost_no_lock > 0, "Memcached without lock should exhibit lost updates under high concurrency"

        # Test 4: Rate Limiter (Redis)
        logger.info("--- Test 4: Redis Rate Limiter (105 requests) ---")
        redis_rl_results = await test_rate_limiter(client, "redis", f"user-rl-redis-{int(time.time())}")
        assert redis_rl_results.get(200) == 100, f"Expected 100 HTTP 200s, got {redis_rl_results.get(200)}"
        assert redis_rl_results.get(429) == 5, f"Expected 5 HTTP 429s, got {redis_rl_results.get(429)}"

        # Test 5: Rate Limiter (Memcached)
        logger.info("--- Test 5: Memcached Rate Limiter (105 requests) ---")
        memcached_rl_results = await test_rate_limiter(client, "memcached", f"user-rl-memcached-{int(time.time())}")
        assert memcached_rl_results.get(200) == 100, f"Expected 100 HTTP 200s, got {memcached_rl_results.get(200)}"
        assert memcached_rl_results.get(429) == 5, f"Expected 5 HTTP 429s, got {memcached_rl_results.get(429)}"

        consistency_summary = {
            "total_sent_increments": total_expected,
            "redis_final_score": redis_final,
            "redis_lost_increments": redis_lost,
            "memcached_lost_increments_with_lock": memcached_lost_with_lock,
            "memcached_lost_increments_no_lock": memcached_lost_no_lock,
            "redis_rate_limit_distribution": redis_rl_results,
            "memcached_rate_limit_distribution": memcached_rl_results,
            "timestamp": time.time()
        }

        output_path = os.path.join(RESULTS_DIR, "consistency_results.json")
        with open(output_path, "w") as f:
            json.dump(consistency_summary, f, indent=2)
        logger.info("Consistency test completed successfully! Results written to %s", output_path)

if __name__ == "__main__":
    asyncio.run(main())
