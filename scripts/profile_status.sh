#!/usr/bin/env bash
set -uo pipefail

APP_DIR="/opt/qbot/app"
PROFILE="${1:-}"

if [[ -z "$PROFILE" || ! "$PROFILE" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  echo "Usage: $0 PROFILE" >&2
  exit 2
fi

ENV_FILE="$APP_DIR/config/profiles/$PROFILE.env"
LOG_FILE="$APP_DIR/logs/hammerhead-garmin-sync-$PROFILE.log"

echo "Profile: $PROFILE"
echo "Env exists: $([[ -r "$ENV_FILE" ]] && echo yes || echo no)"

if [[ ! -r "$ENV_FILE" ]]; then
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

echo "HAMMERHEAD_USER_ID: ${HAMMERHEAD_USER_ID:-}"
echo "HAMMERHEAD_REFRESH_TOKEN: $([[ -n "${HAMMERHEAD_REFRESH_TOKEN:-}" ]] && echo present || echo missing)"
echo "HAMMERHEAD_TOKENSTORE: ${HAMMERHEAD_TOKENSTORE:-}"
echo "GARMIN_TOKENSTORE: ${GARMIN_TOKENSTORE:-}"
echo "PROCESSED_STATE: ${PROCESSED_STATE:-}"
echo "OUTGOING_DIR: ${OUTGOING_DIR:-}"

"$APP_DIR/.venv/bin/python" - "$PROCESSED_STATE" "$OUTGOING_DIR" <<'PY'
import json
import sys
from pathlib import Path

processed_path = Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else Path("")
outgoing_dir = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else Path("")

items = []
if processed_path and processed_path.exists():
    try:
        payload = json.loads(processed_path.read_text(encoding="utf-8"))
        raw = payload.get("processed", []) if isinstance(payload, dict) else payload
        items = [item for item in raw if isinstance(item, dict)]
    except Exception:
        items = []

print(f"Processed entries: {len(items)}")
if items:
    last = max(items, key=lambda item: item.get("updatedAt", ""))
    print(f"Last processed status: {last.get('status', '')} {last.get('activityId', '')} {last.get('updatedAt', '')}")
else:
    print("Last processed status: none")

reports_dir = outgoing_dir / "reports" if outgoing_dir else Path("")
reports = sorted(reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if reports_dir.exists() else []
print(f"Last report: {reports[0] if reports else 'none'}")
PY

echo "Last 20 log lines:"
if [[ -r "$LOG_FILE" ]]; then
  tail -n 20 "$LOG_FILE"
else
  echo "no log"
fi
