#!/usr/bin/env python3
"""test_query_vnext_trips.py — test trips_status handler.

Usage:
    cd /opt/qbot/app
    .venv/bin/python scripts/test_query_vnext_trips.py
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

TESTS: list[tuple[str, str, list[str], int | None]] = [
    # (label, query, expected_intents, min_results)
    ("trips_all",        "pokaż wyjazdy",                  ["trips_status"], 1),
    ("trips_my",         "pokaż moje wyjazdy",             ["trips_status"], 1),
    ("trips_planned",    "co mam zaplanowane",             ["trips_status"], 1),
    ("trips_tosk",       "pokaż Toskanię",                 ["trips_status"], 1),
    ("trips_tuscany",    "pokaż Tuscany",                  ["trips_status"], 1),
    ("trips_when_trail", "kiedy Tuscany Trail",            ["trips_status"], 1),
    ("trips_when_tosk",  "kiedy Toskania",                 ["trips_status"], 1),
    ("trips_to_tosk",    "jaki mam wyjazd do Toskanii",    ["trips_status"], 1),
    # Regression
    ("regression_training","pokaż aktywności z ostatnich 7 dni",["training_recent"], None),
    ("regression_nutrition","pokaż moje jedzenie dzisiaj",["nutrition_day"], None),
    ("regression_garage","pokaż garaż",                   ["garage_status"], None),
    ("regression_memory","co wiem o Toskanii",            ["memories_search"], None),
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

    for label, query, expected_intents, min_results in TESTS:
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
                detail["issues"].append("handler returned ERROR")

            # Check result count for trips_status
            if result.get("intent") == "trips_status" and min_results is not None:
                rc = result.get("data", {}).get("result_count", 0)
                if rc < min_results:
                    detail["issues"].append(f"result_count {rc} < min {min_results}")
                # Check new data fields
                dd = result.get("data", {})
                if "search_terms" not in dd:
                    detail["issues"].append("missing search_terms")
                if "filtered" not in dd:
                    detail["issues"].append("missing filtered")

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
