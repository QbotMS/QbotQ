#!/usr/bin/env python3
"""Nutrition LLM-first canary benchmark v2 — template matching + read-only.

Runs a fixed set of read-only / draft-only nutrition queries against
qbot.query with the nutrition-readonly canary enabled in-process.
Does not change production environment.
64 test cases across 7 categories.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _env_bootstrap() -> None:
    os.environ.setdefault("QBOT_LLM_FIRST_QUERY", "0")
    os.environ.setdefault("QBOT_LLM_FIRST_SAFE_DOMAINS", "1")
    os.environ.setdefault("QBOT_LLM_FIRST_CALENDAR_READONLY", "1")
    os.environ.setdefault("QBOT_LLM_FIRST_NUTRITION_READONLY", "1")
    os.environ.setdefault("QBOT_LLM_FIRST_TIMEOUT_SEC", "3.0")


_env_bootstrap()

from qbot_query_router import classify_intent, llm_first_classify_intent, query


CASES: list[dict[str, Any]] = [
    # ── saved_meals_catalog (12 cases) ───────────────────────────────
    *[{"category": "saved_meals_catalog", "query": q, "expect_template_id": None, "expect_draft": False} for q in [
        "wylistuj zapisane posiłki",
        "pokaż moje posiłki",
        "pokaż szablony posiłków",
        "jakie masz zdefiniowane posiłki",
        "lista templates",
        "pokaż standardowe posiłki",
        "czy są moje posiłki cronometer",
        "lista zapisanych posiłków",
        "wyświetl moje templates",
        "pokaż posiłki z cronometer",
        "lista posiłków",
        "wylistuj szablony",
    ]],
    # ── template_lookup (14 cases) ───────────────────────────────────
    *[{"category": "template_lookup", "query": q, "expect_template_id": 4, "expect_draft": False} for q in [
        "co to jest dieta od Brokuła w mojej bazie?",
        "dieta od Brokuła",
        "Brokuł",
        "Brokuł sport",
        "Brokuł sport 2000",
        "dieta Brokuł sport 2000",
        "mam na myśli brokuł sport 2000",
        "szukam brokuła",
        "pokaż brokuł sport",
        "dieta brokuła sport",
        "pokaż szablon Brokuł",
        "znajdź posiłek Brokuł",
        "co to jest brokuł sport",
        "wyszukaj brokuł sport 2000",
    ]],
    # ── current_day_meals (10 cases) ─────────────────────────────────
    *[{"category": "current_day_meals", "query": q, "expect_template_id": None, "expect_draft": False} for q in [
        "co jadłem dzisiaj",
        "pokaż dzisiejsze posiłki",
        "jakie mam dziś jedzenie",
        "co zjadłem dziś",
        "dzisiejsze jedzenie",
        "current day meals",
        "jakie były dzisiejsze posiłki",
        "pokaż meal list na dziś",
        "co dziś jadłem",
        "pokaż moje dzisiejsze jedzenie",
    ]],
    # ── calorie_balance (10 cases) ───────────────────────────────────
    *[{"category": "calorie_balance", "query": q, "expect_template_id": None, "expect_draft": False} for q in [
        "ile kcal wczoraj",
        "bilans kalorii dziś",
        "czy mam deficyt kaloryczny",
        "jaki jest bilans energetyczny",
        "ile kcal out dzisiaj",
        "nadwyżka kalorii w tym tygodniu",
        "kcal z ostatnich 7 dni",
        "bilans kalorii z ostatnich dni",
        "jaki mam bilans kaloryczny",
        "kalorie z garmin i cronometer",
    ]],
    # ── nutrition_history (10 cases) ─────────────────────────────────
    *[{"category": "nutrition_history", "query": q, "expect_template_id": None, "expect_draft": False} for q in [
        "historia posiłków",
        "pokaż logi posiłków z wczoraj",
        "co jadłem w tym tygodniu",
        "nutrition history",
        "meal history",
        "pokaż wpisy posiłków",
        "lista posiłków z wczoraj",
        "co jadłem przedwczoraj",
        "pokaż historię jedzenia",
        "historia moich posiłków",
    ]],
    # ── nutrition_log_add_draft (8 cases) ─────────────────────────────
    *[{"category": "nutrition_log_add_draft", "query": q, "expect_template_id": 4, "expect_draft": True} for q in [
        "dodaj dzisiaj dietę od Brokuła",
        "dodaj dzisiaj Brokuł sport 2000",
        "zapisz posiłek Brokuł",
        "dodaj posiłek z brokuła sport",
        "dopisz do dzisiejszego jedzenia Brokuł sport",
        "dodaj do spożycia Brokuł",
        "dodaj dzisiaj dietę Brokuł sport",
        "zapisz dzisiaj brokuł sport 2000",
    ]],
]


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * 0.95))
    idx = max(0, min(idx, len(ordered) - 1))
    return float(ordered[idx])


def _extract_template_id(resp: dict[str, Any]) -> int | None:
    template_match = resp.get("template_match")
    if isinstance(template_match, dict):
        tid = template_match.get("template_id")
        if tid is not None:
            try:
                return int(tid)
            except Exception:
                pass
    draft = resp.get("action_draft")
    if isinstance(draft, dict):
        payload = draft.get("payload", {})
        if isinstance(payload, dict) and payload.get("template_id") is not None:
            try:
                return int(payload.get("template_id"))
            except Exception:
                pass
    return None


def _has_table_domain(resp: dict[str, Any], domain_names: set[str]) -> bool:
    for table in resp.get("tables", []) or []:
        if table.get("domain") in domain_names:
            return True
    return False


def _assess_success(case: dict[str, Any], resp: dict[str, Any]) -> bool:
    category = case["category"]
    if category == "saved_meals_catalog":
        return resp.get("status") == "ok" and _has_table_domain(resp, {"saved_meals_catalog"})
    if category == "template_lookup":
        return _extract_template_id(resp) == 4 and resp.get("status") == "ok"
    if category == "current_day_meals":
        return _has_table_domain(resp, {"current_day_meals", "current_day_summary", "meal_logs"}) or _has_table_domain(resp, {"meal_list"})
    if category == "calorie_balance":
        return bool(resp.get("calorie_balance"))
    if category == "nutrition_history":
        return _has_table_domain(resp, {"meal_log_inventory", "meal_logs", "meal_list"})
    if category == "nutrition_log_add_draft":
        draft = resp.get("action_draft")
        if not isinstance(draft, dict):
            return False
        payload = draft.get("payload", {})
        return draft.get("action_type") == "nutrition_log_add" and isinstance(payload, dict) and payload.get("template_id") == 4
    return False


def main() -> int:
    summary: dict[str, Any] = {
        "meta": {
            "flag": os.getenv("QBOT_LLM_FIRST_NUTRITION_READONLY", "0"),
            "timeout_sec": float(os.getenv("QBOT_LLM_FIRST_TIMEOUT_SEC", "3.0")),
            "cases": len(CASES),
        },
        "cases": [],
        "overall": {},
        "by_category": {},
    }

    durations: list[float] = []
    overall_counts = Counter()
    by_category: dict[str, Counter] = defaultdict(Counter)
    misclassifications: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for idx, case in enumerate(CASES, start=1):
        q = case["query"]
        category = case["category"]
        t0 = time.perf_counter()
        kw_intents = classify_intent(q)
        llm = llm_first_classify_intent(q)
        resp = query(q, mode="read_only", scope="all", context="")
        elapsed = time.perf_counter() - t0

        durations.append(elapsed)
        overall_counts["total"] += 1
        by_category[category]["total"] += 1

        llm_status = llm.get("status")
        if llm_status == "use_llm":
            overall_counts["use_llm"] += 1
            by_category[category]["use_llm"] += 1
        elif llm_status == "fallback_needed":
            overall_counts["fallback_needed"] += 1
            by_category[category]["fallback_needed"] += 1
        elif llm_status == "ask_clarification":
            overall_counts["needs_clarification"] += 1
            by_category[category]["needs_clarification"] += 1

        if llm_status == "fallback_needed" and str(llm.get("fallback_reason", "")).startswith("api_error"):
            overall_counts["api_errors"] += 1
            by_category[category]["api_errors"] += 1
        if llm_status == "fallback_needed" and str(llm.get("fallback_reason", "")).startswith("timeout"):
            overall_counts["timeouts"] += 1
            by_category[category]["timeouts"] += 1

        fallback_readonly = bool(
            llm_status == "fallback_needed"
            and not resp.get("action_draft")
            and resp.get("status") in {"ok", "partial", "no_data"}
        )
        if fallback_readonly:
            overall_counts["fallback_readonly"] += 1
            by_category[category]["fallback_readonly"] += 1

        template_ok = _assess_success(case, resp)
        if template_ok:
            overall_counts["template_match_ok"] += 1
            by_category[category]["template_match_ok"] += 1

        row = {
            "idx": idx,
            "category": category,
            "query": q,
            "elapsed_ms": round(elapsed * 1000, 1),
            "keyword_intents": kw_intents,
            "llm_status": llm_status,
            "llm_intent": llm.get("intent"),
            "llm_fallback_reason": llm.get("fallback_reason"),
            "resp_status": resp.get("status"),
            "template_id": _extract_template_id(resp),
            "template_ok": template_ok,
            "needs_clarification": bool(resp.get("needs_clarification")) or llm_status == "ask_clarification",
            "api_error": str(llm.get("fallback_reason", "")).startswith("api_error"),
            "timeout": str(llm.get("fallback_reason", "")).startswith("timeout"),
            "action_draft": bool(resp.get("action_draft")),
            "draft_action_type": (resp.get("action_draft") or {}).get("action_type") if isinstance(resp.get("action_draft"), dict) else None,
        }
        summary["cases"].append(row)

        if not template_ok or row["needs_clarification"] or row["api_error"] or row["timeout"]:
            if len(misclassifications[category]) < 3:
                misclassifications[category].append(row)

    summary["overall"] = {
        "total": overall_counts["total"],
        "template_match_ok": overall_counts["template_match_ok"],
        "use_llm": overall_counts["use_llm"],
        "fallback_readonly": overall_counts["fallback_readonly"],
        "fallback_needed": overall_counts["fallback_needed"],
        "needs_clarification": overall_counts["needs_clarification"],
        "api_errors": overall_counts["api_errors"],
        "timeouts": overall_counts["timeouts"],
        "avg_time": round(sum(durations) / len(durations), 3) if durations else 0.0,
        "p95": round(_p95(durations), 3),
    }

    for category in sorted(by_category.keys()):
        c = by_category[category]
        cat_cases = [row for row in summary["cases"] if row["category"] == category]
        cat_durations = [row["elapsed_ms"] / 1000.0 for row in cat_cases]
        summary["by_category"][category] = {
            "total": c["total"],
            "template_match_ok": c["template_match_ok"],
            "use_llm": c["use_llm"],
            "fallback_readonly": c["fallback_readonly"],
            "fallback_needed": c["fallback_needed"],
            "needs_clarification": c["needs_clarification"],
            "api_errors": c["api_errors"],
            "timeouts": c["timeouts"],
            "avg_time": round(sum(cat_durations) / len(cat_durations), 3) if cat_durations else 0.0,
            "p95": round(_p95(cat_durations), 3),
            "misclassifications": misclassifications.get(category, []),
        }

    out_path = Path("/tmp/qbot_nutrition_llm_first_benchmark.json")
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary["overall"], ensure_ascii=False))
    print(f"saved={out_path}")

    # Per-category summary to stdout
    print("\n=== Per-category ===")
    for cat, stats in sorted(summary["by_category"].items()):
        print(f"  {cat:<25} total={stats['total']:>2}  ok={stats['template_match_ok']:>2}  "
              f"llm={stats['use_llm']:>2}  fallback_ro={stats['fallback_readonly']:>2}  "
              f"err={stats['api_errors']:>2}  to={stats['timeouts']:>2}  "
              f"avg={stats['avg_time']:.2f}s  p95={stats['p95']:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
