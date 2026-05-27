#!/bin/bash
# Install QBot unified CLI wrapper to /usr/local/bin/qbot
# Usage: sudo ./scripts/install-qbot-wrapper.sh [--force]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE="$REPO_DIR/scripts/qbot"
TARGET="/usr/local/bin/qbot"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

echo "=== QBot Wrapper Install ==="
echo "  Source: $SOURCE"
echo "  Target: $TARGET"
echo "  Repo:   $REPO_DIR"
echo "  Venv:   $REPO_DIR/.venv/bin/python"
echo ""

# ── Validate source ──────────────────────────────────────────────────────
if [ ! -f "$SOURCE" ]; then
    echo "ERROR: Source wrapper not found at $SOURCE"
    exit 1
fi

if ! grep -q '^#!/bin/bash' "$SOURCE"; then
    echo "ERROR: $SOURCE does not look like a bash wrapper"
    exit 1
fi

# ── Backup existing wrapper ──────────────────────────────────────────────
if [ -f "$TARGET" ]; then
    BACKUP="${TARGET}.bak.${TIMESTAMP}"
    echo "  Backing up current wrapper to $BACKUP"
    cp "$TARGET" "$BACKUP"
    chmod 644 "$BACKUP"
fi

# ── Install ──────────────────────────────────────────────────────────────
cp "$SOURCE" "$TARGET"
chmod +x "$TARGET"

echo ""
echo "✓ Installed: $TARGET"
echo "  Version:   $(head -3 "$TARGET" | grep -i 'version' || echo 'scripts/qbot (from repo)')"
echo "  Repo path: $REPO_DIR"
echo ""

# ── Quick sanity check ───────────────────────────────────────────────────
echo "  Sanity check:"
if command -v qbot &>/dev/null; then
    QBOT_PATH="$(command -v qbot)"
    echo "    which qbot → $QBOT_PATH"
    if [ "$QBOT_PATH" = "$TARGET" ]; then
        echo "    ✓ Path matches target"
    else
        echo "    ⚠ Path differs from target: $QBOT_PATH vs $TARGET"
        echo "    (check PATH ordering if needed)"
    fi
else
    echo "    ⚠ qbot not found in PATH"
fi

echo ""
echo "  Usage: qbot {nutrition|health|calendar|qcal|planning|ask|telegram|status|query|query-plan|query-understand}"
echo ""
echo "  Test:   qbot --help  (shows usage)"
