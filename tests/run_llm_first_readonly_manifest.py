#!/usr/bin/env python3
"""Benchmark runner for llm_first_readonly_manifest_100.json.

Usage:
  cd /opt/qbot/app && /opt/qbot/app/.venv/bin/python tests/run_llm_first_readonly_manifest.py

No production code is modified.  Feature flags are NOT changed.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qbot_query_router import llm_first_classify_intent

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "llm_first_readonly_manifest_100.json")
TIMEOUT = 3.0


def _call_with_timeout(query: str) -> dict:
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(llm_first_classify_intent, query)
        try:
            result = fut.result(timeout=TIMEOUT)
        except FuturesTimeout:
            fut.cancel()
            elapsed = time.monotonic() - start
            return {
                "status": "timeout",
                "llm_status": "fallback_needed",
                "fallback_reason": f"timeout ({TIMEOUT}s)",
                "raw_intent": None, "normalized_intent": None,
                "domain": None, "intent": None, "confidence": 0.0,
                "needs_clarification": False,
                "_elapsed": elapsed,
            }
        except Exception as exc:
            elapsed = time.monotonic() - start
            return {
                "status": "error",
                "llm_status": "fallback_needed",
                "fallback_reason": f"exception: {exc}",
                "raw_intent": None, "normalized_intent": None,
                "domain": None, "intent": None, "confidence": 0.0,
                "needs_clarification": False,
                "_elapsed": elapsed,
            }
        else:
            elapsed = time.monotonic() - start
            result["_elapsed"] = elapsed
            return result


def categorize(result: dict) -> str:
    ls = result.get("llm_status", "fallback_needed")
    if ls == "use_llm":
        return "use_llm"
    if ls == "ask_clarification":
        return "needs_clarification"
    fb = result.get("fallback_reason", "")
    if "timeout" in fb or result.get("status") == "timeout":
        return "timeout"
    if "api_error" in fb:
        return "api_error"
    return "fallback_readonly"


def fmt(v):
    if v is None: return "-"
    s = str(v)
    return s[:24]


def main():
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    total = len(manifest)
    print(f"=== Manifest benchmark: {total} read-only queries ===")
    print(f"Timeout: {TIMEOUT}s per query")
    print(f"Python:  {sys.executable}")
    print(f"QBOT_LLM_FIRST_QUERY={os.environ.get('QBOT_LLM_FIRST_QUERY','0')}")
    print(f"QBOT_LLM_FIRST_SAFE_DOMAINS={os.environ.get('QBOT_LLM_FIRST_SAFE_DOMAINS','0')}")
    print()

    domain_results: dict[str, list[dict]] = defaultdict(list)
    latencies: list[float] = []
    worst: list[dict] = []

    for i, entry in enumerate(manifest, 1):
        q = entry["query"]
        domain = entry["domain"]
        result = _call_with_timeout(q)
        cat = categorize(result)
        elapsed = result.get("_elapsed", 0)
        latencies.append(elapsed)
        entry_result = {
            "id": entry["id"],
            "domain": domain,
            "query": q,
            "category": cat,
            "llm_intent": result.get("normalized_intent"),
            "llm_status": result.get("llm_status"),
            "confidence": result.get("confidence"),
            "fallback_reason": result.get("fallback_reason"),
            "elapsed": elapsed,
        }
        domain_results[domain].append(entry_result)
        worst.append(entry_result)
        ri = fmt(result.get("raw_intent"))
        ni = fmt(result.get("normalized_intent"))
        fb = result.get("fallback_reason") or ""
        print(f"  {i:>3}/{total} | {cat:<20} | {domain:<12} | {ri:<20}→{ni:<20} | c={result.get('confidence',0):.2f} | {elapsed:5.2f}s | {fb[:40]}")

    # Sort worst by elapsed (descending) for analysis
    worst.sort(key=lambda x: x["elapsed"], reverse=True)

    # ── Per-domain summary ──
    print(f"\n{'='*80}")
    print("Per-domain summary:")
    print(f"{'Domain':<18} {'Total':>6} {'use_llm':>8} {'fallback':>10} {'timeout':>8} {'api_err':>8} {'avg_t':>7} {'p95_t':>7}")
    print(f"{'─'*72}")
    all_lats = []
    all_use_llm = 0
    all_fallback = 0
    all_timeout = 0
    all_apierr = 0
    for domain in ["calendar", "nutrition", "wellness", "training", "planning", "history_search"]:
        entries = domain_results.get(domain, [])
        t = len(entries)
        ul = sum(1 for e in entries if e["category"] == "use_llm")
        fb = sum(1 for e in entries if e["category"] == "fallback_readonly")
        to = sum(1 for e in entries if e["category"] == "timeout")
        ae = sum(1 for e in entries if e["category"] == "api_error")
        lats_d = [e["elapsed"] for e in entries]
        avg_d = sum(lats_d) / len(lats_d) if lats_d else 0
        p95_d = sorted(lats_d)[int(len(lats_d) * 0.95)] if lats_d else 0
        all_lats.extend(lats_d)
        all_use_llm += ul
        all_fallback += fb
        all_timeout += to
        all_apierr += ae
        print(f"{domain:<18} {t:>6} {ul:>8} {fb:>10} {to:>8} {ae:>8} {avg_d:>7.2f}s {p95_d:>7.2f}s")

    all_t = len(manifest)
    avg_all = sum(all_lats) / len(all_lats) if all_lats else 0
    p95_all = sorted(all_lats)[int(len(all_lats) * 0.95)] if all_lats else 0
    print(f"{'─'*72}")
    print(f"{'TOTAL':<18} {all_t:>6} {all_use_llm:>8} {all_fallback:>10} {all_timeout:>8} {all_apierr:>8} {avg_all:>7.2f}s {p95_all:>7.2f}s")
    print()

    # ── Worst 10 ──
    print("=== Top 10 worst cases (highest latency / errors) ===")
    shown = set()
    count = 0
    for w in worst:
        if count >= 10:
            break
        q = w["query"]
        if q in shown:
            continue
        shown.add(q)
        count += 1
        fb = w.get("fallback_reason") or ""
        err_info = f"  fb={fb[:60]}" if fb else ""
        print(f"  #{w['id']:>3} {w['domain']:<12} | {w['category']:<20} | {w['elapsed']:5.2f}s | intent={fmt(w['llm_intent'])} | q={q[:55]}{err_info}")

    # ── LLM intent distribution ──
    print("\n=== LLM intent distribution ===")
    intent_counts = Counter()
    for domain_entries in domain_results.values():
        for e in domain_entries:
            i = e.get("llm_intent") or "?"
            intent_counts[i] += 1
    for intent, cnt in intent_counts.most_common(15):
        print(f"  {cnt:>3}x {intent}")

    print(f"\n=== Benchmark complete ===")


if __name__ == "__main__":
    main()
