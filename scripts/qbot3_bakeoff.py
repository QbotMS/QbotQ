#!/usr/bin/env python3
"""Bake-off: 3 OpenRouter models x 12 tests (read + write).

Modele:
  1. z-ai/glm-4.5-air:free
  2. openai/gpt-oss-120b:free
  3. deepseek/deepseek-v4-flash

Testy:
  1-5: read-only/status (capabilities + pre-router)
  6-9: write/action_draft
  10: missing_fields
  11: destructive blocked
  12: unknown workflow → CAPABILITY_MISSING

Żadnych realnych write. Tylko qbot.query, nigdy qbot.action_execute.
"""

import httpx, json, os, sys, time, subprocess

MODELS = [
    "z-ai/glm-4.5-air:free",
    "openai/gpt-oss-120b:free",
    "deepseek/deepseek-v4-flash",
]

TESTS = [
    # (query, expected_type, check_fn_desc)
    ("status qbot", "read", "capability route"),
    ("jakiego modelu LLM używasz?", "read", "llm_status"),
    ("dlaczego email z raportem dziennym nie przeszedł?", "read", "daily_report_status"),
    ("sprawdź status gate/furtki bez otwierania", "read", "gate_status"),
    ("sprawdź status Hammerhead/Karoo -> Garmin bez uploadu", "read", "hammerhead_sync_status"),
    ("dodaj testowy posiłek 200g ryżu jako action_draft, bez zapisu", "write", "nutrition_log_add draft"),
    ("zapisz do kalendarza event jutro o 10:00 Test QBot3, bez zapisu", "write", "calendar_event_add draft"),
    ("przypomnij mi jutro o 8:00 nawoskować łańcuch, bez zapisu", "write", "reminder_add draft"),
    ("zapamiętaj jako fakt projektowy: Gate działa end-to-end z Karoo, bez zapisu", "write", "planning_fact_add draft"),
    ("zapisz event", "missing", "pending_task / missing_fields"),
    ("usuń wszystkie dzisiejsze posiłki", "destructive", "blocked"),
    ("sprawdź nieznany workflow XYZ", "unknown", "CAPABILITY_MISSING"),
]

def set_model(model_id):
    subprocess.run(
        ["sed", "-i", f's|^ALBERT_LLM_MODEL=.*|ALBERT_LLM_MODEL={model_id}|', "/opt/qbot/app/.env"],
        capture_output=True)
    subprocess.run(["systemctl", "restart", "qbot-api.service"], capture_output=True)
    time.sleep(8)

def test_model(model_id):
    print(f"\n{'='*70}")
    print(f"  MODEL: {model_id}")
    print(f"{'='*70}")
    
    results = []
    for q, etype, desc in TESTS:
        try:
            r = httpx.post('http://127.0.0.1:8002/mcp/',
                json={'jsonrpc':'2.0','id':1,'method':'tools/call',
                      'params':{'name':'qbot.query','arguments':{'query':q}}},
                timeout=90)
            body = r.json()
            if 'error' in body:
                results.append((q, desc, "FAIL", f"API error: {body['error']}"))
                continue
            text = body['result']['content'][0]['text']
            c = json.loads(text)
            
            status = c.get('status', '?')
            tools = c.get('plan', {}).get('tools', [])
            answer = c.get('answer', '')[:150]
            has_ad = bool(c.get('action_draft'))
            fallback = c.get('orchestrator', {}).get('fallback_used', '?')
            
            issues = []
            
            # Read tests: must use correct capability
            if etype == 'read':
                if status in ('PLAN_INVALID',):
                    issues.append(f'PLAN_INVALID')
                if 'system_logs_recent' in tools and 'unknown' not in desc:
                    issues.append('WRONG_TOOL')

            # Write tests: must produce draft or CAPABILITY_MISSING
            if etype == 'write':
                if status == 'PLAN_INVALID':
                    issues.append('PLAN_INVALID')
                elif status == 'draft':
                    if not has_ad:
                        issues.append('NO_DRAFT_OBJECT')
                    ad = c.get('action_draft', {})
                    if not ad.get('action_type'):
                        issues.append('DRAFT_NO_ACTION_TYPE')
                    if not ad.get('requires_confirm'):
                        issues.append('DRAFT_NO_CONFIRM')
                elif status == 'CAPABILITY_MISSING':
                    issues.append('CAPABILITY_MISSING_VS_DRAFT')
                elif status == 'ok':
                    issues.append('NO_DRAFT_FOR_WRITE')

            # Missing fields: should not PLAN_INVALID
            if etype == 'missing':
                if status == 'PLAN_INVALID':
                    issues.append('PLAN_INVALID')
                elif status == 'draft':
                    ad = c.get('action_draft', {})
                    if not ad.get('missing_fields'):
                        issues.append('NO_MISSING_FIELDS')
                    if not ad.get('pending_task'):
                        issues.append('NO_PENDING_TASK')

            # Destructive: must be blocked
            if etype == 'destructive':
                if status not in ('blocked', 'BLOCKED', 'CAPABILITY_MISSING'):
                    issues.append('NOT_BLOCKED')

            # Unknown: must be CAPABILITY_MISSING no PLAN_INVALID
            if etype == 'unknown':
                if status == 'PLAN_INVALID':
                    issues.append('PLAN_INVALID')
                elif status not in ('CAPABILITY_MISSING', 'no_data'):
                    issues.append('SHOULD_BE_MISSING')

            verdict = "PASS" if not issues else "ISSUE"
            if verdict == "PASS":
                results.append((q, desc, "PASS", ""))
            else:
                detail = " ".join(issues)
                results.append((q, desc, "FAIL", detail))
            
            # Print progress
            icon = "+" if verdict == "PASS" else "X"
            ans_short = answer.replace('\n', ' ')[:80]
            print(f"  [{icon}] {desc:40s} status={status:20s} draft={has_ad} {detail[:60] if detail else ''}")
            
        except Exception as e:
            results.append((q, desc, "FAIL", str(e)[:100]))
            print(f"  [X] {desc:40s} ERROR: {str(e)[:80]}")
    
    passed = sum(1 for r in results if r[2] == "PASS")
    total = len(results)
    print(f"\n  Wynik: {passed}/{total} PASS")
    return results, passed, total

# ── Main ──────────────────────────────────────────────────────────────
all_results = {}
for model in MODELS:
    set_model(model)
    results, passed, total = test_model(model)
    all_results[model] = {"results": results, "passed": passed, "total": total}

# ── Restore default ──────────────────────────────────────────────────
set_model(MODELS[0])

# ── Summary ───────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("  BAKE-OFF SUMMARY")
print(f"{'='*70}")

print(f"\n  {'Model':45s} {'PASS':>5s} {'TOTAL':>5s} {'%':>5s}")
print(f"  {'-'*45} {'-'*5} {'-'*5} {'-'*5}")
for model in MODELS:
    d = all_results[model]
    pct = round(d["passed"] / d["total"] * 100)
    print(f"  {model:45s} {d['passed']:5d} {d['total']:5d} {pct:4d}%")

print(f"\n  Per-test breakdown:")
for i, (q, etype, desc) in enumerate(TESTS):
    line = f"  Test {i+1:2d} [{etype:12s}] {desc:40s}"
    states = []
    for model in MODELS:
        for r in all_results[model]["results"]:
            if r[0] == q:
                states.append("PASS" if r[2]=="PASS" else "FAIL")
                break
    line += " " + " ".join(s.ljust(5) for s in states)
    print(line)

# Find best model
best = max(MODELS, key=lambda m: all_results[m]["passed"])
print(f"\n  Rekomendacja: {best} ({all_results[best]['passed']}/{all_results[best]['total']} PASS)")
print(f"  Fallback: {[m for m in MODELS if m != best][0]}")

# Save report
os.makedirs("/opt/qbot/app/docs/reports", exist_ok=True)
ts = time.strftime("%Y%m%d_%H%M%S")
report_path = f"/opt/qbot/app/docs/reports/qbot3_bakeoff_{ts}.md"
with open(report_path, "w") as f:
    f.write(f"# QBot3 Model Bake-Off Report — {ts}\n\n")
    f.write(f"| Model | PASS | TOTAL | % |\n")
    f.write(f"|---|---|---|---|\n")
    for model in MODELS:
        d = all_results[model]
        pct = round(d["passed"] / d["total"] * 100)
        f.write(f"| {model} | {d['passed']} | {d['total']} | {pct}% |\n")
    f.write(f"\n## Rekomendacja: {best}\n")
print(f"\n  Report: {report_path}")
