import asyncio
import json
import logging
import os
import sys
import redis.asyncio as aioredis
import aiomcache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("memory_bench")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MEMCACHED_URL = os.getenv("MEMCACHED_URL", "localhost:11211")
NUM_ITEMS = int(os.getenv("NUM_ITEMS", "100000"))

# Sample 2KB payload
SAMPLE_PAYLOAD = {
    "id": 1,
    "name": "Electronics Pro Series Model 1",
    "description": "Engineered with ultra-precision aerospace-grade aluminum casing, multi-core accelerated processing architecture, and next-generation low-latency dynamic interfaces. Features high-dynamic-range true-color calibration, dual-band beamforming antenna arrays, enterprise-grade thermal dispersion dissipation baffles, and dedicated coprocessors for real-time sensor processing and telemetry data aggregation. Designed specifically for demanding high-throughput continuous operational workflows, mission-critical infrastructure deployments, and seamless distributed edge computing ecosystem integration with industry-standard protocols. Extended testing verifies sub-millisecond bus interconnect transaction latencies and resilience under extreme vibration and thermal gradients.",
    "price": 199.99,
    "category": "Electronics",
    "sku": "SKU-ELE-0000001",
    "stock": 450,
    "attributes": {
        "color": "Space Gray",
        "weight_grams": 850,
        "dimensions_mm": {"length": 210, "width": 140, "height": 28},
        "material": "Recycled Aluminum & Polycarbonate Composite",
        "certifications": ["FCC", "CE", "RoHS", "ISO9001", "EnergyStar"],
        "origin_country": "Taiwan",
        "warranty_months": 24,
        "is_waterproof": True,
        "ip_rating": "IP68"
    },
    "specifications": {
        "architecture": "Armv9 64-bit multi-cluster",
        "core_count": 8,
        "clock_speed_ghz": 3.2,
        "memory_capacity_gb": 32,
        "storage_nvme_tb": 2,
        "bus_bandwidth_gbps": 128.0,
        "thermal_design_power_watts": 65,
        "supported_codecs": ["AV1", "H.265/HEVC", "ProRes RAW", "VP9", "Opus"],
        "network_interfaces": ["2.5GbE LAN", "Wi-Fi 6E (802.11ax)", "Bluetooth 5.3 Low Energy"]
    },
    "reviews_summary": "Comprehensive engineering benchmark tests reveal unmatched throughput and efficiency under continuous heavy load. Thermal management remains remarkably silent under sustained workloads, and API integration into existing distributed infrastructure was straightforward and well-documented. Highly recommended for enterprise production deployment.",
    "created_at": "2026-09-22T00:00:00Z",
    "updated_at": "2026-09-22T00:00:00Z"
}

payload_json = json.dumps(SAMPLE_PAYLOAD)
payload_bytes = payload_json.encode("utf-8")
PAYLOAD_SIZE_BYTES = len(payload_bytes)

async def measure_redis():
    logger.info("Connecting to Redis at %s...", REDIS_URL)
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r.flushall()
    info_before = await r.info("memory")
    used_before = info_before["used_memory"]

    logger.info("Inserting %d keys (size ~%d bytes) into Redis...", NUM_ITEMS, PAYLOAD_SIZE_BYTES)
    pipe = r.pipeline(transaction=False)
    batch = 5000
    for i in range(1, NUM_ITEMS + 1):
        pipe.set(f"product:{i}", payload_json)
        if i % batch == 0:
            await pipe.execute()
            pipe = r.pipeline(transaction=False)
    await pipe.execute()

    info_after = await r.info("memory")
    used_after = info_after["used_memory"]
    await r.aclose()

    net_memory_bytes = used_after - used_before
    reported_mb = round(used_after / (1024 * 1024), 2)
    bytes_per_key = net_memory_bytes / NUM_ITEMS
    overhead_per_key = round(bytes_per_key - PAYLOAD_SIZE_BYTES, 2)

    return {
        "backend": "Redis 7",
        "reported_used_memory_mb": reported_mb,
        "net_memory_mb": round(net_memory_bytes / (1024 * 1024), 2),
        "overhead_per_key_bytes": overhead_per_key,
        "total_bytes_per_key": round(bytes_per_key, 2)
    }

async def measure_memcached():
    host = MEMCACHED_URL.split("://")[-1].split(":")[0]
    port = int(MEMCACHED_URL.split(":")[-1]) if ":" in MEMCACHED_URL else 11211
    logger.info("Connecting to Memcached at %s:%d...", host, port)
    mc = aiomcache.Client(host, port)
    await mc.flush_all()
    stats_before = await mc.stats()
    bytes_before = int(stats_before.get(b"bytes", 0))

    logger.info("Inserting %d keys (size ~%d bytes) into Memcached...", NUM_ITEMS, PAYLOAD_SIZE_BYTES)
    # Memcached insertion
    batch_size = 500
    for chunk_start in range(1, NUM_ITEMS + 1, batch_size):
        tasks = [
            mc.set(f"v1:product:{i}".encode("utf-8"), payload_bytes)
            for i in range(chunk_start, min(chunk_start + batch_size, NUM_ITEMS + 1))
        ]
        await asyncio.gather(*tasks)

    stats_after = await mc.stats()
    bytes_after = int(stats_after.get(b"bytes", 0))
    await mc.close()

    net_memory_bytes = bytes_after - bytes_before
    reported_mb = round(bytes_after / (1024 * 1024), 2)
    bytes_per_key = net_memory_bytes / NUM_ITEMS
    overhead_per_key = round(bytes_per_key - PAYLOAD_SIZE_BYTES, 2)

    return {
        "backend": "Memcached 1.6",
        "reported_used_memory_mb": reported_mb,
        "net_memory_mb": round(net_memory_bytes / (1024 * 1024), 2),
        "overhead_per_key_bytes": overhead_per_key,
        "total_bytes_per_key": round(bytes_per_key, 2)
    }

async def main():
    logger.info("Payload size: %d bytes (~%.2f KB)", PAYLOAD_SIZE_BYTES, PAYLOAD_SIZE_BYTES / 1024)
    redis_res = await measure_redis()
    mc_res = await measure_memcached()

    print("\n" + "=" * 60)
    print("MEMORY COMPARISON: 100,000 PRODUCTS (~2KB EACH)")
    print("=" * 60)
    print(f"{'Storage Backend':<20} | {'Reported Used Memory (MB)':<25} | {'Overhead per Key (Bytes)':<25}")
    print("-" * 76)
    print(f"{redis_res['backend']:<20} | {redis_res['reported_used_memory_mb']:<25} | {redis_res['overhead_per_key_bytes']:<25}")
    print(f"{mc_res['backend']:<20} | {mc_res['reported_used_memory_mb']:<25} | {mc_res['overhead_per_key_bytes']:<25}")
    print("=" * 60 + "\n")

    os.makedirs("results", exist_ok=True)
    with open("results/memory_comparison.json", "w") as f:
        json.dump({"payload_size_bytes": PAYLOAD_SIZE_BYTES, "redis": redis_res, "memcached": mc_res}, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
