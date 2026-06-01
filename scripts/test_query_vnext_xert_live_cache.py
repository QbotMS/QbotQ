#!/usr/bin/env python3
"""test_query_vnext_xert_live_cache.py — test xert_status with live/cache model.

Usage:
    cd /opt/qbot/app
    .venv/bin/python scripts/test_query_vnext_xert_live_cache.py
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

TESTS: list[tuple[str, str, list[str]]] = [
    ("xert_cache_main",  "pokaż Xert",                ["xert_status"]),
    ("regression_nutrition","pokaż moje jedzenie dzisiaj",["nutrition_day"]),
    ("regression_garage","szukaj Rapha",                ["garage_search"]),
    ("regression_memory","co wiem o rowerze",           ["memories_search"]),
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
            if status == "ERROR":
                detail["issues"].append("handler returned ERROR")

            # For xert_status, check data fields
            if result.get("intent") == "xert_status":
                dd = result.get("data", {})
                if "source_type" not in dd:
                    detail["issues"].append("missing source_type in data")
                if "cache_age_minutes" not in dd:
                    detail["issues"].append("missing cache_age_minutes in data")
                # Check no secrets in output
                answer = result.get("answer", "")
                for secret_word in ["XERT_EMAIL", "XERT_PASSWORD", "xert_public", "token"]:
                    if secret_word in answer:
                        detail["issues"].append(f"secret leaked in answer: {secret_word}")
                output_str = json.dumps(result, default=str)
                if "xert_public" in output_str.lower():
                    pass  # This is the standard auth username, not a secret
                if "XERT_EMAIL" in output_str or "XERT_PASSWORD" in output_str:
                    detail["issues"].append("secret leaked in output")

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
