-- Schema and Data Initialization for Product Catalog
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

-- Fast bulk seed of 100,000 products (~2KB each) using generate_series
DO $$
DECLARE
    current_cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO current_cnt FROM products;
    IF current_cnt < 100000 THEN
        RAISE NOTICE 'Seeding 100,000 products...';

        INSERT INTO products (
            id, name, description, price, category, sku, stock,
            attributes, specifications, reviews_summary, created_at, updated_at
        )
        SELECT
            i AS id,
            (ARRAY['Electronics', 'Computers', 'Smartphones', 'Audio', 'Cameras', 'Wearables', 'Gaming', 'Home Appliances', 'Networking', 'Office Supplies'])[1 + (i % 10)]
            || ' Pro Series Model ' || i AS name,

            'Engineered with ultra-precision aerospace-grade aluminum casing, multi-core accelerated processing architecture, and next-generation low-latency dynamic interfaces. Features high-dynamic-range true-color calibration, dual-band beamforming antenna arrays, enterprise-grade thermal dispersion dissipation baffles, and dedicated coprocessors for real-time sensor processing and telemetry data aggregation. Designed specifically for demanding high-throughput continuous operational workflows, mission-critical infrastructure deployments, and seamless distributed edge computing ecosystem integration with industry-standard protocols. Extended testing verifies sub-millisecond bus interconnect transaction latencies and resilience under extreme vibration and thermal gradients.' AS description,

            ROUND((19.99 + (i % 1500) * 1.25)::numeric, 2) AS price,

            (ARRAY['Electronics', 'Computers', 'Smartphones', 'Audio', 'Cameras', 'Wearables', 'Gaming', 'Home Appliances', 'Networking', 'Office Supplies'])[1 + (i % 10)] AS category,

            'SKU-' || UPPER(SUBSTRING((ARRAY['Electronics', 'Computers', 'Smartphones', 'Audio', 'Cameras', 'Wearables', 'Gaming', 'Home Appliances', 'Networking', 'Office Supplies'])[1 + (i % 10)] FROM 1 FOR 3)) || '-' || LPAD(i::text, 7, '0') AS sku,

            10 + (i % 990) AS stock,

            jsonb_build_object(
                'color', (ARRAY['Space Gray', 'Silver', 'Midnight Black', 'Arctic White', 'Deep Blue'])[1 + (i % 5)],
                'weight_grams', 450 + (i % 1200),
                'dimensions_mm', jsonb_build_object('length', 210, 'width', 140, 'height', 28),
                'material', 'Recycled Aluminum & Polycarbonate Composite',
                'certifications', jsonb_build_array('FCC', 'CE', 'RoHS', 'ISO9001', 'EnergyStar'),
                'origin_country', 'Taiwan',
                'warranty_months', 24,
                'is_waterproof', (i % 2 = 0),
                'ip_rating', CASE WHEN (i % 2 = 0) THEN 'IP68' ELSE 'IP54' END
            ) AS attributes,

            jsonb_build_object(
                'architecture', 'Armv9 64-bit multi-cluster',
                'core_count', 8 + (i % 8) * 2,
                'clock_speed_ghz', ROUND((2.4 + (i % 16) * 0.1)::numeric, 2),
                'memory_capacity_gb', 16 * (1 + (i % 4)),
                'storage_nvme_tb', 1 + (i % 4),
                'bus_bandwidth_gbps', 128.0,
                'thermal_design_power_watts', 65 + (i % 30),
                'supported_codecs', jsonb_build_array('AV1', 'H.265/HEVC', 'ProRes RAW', 'VP9', 'Opus'),
                'network_interfaces', jsonb_build_array('2.5GbE LAN', 'Wi-Fi 6E (802.11ax)', 'Bluetooth 5.3 Low Energy')
            ) AS specifications,

            'Comprehensive engineering benchmark tests reveal unmatched throughput and efficiency under continuous heavy load. Thermal management remains remarkably silent under sustained workloads, and API integration into existing distributed infrastructure was straightforward and well-documented. Highly recommended for enterprise production deployment.' AS reviews_summary,

            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM generate_series(1, 100000) AS i;

        PERFORM setval(pg_get_serial_sequence('products', 'id'), (SELECT MAX(id) FROM products));
        RAISE NOTICE 'Successfully seeded 100,000 products.';
    ELSE
        RAISE NOTICE 'Products table already contains % rows. Skipping seeding.', current_cnt;
    END IF;
END $$;
