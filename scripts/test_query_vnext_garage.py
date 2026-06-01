#!/usr/bin/env python3
"""test_query_vnext_garage.py — test garage_status and garage_search intent handlers.

Usage:
    cd /opt/qbot/app
    .venv/bin/python scripts/test_query_vnext_garage.py
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

TESTS: list[tuple[str, str, list[str], bool]] = [
    # (label, query, expected_intents, expect_sources)
    ("garage_status_1",      "pokaż garaż",                     ["garage_status"], True),
    ("garage_status_2",      "co mam w garażu",                  ["garage_status"], True),
    ("garage_status_3",      "pokaż mój sprzęt",                 ["garage_status"], True),
    ("garage_search_helmets","pokaż kaski",                      ["garage_search"], True),
    ("garage_search_shoes",  "jakie mam buty",                   ["garage_search"], True),
    ("garage_search_jackets","pokaż kurtki",                     ["garage_search"], True),
    ("garage_search_rapha",  "szukaj Rapha",                     ["garage_search"], True),
    ("garage_search_pedaled","szukaj PEdALED",                   ["garage_search"], True),
    ("garage_search_sram",   "pokaż komponenty SRAM",            ["garage_search"], True),
    # Regression
    ("regression_nutrition", "pokaż moje jedzenie dzisiaj",      ["nutrition_day"], True),
    ("regression_balance",   "pokaż bilans 7 dni",               ["nutrition_range"], True),
    ("regression_xert",      "pokaż Xert",                       ["xert_status"], True),
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

    for label, query, expected_intents, expect_sources in TESTS:
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
            if status == "OK":
                if not result.get("sources_used"):
                    detail["issues"].append("OK but sources_used empty")
            elif status == "ERROR":
                detail["issues"].append(f"handler returned ERROR")

            # For garage_search, check result_count
            if result.get("intent") == "garage_search":
                dd = result.get("data", {})
                if dd.get("result_count", 0) == 0:
                    detail["issues"].append("garage_search returned 0 results — may be OK")
                    # This is informational, not an error

            if detail["issues"]:
                detail["status"] = "PARTIAL" if status != "ERROR" else "ERROR"
            else:
                detail["status"] = "OK" if status != "ERROR" else "ERROR"
                if status == "PARTIAL":
                    detail["status"] = "PARTIAL"

            detail["sources_used"] = result.get("sources_used", [])
            detail["warnings"] = result.get("warnings", [])

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
