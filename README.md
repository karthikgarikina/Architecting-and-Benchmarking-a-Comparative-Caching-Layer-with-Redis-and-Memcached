# Comparative Caching Layer: Redis 7 vs. Memcached 1.6

A production-grade, low-latency Product Catalog API and benchmarking suite demonstrating complex distributed caching patterns across **Redis 7** and **Memcached 1.6**, backed by a **PostgreSQL 16** relational database seeded with 100,000 product records (~2KB each).

---

## 1. Overview & Architectural Comparison

In distributed systems, memory access latency (~100ns) is orders of magnitude faster than disk I/O (~1-10ms). While both Redis and Memcached serve as in-memory data layers, their internal architectures dictate fundamentally different trade-offs:

| Dimension | Redis 7 | Memcached 1.6 |
|---|---|---|
| **Architecture** | Single-threaded event loop (I/O threads for network) | Multi-threaded event-driven (pthread per core) |
| **Data Structures** | Strings, Hashes, Sorted Sets (ZSET), Lists, Sets, Streams, Bitmaps | Strings only (raw bytes / serialized blobs up to 1MB) |
| **Atomicity** | Built-in single-threaded commands, Lua scripts, MULTI/EXEC | Atomic single-key operations (`add`, `incr`, `decr`, `cas`) |
| **Leaderboards** | Native `ZINCRBY` / `ZREVRANGE` in $O(\log N)$ time | Serialized lists requiring application-level distributed locks (`add`) |
| **Partial Updates** | Native `HSET` / `HGET` on individual fields | Full get-deserialize-modify-serialize-set roundtrip |
| **Invalidation** | Pub/Sub notifications (`PUBLISH product_invalidation`) | Generational Cache Versioning (`v{ver}:product:{id}`) |
| **Memory Allocation**| `jemalloc` with dynamic `robj` + `dictEntry` wrappers | Slab allocation (fixed chunk power-of-two classes) |

---

## 2. System Architecture

```
                       +-----------------------------------+
                       |          Load Generator           |
                       |    Locust / memtier_benchmark     |
                       +-----------------+-----------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| Consistency Test                                                                  |
|   +--------------------------+               +--------------------------+         |
|   |        Process 1         |               |        Process 2         |         |
|   | (10 concurrent workers)  |               | (10 concurrent workers)  |         |
|   +------------+-------------+               +------------+-------------+         |
|                |                                          |                       |
|                +--------------------+---------------------+                       |
|                                     | Concurrent Incr                             |
|                                     v                                             |
|                     +-------------------------------+                             |
|                     |      Product Catalog API      |                             |
|                     |   (FastAPI / Python 3.11)     |                             |
|                     +---------------+---------------+                             |
+-------------------------------------|---------------------------------------------+
               |                      |                      |
      Read/Write             Read/Write              Fallback / Seed
               v                      v                      v
       +---------------+      +---------------+      +---------------+
       |    Redis 7    |      | Memcached 1.6 |      | PostgreSQL 16 |
       | (ZSET/Hashes) |      | (Slab / Lock) |      | (100,000 rows)|
       +---------------+      +---------------+      +---------------+
```

---

## 3. The 5 Implemented Caching Patterns

### Pattern 1: Product Metadata Caching (`GET /products/:id`)
- **Redis**: Key `product:{id}` stored with 300s TTL.
- **Memcached**: Key `v{version}:product:{id}` stored with 300s TTL.
- Cache Miss: Fetches ~2KB record from PostgreSQL, caches it, and returns `X-Cache: MISS`.
- Cache Hit: Serves directly from memory and returns `X-Cache: HIT`.

### Pattern 2: Cache Invalidation (`POST /products/:id`)
- **Redis**: Deletes key and broadcasts event via `PUBLISH product_invalidation {id}`.
- **Memcached**: Increments the global version key `global_product_version`, instantaneously invalidating all previous product cache keys via generational prefix invalidation.

### Pattern 3: Most Viewed Products Leaderboard (`GET /leaderboard`, `POST /products/:id/view`)
- **Redis**: Uses `ZINCRBY leaderboard:views 1 {id}` for atomic $O(\log N)$ updates and `ZREVRANGE leaderboard:views 0 9 WITHSCORES` to fetch the top 10.
- **Memcached**: Retrieves serialized JSON list, sorts in memory, and writes back.
  - **With Lock**: Acquires a distributed lock using Memcached atomic `add lock:leaderboard:views locked ex=5` with exponential backoff and jitter. Guarantees 0 lost increments.
  - **Without Lock (`?no_lock=true`)**: Naive read-modify-write introduces severe race conditions, resulting in hundreds of lost increments under high concurrency.

### Pattern 4: Distributed Rate Limiting (`GET /rate-limit-test` or middleware)
- 100 requests per minute per user (`X-User-ID` header).
- **Redis**: Executes an atomic Lua script executing `INCR` + `EXPIRE` in a single server roundtrip:
  ```lua
  local current = redis.call('INCR', KEYS[1])
  if tonumber(current) == 1 then
      redis.call('EXPIRE', KEYS[1], ARGV[1])
  end
  return current
  ```
- **Memcached**: Uses atomic `incr`. If key is not present, safely initializes using `add` (Set if Not Exists), retrying `incr` upon race conditions.

### Pattern 5: User Session Storage (`/session/:id`)
- **Redis**: Uses Redis Hashes (`HSET session:{id} key value`, `HGETALL session:{id}`). Updating a single field (e.g., `last_login`) modifies **only that field** in Redis memory.
- **Memcached**: Stores the entire session as a serialized JSON string. Updating one field requires deserializing the entire object, modifying it, and re-serializing the full string back to Memcached.

---

## 4. Setup & Running the Environment

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) (Docker Compose v2+ / v5+)

### Environment Variables
Review `.env.example` and `.env`:
```ini
API_PORT=8000
REDIS_URL=redis://redis:6379/0
MEMCACHED_URL=memcached:11211
DATABASE_URL=postgresql://catalog_user:catalog_pass@db:5432/catalog_db
DEFAULT_CACHE_BACKEND=redis
RATE_LIMIT_MAX_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
PRODUCT_CACHE_TTL=300
SESSION_CACHE_TTL=86400
```

### Starting All Services
Run Docker Compose:
```bash
docker compose up -d --build
```

Verify that all four containers reach the `healthy` status:
```bash
docker ps
```
Output:
```
CONTAINER ID   IMAGE                 STATUS                   PORTS                      NAMES
...            ...-app               Up (healthy)             0.0.0.0:8000->8000/tcp     caching-app
...            postgres:16-alpine    Up (healthy)             0.0.0.0:5432->5432/tcp     caching-db
...            memcached:1.6-alpine  Up (healthy)             0.0.0.0:11211->11211/tcp   caching-memcached
...            redis:7-alpine        Up (healthy)             0.0.0.0:6379->6379/tcp     caching-redis
```

---

## 5. Verification & Testing Guide

### 1. Relational Database Seeding Verification (100,000 rows)
Check that PostgreSQL is seeded with exactly 100,000 product rows:
```bash
docker exec caching-db psql -U catalog_user -d catalog_db -c "SELECT count(*) FROM products;"
```
Expected Output:
```
 count  
--------
 100000
```

### 2. Cache Hit/Miss & Invalidation Verification
**Redis Backend:**
```bash
# First request -> MISS (fetches ~2KB JSON from Postgres and caches with 300s TTL)
curl -i -H "X-Cache-Backend: redis" http://localhost:8000/products/1

# Second request -> HIT (served directly from Redis memory)
curl -i -H "X-Cache-Backend: redis" http://localhost:8000/products/1

# Check Redis key
docker exec caching-redis redis-cli keys "product:*"
```

**Memcached Backend:**
```bash
# First request -> MISS
curl -i -H "X-Cache-Backend: memcached" http://localhost:8000/products/1

# Second request -> HIT
curl -i -H "X-Cache-Backend: memcached" http://localhost:8000/products/1

# Verify via Memcached stats
docker exec caching-app python -c "import socket; s = socket.socket(); s.connect(('memcached', 11211)); s.sendall(b'stats items\r\n'); print(s.recv(1024).decode()); s.close()"
```

### 3. Session Store Verification (Hash vs Serialized String)
Create and partially update a session:
```bash
# 1. Store session in Redis
curl -X POST http://localhost:8000/session/sess-1 \
  -H "X-Cache-Backend: redis" -H "Content-Type: application/json" \
  -d '{"session_id":"sess-1","user_id":"u-1","username":"alice","last_login":"2026-09-22T10:00:00Z"}'

# 2. Update only 'last_login'
curl -X PATCH http://localhost:8000/session/sess-1 \
  -H "X-Cache-Backend: redis" -H "Content-Type: application/json" \
  -d '{"last_login":"2026-09-22T12:00:00Z"}'

# 3. Verify in Redis CLI that only one field was updated
docker exec caching-redis redis-cli HGET session:sess-1 last_login
# Output: 2026-09-22T12:00:00Z

# 4. Repeat in Memcached and inspect serialized JSON string
curl -X POST http://localhost:8000/session/sess-1 \
  -H "X-Cache-Backend: memcached" -H "Content-Type: application/json" \
  -d '{"session_id":"sess-1","user_id":"u-1","username":"alice","last_login":"2026-09-22T10:00:00Z"}'

docker exec caching-app python -c "import socket; s = socket.socket(); s.connect(('memcached', 11211)); s.sendall(b'get session:sess-1\r\n'); print(s.recv(1024).decode()); s.close()"
```

### 4. Running the Automated Consistency Test
The consistency suite verifies:
- **Redis Leaderboard**: Atomic increments (`ZINCRBY`) under 10 concurrent workers $\times$ 100 increments = exactly 1000.
- **Memcached Leaderboard (With Lock)**: Distributed locking via `add` under 10 concurrent workers $\times$ 100 increments = exactly 1000 (0 lost increments).
- **Memcached Leaderboard (No Lock)**: Demonstrates race condition deficit ($< 1000$, resulting in hundreds of lost increments).
- **Distributed Rate Limiter**: 105 rapid requests per user resulting in exactly 100 HTTP 200s and 5 HTTP 429s.

**To run the test:**

On Windows PowerShell:
```powershell
.\test_consistency.ps1
```
*(or `powershell -ExecutionPolicy Bypass -File test_consistency.ps1` or run `test_consistency.bat`)*

On Linux / macOS:
```bash
./test_consistency.sh
```

Or via direct Docker command:
```bash
docker exec caching-app python app/scripts/test_consistency.py
```

**Expected terminal output upon completion:**
```text
Consistency test completed successfully! Results written to results/consistency_results.json
```
*(Note: The above text is the completion status message displayed by the script, not a command to type).*


---

## 6. Memory Comparison Table

The following table compares the actual memory overhead of storing **100,000 product objects (2KB payload each)** across both storage backends. Values were derived using `INFO memory` for Redis 7 and `stats` for Memcached 1.6:

| Storage Backend | Reported Used Memory (MB) | Overhead per Key (Bytes) |
|---|---|---|
| **Redis 7** | **251.94** | **536.78** |
| **Memcached 1.6** | **206.46** | **74.86** |

### Deep-Dive Analysis
1. **Payload Size**: Raw JSON payload for each product is 2,090 bytes (~2.04 KB). 100,000 items equal 199.31 MB of raw data.
2. **Redis Overhead (536.78 bytes/key)**:
   - Redis wraps keys and values in internal `robj` structures (16 bytes each).
   - The main dictionary stores each entry in a `dictEntry` structure (24-32 bytes).
   - Strings use SDS (Simple Dynamic String) headers with unused capacity buffers.
   - `jemalloc` rounds allocations to power-of-two or fixed chunk size classes (e.g. 2048 to 2560 bytes).
3. **Memcached Overhead (74.86 bytes/key)**:
   - Memcached utilizes a specialized C `item` header (48-56 bytes) containing LRU pointers, flags, and key length.
   - Its Slab Allocator slices pre-allocated 1MB pages into fixed-size chunk classes, minimizing fragmentation for uniform object sizes.

---

## 7. Benchmarking Suite (`memtier_benchmark`)

The automated benchmark script executes `memtier_benchmark` against Redis 7 and Memcached 1.6 across pipeline depths **1, 10, and 50** with a **9:1 Read/Write ratio** (Set:Get = 1:9) and a **Gaussian key distribution (G:G)**:

### Running Benchmarks
On Linux/macOS:
```bash
./run_benchmarks.sh
```
On Windows:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_benchmarks.ps1
```

Results are saved to:
- `results/redis_bench.txt`
- `results/memcached_bench.txt`

### Benchmark Performance Summary

| Backend | Pipeline Depth | Throughput (Ops/sec) | p50 Latency (ms) | p99 Latency (ms) | Bandwidth (MB/s) |
|---|---|---|---|---|---|
| **Redis 7** | Pipeline 1 | 66,581.44 | 0.135 | 0.551 | 37.32 |
| **Redis 7** | Pipeline 10 | 410,404.58 | 0.183 | 1.143 | 230.22 |
| **Redis 7** | Pipeline 50 | 339,392.62 | 0.495 | 22.783 | 190.38 |
| **Memcached 1.6** | Pipeline 1 | 67,014.61 | 0.119 | 0.631 | 36.97 |
| **Memcached 1.6** | Pipeline 10 | 327,338.67 | 0.207 | 1.495 | 180.74 |
| **Memcached 1.6** | Pipeline 50 | 511,823.11 | 0.431 | 6.495 | 282.60 |

### Key Architectural Takeaways:
- **Pipeline Depth 1**: Both backends perform identically (~66k-67k ops/sec) because network socket round-trip time dominates.
- **Pipelining Effect**: Pipelining amortizes syscall overhead (`read`/`write`) over multiple operations.
- **Deep Pipelines (50)**: Memcached's multi-threaded worker architecture scales up to 511k ops/sec with low p99 latency (6.49ms), whereas Redis's single-threaded event loop becomes CPU-bound on command deserialization, causing queuing latencies at p99 (22.78ms).

---

## 8. Application Load Testing with Locust

Locust simulates real user journeys:
1. `GET /products/:id` (Metadata caching)
2. `POST /products/:id/view` (Leaderboard increment)
3. `GET /leaderboard` (Top 10 retrieval)
4. `GET /rate-limit-test` (Rate limiter check)
5. `PATCH /session/:id` (Session modification)

To run a headless load test:
```bash
docker exec caching-app locust -f locustfile.py --headless -u 20 -r 5 --run-time 30s -H http://localhost:8000
```
Or open the Locust Web UI at `http://localhost:8089` by adding port mapping `8089:8089` and running `locust -f locustfile.py`.

---

## 9. Submission Artifacts (`submission.json`)

The `submission.json` file in the root directory summarizes the benchmark and consistency results:

```json
{
  "benchmarks": {
    "redis_ops_p1": 66581.44,
    "memcached_ops_p1": 67014.61,
    "redis_p99_ms": 0.551,
    "memcached_p99_ms": 0.631
  },
  "consistency": {
    "memcached_lost_increments_no_lock": 407,
    "memcached_lost_increments_with_lock": 0
  }
}
```

---

## 10. Verification Checklist

- [x] **Requirement 1**: `docker-compose.yml` with `app`, `redis:7-alpine`, `memcached:1.6-alpine`, `postgres:16-alpine`. All reach `healthy`. Database seeded with 100,000 product rows.
- [x] **Requirement 2**: Endpoints support `X-Cache-Backend: redis` and `X-Cache-Backend: memcached`. Cache hit/miss verified with 300s TTL.
- [x] **Requirement 3**: Redis Leaderboard uses `ZINCRBY` and `ZREVRANGE ... WITHSCORES`. Race test yields exactly 1000.
- [x] **Requirement 4**: Memcached Leaderboard implements distributed lock via `add` with backoff. Race test yields exactly 1000 (0 lost increments with lock; 407 lost without lock).
- [x] **Requirement 5**: Rate limiter (100 req/min). Redis uses atomic Lua script; Memcached uses `incr` with safe `add` initialization. Tested with 105 rapid requests -> 100 HTTP 200s, 5 HTTP 429s.
- [x] **Requirement 6**: `run_benchmarks.sh` / `scripts/run_benchmarks.ps1` runs `memtier_benchmark` with pipelines 1, 10, 50, 9:1 R/W ratio, Gaussian distribution, saving to `results/redis_bench.txt` and `results/memcached_bench.txt`.
- [x] **Requirement 7**: Session storage uses Redis Hashes (`HSET`/`HGETALL`) for individual field updates and Memcached for serialized JSON strings.
- [x] **Requirement 8**: `submission.json` created in root directory with required schema and `memcached_lost_increments_with_lock = 0`.
- [x] **Requirement 9**: Markdown table in `README.md` with columns `Storage Backend`, `Reported Used Memory (MB)`, `Overhead per Key (Bytes)` derived from `INFO memory` and `stats`.
- [x] **Requirement 10**: `.env.example` and `.env` document `REDIS_URL`, `MEMCACHED_URL`, `DATABASE_URL`, and `API_PORT`.
