#!/usr/bin/env bash
set -euo pipefail

LOCAL_URL="${LOCAL_URL:-http://127.0.0.1:8002/photos/activities?days=30}"
PUBLIC_URL="${PUBLIC_URL:-https://qbot.cytr.us/photos/activities?days=30}"
MAX_SEC="${MAX_SEC:-8}"

check_url() {
    local label="$1"
    local url="$2"
    local tmp
    tmp="$(mktemp /tmp/smoke_photos_activities.XXXXXX)"
    trap 'rm -f "$tmp"' RETURN

    echo "=== ${label}: ${url} ==="
    http_code="$(curl -sS --max-time "${MAX_SEC}" -o "$tmp" -w '%{http_code}' "${url}" || true)"
    echo "HTTP ${http_code}"
    if [ "${http_code}" != "200" ]; then
        echo "FAIL: HTTP request failed"
        cat "$tmp" 2>/dev/null || true
        return 1
    fi

    python3 -m json.tool "$tmp" >/dev/null
    python3 - <<'PY' "$tmp"
import json
import sys
from datetime import datetime

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    actual = json.load(fh)
if not isinstance(actual, dict) or not isinstance(actual.get("activities"), list):
    raise SystemExit(f"unexpected payload shape: {actual!r}")
if not actual["activities"]:
    raise SystemExit("activities list is empty")

required = {"id", "source", "title", "startLocal", "endLocal", "distanceKm", "durationSec"}
starts = []
for item in actual["activities"]:
    if not isinstance(item, dict):
        raise SystemExit(f"unexpected activity item: {item!r}")
    missing = required - set(item)
    if missing:
        raise SystemExit(f"missing fields {sorted(missing)} in {item!r}")
    starts.append(datetime.fromisoformat(str(item["startLocal"]).replace("Z", "+00:00")))

if starts != sorted(starts, reverse=True):
    raise SystemExit("activities are not sorted newest-first")

print("OK")
PY
}

check_url "LOCAL" "${LOCAL_URL}"
check_url "PUBLIC" "${PUBLIC_URL}"
