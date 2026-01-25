#!/bin/bash
# Rollback to previous dependencies

set -e  # Exit on error

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  DEPENDENCY ROLLBACK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if backup exists
if [ ! -f "requirements.txt.backup" ]; then
    echo "❌ Error: requirements.txt.backup not found!"
    echo "Cannot rollback without backup file."
    exit 1
fi

echo "📋 Backup found: requirements.txt.backup"
echo ""

# Show what will be rolled back
echo "Changes to rollback:"
echo "  cryptography: 44.0.1 → 43.0.0"
echo "  protobuf: 5.29.3 → 6.33.4"
echo ""

# Confirm rollback
read -p "Continue with rollback? (y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Rollback cancelled"
    exit 0
fi

echo "🔄 Rolling back dependencies..."

# Backup current requirements (just in case)
cp requirements.txt requirements.txt.new

# Restore from backup
cp requirements.txt.backup requirements.txt

echo "✅ requirements.txt restored from backup"
echo ""

# Reinstall dependencies
echo "📦 Reinstalling dependencies..."
pip install -r requirements.txt --quiet

echo "✅ Dependencies reinstalled"
echo ""

# Verify rollback
echo "🔍 Verifying rollback..."
echo ""

CRYPTO_VERSION=$(pip show cryptography | grep Version | awk '{print $2}')
PROTOBUF_VERSION=$(pip show protobuf | grep Version | awk '{print $2}')

echo "  cryptography: $CRYPTO_VERSION (expected: 43.0.0)"
echo "  protobuf: $PROTOBUF_VERSION (expected: 6.33.4)"
echo ""

if [ "$CRYPTO_VERSION" == "43.0.0" ] && [ "$PROTOBUF_VERSION" == "6.33.4" ]; then
    echo "✅ Rollback verified successfully!"
    echo ""
    echo "Next steps:"
    echo "  1. Run tests: pytest tests/unit/ -v"
    echo "  2. Commit rollback: git add requirements.txt && git commit -m 'rollback: Revert dependency updates'"
    echo "  3. Push to Railway: git push"
else
    echo "⚠️  Warning: Version mismatch detected!"
    echo "  Expected cryptography 43.0.0, got $CRYPTO_VERSION"
    echo "  Expected protobuf 6.33.4, got $PROTOBUF_VERSION"
    echo ""
    echo "Manual intervention may be required."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ROLLBACK COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
