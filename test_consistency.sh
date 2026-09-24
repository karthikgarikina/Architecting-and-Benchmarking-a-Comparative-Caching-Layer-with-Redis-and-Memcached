#!/usr/bin/env bash
set -e

echo "Running Consistency Test inside container..."
docker exec caching-app python app/scripts/test_consistency.py
docker cp caching-app:/workspace/results/consistency_results.json results/consistency_results.json
echo ""
echo "Consistency test completed successfully! Results written to results/consistency_results.json"
