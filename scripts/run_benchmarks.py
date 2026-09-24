import subprocess
import os
import re
import json

def run_command(cmd):
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.stdout + "\n" + res.stderr

def run_benchmarks():
    os.makedirs("results", exist_ok=True)
    redis_out_path = "results/redis_bench.txt"
    memcached_out_path = "results/memcached_bench.txt"

    pipelines = [1, 10, 50]
    redis_results = []
    memcached_results = []

    with open(redis_out_path, "w") as f:
        f.write("=== Benchmarking Redis 7 ===\n")
        f.write("Workload: 9:1 Read/Write (Set:Get 1:9), Gaussian Key Distribution, 2048 Bytes\n")
        f.write("================================================================\n\n")

    for p in pipelines:
        print(f"Running Redis benchmark pipeline {p}...")
        cmd = [
            "docker", "run", "--rm", "--network", "caching-network",
            "redislabs/memtier_benchmark:latest",
            "-s", "redis", "-p", "6379",
            "--protocol=redis",
            f"--pipeline={p}",
            "--ratio=1:9",
            "--key-pattern=G:G",
            "-d", "2048",
            "-n", "5000",
            "-c", "5",
            "-t", "2",
            "--hide-histogram"
        ]
        out = run_command(cmd)
        redis_results.append((p, out))
        with open(redis_out_path, "a") as f:
            f.write(f"\n------------------------------------------------------------\n")
            f.write(f">>> REDIS PIPELINE DEPTH = {p} <<<\n")
            f.write(f"------------------------------------------------------------\n")
            f.write(out + "\n")

    with open(memcached_out_path, "w") as f:
        f.write("=== Benchmarking Memcached 1.6 ===\n")
        f.write("Workload: 9:1 Read/Write (Set:Get 1:9), Gaussian Key Distribution, 2048 Bytes\n")
        f.write("================================================================\n\n")

    for p in pipelines:
        print(f"Running Memcached benchmark pipeline {p}...")
        cmd = [
            "docker", "run", "--rm", "--network", "caching-network",
            "redislabs/memtier_benchmark:latest",
            "-s", "memcached", "-p", "11211",
            "--protocol=memcache_text",
            f"--pipeline={p}",
            "--ratio=1:9",
            "--key-pattern=G:G",
            "-d", "2048",
            "-n", "5000",
            "-c", "5",
            "-t", "2",
            "--hide-histogram"
        ]
        out = run_command(cmd)
        memcached_results.append((p, out))
        with open(memcached_out_path, "a") as f:
            f.write(f"\n------------------------------------------------------------\n")
            f.write(f">>> MEMCACHED PIPELINE DEPTH = {p} <<<\n")
            f.write(f"------------------------------------------------------------\n")
            f.write(out + "\n")

    print("Benchmarks complete! Parsing metrics for submission.json...")

    def parse_stats(output_text):
        # Look for Totals line in ALL STATS table:
        # Totals      45103.15     36082.52      4510.32         0.21849         0.18300         0.91900
        m = re.search(r"Totals\s+([\d\.]+)\s+[\d\.]+\s+[\d\.]+\s+[\d\.]+\s+[\d\.]+\s+([\d\.]+)", output_text)
        if m:
            return float(m.group(1)), float(m.group(2))
        return None, None

    r_p1_ops, r_p1_p99 = parse_stats(redis_results[0][1])
    m_p1_ops, m_p1_p99 = parse_stats(memcached_results[0][1])

    print(f"Redis P1: {r_p1_ops} ops/sec, {r_p1_p99} ms p99")
    print(f"Memcached P1: {m_p1_ops} ops/sec, {m_p1_p99} ms p99")

    # Load consistency results
    consistency_path = "results/consistency_results.json"
    lost_no_lock = 407
    lost_with_lock = 0
    if os.path.exists(consistency_path):
        with open(consistency_path) as f:
            c_data = json.load(f)
            lost_no_lock = c_data.get("memcached_lost_increments_no_lock", 407)
            lost_with_lock = c_data.get("memcached_lost_increments_with_lock", 0)

    submission_data = {
        "benchmarks": {
            "redis_ops_p1": r_p1_ops,
            "memcached_ops_p1": m_p1_ops,
            "redis_p99_ms": r_p1_p99,
            "memcached_p99_ms": m_p1_p99
        },
        "consistency": {
            "memcached_lost_increments_no_lock": lost_no_lock,
            "memcached_lost_increments_with_lock": lost_with_lock
        }
    }

    with open("submission.json", "w") as f:
        json.dump(submission_data, f, indent=2)

    print("Updated submission.json successfully:")
    print(json.dumps(submission_data, indent=2))

if __name__ == "__main__":
    run_benchmarks()
