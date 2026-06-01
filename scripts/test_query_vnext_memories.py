#!/usr/bin/env python3
"""test_query_vnext_memories.py — test memories_search handler.

Usage:
    cd /opt/qbot/app
    .venv/bin/python scripts/test_query_vnext_memories.py
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
    # (label, query, expected_intents, expect_memory_source)
    ("memories_all",     "pokaż notatki",                ["memories_search"], True),
    ("memories_memory",  "pokaż pamięć",                 ["memories_search"], True),
    ("memories_bike",    "co wiem o rowerze",            ["memories_search"], True),
    ("memories_tuscany", "co pamiętasz o Toskanii",       ["memories_search"], True),
    ("memories_outfit",  "znajdź w notatkach outfit",    ["memories_search"], True),
    ("memories_xert",    "pokaż fakty o Xert",           ["memories_search"], True),
    ("memories_rapha",   "przypomnij mi o Rapha",        ["memories_search"], True),
    # Regression — these must NOT go to memories_search
    ("regression_garage_search","szukaj Rapha",          ["garage_search"], False),
    ("regression_garage_status","pokaż garaż",           ["garage_status"], False),
    ("regression_nutrition","pokaż moje jedzenie dzisiaj",["nutrition_day"], False),
    ("regression_balance","pokaż bilans 7 dni",           ["nutrition_range"], False),
    ("regression_xert",  "pokaż Xert",                   ["xert_status"], False),
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

    for label, query, expected_intents, expect_memory_source in TESTS:
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

            # Check sources for memories_search
            if result.get("intent") == "memories_search":
                sources = result.get("sources_used", [])
                has_memory_source = any("memory" in s or "memories" in s for s in sources)
                if expect_memory_source and not has_memory_source:
                    detail["issues"].append(f"expected memory source in sources_used: {sources}")

                dd = result.get("data", {})
                if "result_count" not in dd:
                    detail["issues"].append("missing result_count in data")
                if "results" not in dd:
                    detail["issues"].append("missing results in data")

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
