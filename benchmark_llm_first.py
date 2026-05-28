#!/usr/bin/env python3
"""Benchmark for LLM-first classifier — safe test harness with timeouts.

Usage:
  cd /opt/qbot/app && /opt/qbot/app/.venv/bin/python benchmark_llm_first.py

Each query gets a 20-second timeout.  Failures are isolated — one hung
query does not block the rest.  No production code is modified.
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qbot_query_router import classify_intent, llm_first_classify_intent

TIMEOUT_SEC = 20

TEST_QUERIES: list[str] = [
    # ── Docs (5) ──
    "Przeczytaj Biblię QBot i podaj zasady MCP",
    "Sprawdź Know-how dla Telegram 404",
    "Przeczytaj dokumenty kanoniczne QBot",
    "Czy jest instrukcja projektu?",
    "pokaż dokumentację QBot",
    # ── Status / readiness (6) ──
    "status QBot",
    "readiness QBot",
    "jaki jest status systemu?",
    "czy wszystko działa?",
    "czy integracje działają poprawnie?",
    "raport gotowości QBot",
    # ── Nutrition (7) ──
    "Co jadłem wczoraj?",
    "pokaż co jadłem dzisiaj",
    "ile kcal wczoraj?",
    "pokaż dzisiejsze posiłki",
    "jaki jest bilans kaloryczny z ostatnich 3 dni?",
    "co jadłem na śniadanie?",
    "pokaż stan odżywienia z ostatniego tygodnia",
    # ── Reminders (5) ──
    "Dodaj przypomnienie jutro o 8:00: test LLM first",
    "pokaż moje przypomnienia",
    "przypomnij mi o wizycie u dentysty",
    "jakie mam zaplanowane przypomnienia?",
    "usuń przypomnienie o wizycie",
    # ── Calendar events (5) ──
    "Dodaj wydarzenie jutro 18-19 trening",
    "pokaż wydarzenia na dzisiaj",
    "jaka jest lista wydarzeń w tym tygodniu?",
    "zaplanuj spotkanie w piątek",
    "odwołaj wydarzenie nr 12",
    # ── Planning facts (3) ──
    "Pokaż moje planning facts",
    "zapisz fakt planistyczny: trening w sobotę",
    "jakie mam założenia planistyczne?",
    # ── Weather (3) ──
    "Jaka jest pogoda w Markach jutro?",
    "czy jutro będzie padać?",
    "jaka temperatura w Warszawie?",
    # ── History / ambiguous (5) ──
    "zrób to co wczoraj",
    "co robiłem wczoraj?",
    "pokaż historię moich treningów",
    "jakie treningi zrobiłem w tym miesiącu?",
    "pokaż ostatnie aktywności",
    # ── Decisions / Telegram-style (4) ──
    "czy był już omawiany temat Telegram 404?",
    "jaka jest decyzja MS w sprawie narzędzi MCP?",
    "czy ten problem był już rozwiązany?",
    "zgadzam się z propozycją, zapisz to",
    # ── Write intents (4) ──
    "dodaj posiłek 500 kcal",
    "usuń wydarzenie nr 5",
    "zaktualizuj przypomnienie o wizycie",
    "zapisz notatkę: test integracji",
    # ── Supplement / health (3) ──
    "pokaż stan magazynu suplementów",
    "jaka jest rada zdrowotna na dziś?",
    "czy powinienem brać witaminę D?",
    # ── Misc (3) ──
    "pokaż raport dzienny",
    "jaki był mój sen ostatniej nocy?",
    "pokaż listę tras RWGPS",
]


def classify_with_timeout(
    query: str,
    timeout: int = TIMEOUT_SEC,
) -> dict[str, Any]:
    """Run llm_first_classify_intent with a per-query timeout.

    Returns a result dict with extra fields:
      - _timeout: bool
      - _elapsed: float (seconds)
      - _error: str | None
    """
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(llm_first_classify_intent, query)
        try:
            result = fut.result(timeout=timeout)
        except FuturesTimeout:
            fut.cancel()
            elapsed = time.monotonic() - start
            return {
                "status": "timeout",
                "error": f"Query timed out after {timeout}s",
                "_timeout": True,
                "_elapsed": elapsed,
                "_error": f"timeout ({timeout}s)",
                "domain": None, "intent": None, "parameters": {},
                "confidence": 0.0, "needs_clarification": False,
                "clarification_question": "", "readers": [],
                "action_type": None, "is_write_intent": False,
            }
        except Exception as exc:
            elapsed = time.monotonic() - start
            return {
                "status": "error",
                "error": f"Exception: {exc}",
                "_timeout": False,
                "_elapsed": elapsed,
                "_error": str(exc)[:100],
                "domain": None, "intent": None, "parameters": {},
                "confidence": 0.0, "needs_clarification": False,
                "clarification_question": "", "readers": [],
                "action_type": None, "is_write_intent": False,
            }
        else:
            elapsed = time.monotonic() - start
            result["_timeout"] = False
            result["_elapsed"] = elapsed
            result["_error"] = result.get("error") or None
            return result


def run_benchmark(queries: list[str]) -> list[dict[str, Any]]:
    """Run benchmark for all queries, one by one with timeout isolation."""
    print(f"Benchmark: {len(queries)} queries, {TIMEOUT_SEC}s timeout each")
    print(f"Feature flag QBOT_LLM_FIRST_QUERY={os.getenv('QBOT_LLM_FIRST_QUERY', '0')}")
    print()

    results: list[dict[str, Any]] = []
    for i, q in enumerate(queries, 1):
        kw = classify_intent(q)
        llm = classify_with_timeout(q)
        kw_intents = kw

        # Determine divergence
        diff: list[str] = []
        llm_status = llm.get("status", "error")
        if llm_status in ("timeout", "error"):
            diff.append(f"LLM {llm_status}: {llm.get('_error', '')}")
        elif llm.get("intent") and llm["intent"] not in set(kw_intents):
            diff.append(f"LLM intent '{llm['intent']}' not in keyword intents {kw_intents}")

        # Recommendation
        if llm_status in ("timeout", "error", "fallback_needed"):
            rec = "fallback_readonly"
        elif llm.get("needs_clarification"):
            rec = "ask_clarification"
        elif llm.get("confidence", 0) >= 0.6:
            rec = "use_llm"
        else:
            rec = "ask_clarification"

        results.append({
            "query": q,
            "keyword_intents": kw_intents,
            "llm_result": llm,
            "recommendation": rec,
            "differences": diff,
            "elapsed": llm.get("_elapsed", 0),
        })

    return results


def fmt(v: Any) -> str:
    if v is None or v == "?":
        return "-"
    return str(v)[:22]


def main():
    queries = TEST_QUERIES

    print(f"{'#'*90}")
    print(f"# LLM-first benchmark — {len(queries)} queries")
    print(f"# Timeout per query: {TIMEOUT_SEC}s")
    print(f"# Python: {sys.executable}")
    print(f"{'#'*90}")
    print()

    results = run_benchmark(queries)

    # ── Table ──
    hdr = f"{'#':>4} | {'REC':<14} | {'KW':<22} | {'LLM INTENT':<24} | {'CONF':<5} | {'TIME':<6} | NOTE"
    sep = "─" * len(hdr)
    print(hdr)
    print(sep)

    rec_counts: dict[str, int] = {}
    api_errors = 0
    timeouts = 0
    total_elapsed = 0.0
    diverged = 0

    for i, r in enumerate(results, 1):
        llm = r["llm_result"]
        kw = ", ".join(r["keyword_intents"][:2])
        li = fmt(llm.get("intent"))
        conf = llm.get("confidence", 0.0)
        rec = r["recommendation"]
        elapsed = r.get("elapsed", 0)
        total_elapsed += elapsed
        rec_counts[rec] = rec_counts.get(rec, 0) + 1
        if r["differences"]:
            diverged += 1

        note = ""
        if llm.get("status") in ("timeout", "error"):
            note = f"{llm['status']}: {llm.get('_error', '')[:50]}"
            if llm["status"] == "timeout":
                timeouts += 1
            else:
                api_errors += 1
        elif r["differences"]:
            note = r["differences"][0][:55]

        print(f"{i:>4} | {rec:<14} | {kw:<22} | {li:<24} | {conf:<5.2f} | {elapsed:<6.2f}s | {note[:55]}")

    # ── Summary ──
    print(f"\n{'='*90}")
    total = len(results)
    print(f"Total queries:     {total}")
    print(f"  use_llm:         {rec_counts.get('use_llm', 0)} ({rec_counts.get('use_llm', 0)*100//total}%)")
    print(f"  fallback_readonly: {rec_counts.get('fallback_readonly', 0)} ({rec_counts.get('fallback_readonly', 0)*100//total}%)")
    print(f"  ask_clarification: {rec_counts.get('ask_clarification', 0)} ({rec_counts.get('ask_clarification', 0)*100//total}%)")
    print(f"  diverged:        {diverged} ({diverged*100//total}%)")
    print(f"  api_errors:      {api_errors}")
    print(f"  timeouts:        {timeouts}")
    print(f"  avg time:        {total_elapsed/total:.2f}s")
    print(f"  total time:      {total_elapsed:.1f}s")
    print()

    # ── Errors / timeouts detail ──
    bad = [r for r in results if r["llm_result"].get("status") in ("timeout", "error")]
    if bad:
        print("=== Queries with errors/timeouts ===")
        for r in bad:
            llm = r["llm_result"]
            t = llm.get("_elapsed", 0)
            print(f"  [{llm['status']}] ({t:.1f}s) {r['query']}")
            print(f"         {llm.get('_error', '')}")

    # ── Diverged detail ──
    divs = [r for r in results if r["differences"] and r["llm_result"].get("status") not in ("timeout", "error")]
    if divs:
        print(f"\n=== Divergent (LLM vs keyword) — {len(divs)} queries ===")
        for r in divs:
            llm = r["llm_result"]
            print(f"  Q: {r['query']}")
            print(f"  KW: {r['keyword_intents']}")
            print(f"  LLM: intent={fmt(llm.get('intent'))}, dom={fmt(llm.get('domain'))}, conf={llm.get('confidence')}")
            print()

    print(f"\n{'='*90}")
    print("BENCHMARK COMPLETE")


if __name__ == "__main__":
    main()
