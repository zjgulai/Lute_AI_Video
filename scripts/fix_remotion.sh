#!/bin/bash
# One-click Remotion binding fix for the current platform
set -e

RENDERING_DIR="$(cd "$(dirname "$0")/../rendering" && pwd)"
cd "$RENDERING_DIR"

echo "=== Remotion Binding Fix ==="
echo "Platform: $(uname -s) $(uname -m)"
echo "Working dir: $RENDERING_DIR"

# Backup node_modules
if [ -d node_modules.bak ]; then
    rm -rf node_modules.bak
fi
if [ -d node_modules ]; then
    mv node_modules node_modules.bak
    echo "Backed up old node_modules to node_modules.bak"
fi

# Remove lock to force fresh resolution
rm -f package-lock.json

# Fresh install for current platform
echo "Installing dependencies for current platform..."
npm install

# Verify
echo ""
echo "=== Verification ==="
if npx remotion --version 2>/dev/null; then
    echo "✓ Remotion is working!"
else
    echo "✗ Remotion still has binding issues."
    echo ""
    echo "Try manually installing platform-specific packages:"
    ARCH=$(uname -m)
    case "$ARCH" in
        arm64|aarch64) PLAT="arm64" ;;
        x86_64)        PLAT="x64" ;;
        *)             PLAT="$ARCH" ;;
    esac
    echo "  npm install @rspack/binding-linux-${PLAT}-gnu"
    echo "  npm install @remotion/compositor-linux-${PLAT}-gnu"
    echo ""
    echo "If that fails, try building from source:"
    echo "  npm rebuild"
fi

echo "=== Done ==="
