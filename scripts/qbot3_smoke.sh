#!/usr/bin/env bash
# QBot3 Smoke Test — run this morning to verify QBot3 is operational
# Generates JSON and Markdown reports in docs/reports/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/.."

# Auto-detect venv Python
if [ -f "$APP_DIR/.venv/bin/python3" ]; then
    PYTHON="$APP_DIR/.venv/bin/python3"
else
    PYTHON="python3"
fi
REPORT_DIR="$APP_DIR/docs/reports"
mkdir -p "$REPORT_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M)
REPORT_JSON="$REPORT_DIR/qbot3_smoke_$TIMESTAMP.json"
REPORT_MD="$REPORT_DIR/qbot3_smoke_$TIMESTAMP.md"

echo "=== QBot3 Smoke Test $TIMESTAMP ==="
echo ""

# ── 1. Environment check (no secrets) ──────────────────────────────────
echo "--- ENV CHECK ---"
echo "ALBERT_LLM_PROVIDER=${ALBERT_LLM_PROVIDER:-openai}"
echo "QBOT3_ENABLED=${QBOT3_ENABLED:-0}"
echo ""

# ── 2. Python compile all ──────────────────────────────────────────────
echo "--- COMPILE ALL ---"
cd "$APP_DIR"
COMPILE_FAIL=0
for f in qbot3/*.py qbot3/llm/*.py qbot3/adapters/*.py; do
    if $PYTHON -m py_compile "$f" 2>/dev/null; then
        echo "  OK: $f"
    else
        echo "  FAIL: $f"
        COMPILE_FAIL=1
    fi
done
echo ""

# ── 3. Import test ────────────────────────────────────────────────────
echo "--- IMPORT TEST ---"
python3 -c "
from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, PLAN_INVALID
from qbot3.tool_registry import list_all_tools, tool_descriptions
all_tools = list_all_tools()
print(f'  Tools registered: {len(all_tools)}')
descs = tool_descriptions()
print(f'  Tool descriptions: {len(descs)}')
implemented = [n for n, s in all_tools.items() if s.get(\"status\", \"\") != \"error\"]
print(f'  Implemented: {len(implemented)}')
print(f'  Sample: {list(sorted(all_tools.keys()))}')
" 2>&1 || echo "  IMPORT TEST FAILED"
echo ""

# ── 4. MCP tools/list via direct Python (no server needed) ────────────
echo "--- INTERNAL MCP TOOLS ---"
$PYTHON -c "
from qbot3.adapters.mcp_adapter import handle_qbot3_mcp
result = handle_qbot3_mcp({'method': 'tools/list', 'id': 1})
tools = [t['name'] for t in result['result']['tools']]
print(f'  MCP tools: {tools}')
assert 'qbot.query' in tools, 'qbot.query missing'
assert 'qbot.action_execute' in tools, 'qbot.action_execute missing'
print('  ✅ MCP tools list OK')
" 2>&1 || echo "  MCP TOOLS FAIL"
echo ""

# ── 5. Capability scanner ─────────────────────────────────────────────
echo "--- CAPABILITY STATUS ---"
$PYTHON -c "
from qbot3.tool_registry import list_all_tools
all_tools = list_all_tools()
read = [n for n, s in all_tools.items() if s.get('safety') != 'write' and 'error' not in s]
write = [n for n, s in all_tools.items() if s.get('safety') == 'write' and 'error' not in s]
broken = [n for n, s in all_tools.items() if 'error' in s]
print(f'  Read tools: {len(read)}')
print(f'  Write tools: {len(write)}')
if broken:
    print(f'  Broken: {broken}')
else:
    print('  ✅ All tools loaded')
" 2>&1 || echo "  CAPABILITY SCAN FAIL"
echo ""

# ── 6. Core query tests (mock provider) ────────────────────────────────
echo "--- QUERY TESTS (mock) ---"
export ALBERT_LLM_PROVIDER=mock
QUERIES=(
    "status qbot"
    "readiness qbot"
    "co jest w QBOT_KNOWHOW o LLM Orchestrator"
    "co jest w QBOT_BIBLE o QBot3"
    "co jadłem dzisiaj?"
    "jaki mam dziś bilans kalorii?"
    "jakie mam zaplanowane eventy?"
    "pokaż trasy RWGPS"
    "dlaczego nie masz danych Garmin za dziś?"
    "dodaj 0,5 kg truskawek"
    "dodaj event Bikepacking w Toskanii 4-13 czerwca 2026"
    "pokaż dostępne narzędzia"
)

RESULTS_JSON='['
FIRST=true
PASS=0
TOTAL=0

for q in "${QUERIES[@]}"; do
    TOTAL=$((TOTAL + 1))
    echo -n "  [$TOTAL/${#QUERIES[@]}] $q ... "
    RESPONSE=$(QBOT3_ENABLED=1 $PYTHON -c "
import sys, json
from qbot3.agent_runtime import orchestrate_query
try:
    r = orchestrate_query('$q')
    print(json.dumps({'status': r.get('status', 'ERROR'), 'plan': r.get('plan', {}), 'answer_len': len(r.get('answer', '')), 'req_id': r.get('request_id', '')}))
except Exception as e:
    print(json.dumps({'status': 'RUNTIME_ERROR', 'error': str(e)[:100]}))
" 2>/dev/null)
    STATUS=$(echo "$RESPONSE" | $PYTHON -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('status','PARSE_ERROR'))" 2>/dev/null || echo "NETWORK_ERROR")
    REQ_ID=$(echo "$RESPONSE" | $PYTHON -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('req_id',''))" 2>/dev/null || echo "")
    echo "$STATUS (req: $REQ_ID)"
    if [ "$STATUS" = "ok" ] || [ "$STATUS" = "draft" ] || [ "$STATUS" = "clarify" ] || [ "$STATUS" = "partial" ]; then
        PASS=$((PASS + 1))
    fi
    if $FIRST; then FIRST=false; else RESULTS_JSON+=","; fi
    RESULTS_JSON+="{\"query\":\"$q\",\"status\":\"$STATUS\"}"
done
RESULTS_JSON+="]"
echo "$RESULTS_JSON" > "$REPORT_JSON"
echo ""

# ── 7. Action draft test ──────────────────────────────────────────────
echo "--- ACTION DRAFT ---"
$PYTHON -c "
import json
from qbot3.agent_runtime import orchestrate_query
r = orchestrate_query('dodaj 0,5 kg truskawek do dzisiejszego spożycia')
ad = r.get('action_draft', {})
print(f'  Action type: {ad.get(\"action_type\")}')
print(f'  Requires confirm: {ad.get(\"requires_confirm\")}')
print(f'  Idempotency key: {ad.get(\"idempotency_key_suggestion\", \"\")[:20]}')
print(f'  Dry run available: {ad.get(\"dry_run_available\")}')
print(f'  Human summary: {ad.get(\"human_summary\", \"\")[:80]}')
# P4 contract checks
assert ad.get('action_type'), 'Missing action_type'
assert ad.get('requires_confirm') == True, 'requires_confirm must be True'
assert ad.get('idempotency_key_suggestion'), 'Missing idempotency_key_suggestion'
print('  ✅ P4 draft contract OK')
" 2>&1 || echo "  ACTION DRAFT FAIL"
echo ""

# ── 8. Action execute dry_run ─────────────────────────────────────────
echo "--- ACTION EXECUTE DRY RUN ---"
$PYTHON -c "
import json
from qbot3.adapters.mcp_adapter import handle_qbot3_mcp
result = handle_qbot3_mcp({
    'method': 'tools/call',
    'id': 1,
    'params': {
        'name': 'qbot.action_execute',
        'arguments': {
            'action_type': 'calendar_event_add',
            'payload_json': {'date_start': '2026-07-01', 'title': 'Test Dry Run', 'event_type': 'note'},
            'idempotency_key': 'test_dry_run_qbot3',
            'confirm': True,
            'dry_run': True,
        }
    }
})
content = result['result']['content'][0]
data = json.loads(content['text'])
print(f'  Status: {data.get(\"status\")}')
print(f'  Dry run: {data.get(\"dry_run\")}')
if data.get('note'):
    print(f'  Note: {data.get(\"note\")}')
" 2>&1 || echo "  ACTION EXECUTE DRY RUN FAIL"
echo ""

# ── 9. Docs search test ───────────────────────────────────────────────
echo "--- DOCS SEARCH ---"
$PYTHON -c "
from qbot3.tool_registry import lookup
docs_tool = lookup('canonical_docs')
if docs_tool:
    print(f'  canonical_docs: {docs_tool.get(\"status\", \"implemented\")}')
else:
    print('  canonical_docs: NOT FOUND')
docs_list = lookup('docs_list_qbot')
if docs_list:
    print(f'  docs_list_qbot: {docs_list.get(\"status\", \"implemented\")}')
else:
    print('  docs_list_qbot: NOT FOUND')
" 2>&1 || echo "  DOCS SEARCH FAIL"
echo ""

# ── 10. Error taxonomy test ──────────────────────────────────────────
echo "--- ERROR TAXONOMY ---"
$PYTHON -c "
from qbot3.errors import OK, ERROR, DATA_MISSING, CONNECTOR_MISSING, AUTH_MISSING, DOC_MISSING
from qbot3.errors import NOT_IMPLEMENTED, PLAN_INVALID, SAFETY_BLOCKED, LEGACY_FALLBACK_BLOCKED
from qbot3.errors import TOOL_ERROR, PROVIDER_ERROR, READY_WITH_WARNINGS, NEEDS_LOCATION, DUPLICATE
from qbot3.errors import error_result, success_result
codes = [OK, ERROR, READY_WITH_WARNINGS, DATA_MISSING, CONNECTOR_MISSING, AUTH_MISSING, DOC_MISSING, NOT_IMPLEMENTED, PLAN_INVALID, SAFETY_BLOCKED, LEGACY_FALLBACK_BLOCKED, TOOL_ERROR, PROVIDER_ERROR, NEEDS_LOCATION, DUPLICATE]
err = error_result(DATA_MISSING, 'test')
suc = success_result({'key': 'value'})
print(f'  Codes: {len(codes)}')
print(f'  error_result: {err}')
print(f'  success_result: {suc}')
assert err['status'] == 'DATA_MISSING'
assert suc['status'] == 'OK'
print('  ✅ Error taxonomy OK')
" 2>&1 || echo "  ERROR TAXONOMY FAIL"
echo ""

# ── Summary ───────────────────────────────────────────────────────────
echo "=== SMOKE SUMMARY ==="
echo "Tests passed: $PASS/$TOTAL"
echo "Compile: $([ $COMPILE_FAIL -eq 0 ] && echo 'OK' || echo 'FAIL')"
echo "Report JSON: $REPORT_JSON"
echo "Report MD: $REPORT_MD"

# Write Markdown report
cat > "$REPORT_MD" <<MDEOF
# QBot3 Smoke Test — ${TIMESTAMP}

## Summary
- **Date**: $(date)
- **Provider**: ${ALBERT_LLM_PROVIDER:-openai}
- **QBOT3_ENABLED**: ${QBOT3_ENABLED:-0}
- **Tests passed**: $PASS/$TOTAL
- **Compile**: $([ $COMPILE_FAIL -eq 0 ] && echo 'OK' || echo 'FAIL')

## Results
| # | Query | Status |
|---|---|---|
$($PYTHON -c "
import json
with open('$REPORT_JSON') as f:
    data = json.load(f)
for i, r in enumerate(data, 1):
    q = r['query'].replace('|', '\\|')
    s = r['status']
    print(f'| {i} | {q} | {s} |')
" 2>/dev/null || echo "| - | Parse error | - |")

## Notes
- Generated by \`scripts/qbot3_smoke.sh\`
- All queries use **mock provider** (no API cost)
- Real provider test: see \`QBOT3_PROVIDER_DRY_TEST.md\`
MDEOF

echo ""
echo "Markdown report written to: $REPORT_MD"
