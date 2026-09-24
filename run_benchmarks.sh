#!/usr/bin/env bash
set -e

# Ensure results directory exists
mkdir -p results

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
MEMCACHED_HOST="${MEMCACHED_HOST:-memcached}"
MEMCACHED_PORT="${MEMCACHED_PORT:-11211}"
NETWORK="${DOCKER_NETWORK:-caching-network}"

PIPELINES=(1 10 50)
DATA_SIZE=2048
# In memtier_benchmark, --ratio is SET:GET. A 9:1 Read/Write workload corresponds to 1:9 (1 SET : 9 GETs).
RATIO="1:9"
KEY_PATTERN="G:G"
REQUESTS=5000
CLIENTS=5
THREADS=2

echo "=========================================================="
echo " Starting memtier_benchmark Comparison Suite"
echo " Redis: $REDIS_HOST:$REDIS_PORT | Memcached: $MEMCACHED_HOST:$MEMCACHED_PORT"
echo " Workload: 9:1 Read/Write (Set:Get 1:9) | Distribution: Gaussian (G:G) | Data: ${DATA_SIZE}B"
echo "=========================================================="

# Check if memtier_benchmark is installed locally or should run via docker
RUN_CMD=""
if command -v memtier_benchmark &> /dev/null; then
    RUN_CMD="memtier_benchmark"
elif command -v docker &> /dev/null; then
    RUN_CMD="docker run --rm --network $NETWORK redislabs/memtier_benchmark:latest"
else
    echo "Error: Neither memtier_benchmark nor docker found in PATH."
    exit 1
fi

REDIS_OUT="results/redis_bench.txt"
MEMCACHED_OUT="results/memcached_bench.txt"

echo "=== Benchmarking Redis 7 ===" > "$REDIS_OUT"
echo "Timestamp: $(date)" >> "$REDIS_OUT"
echo "Workload: 9:1 Read/Write (Set:Get 1:9), Gaussian Key Distribution, 2048 Bytes" >> "$REDIS_OUT"
echo "================================================================" >> "$REDIS_OUT"

for p in "${PIPELINES[@]}"; do
    echo "Running Redis benchmark with Pipeline Depth: $p ..."
    echo -e "\n------------------------------------------------------------" >> "$REDIS_OUT"
    echo ">>> REDIS PIPELINE DEPTH = $p <<<" >> "$REDIS_OUT"
    echo "------------------------------------------------------------" >> "$REDIS_OUT"
    
    $RUN_CMD \
        -s "$REDIS_HOST" -p "$REDIS_PORT" \
        --protocol=redis \
        --pipeline="$p" \
        --ratio="$RATIO" \
        --key-pattern="$KEY_PATTERN" \
        --data-size="$DATA_SIZE" \
        --requests="$REQUESTS" \
        --clients="$CLIENTS" \
        --threads="$THREADS" \
        --hide-histogram >> "$REDIS_OUT" 2>&1 || true
done

echo "Redis benchmarks complete. Results saved to $REDIS_OUT."

echo "=== Benchmarking Memcached 1.6 ===" > "$MEMCACHED_OUT"
echo "Timestamp: $(date)" >> "$MEMCACHED_OUT"
echo "Workload: 9:1 Read/Write (Set:Get 1:9), Gaussian Key Distribution, 2048 Bytes" >> "$MEMCACHED_OUT"
echo "================================================================" >> "$MEMCACHED_OUT"

for p in "${PIPELINES[@]}"; do
    echo "Running Memcached benchmark with Pipeline Depth: $p ..."
    echo -e "\n------------------------------------------------------------" >> "$MEMCACHED_OUT"
    echo ">>> MEMCACHED PIPELINE DEPTH = $p <<<" >> "$MEMCACHED_OUT"
    echo "------------------------------------------------------------" >> "$MEMCACHED_OUT"
    
    $RUN_CMD \
        -s "$MEMCACHED_HOST" -p "$MEMCACHED_PORT" \
        --protocol=memcache_text \
        --pipeline="$p" \
        --ratio="$RATIO" \
        --key-pattern="$KEY_PATTERN" \
        --data-size="$DATA_SIZE" \
        --requests="$REQUESTS" \
        --clients="$CLIENTS" \
        --threads="$THREADS" \
        --hide-histogram >> "$MEMCACHED_OUT" 2>&1 || true
done

echo "Memcached benchmarks complete. Results saved to $MEMCACHED_OUT."
echo "=========================================================="
echo " Benchmark suite finished successfully."
echo "=========================================================="
