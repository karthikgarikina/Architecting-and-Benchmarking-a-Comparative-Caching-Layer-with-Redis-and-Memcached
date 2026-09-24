import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seeder")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://catalog_user:catalog_pass@db:5432/catalog_db")
TARGET_COUNT = 100000

SAMPLE_CATEGORIES = [
    "Electronics", "Computers", "Smartphones", "Audio", "Cameras",
    "Wearables", "Gaming", "Home Appliances", "Networking", "Office Supplies"
]

SAMPLE_DESCRIPTIONS = [
    "Engineered with ultra-precision aerospace-grade aluminum casing, multi-core accelerated processing architecture, and next-generation low-latency dynamic interfaces. Features high-dynamic-range true-color calibration, dual-band beamforming antenna arrays, enterprise-grade thermal dispersion dissipation baffles, and dedicated coprocessors for real-time sensor processing and telemetry data aggregation. Designed specifically for demanding high-throughput continuous operational workflows, mission-critical infrastructure deployments, and seamless distributed edge computing ecosystem integration with industry-standard protocols.",
    "A state-of-the-art enterprise hardware component featuring high-density dual-channel memory buffers, redundant failover power supplies, active noise-canceling multi-stage ventilation fans, and cryptographic hardware-level cryptographic key stores. Tested extensively across extreme operational temperature gradients and high vibrational stress environments, ensuring continuous five-nines (99.999%) uptime availability, sub-millisecond bus interconnect transaction latencies, and granular programmatic telemetry monitoring.",
    "Next-generation consumer flagship device combining ergonomic organic form-factors with resilient nano-ceramic reinforced glass displays. Integrates a custom 8-core hybrid architecture with dedicated neural processing cores, hyper-fast PCI-Express storage buses, and an intelligent battery management system capable of adaptive power envelope optimization across demanding mixed workloads, content authoring, and extended real-time computing."
]

SAMPLE_REVIEWS = [
    "Comprehensive engineering benchmark tests reveal unmatched throughput and efficiency under continuous heavy load. Thermal management remains remarkably silent under sustained workloads, and API integration into existing distributed infrastructure was straightforward and well-documented. Highly recommended for enterprise production deployment.",
    "Exceptional build quality, crisp response times, and remarkably consistent telemetry reporting. Has been running continuously for over 60 days without a single memory leak, bus failure, or unhandled exception. The extended telemetry and hardware-level diagnostics have significantly reduced our mean-time-to-detection."
]

def generate_record(idx: int):
    cat = SAMPLE_CATEGORIES[idx % len(SAMPLE_CATEGORIES)]
    desc = SAMPLE_DESCRIPTIONS[idx % len(SAMPLE_DESCRIPTIONS)]
    rev = SAMPLE_REVIEWS[idx % len(SAMPLE_REVIEWS)]
    sku = f"SKU-{cat[:3].upper()}-{idx:07d}"
    price = round(19.99 + (idx % 1500) * 1.25, 2)
    stock = 10 + (idx % 990)

    attributes = {
        "color": ["Space Gray", "Silver", "Midnight Black", "Arctic White", "Deep Blue"][idx % 5],
        "weight_grams": 450 + (idx % 1200),
        "dimensions_mm": {"length": 210, "width": 140, "height": 28},
        "material": "Recycled Aluminum & Polycarbonate Composite",
        "certifications": ["FCC", "CE", "RoHS", "ISO9001", "EnergyStar"],
        "origin_country": "Taiwan",
        "warranty_months": 24,
        "is_waterproof": bool(idx % 2 == 0),
        "ip_rating": "IP68" if idx % 2 == 0 else "IP54"
    }

    specifications = {
        "architecture": "Armv9 64-bit multi-cluster",
        "core_count": 8 + (idx % 8) * 2,
        "clock_speed_ghz": round(2.4 + (idx % 16) * 0.1, 2),
        "memory_capacity_gb": 16 * (1 + (idx % 4)),
        "storage_nvme_tb": 1 + (idx % 4),
        "bus_bandwidth_gbps": 128.0,
        "thermal_design_power_watts": 65 + (idx % 30),
        "supported_codecs": ["AV1", "H.265/HEVC", "ProRes RAW", "VP9", "Opus"],
        "network_interfaces": ["2.5GbE LAN", "Wi-Fi 6E (802.11ax)", "Bluetooth 5.3 Low Energy"]
    }

    now = datetime.utcnow()

    return (
        idx,
        f"{cat} Pro Series Model {idx}",
        desc,
        price,
        cat,
        sku,
        stock,
        json.dumps(attributes),
        json.dumps(specifications),
        rev,
        now,
        now
    )

async def seed_database():
    start_time = time.time()
    logger.info("Connecting to database: %s", DATABASE_URL)
    
    conn = None
    retries = 30
    for i in range(retries):
        try:
            conn = await asyncpg.connect(dsn=DATABASE_URL)
            break
        except Exception as e:
            logger.warning("Waiting for database connection (%d/%d): %s", i + 1, retries, e)
            await asyncio.sleep(2)
            
    if not conn:
        logger.error("Failed to connect to database after %d attempts", retries)
        sys.exit(1)

    try:
        # Ensure table exists
        await conn.execute("""
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
        """)

        current_count = await conn.fetchval("SELECT COUNT(*) FROM products")
        logger.info("Current product count in database: %d", current_count)

        if current_count >= TARGET_COUNT:
            logger.info("Database already seeded with %d products. Skipping seeding.", current_count)
            return

        needed = TARGET_COUNT - current_count
        logger.info("Seeding %d product records into PostgreSQL...", needed)

        batch_size = 10000
        records = []
        columns = [
            "id", "name", "description", "price", "category", "sku", "stock",
            "attributes", "specifications", "reviews_summary", "created_at", "updated_at"
        ]

        start_id = current_count + 1
        for i in range(start_id, TARGET_COUNT + 1):
            records.append(generate_record(i))
            if len(records) >= batch_size:
                await conn.copy_records_to_table("products", records=records, columns=columns)
                logger.info("Inserted batch up to id %d / %d (%.1f%%)", i, TARGET_COUNT, (i / TARGET_COUNT) * 100)
                records = []

        if records:
            await conn.copy_records_to_table("products", records=records, columns=columns)
            logger.info("Inserted final batch up to %d", TARGET_COUNT)

        # Update sequence so next inserts start at TARGET_COUNT + 1
        await conn.execute("SELECT setval(pg_get_serial_sequence('products', 'id'), (SELECT MAX(id) FROM products));")

        final_count = await conn.fetchval("SELECT COUNT(*) FROM products")
        elapsed = time.time() - start_time
        logger.info("Seeding completed successfully! Total rows: %d in %.2f seconds.", final_count, elapsed)

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(seed_database())
