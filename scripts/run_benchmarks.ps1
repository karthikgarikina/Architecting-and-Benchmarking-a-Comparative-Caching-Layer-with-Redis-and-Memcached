New-Item -ItemType Directory -Force -Path 'results'

"=== Benchmarking Redis 7 ===" | Out-File -FilePath 'results/redis_bench.txt' -Encoding utf8
"Workload: 9:1 Read/Write (Set:Get 1:9), Gaussian Key Distribution, 2048 Bytes" | Out-File -FilePath 'results/redis_bench.txt' -Append -Encoding utf8
"================================================================" | Out-File -FilePath 'results/redis_bench.txt' -Append -Encoding utf8

$pipelines = @(1, 10, 50)
foreach ($p in $pipelines) {
    Write-Host "Running Redis Pipeline $p ..."
    "`n------------------------------------------------------------" | Out-File -FilePath 'results/redis_bench.txt' -Append -Encoding utf8
    "REDIS PIPELINE DEPTH: $p" | Out-File -FilePath 'results/redis_bench.txt' -Append -Encoding utf8
    "------------------------------------------------------------" | Out-File -FilePath 'results/redis_bench.txt' -Append -Encoding utf8
    docker run --rm --network caching-network redislabs/memtier_benchmark:latest -s redis -p 6379 --protocol=redis --pipeline=$p --ratio=1:9 --key-pattern=G:G -d 2048 -n 5000 -c 5 -t 2 --hide-histogram | Out-File -FilePath 'results/redis_bench.txt' -Append -Encoding utf8
}

"=== Benchmarking Memcached 1.6 ===" | Out-File -FilePath 'results/memcached_bench.txt' -Encoding utf8
"Workload: 9:1 Read/Write (Set:Get 1:9), Gaussian Key Distribution, 2048 Bytes" | Out-File -FilePath 'results/memcached_bench.txt' -Append -Encoding utf8
"================================================================" | Out-File -FilePath 'results/memcached_bench.txt' -Append -Encoding utf8

foreach ($p in $pipelines) {
    Write-Host "Running Memcached Pipeline $p ..."
    "`n------------------------------------------------------------" | Out-File -FilePath 'results/memcached_bench.txt' -Append -Encoding utf8
    "MEMCACHED PIPELINE DEPTH: $p" | Out-File -FilePath 'results/memcached_bench.txt' -Append -Encoding utf8
    "------------------------------------------------------------" | Out-File -FilePath 'results/memcached_bench.txt' -Append -Encoding utf8
    docker run --rm --network caching-network redislabs/memtier_benchmark:latest -s memcached -p 11211 --protocol=memcache_text --pipeline=$p --ratio=1:9 --key-pattern=G:G -d 2048 -n 5000 -c 5 -t 2 --hide-histogram | Out-File -FilePath 'results/memcached_bench.txt' -Append -Encoding utf8
}
Write-Host "Benchmark runs completed successfully!"
