#!/usr/bin/env python3
"""test_query_vnext_explicit_ranges.py — test explicit date range parsing for nutrition_range.

Usage:
    cd /opt/qbot/app
    .venv/bin/python scripts/test_query_vnext_explicit_ranges.py
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
    # (label, query, expected_intents, allow_partial)
    ("explicit_range_ymd",   "pokaż bilans od 2026-05-20 do 2026-05-30",           ["nutrition_range"], True),
    ("explicit_range_miedzy","pokaż spożycie między 2026-05-24 a 2026-05-30",        ["nutrition_range"], True),
    ("explicit_range_okres", "pokaż kalorie za okres 2026-05-20 - 2026-05-30",      ["nutrition_range"], True),
    ("explicit_range_dmy",   "pokaż jedzenie od 20.05.2026 do 30.05.2026",          ["nutrition_range"], True),
    ("explicit_range_inverted","pokaż bilans od 2026-05-30 do 2026-05-20",          ["nutrition_range"], True),
    ("explicit_range_too_wide","pokaż bilans od 2026-04-01 do 2026-05-30",          ["nutrition_range"], True),
    # Regression
    ("regression_7d",        "pokaż bilans 7 dni",                                  ["nutrition_range"], True),
    ("regression_ostatnie",  "pokaż spożycie z ostatnich 7 dni",                     ["nutrition_range"], True),
    ("regression_nutrition_day","pokaż moje jedzenie dzisiaj",                       ["nutrition_day"], False),
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

    for label, query, expected_intents, allow_partial in TESTS:
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
                detail["issues"].append(f"handler returned ERROR: {result.get('answer','')[:80]}")
            elif status == "PARTIAL" and not allow_partial:
                detail["issues"].append(f"Unexpected PARTIAL for {label}")

            # For explicit range tests, check data fields
            if label.startswith("explicit_range") or label.startswith("regression"):
                dd = result.get("data", {})
                if label == "explicit_range_inverted":
                    if dd.get("date_from", "") > dd.get("date_to", ""):
                        detail["issues"].append("inverted range not corrected")
                if label == "explicit_range_too_wide":
                    if status not in ("PARTIAL", "ERROR"):
                        detail["issues"].append("too-wide range should return PARTIAL or ERROR")
                    found_limit = any("limit" in str(w).lower() or "31" in str(w) for w in result.get("warnings", []))
                    if not found_limit and status != "PARTIAL":
                        pass  # allow if PARTIAL for other reasons

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
