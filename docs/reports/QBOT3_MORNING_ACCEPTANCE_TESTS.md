# QBot3 Morning Acceptance Tests — 2026-05-28 (Updated)

## Prerequisites

```bash
export QBOT3_ENABLED=1
# Optional: export ALBERT_LLM_PROVIDER=openai  (default: openai)
# For zero-cost testing: export ALBERT_LLM_PROVIDER=mock
```

## Quick Smoke Test

```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock bash /opt/qbot/app/scripts/qbot3_smoke.sh
```

## Detailed Test Suite

---

### 1. Status

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
from qbot3.agent_runtime import orchestrate_query
r = orchestrate_query('status qbot')
print(f'Status: {r.get(\"status\")}')
print(f'Orchestrator: {r.get(\"orchestrator\",{})}')
print(f'Request ID: {r.get(\"request_id\")}')
print(f'Fallback: {r.get(\"orchestrator\",{}).get(\"fallback_used\")}')
"
```

**Expected:** `status=ok`, `orchestrator.enabled=true`, `orchestrator.fallback_used=false`, `orchestrator.name=Albert`, `request_id` present

---

### 2. Readiness

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
from qbot3.agent_runtime import orchestrate_query
r = orchestrate_query('readiness qbot')
print(f'Status: {r.get(\"status\")}')
print(f'Fallback: {r.get(\"orchestrator\",{}).get(\"fallback_used\")}')
"
```

**Expected:** `status=ok` or `partial`, `fallback_used=false`

---

### 3. Docs Search — BIBLE

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
from qbot3.agent_runtime import orchestrate_query
r = orchestrate_query('co jest w QBOT_BIBLE o QBot3')
print(f'Status: {r.get(\"status\")}')
print(f'Tools: {r.get(\"plan\",{}).get(\"tools\",[])}')
print(f'Answer: {r.get(\"answer\",\"\")[:300]}')
"
```

**Expected:** `status=ok`, tools=`['canonical_docs']`, answer zawiera fragmenty z QBOT_BIBLE

---

### 4. Docs Search — KNOWHOW

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
from qbot3.agent_runtime import orchestrate_query
r = orchestrate_query('co jest w QBOT_KNOWHOW o LLM Orchestrator')
print(f'Status: {r.get(\"status\")}')
print(f'Tools: {r.get(\"plan\",{}).get(\"tools\",[])}')
print(f'Answer: {r.get(\"answer\",\"\")[:300]}')
"
```

**Expected:** `status=ok`, tools=`['canonical_docs']`, **not** `no_data`

---

### 5. Today's Meals

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
from qbot3.agent_runtime import orchestrate_query
r = orchestrate_query('co jadłem dzisiaj?')
print(f'Status: {r.get(\"status\")}')
print(f'Tools: {r.get(\"plan\",{}).get(\"tools\",[])}')
print(f'Answer: {r.get(\"answer\",\"\")[:300]}')
"
```

**Expected:** `status=ok`, tools zawiera `nutrition_day_summary` albo `nutrition_meal_list`

---

### 6. Daily Balance

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
from qbot3.agent_runtime import orchestrate_query
r = orchestrate_query('jaki mam dziś bilans kalorii?')
print(f'Status: {r.get(\"status\")}')
print(f'Tools: {r.get(\"plan\",{}).get(\"tools\",[])}')
print(f'Answer: {r.get(\"answer\",\"\")[:300]}')
"
```

**Expected:** Pokazuje kcal_in, wzmiankę o kcal_out jeśli dostępne, albo informację czego brakuje

---

### 7. Garmin Diagnostics

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
from qbot3.agent_runtime import orchestrate_query
r = orchestrate_query('dlaczego nie masz danych Garmin za dziś?')
print(f'Status: {r.get(\"status\")}')
print(f'Tools: {r.get(\"plan\",{}).get(\"tools\",[])}')
print(f'Answer: {r.get(\"answer\",\"\")[:300]}')
"
```

**Expected:** `status=ok`, tools zawiera `garmin_diagnostics`, wyjaśnia czy brak danych w DB

---

### 8. Nutrition Draft (Strawberries)

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
import json
from qbot3.agent_runtime import orchestrate_query
r = orchestrate_query('dodaj 0,5 kg truskawek do dzisiejszego spożycia')
print(f'Status: {r.get(\"status\")}')
print(f'Action draft exists: {bool(r.get(\"action_draft\"))}')
ad = r.get('action_draft', {})
print(f'action_type: {ad.get(\"action_type\")}')
print(f'requires_confirm: {ad.get(\"requires_confirm\")}')
print(f'idempotency_key_suggestion: {str(ad.get(\"idempotency_key_suggestion\",\"\"))[:20]}')
print(f'dry_run_available: {ad.get(\"dry_run_available\")}')
print(f'Answer: {r.get(\"answer\",\"\")[:200]}')
"
```

**Expected:** `status=draft` albo `clarify` (jeśli brak makr), action_draft istnieje z pełnym P4 kontraktem

---

### 9. Event Draft

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
import json
from qbot3.agent_runtime import orchestrate_query
r = orchestrate_query('dodaj event Bikepacking w Toskanii 4-13 czerwca 2026')
print(f'Status: {r.get(\"status\")}')
print(f'Action draft exists: {bool(r.get(\"action_draft\"))}')
ad = r.get('action_draft', {})
print(f'action_type: {ad.get(\"action_type\")}')
print(f'payload: {json.dumps(ad.get(\"payload\",{}), ensure_ascii=False)[:200]}')
"
```

**Expected:** `status=draft`, `action_draft.action_type=calendar_event_add`

---

### 10. Action Execute Dry Run

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
import json
from qbot3.adapters.mcp_adapter import handle_qbot3_mcp
r = handle_qbot3_mcp({
    'method': 'tools/call', 'id': 1,
    'params': {
        'name': 'qbot.action_execute',
        'arguments': {
            'action_type': 'nutrition_log_add',
            'payload_json': {'date': '2026-05-29', 'meal_name': 'test'},
            'idempotency_key': 'test_qbot3_morning',
            'confirm': True,
            'dry_run': True,
        }
    }
})
content = json.loads(r['result']['content'][0]['text'])
print(f'Status: {content.get(\"status\")}')
print(f'Dry run: {content.get(\"dry_run\")}')
"
```

**Expected:** `status=OK`, `dry_run=True`

---

### 11. MCP Tools List

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
from qbot3.adapters.mcp_adapter import handle_qbot3_mcp
r = handle_qbot3_mcp({'method': 'tools/list', 'id': 1})
tools = [t['name'] for t in r['result']['tools']]
print(f'Tools: {tools}')
"
```

**Expected:** `['qbot.query', 'qbot.action_execute']`

---

### 12. No Nutrition Fallback Test

**Command:**
```bash
QBOT3_ENABLED=1 ALBERT_LLM_PROVIDER=mock python3 -c "
from qbot3.agent_runtime import orchestrate_query
r = orchestrate_query('co jest w QBOT_KNOWHOW o LLM Orchestrator')
tools = r.get('plan', {}).get('tools', [])
print(f'Tools: {tools}')
print(f'No nutrition fallback: {not any(\"nutrition\" in str(t) for t in tools)}')
"
```

**Expected:** tools NIE zawierają `nutrition_*` — dokumenty nie mogą iść w nutrition

---

## Expected Results Matrix

| # | Test | Expected Status | Fallback | P4 Contract |
|---|---|---|---|---|
| 1 | Status | ok | false | — |
| 2 | Readiness | ok/partial | false | — |
| 3 | BIBLE docs | ok | false | — |
| 4 | KNOWHOW docs | ok | false | — |
| 5 | Today's meals | ok | false | — |
| 6 | Daily balance | ok/partial/no_data | false | — |
| 7 | Garmin diagnostics | ok | false | — |
| 8 | Nutrition draft | draft/clarify | false | ✅ full P4 |
| 9 | Event draft | draft | false | ✅ full P4 |
| 10 | Action dry run | OK (dry_run=True) | — | ✅ |
| 11 | MCP tools | 2 tools | — | — |
| 12 | No nutrition fallback | true | — | — |
