# QBot3 Morning Acceptance Tests — 2026-05-28

## Prerequisites

```bash
export QBOT3_ENABLED=1
# Optional: export ALBERT_LLM_PROVIDER=openai  (default: openai)
systemctl restart qbot-api.service
```

## Test Suite

---

### 1. Status

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"qbot.query","arguments":{"query":"status qbot"}}}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); c=d['result']['content'][0]; r=json.loads(c['text']); print(f'Status: {r.get(\"status\")}'); print(f'Orchestrator: {r.get(\"orchestrator\",{})}'); print(f'Answer: {r.get(\"answer\",\"\")[:200]}')"
```

**Expected:** `status=ok`, `orchestrator.enabled=true`, `orchestrator.fallback_used=false`, `orchestrator.name=Albert`

---

### 2. Readiness

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"qbot.query","arguments":{"query":"readiness qbot"}}}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); c=d['result']['content'][0]; r=json.loads(c['text']); print(f'Status: {r.get(\"status\")}'); print(f'Fallback: {r.get(\"orchestrator\",{}).get(\"fallback_used\")}')"
```

**Expected:** `status=ok` or `partial`, `fallback_used=false`

---

### 3. Docs Search — BIBLE

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"qbot.query","arguments":{"query":"co jest w QBOT_BIBLE o QBot3"}}}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); c=d['result']['content'][0]; r=json.loads(c['text']); print(f'Status: {r.get(\"status\")}'); print(f'Tools: {r.get(\"plan\",{}).get(\"tools\",[])}'); print(f'Answer: {r.get(\"answer\",\"\")[:300]}')"
```

**Expected:** `status=ok`, tools=`['canonical_docs']`, answer zawiera fragmenty z QBOT_BIBLE

---

### 4. Docs Search — KNOWHOW

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"qbot.query","arguments":{"query":"co jest w QBOT_KNOWHOW o LLM Orchestrator"}}}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); c=d['result']['content'][0]; r=json.loads(c['text']); print(f'Status: {r.get(\"status\")}'); print(f'Tools: {r.get(\"plan\",{}).get(\"tools\",[])}'); print(f'Answer: {r.get(\"answer\",\"\")[:300]}')"
```

**Expected:** `status=ok`, tools=`['canonical_docs']`, **not** `no_data`

---

### 5. Today's Meals

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"qbot.query","arguments":{"query":"co jadłem dzisiaj?"}}}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); c=d['result']['content'][0]; r=json.loads(c['text']); print(f'Status: {r.get(\"status\")}'); print(f'Tools: {r.get(\"plan\",{}).get(\"tools\",[])}'); print(f'Answer: {r.get(\"answer\",\"\")[:300]}')"
```

**Expected:** `status=ok`, tools zawiera `nutrition_day_summary` albo `nutrition_meal_list`

---

### 6. Daily Balance

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"qbot.query","arguments":{"query":"jaki mam dziś bilans kalorii?"}}}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); c=d['result']['content'][0]; r=json.loads(c['text']); print(f'Status: {r.get(\"status\")}'); print(f'Answer: {r.get(\"answer\",\"\")[:300]}')"
```

**Expected:** Pokazuje kcal_in, wzmiankę o kcal_out jeśli dostępne, albo informację czego brakuje

---

### 7. Garmin Diagnostics

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"qbot.query","arguments":{"query":"dlaczego nie masz danych Garmin za dziś?"}}}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); c=d['result']['content'][0]; r=json.loads(c['text']); print(f'Status: {r.get(\"status\")}'); print(f'Answer: {r.get(\"answer\",\"\")[:300]}')"
```

**Expected:** `status=ok`, wyjaśnia czy brak danych w DB, kiedy ostatni import, itp.

---

### 8. Nutrition Draft (Strawberries)

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"qbot.query","arguments":{"query":"dodaj 0,5 kg truskawek do dzisiejszego spożycia"}}}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); c=d['result']['content'][0]; r=json.loads(c['text']); print(f'Status: {r.get(\"status\")}'); print(f'Ad: {bool(r.get(\"action_draft\"))}'); print(f'Answer: {r.get(\"answer\",\"\")[:200]}')"
```

**Expected:** `status=draft` albo `clarify` (jeśli brak makr), action_draft istnieje albo pyta o makra

---

### 9. Event Draft

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"qbot.query","arguments":{"query":"dodaj event Bikepacking w Toskanii 4-13 czerwca 2026"}}}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); c=d['result']['content'][0]; r=json.loads(c['text']); print(f'Status: {r.get(\"status\")}'); print(f'Ad: {bool(r.get(\"action_draft\"))}'); ad=r.get('action_draft',{}); print(f'Action: {ad.get(\"action_type\")}'); print(f'Payload: {json.dumps(ad.get(\"payload\",{}), ensure_ascii=False)[:200]}')"
```

**Expected:** `status=draft`, `action_draft.action_type=calendar_event_add`, payload zawiera date_start=2026-06-04, date_end=2026-06-13

---

### 10. Action Execute Dry Run

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"qbot.action_execute","arguments":{"action_type":"calendar_event_add","payload_json":{"date_start":"2026-07-01","title":"Test QBot3","event_type":"note"},"idempotency_key":"test_qbot3_dry_run","confirm":true,"dry_run":true}}}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); c=d['result']['content'][0]; r=json.loads(c['text']); print(f'Status: {r.get(\"status\")}')"
```

**Expected:** `status=BLOCKED` (since action_exec is not fully wired through safety for calendar events) OR `status=OK` with dry_run info

---

### 11. MCP Tools List

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); tools=[t['name'] for t in d['result']['tools']]; print(f'Tools: {tools}')"
```

**Expected:** `['qbot.query', 'qbot.action_execute']`

---

### 12. No Nutrition Fallback Test

**Command:**
```bash
curl -s -X POST http://127.0.0.1:8002/mcp/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"qbot.query","arguments":{"query":"co jest w QBOT_KNOWHOW o LLM Orchestrator"}}}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); c=d['result']['content'][0]; r=json.loads(c['text']); print(f'Status: {r.get(\"status\")}'); print(f'Tools: {r.get(\"plan\",{}).get(\"tools\",[])}'); print(f'No nutrition fallback: {not any(\"nutrition\" in str(t) for t in r.get(\"plan\",{}).get(\"tools\",[]))}')"
```

**Expected:** tools NIE zawierają `nutrition_*` — dokumenty nie mogą iść w nutrition

## Expected Results Matrix

| # | Test | Expected Status | Fallback |
|---|---|---|---|
| 1 | Status | ok | false |
| 2 | Readiness | ok/partial | false |
| 3 | BIBLE docs | ok | false |
| 4 | KNOWHOW docs | ok | false |
| 5 | Today's meals | ok | false |
| 6 | Daily balance | ok/partial/no_data | false |
| 7 | Garmin diagnostics | ok | false |
| 8 | Nutrition draft | draft/clarify | false |
| 9 | Event draft | draft | false |
| 10 | Action dry run | OK/BLOCKED | — |
| 11 | MCP tools | 2 tools | — |
| 12 | No nutrition fallback | true | — |
