#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8002}"
URL="${BASE_URL}/ride-readiness"
MAX_SEC=8
TMPFILE=$(mktemp /tmp/smoke_ride_readiness.XXXXXX)
trap "rm -f $TMPFILE" EXIT

PASS=0
FAIL=0

log_ok()  { echo "  [PASS] $1"; PASS=$((PASS+1)); }
log_fail(){ echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "=== Smoke test: ${URL} ==="

# 1. Response not empty
HTTP_CODE=$(curl -sS --max-time ${MAX_SEC} -o "$TMPFILE" -w '%{http_code}' "${URL}" 2>/dev/null || true)
if [ -z "${HTTP_CODE}" ] || [ "${HTTP_CODE}" = "000" ]; then
    log_fail "No HTTP response (timeout or connection refused)"
    exit 1
fi
log_ok "HTTP ${HTTP_CODE}"

# 2. Response body not empty
if [ ! -s "$TMPFILE" ]; then
    log_fail "Response body empty"
    exit 1
fi
log_ok "Response body non-empty (size: $(wc -c < "$TMPFILE") bytes)"

# 3. Parseable JSON
if ! jq -e . "$TMPFILE" >/dev/null 2>&1; then
    log_fail "Response is not valid JSON"
    echo "--- Raw response ---"
    cat "$TMPFILE"
    exit 1
fi
log_ok "Valid JSON"

# 4. Check required fields exist
for f in ok status source updatedAt warnings; do
    if ! jq -e ".${f}" "$TMPFILE" >/dev/null 2>&1; then
        log_fail "Missing required field: ${f}"
    else
        log_ok "Field present: ${f}"
    fi
done

# 5. If ok=true, check wPrimeKj, ltpWatts, ftpWatts
OK_VAL=$(jq -r '.ok' "$TMPFILE")
STATUS_VAL=$(jq -r '.status' "$TMPFILE")
echo "  [INFO] ok=${OK_VAL} status=${STATUS_VAL}"

if [ "${OK_VAL}" = "true" ]; then
    for f in wPrimeKj ltpWatts ftpWatts; do
        VAL=$(jq -r ".${f}" "$TMPFILE")
        if [ "${VAL}" = "null" ] || [ "${VAL}" = "" ]; then
            log_fail "${f} is null/empty but ok=true"
        else
            log_ok "${f}=${VAL}"
        fi
    done
fi

# 6. If ok=false, check warnings or reasons
if [ "${OK_VAL}" = "false" ]; then
    WARN_COUNT=$(jq -r '.warnings | length' "$TMPFILE")
    REASONS_COUNT=$(jq -r '.reasons | length' "$TMPFILE" 2>/dev/null || echo "0")
    echo "  [INFO] warnings=${WARN_COUNT} reasons=${REASONS_COUNT}"
    if [ "${WARN_COUNT}" -eq 0 ] && [ "${REASONS_COUNT}" -eq 0 ]; then
        log_fail "ok=false but no warnings or reasons"
    fi
fi

echo "=== Smoke test complete: ${PASS} passed, ${FAIL} failed ==="
[ "${FAIL}" -eq 0 ] && exit 0 || exit 1
