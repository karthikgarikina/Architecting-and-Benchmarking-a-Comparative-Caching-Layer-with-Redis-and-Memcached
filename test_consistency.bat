@echo off
echo Running Consistency Test inside container...
docker exec caching-app python app/scripts/test_consistency.py
if %ERRORLEVEL% equ 0 (
    docker cp caching-app:/workspace/results/consistency_results.json results/consistency_results.json
    echo.
    echo Consistency test completed successfully! Results written to results/consistency_results.json
) else (
    echo.
    echo Consistency test failed!
    exit /b 1
)
