#!/usr/bin/env python3
"""Benchmark nutrition language variants — 100+ natural language queries.

Expects qbot-api.service running on 127.0.0.1:8002.
Output: /tmp/qbot_nutrition_language_variants_benchmark.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime

MCP_URL = "http://127.0.0.1:8002/mcp/"
TIMEOUT_SEC = 3.0
OUTPUT_PATH = "/tmp/qbot_nutrition_language_variants_benchmark.json"

# ── Manifest ──────────────────────────────────────────────────────────
# (query, expected_template_id or None, expected_action, note)
# expected_action: "read_only" | "draft" | "needs_clarification" | "no_match"

MANIFEST: list[tuple[str, int | None, str, str]] = [
    # ══════════════════════════════════════════════════════════════════
    # 1. Exact names – read-only (7)
    # ══════════════════════════════════════════════════════════════════
    ("co to jest Brokuł sport 2000 w mojej bazie?", 4, "read_only", "exact name, read"),
    ("co to jest Wiejski HP w mojej bazie?", 5, "read_only", "exact name, read"),
    ("co to jest Białko / owsiane / pół banana w mojej bazie?", 6, "read_only", "exact name, read"),
    ("co to jest Białko / owsiane / banan w mojej bazie?", 7, "read_only", "exact name, read"),
    ("co to jest Białko / owsiane w mojej bazie?", 8, "read_only", "exact name, read"),
    ("co to jest Białko / woda / banan w mojej bazie?", 9, "read_only", "exact name, read"),
    ("co to jest Białko z wodą w mojej bazie?", 10, "read_only", "exact name, read"),

    # ══════════════════════════════════════════════════════════════════
    # 2. Exact names – draft (14)
    # ══════════════════════════════════════════════════════════════════
    ("dodaj dzisiaj Brokuł sport 2000", 4, "draft", "exact name, dodaj"),
    ("dopisz do dzisiejszego spożycia Brokuł sport 2000", 4, "draft", "exact name, dopisz"),
    ("dodaj dzisiaj Wiejski HP", 5, "draft", "exact name, dodaj"),
    ("dopisz do dzisiejszego spożycia Wiejski HP", 5, "draft", "exact name, dopisz"),
    ("dodaj dzisiaj Białko / owsiane / pół banana", 6, "draft", "exact name, dodaj"),
    ("dopisz do dzisiejszego spożycia Białko / owsiane / pół banana", 6, "draft", "exact name, dopisz"),
    ("dodaj dzisiaj Białko / owsiane / banan", 7, "draft", "exact name, dodaj"),
    ("dopisz do dzisiejszego spożycia Białko / owsiane / banan", 7, "draft", "exact name, dopisz"),
    ("dodaj dzisiaj Białko / owsiane", 8, "draft", "exact name, dodaj"),
    ("dopisz do dzisiejszego spożycia Białko / owsiane", 8, "draft", "exact name, dopisz"),
    ("dodaj dzisiaj Białko / woda / banan", 9, "draft", "exact name, dodaj"),
    ("dopisz do dzisiejszego spożycia Białko / woda / banan", 9, "draft", "exact name, dopisz"),
    ("dodaj dzisiaj Białko z wodą", 10, "draft", "exact name, dodaj"),
    ("dopisz do dzisiejszego spożycia Białko z wodą", 10, "draft", "exact name, dopisz"),

    # ══════════════════════════════════════════════════════════════════
    # 3. Synonyms & natural variants (20)
    # ══════════════════════════════════════════════════════════════════
    ("co to jest dieta od Brokuła w mojej bazie?", 4, "read_only", "'dieta od' synonym"),
    ("dodaj dzisiaj dietę od Brokuła", 4, "draft", "'dieta od' + dodaj"),
    ("dopisz do dzisiejszego spożycia dietę od Brokuła", 4, "draft", "'dieta od' + dopisz"),
    ("dodaj dzisiaj brokuła", 4, "draft", "genitive 'brokuła'"),
    ("dopisz dzisiaj wiejskiego", 5, "draft", "genitive 'wiejskiego'"),
    ("co to jest wiejski w mojej bazie?", 5, "read_only", "'wiejski' shortcut"),
    ("dodaj dzisiaj wiejski", 5, "draft", "'wiejski' shortcut + dodaj"),
    ("pokaż Wiejski HP", 5, "read_only", "'pokaż' synonym"),
    ("znajdź brokula sport", 4, "read_only", "'znajdź' synonym"),
    ("szukam brokula", 4, "read_only", "'szukam' synonym"),
    ("dodaj pół banana", 6, "draft", "'pół banana' shortcut"),
    ("dopisz owsiane z bananem", 7, "draft", "'owsiane z bananem' variant"),
    ("dodaj owsiane z pół bananem", 6, "draft", "'owsiane z pół bananem' variant"),
    ("dodaj dzisiaj białko na wodzie", 10, "draft", "'białko na wodzie' variant"),
    ("dopisz białko z wodą", 10, "draft", "'białko z wodą' normal"),
    ("dodaj dzisiaj owsiane banan", 7, "draft", "'owsiane banan' shortcut"),
    ("dodaj dzisiaj woda banan", 9, "draft", "'woda banan' shortcut"),
    ("dodaj dzisiaj owsiane pol banana", 6, "draft", "'owsiane pol banana' shortcut"),
    ("co to jest woda banan w mojej bazie?", 9, "read_only", "'woda banan' read"),
    ("dodaj dzisiaj bialko woda", 9, "draft", "'bialko woda' shortcut"),

    # ══════════════════════════════════════════════════════════════════
    # 4. Typos (12)
    # ══════════════════════════════════════════════════════════════════
    ("dodaj dzisiaj brokul sport 2000", 4, "draft", "typo: brokul (no diacritic)"),
    ("co to jest wiejski hp w mojej bazie?", 5, "read_only", "typo: lowercase hp"),
    ("dopisz dzisiaj bialko owsiane pol banana", 6, "draft", "typo: bialko, pol"),
    ("dodaj dzisiaj bialko owsiane banan", 7, "draft", "typo: bialko"),
    ("dopisz bialko owsiane", 8, "draft", "typo: bialko"),
    ("dodaj dzisiaj bialko woda banan", 9, "draft", "typo: bialko"),
    ("co to jest bialko z woda w mojej bazie?", 10, "read_only", "typo: bialko, woda"),
    ("dodaj brokula sport", 4, "draft", "typo/miss: no '2000'"),
    ("dopisz wiejskie hp", 5, "draft", "typo: 'wiejskie' instead of 'wiejski'"),
    ("dodaj owsiane pol banan", 6, "draft", "typo: 'pol banan' instead of 'pol banana'"),
    ("dodaj wode banan", 9, "draft", "typo: 'wode' instead of 'woda'"),
    ("co to jest bialko z wode w mojej bazie?", 10, "read_only", "typo: 'wode' instead of 'woda'"),

    # ══════════════════════════════════════════════════════════════════
    # 5. Inflection / fleksja (12)
    # ══════════════════════════════════════════════════════════════════
    ("co to jest brokuł sport 2000 w bazie?", 4, "read_only", "bez 'mojej'"),
    ("dodaj dzisiaj brokuła sport 2000", 4, "draft", "genitive 'brokuła' + full name"),
    ("dopisz wiejskiego hp", 5, "draft", "genitive 'wiejskiego hp'"),
    ("dodaj owsiane z bananem", 7, "draft", "instrumental 'z bananem'"),
    ("dodaj owsiane z pół bananem", 6, "draft", "instrumental 'z pół bananem'"),
    ("co to jest owsiane z wodą i bananem?", 9, "read_only", "instrumental 'z wodą i bananem'"),
    ("dodaj białka owsiane", 8, "draft", "plural/genitive 'białka'"),
    ("dopisz białka z wodą", 10, "draft", "plural/genitive 'białka'"),
    ("co to jest wiejskiego hp w bazie?", 5, "read_only", "genitive 'wiejskiego hp'"),
    ("dodaj owsianego z bananem", 7, "draft", "genitive 'owsianego'"),
    ("dopisz owsianego z pół bananem", 6, "draft", "genitive 'owsianego z pół bananem'"),
    ("dodaj brokułowi sport 2000", 4, "draft", "dative 'brokułowi' (rare)"),

    # ══════════════════════════════════════════════════════════════════
    # 6. Digressions / context (10)
    # ══════════════════════════════════════════════════════════════════
    ("dodaj to co zwykle z wodą", None, "needs_clarification", "digression: 'to co zwykle' ambiguous"),
    ("dopisz to co jadłem wczoraj", None, "needs_clarification", "digression: 'to co jadłem wczoraj'"),
    ("dodaj jak zwykle owsiane", None, "needs_clarification", "digression: 'jak zwykle owsiane' ambiguous"),
    ("dopisz moją standardową porcję brokuła", 4, "draft", "digression: 'moją standardową porcję'"),
    ("dodaj dzisiaj to samo co wczoraj na obiad", None, "needs_clarification", "digression: 'to samo co wczoraj'"),
    ("zapisz mi brokuła jak zawsze", 4, "draft", "digression: 'jak zawsze'"),
    ("dopisz porcję białka z wodą jak rano", 10, "draft", "digression: 'jak rano'"),
    ("dodaj owsiane, ale z bananem a nie pół banana", 7, "draft", "clarification inline: 'nie pół banana'"),
    ("dopisz taką samą porcję wiejskiego", 5, "draft", "digression: 'taką samą porcję'"),
    ("dodaj jak ostatnio brokuła", 4, "draft", "digression: 'jak ostatnio'"),

    # ══════════════════════════════════════════════════════════════════
    # 7. Ambiguous cases (12)
    # ══════════════════════════════════════════════════════════════════
    ("co to jest Białko w mojej bazie?", None, "needs_clarification", "ambiguous: 'Białko' -> 5 templates"),
    ("dodaj dzisiaj Białko", None, "needs_clarification", "ambiguous: 'Białko' -> 5 templates"),
    ("dopisz Białko", None, "needs_clarification", "ambiguous: 'Białko' -> 5 templates"),
    ("co to jest owsiane w mojej bazie?", None, "needs_clarification", "ambiguous: 'owsiane' -> 6/7/8"),
    ("dodaj dzisiaj owsiane", None, "needs_clarification", "ambiguous: 'owsiane' -> 6/7/8"),
    ("dopisz owsiane", None, "needs_clarification", "ambiguous: 'owsiane' -> 6/7/8"),
    ("banan", None, "needs_clarification", "ambiguous: 'banan' -> 7 or 9"),
    ("dodaj banan", None, "needs_clarification", "ambiguous: 'banan' -> 7 or 9"),
    ("woda", None, "needs_clarification", "ambiguous: 'woda' -> 9 or 10"),
    ("dodaj woda", None, "needs_clarification", "ambiguous: 'woda' -> 9 or 10"),
    ("dopisz banan", None, "needs_clarification", "ambiguous: 'banan' -> 7 or 9"),
    ("dodaj z wodą", None, "needs_clarification", "ambiguous: 'z wodą' -> 9 or 10"),

    # ══════════════════════════════════════════════════════════════════
    # 8. No matching template in DB (10)
    # ══════════════════════════════════════════════════════════════════
    ("dodaj dzisiaj makaron z serem", None, "no_match", "no such template"),
    ("co to jest pizza w mojej bazie?", None, "no_match", "no such template"),
    ("dopisz ryż z kurczakiem", None, "no_match", "no such template"),
    ("dodaj jajecznicę", None, "no_match", "no such template"),
    ("co to jest łosoś w mojej bazie?", None, "no_match", "no such template"),
    ("dodaj dzisiaj sałatkę grecką", None, "no_match", "no such template"),
    ("dopisz owsiankę na mleku", None, "no_match", "no such template"),
    ("dodaj szpinak z fetą", None, "no_match", "no such template"),
    ("co to jest tortilla w mojej bazie?", None, "no_match", "no such template"),
    ("dodaj dzisiaj awokado", None, "no_match", "no such template"),

    # ══════════════════════════════════════════════════════════════════
    # 9. List / catalog queries (4)
    # ══════════════════════════════════════════════════════════════════
    ("wylistuj zapisane posiłki", None, "read_only", "list all templates"),
    ("pokaż wszystkie posiłki", None, "read_only", "list all templates"),
    ("co mam zapisane w meal_templates?", None, "read_only", "list all templates"),
    ("jakie mam diety w bazie?", None, "read_only", "list all templates"),

    # ══════════════════════════════════════════════════════════════════
    # 10. Abbreviations & shorthand (8)
    # ══════════════════════════════════════════════════════════════════
    ("dodaj dzisiaj HP", 5, "draft", "abbreviation: HP"),
    ("dopisz owsiane PB", 6, "draft", "abbreviation: 'owsiane PB' for pół banana"),
    ("co to jest B O B w mojej bazie?", None, "needs_clarification", "abbreviation: B/O/B ambiguous"),
    ("dodaj B O", 8, "draft", "abbreviation: B/O -> Białko owsiane"),
    ("dopisz B W B", 9, "draft", "abbreviation: B/W/B -> woda banan"),
    ("dodaj BZW", 10, "draft", "abbreviation: BZW -> Białko z wodą"),
    ("co to jest B O w bazie?", 8, "read_only", "abbreviation: B/O -> owsiane"),
    ("dodaj dzisiaj B O PB", 6, "draft", "abbreviation: B/O/PB -> owsiane pół banana"),

    # ══════════════════════════════════════════════════════════════════
    # 11. Extra edge cases (10)
    # ══════════════════════════════════════════════════════════════════
    ("co to jest 2000 kcal brokuł w bazie?", 4, "read_only", "kcal + name reversed"),
    ("dopisz 2011 kcal brokuła", 4, "draft", "kcal numeric match"),
    ("dodaj posiłek o wartości 330 kcal owsiane banan", 7, "draft", "kcal + name combined"),
    ("dopisz dietę 2000 kcal", None, "needs_clarification", "kcal only ambiguous"),
    ("dodaj na dziś wiejski z rana", 5, "draft", "temporal context 'z rana'"),
    ("zapisz na wieczór brokuła", 4, "draft", "temporal context 'na wieczór'"),
    ("dopisz przed treningiem owsiane banan", 7, "draft", "temporal context 'przed treningiem'"),
    ("dodaj po treningu białko z wodą", 10, "draft", "temporal context 'po treningu'"),
    ("co to jest 184 kcal wiejski w bazie?", 5, "read_only", "kcal + name"),
    ("dodaj 225 kcal owsiane", 8, "draft", "kcal exact match Białko owsiane"),
]


def mcp_call(query: str) -> tuple[dict, float]:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "qbot.query", "arguments": {"query": query}}}
    t0 = time.time()
    r = subprocess.run(
        ["curl", "-s", MCP_URL, "-H", "Content-Type: application/json",
         "-d", json.dumps(body)],
        capture_output=True, text=True, timeout=TIMEOUT_SEC + 2)
    elapsed = time.time() - t0
    try:
        result = json.loads(r.stdout)
        content = result.get("result", {}).get("content", [{}])[0]
        return json.loads(content["text"]), elapsed
    except Exception as e:
        return {"_error": str(e), "_raw": r.stdout[:300]}, elapsed


def classify_result(r: dict) -> tuple[str, int | None]:
    """Classify actual result. Returns (action_type, template_id or None)."""
    if "_error" in r:
        return "api_error", None

    ad = r.get("action_draft")
    nc = r.get("needs_clarification", False)
    status = r.get("status")
    missing = r.get("missing_fields", []) or r.get("missing", [])

    if nc or status == "partial":
        return "needs_clarification", None

    if ad:
        p = ad.get("payload", {})
        tid = p.get("template_id")
        has_macros = (p.get("kcal_total") is not None and
                      p.get("kcal_total") != "?" and
                      p.get("kcal_total") != "N/A")
        if tid and has_macros:
            return "draft", tid
        # draft without template_id — ambiguous
        return "needs_clarification", None

    if status == "ok":
        # Check if answer mentions a template
        answer = r.get("answer", "")
        tables = r.get("tables", [])
        for table in tables:
            for row in table.get("rows", []):
                tid = row.get("template_id") or row.get("id")
                if tid:
                    return "read_only", tid
        # No template found
        return "no_match", None

    return "no_match", None


def run() -> None:
    results = []
    total = len(MANIFEST)
    tm_ok = draft_ok = clarify_ok = no_match_ok = 0
    false_positives: list[dict] = []
    wrong_templates: list[dict] = []
    api_errors = 0
    timeouts = 0
    latencies: list[float] = []

    print(f"Running {total} queries (timeout={TIMEOUT_SEC}s)...")

    for i, (query, exp_tid, exp_action, note) in enumerate(MANIFEST):
        r, elapsed = mcp_call(query)
        latencies.append(elapsed)

        if "_error" in r:
            api_errors += 1
            results.append({
                "idx": i, "query": query, "expected_tid": exp_tid,
                "expected_action": exp_action, "actual_action": "api_error",
                "actual_tid": None, "note": note, "elapsed": round(elapsed, 3),
                "error": r.get("_error"),
            })
            if elapsed >= TIMEOUT_SEC:
                timeouts += 1
            continue

        if elapsed >= TIMEOUT_SEC:
            timeouts += 1

        actual_action, actual_tid = classify_result(r)

        # Determine success/failure
        expected_tid_match = (
            exp_tid is None or
            (actual_tid == exp_tid)
        )
        expected_action_match = (actual_action == exp_action)

        is_ok = expected_tid_match and expected_action_match

        if is_ok:
            if actual_action == "read_only":
                tm_ok += 1
            elif actual_action == "draft":
                draft_ok += 1
            elif actual_action == "needs_clarification":
                clarify_ok += 1
            elif actual_action == "no_match":
                no_match_ok += 1
        else:
            entry = {
                "idx": i, "query": query, "note": note,
                "expected_tid": exp_tid, "expected_action": exp_action,
                "actual_tid": actual_tid, "actual_action": actual_action,
                "elapsed": round(elapsed, 3), "answer": r.get("answer", "")[:150],
            }
            if actual_tid is not None and exp_tid is not None and actual_tid != exp_tid:
                wrong_templates.append(entry)
            else:
                false_positives.append(entry)

        results.append({
            "idx": i, "query": query, "note": note,
            "expected_tid": exp_tid, "expected_action": exp_action,
            "actual_tid": actual_tid, "actual_action": actual_action,
            "elapsed": round(elapsed, 3), "ok": is_ok,
        })

        # Progress
        if (i + 1) % 20 == 0:
            print(f"  ... {i+1}/{total}")

    # Stats
    avg_time = sum(latencies) / len(latencies)
    sorted_lat = sorted(latencies)
    p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
    worst_10 = sorted(
        [r for r in results if not r.get("ok", True)],
        key=lambda x: -x.get("elapsed", 0)
    )[:10]

    output = {
        "meta": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total_queries": total,
            "timeout_sec": TIMEOUT_SEC,
            "mcp_url": MCP_URL,
        },
        "summary": {
            "total": total,
            "template_match_ok": tm_ok,
            "draft_ok": draft_ok,
            "needs_clarification_ok": clarify_ok,
            "no_match_ok": no_match_ok,
            "false_positive": len(false_positives),
            "wrong_template": len(wrong_templates),
            "api_errors": api_errors,
            "timeouts": timeouts,
            "avg_time_ms": round(avg_time * 1000, 1),
            "p95_ms": round(p95 * 1000, 1),
        },
        "worst_10": worst_10,
        "false_positives": false_positives,
        "wrong_templates": wrong_templates,
        "results": results,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Results saved to {OUTPUT_PATH}")
    print(f"\n{'='*60}")
    print(f"BENCHMARK SUMMARY ({total} queries)")
    print(f"{'='*60}")
    print(f"  template_match_ok:     {tm_ok}")
    print(f"  draft_ok:              {draft_ok}")
    print(f"  needs_clarification_ok:{clarify_ok}")
    print(f"  no_match_ok:           {no_match_ok}")
    print(f"  false_positive:        {len(false_positives)}")
    print(f"  wrong_template:        {len(wrong_templates)}")
    print(f"  api_errors:            {api_errors}")
    print(f"  timeouts:              {timeouts}")
    print(f"  avg_time:              {avg_time*1000:.1f} ms")
    print(f"  p95:                   {p95*1000:.1f} ms")

    if wrong_templates:
        print(f"\n  WRONG TEMPLATES:")
        for e in wrong_templates:
            print(f"    [{e['idx']}] {e['query'][:60]}")
            print(f"         expected={e['expected_tid']} actual={e['actual_tid']} ({e['note']})")

    if false_positives:
        print(f"\n  FALSE POSITIVES:")
        for e in false_positives:
            print(f"    [{e['idx']}] {e['query'][:60]}")
            print(f"         expected={e['expected_action']}:{e['expected_tid']} actual={e['actual_action']}:{e['actual_tid']} ({e['note']})")

    print(f"\n  TOP 10 WORST (by latency):")
    for e in worst_10[:5]:
        print(f"    [{e['idx']}] {e['query'][:55]}  {e['elapsed']*1000:.0f}ms  {e.get('note','')}")


if __name__ == "__main__":
    run()
