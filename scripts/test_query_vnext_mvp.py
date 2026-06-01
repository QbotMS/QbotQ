#!/usr/bin/env python3
"""test_query_vnext_mvp.py — regression test runner for query_vnext handler.

Usage:
    cd /opt/qbot/app
    .venv/bin/python scripts/test_query_vnext_mvp.py
"""
from __future__ import annotations

import json
import sys
import traceback

sys.path.insert(0, "/opt/qbot/app")
from qbot_query_handler import handle_query

REQUIRED_ENVELOPE_KEYS = [
    "status", "engine", "intent", "answer", "data",
    "sources_used", "missing_sources", "freshness",
    "action_draft", "fallback_reason", "warnings",
]

TESTS: list[tuple[str, str, list[str]]] = [
    # (label, query, expected_intents)
    ("daily_balance_today",   "pokaż dzisiejszy bilans kalorii",       ["daily_balance"]),
    ("nutrition_day_today",   "pokaż moje jedzenie dzisiaj",          ["nutrition_day"]),
    ("nutrition_day_0530",    "pokaż moje jedzenie 2026-05-30",       ["nutrition_day"]),
    ("daily_balance_0530",    "pokaż bilans kalorii 2026-05-30",      ["daily_balance"]),
    # nutrition_intake_logs_list tests
    ("intake_logs_list_today","pokaż całe jedzenie dziś",             ["nutrition_intake_logs_list"]),
    ("intake_logs_list_0531", "pokaż intake_logs dla 2026-05-31",     ["nutrition_intake_logs_list"]),
    ("intake_logs_list_meal", "co dziś jadłem",                       ["nutrition_intake_logs_list"]),
    ("intake_logs_list_raw",  "pokaż surową listę wpisów 2026-05-31", ["nutrition_intake_logs_list"]),
    ("intake_logs_list_lista","lista posiłków z dziś",                ["nutrition_intake_logs_list"]),
    ("sleep_day_today",       "pokaż sen dzisiaj",                   ["sleep_day"]),
    ("wellness_day_today",    "pokaż wellness dzisiaj",               ["wellness_day"]),
    ("energy_day_today",      "pokaż energię dzisiaj",               ["energy_day"]),
    ("training_recent_7d",    "pokaż aktywności z ostatnich 7 dni",   ["training_recent"]),
    ("xert_status",           "pokaż Xert",                          ["xert_status"]),
    # nutrition_range tests
    ("nutrition_range_7d",    "pokaż bilans 7 dni",                   ["nutrition_range"]),
    ("nutrition_range_ost",   "pokaż bilans kalorii za ostatnie 7 dni",["nutrition_range"]),
    ("nutrition_range_spoz",  "pokaż spożycie z ostatnich 7 dni",      ["nutrition_range"]),
    ("nutrition_range_pon",   "pokaż kalorie od poniedziałku",         ["nutrition_range"]),
]

# Known limitations: these datetimes may have no data in public.*
PARTIAL_ALLOWED = {"nutrition_day_today", "nutrition_day_0530",
                   "daily_balance_today", "daily_balance_0530",
                   "nutrition_range_7d", "nutrition_range_ost",
                   "nutrition_range_spoz", "nutrition_range_pon",
                   "intake_logs_list_today", "intake_logs_list_0531",
                   "intake_logs_list_meal", "intake_logs_list_raw",
                   "intake_logs_list_lista"}


def _check_envelope(result: dict) -> list[str]:
    issues = []
    for key in REQUIRED_ENVELOPE_KEYS:
        if key not in result:
            issues.append(f"missing key '{key}'")
    return issues


def run():
    summary = {
        "test_time": __import__("datetime").datetime.now().isoformat(),
        "total": len(TESTS),
        "passed": 0,
        "failed": 0,
        "partial": 0,
        "details": [],
    }

    for label, query, expected_intents in TESTS:
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
                if not result.get("intent"):
                    detail["issues"].append("OK but intent empty")
            elif status in ("PARTIAL", "ERROR") and label not in PARTIAL_ALLOWED:
                detail["issues"].append(
                    f"Unexpected {status} for label not in PARTIAL_ALLOWED"
                )

            if detail["issues"]:
                detail["status"] = "PARTIAL" if status != "ERROR" else "ERROR"
            else:
                detail["status"] = "OK" if status != "ERROR" else "ERROR"
                if status == "PARTIAL":
                    detail["status"] = "PARTIAL"

            detail["sources_used"] = result.get("sources_used", [])
            detail["missing_sources"] = result.get("missing_sources", [])
            detail["warnings"] = result.get("warnings", [])
            detail["fallback_reason"] = result.get("fallback_reason")

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
