#!/bin/bash
# Setup GitHub Secrets for CI/CD Pipeline
# Run this script to configure all required secrets for the CI/CD pipeline

set -e

echo "=========================================="
echo "GitHub Secrets Setup for Boss Workflow"
echo "=========================================="
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed."
    echo "Install it from: https://cli.github.com/"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ Not authenticated with GitHub."
    echo "Run: gh auth login"
    exit 1
fi

echo "✅ GitHub CLI is authenticated"
echo ""

# Repository information
REPO="outwareai/boss-workflow"
echo "Repository: $REPO"
echo ""

# Function to set a secret
set_secret() {
    local secret_name=$1
    local secret_description=$2
    local optional=${3:-false}

    echo "Setting: $secret_name"
    echo "Description: $secret_description"

    if [ "$optional" = true ]; then
        read -p "Skip this secret? (y/N): " skip
        if [ "$skip" = "y" ] || [ "$skip" = "Y" ]; then
            echo "⏭️ Skipped"
            echo ""
            return
        fi
    fi

    read -sp "Enter value for $secret_name: " secret_value
    echo ""

    if [ -z "$secret_value" ]; then
        echo "⚠️ Empty value, skipping..."
        echo ""
        return
    fi

    gh secret set "$secret_name" --repo "$REPO" --body "$secret_value"
    echo "✅ Secret set successfully"
    echo ""
}

echo "=========================================="
echo "Required Secrets"
echo "=========================================="
echo ""

# Required secrets
set_secret "RAILWAY_TOKEN" "Railway API token for deployments (get from railway.app/account/tokens)"
set_secret "TELEGRAM_BOT_TOKEN" "Telegram bot token for E2E tests (from @BotFather)"
set_secret "TELEGRAM_BOSS_CHAT_ID" "Boss's Telegram chat ID for E2E tests"
set_secret "DEEPSEEK_API_KEY" "DeepSeek API key for integration tests"

echo "=========================================="
echo "Optional Secrets"
echo "=========================================="
echo ""

# Optional secrets
set_secret "CODECOV_TOKEN" "Codecov token for coverage reports (optional)" true
set_secret "DISCORD_WEBHOOK_URL" "Discord webhook for notifications (optional)" true

echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "✅ All secrets have been configured"
echo ""
echo "Next steps:"
echo "1. Verify secrets: gh secret list --repo $REPO"
echo "2. Setup branch protection rules (see .github/BRANCH_PROTECTION.md)"
echo "3. Push a commit to trigger the CI pipeline"
echo ""
