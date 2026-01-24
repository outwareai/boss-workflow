#!/bin/bash

# Run load tests in sequence
echo "Starting Boss Workflow Load Tests"
echo "=================================="
echo ""

# Check if LOAD_TEST_HOST is set
if [ -z "$LOAD_TEST_HOST" ]; then
    echo "LOAD_TEST_HOST not set, using default: http://localhost:8000"
    export LOAD_TEST_HOST="http://localhost:8000"
else
    echo "Target: $LOAD_TEST_HOST"
fi

echo ""

# Make reports directory
mkdir -p tests/load/reports

# Run benchmarks first
echo "Running performance benchmarks..."
python tests/load/benchmark.py "$LOAD_TEST_HOST"

echo ""
echo "=================================="
echo "Starting Load Test Scenarios"
echo "=================================="

# Light load (warmup)
echo ""
echo "Running light load test (100 users)..."
python tests/load/scenarios.py light

# Medium load
echo ""
echo "Running medium load test (500 users)..."
python tests/load/scenarios.py medium

# Heavy load (target: 1000 req/min)
echo ""
echo "Running heavy load test (1000 users)..."
python tests/load/scenarios.py heavy

# Spike test
echo ""
echo "Running spike test (2000 users)..."
python tests/load/scenarios.py spike

echo ""
echo "=================================="
echo "Load tests complete!"
echo "=================================="
echo "Reports available in tests/load/reports/"
echo ""
echo "Generated files:"
ls -lh tests/load/reports/
