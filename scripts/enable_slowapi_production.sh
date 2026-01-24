#!/bin/bash
# Enable Slowapi Rate Limiting in Production on Railway
#
# This script sets up all Railway environment variables for slowapi rate limiting.
# Usage: ./scripts/enable_slowapi_production.sh
#
# Prerequisites:
# 1. Railway CLI installed: https://docs.railway.app/cli/cli
# 2. Logged in to Railway: railway login
# 3. Project selected: railway select -p boss-workflow
#

set -e

echo "======================================"
echo "Enabling Slowapi Rate Limiting"
echo "======================================"
echo ""

# Check if railway CLI is available
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Please install it:"
    echo "   https://docs.railway.app/cli/cli"
    exit 1
fi

# Check if user is logged in
if ! railway whoami &> /dev/null; then
    echo "❌ Not logged in to Railway. Please run: railway login"
    exit 1
fi

echo "📋 Fetching current variables..."
echo ""

# Get current environment
CURRENT_ENV=$(railway variables -s boss-workflow 2>/dev/null | head -5 || echo "")
if [ -z "$CURRENT_ENV" ]; then
    echo "⚠️  Could not fetch current variables. Make sure project is selected."
    echo "   Run: railway select -p boss-workflow"
    exit 1
fi

echo "✅ Project connected: boss-workflow"
echo ""

# Display current rate limiting status
echo "📊 Current Rate Limiting Status:"
echo "================================"
current_slowapi=$(railway variables -s boss-workflow | grep "USE_SLOWAPI_RATE_LIMITING" || echo "NOT_SET")
if [ "$current_slowapi" = "NOT_SET" ]; then
    echo "  USE_SLOWAPI_RATE_LIMITING: Not set (will use custom middleware)"
else
    echo "  USE_SLOWAPI_RATE_LIMITING: $current_slowapi"
fi

current_auth=$(railway variables -s boss-workflow | grep "RATE_LIMIT_AUTHENTICATED" || echo "NOT_SET")
if [ "$current_auth" = "NOT_SET" ]; then
    echo "  RATE_LIMIT_AUTHENTICATED: Not set"
else
    echo "  RATE_LIMIT_AUTHENTICATED: $current_auth"
fi

current_public=$(railway variables -s boss-workflow | grep "RATE_LIMIT_PUBLIC" || echo "NOT_SET")
if [ "$current_public" = "NOT_SET" ]; then
    echo "  RATE_LIMIT_PUBLIC: Not set"
else
    echo "  RATE_LIMIT_PUBLIC: $current_public"
fi

echo ""

# Confirm before making changes
read -p "Continue with enabling slowapi rate limiting? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "❌ Cancelled"
    exit 0
fi

echo ""
echo "🚀 Setting environment variables..."
echo "===================================="

# Set the variables
echo "Setting USE_SLOWAPI_RATE_LIMITING=true..."
railway variables set USE_SLOWAPI_RATE_LIMITING=true -s boss-workflow

echo "Setting RATE_LIMIT_AUTHENTICATED=100/minute..."
railway variables set RATE_LIMIT_AUTHENTICATED="100/minute" -s boss-workflow

echo "Setting RATE_LIMIT_PUBLIC=20/minute..."
railway variables set RATE_LIMIT_PUBLIC="20/minute" -s boss-workflow

echo ""
echo "✅ Variables set successfully!"
echo ""

# Verify the changes
echo "📋 Verifying configuration..."
echo "================================"
railway variables -s boss-workflow | grep -E "USE_SLOWAPI_RATE_LIMITING|RATE_LIMIT_AUTHENTICATED|RATE_LIMIT_PUBLIC"

echo ""
echo "📝 Next Steps:"
echo "============="
echo "1. Commit your code changes:"
echo "   git add ."
echo "   git commit -m 'feat(rate-limit): Enable slowapi in production with monitoring'"
echo "   git push"
echo ""
echo "2. Wait for auto-deployment (2-3 minutes)"
echo ""
echo "3. Verify deployment:"
echo "   python test_full_loop.py verify-deploy"
echo ""
echo "4. Monitor logs:"
echo "   railway logs -s boss-workflow -f --lines 100 | grep -i rate"
echo ""
echo "5. Run tests:"
echo "   python test_full_loop.py test-all"
echo ""
echo "🎯 For detailed monitoring guide, see:"
echo "   docs/PRODUCTION_VALIDATION.md"
echo ""

