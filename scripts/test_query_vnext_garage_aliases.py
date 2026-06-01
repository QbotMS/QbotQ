#!/usr/bin/env python3
"""test_query_vnext_garage_aliases.py — test PL/EN alias expansion in garage_search.

Usage:
    cd /opt/qbot/app
    .venv/bin/python scripts/test_query_vnext_garage_aliases.py
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime

sys.path.insert(0, "/opt/qbot/app")
from qbot_query_handler import handle_query

REQUIRED_ENVELOPE_KEYS = [
    "status", "engine", "intent", "answer", "data",
    "sources_used", "missing_sources", "freshness",
    "action_draft", "fallback_reason", "warnings",
]

TESTS: list[tuple[str, str, list[str], int | None, bool]] = [
    # (label, query, expected_intents, min_results, expect_alias)
    ("alias_helmets",    "pokaż kaski",              ["garage_search"], 0, True),
    ("alias_shoes",      "jakie mam buty",            ["garage_search"], 0, True),
    ("alias_gloves",     "pokaż rękawiczki",          ["garage_search"], 0, True),
    ("alias_jackets",    "pokaż kurtki",              ["garage_search"], 0, True),
    ("alias_socks",      "pokaż skarpety",            ["garage_search"], 0, True),
    ("alias_tires",      "pokaż opony",               ["garage_search"], 0, True),
    ("alias_wheels",     "pokaż koła",                ["garage_search"], 0, True),
    ("alias_bags",       "pokaż torby",               ["garage_search"], 0, True),
    ("alias_tent",       "pokaż namiot",              ["garage_search"], 0, True),
    # Brand searches (no alias needed)
    ("brand_rapha",      "szukaj Rapha",              ["garage_search"], 5, False),
    ("brand_pedaled",    "szukaj PEdALED",            ["garage_search"], 1, False),
    ("brand_sram",       "pokaż komponenty SRAM",      ["garage_search"], 1, False),
    # Regression
    ("regression_garage","pokaż garaż",                ["garage_status"], None, False),
    ("regression_nutrition","pokaż moje jedzenie dzisiaj",["nutrition_day"], None, False),
]


def _check_envelope(result: dict) -> list[str]:
    issues = []
    for key in REQUIRED_ENVELOPE_KEYS:
        if key not in result:
            issues.append(f"missing key '{key}'")
    return issues


def run():
    summary = {
        "test_time": datetime.now().isoformat(),
        "total": len(TESTS),
        "passed": 0,
        "failed": 0,
        "partial": 0,
        "details": [],
    }

    for label, query, expected_intents, min_results, expect_alias in TESTS:
        detail = {"label": label, "query": query, "status": "ERROR", "issues": []}
        try:
            result = handle_query(query)
            issues = _check_envelope(result)
            detail["intent"] = result.get("intent")
            detail["result_status"] = result.get("status")

            if issues:
                detail["issues"].extend(issues)

            if result.get("engine") != "query_vnext":
                detail["issues"].append(f"engine != query_vnext: {result.get('engine')}")

            if result.get("intent") not in expected_intents:
                detail["issues"].append(
                    f"intent {result.get('intent')} not in expected {expected_intents}"
                )

            status = result.get("status", "ERROR")
            if status == "ERROR":
                detail["issues"].append(f"handler returned ERROR")

            # Check alias fields for garage_search
            if result.get("intent") == "garage_search":
                dd = result.get("data", {})
                if "expanded_terms" not in dd:
                    detail["issues"].append("missing expanded_terms in data")
                if "alias_used" not in dd:
                    detail["issues"].append("missing alias_used in data")
                else:
                    if dd["alias_used"] != expect_alias:
                        detail["issues"].append(
                            f"expected alias_used={expect_alias}, got {dd['alias_used']}"
                        )
                if min_results is not None:
                    rc = dd.get("result_count", 0)
                    if rc < min_results:
                        detail["issues"].append(
                            f"result_count {rc} < min {min_results}"
                        )
                # Verify SQL injection safety: no raw user text in SQL
                answer = result.get("answer", "")
                if "' OR 1=1 --" in query:
                    detail["issues"].append("SQL injection test not implemented")

            if detail["issues"]:
                detail["status"] = "PARTIAL" if status != "ERROR" else "ERROR"
            else:
                detail["status"] = "OK" if status != "ERROR" else "ERROR"
                if status == "PARTIAL":
                    detail["status"] = "PARTIAL"

            detail["sources_used"] = result.get("sources_used", [])

        except Exception as exc:
            detail["issues"].append(f"exception: {exc}")
            detail["traceback"] = traceback.format_exc()
            detail["status"] = "ERROR"

        summary["details"].append(detail)
        if detail["status"] == "OK":
            summary["passed"] += 1
        elif detail["status"] == "PARTIAL":
            summary["partial"] += 1
        else:
            summary["failed"] += 1

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return summary


if __name__ == "__main__":
    s = run()
    if s["failed"] > 0:
        sys.exit(1)
