#!/bin/bash

###############################################################################
# Pre-Deployment Smoke Tests
#
# This script runs critical smoke tests before deploying to production.
# If ANY critical test fails, deployment is BLOCKED.
#
# Usage:
#   ./scripts/pre_deploy_check.sh          # Run all smoke tests
#   ./scripts/pre_deploy_check.sh verbose  # Show detailed output
#
# Exit codes:
#   0 = All tests passed - safe to deploy
#   1 = One or more tests failed - BLOCKING deployment
###############################################################################

set -e

VERBOSE="${1:-}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "PRE-DEPLOYMENT SMOKE TESTS"
echo "=========================================="
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}ERROR: pytest not found${NC}"
    echo "Install with: pip install -r requirements.txt"
    exit 1
fi

# Run critical intent tests
echo -e "${YELLOW}Running critical intent smoke tests...${NC}"
echo ""

if [ "$VERBOSE" = "verbose" ]; then
    PYTEST_ARGS="-v --tb=short"
else
    PYTEST_ARGS="-q --tb=short"
fi

if pytest tests/smoke/test_critical_intents.py $PYTEST_ARGS; then
    SMOKE_RESULT=0
else
    SMOKE_RESULT=1
fi

echo ""
echo "=========================================="

if [ $SMOKE_RESULT -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CRITICAL TESTS PASSED${NC}"
    echo "Status: Safe to deploy"
    echo "=========================================="
    exit 0
else
    echo -e "${RED}❌ CRITICAL TESTS FAILED${NC}"
    echo "Status: BLOCKING DEPLOYMENT"
    echo ""
    echo "Action required:"
    echo "1. Review test output above"
    echo "2. Fix failing tests"
    echo "3. Run this script again"
    echo "4. Once tests pass, deployment will proceed"
    echo "=========================================="
    exit 1
fi
