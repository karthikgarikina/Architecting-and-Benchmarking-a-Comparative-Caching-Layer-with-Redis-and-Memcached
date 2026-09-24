Write-Host "Running Consistency Test inside container..." -ForegroundColor Cyan
docker exec caching-app python app/scripts/test_consistency.py
if ($LASTEXITCODE -eq 0) {
    docker cp caching-app:/workspace/results/consistency_results.json results/consistency_results.json
    Write-Host "`nConsistency test completed successfully! Results written to results/consistency_results.json" -ForegroundColor Green
} else {
    Write-Host "`nConsistency test failed!" -ForegroundColor Red
    exit 1
}
