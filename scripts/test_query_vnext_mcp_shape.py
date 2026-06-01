#!/usr/bin/env python3
"""test_query_vnext_mcp_shape.py — verify query_vnext envelope is MCP-safe.

Simulates how qbot_mcp_adapter.py would wrap handle_query() output.
Does NOT call MCP, does NOT change production.

Usage:
    cd /opt/qbot/app
    .venv/bin/python scripts/test_query_vnext_mcp_shape.py
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import date, datetime

sys.path.insert(0, "/opt/qbot/app")
from qbot_query_handler import handle_query

REQUIRED_ENVELOPE_KEYS = [
    "status", "engine", "intent", "answer", "data",
    "sources_used", "missing_sources", "freshness",
    "action_draft", "fallback_reason", "warnings",
]

VALID_STATUSES = {"OK", "PARTIAL", "ERROR", "UNRECOGNIZED"}
RECOGNIZED_INTENTS = {
    "daily_balance", "nutrition_day", "sleep_day",
    "wellness_day", "energy_day", "training_recent", "xert_status",
}

TESTS: list[tuple[str, str, str | None]] = [
    # (label, query, expected_intent_or_None)
    ("daily_balance_today",   "pokaż dzisiejszy bilans kalorii",     "daily_balance"),
    ("nutrition_day_today",   "pokaż moje jedzenie dzisiaj",          "nutrition_day"),
    ("sleep_day_today",       "pokaż sen dzisiaj",                   "sleep_day"),
    ("wellness_day_today",    "pokaż wellness dzisiaj",               "wellness_day"),
    ("energy_day_today",      "pokaż energię dzisiaj",               "energy_day"),
    ("training_recent_7d",    "pokaż aktywności z ostatnich 7 dni",   "training_recent"),
    ("xert_status",           "pokaż Xert",                          "xert_status"),
    ("unrecognized_poem",     "napisz mi wiersz",                    "unrecognized"),
    ("unrecognized_noise",    "blah blah blah asdf 12345",           "unrecognized"),
]


def _simulate_mcp_wrapper(handler_result: dict) -> dict:
    """Simulate what _mcp_result_content() does in qbot_mcp_adapter.py.

    Converts to JSON-safe types and wraps in MCP content format.
    """
    def _json_default(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    normalized = json.loads(
        json.dumps(handler_result, ensure_ascii=False, default=_json_default)
    )
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(normalized, ensure_ascii=False),
            }
        ],
        "structuredContent": normalized,
    }


def _check_envelope(result: dict) -> list[str]:
    issues = []
    for key in REQUIRED_ENVELOPE_KEYS:
        if key not in result:
            issues.append(f"missing envelope key '{key}'")
    return issues


def run():
    summary = {
        "test_time": datetime.now().isoformat(),
        "engine_under_test": "query_vnext",
        "mcp_wrapper_simulated": "_mcp_result_content() from qbot_mcp_adapter.py:431",
        "total": len(TESTS),
        "passed": 0,
        "failed": 0,
        "partial": 0,
        "details": [],
        "mcp_shape_verdict": None,
    }

    envelope_issues_total = 0
    serialization_ok = True
    mcp_shape_ok = True

    for label, query, expected_intent in TESTS:
        detail = {
            "label": label,
            "query": query,
            "status": "ERROR",
            "issues": [],
            "mcp_serializable": False,
        }
        try:
            result = handle_query(query)
            detail["result_status"] = result.get("status")
            detail["intent"] = result.get("intent")

            # 1. Check envelope has all keys
            env_issues = _check_envelope(result)
            if env_issues:
                detail["issues"].extend(env_issues)
                envelope_issues_total += len(env_issues)

            # 2. Status validity
            status = result.get("status", "")
            if status not in VALID_STATUSES:
                detail["issues"].append(f"invalid status '{status}' (expected one of {VALID_STATUSES})")

            # 3. Engine check for recognized intents
            intent = result.get("intent", "")
            if intent in RECOGNIZED_INTENTS:
                if result.get("engine") != "query_vnext":
                    detail["issues"].append(f"engine != 'query_vnext': {result.get('engine')}")

            # 4. Unrecognized handling
            if expected_intent == "unrecognized":
                if intent != "unrecognized":
                    detail["issues"].append(
                        f"expected unrecognized but got intent={intent}"
                    )
                if status != "UNRECOGNIZED":
                    detail["issues"].append(
                        f"unrecognized query should have UNRECOGNIZED status, got {status}"
                    )

            # 5. answer is string
            answer = result.get("answer")
            if not isinstance(answer, str):
                detail["issues"].append(f"answer is not a string: {type(answer)}")

            # 6. sources_used for recognized intents
            if intent in RECOGNIZED_INTENTS and status in ("OK", "PARTIAL"):
                if not result.get("sources_used"):
                    detail["issues"].append(
                        f"intent={intent} status={status} but sources_used is empty"
                    )

            # 7. JSON serialization test
            try:
                json.dumps(result, ensure_ascii=False, default=str)
                detail["mcp_serializable"] = True
            except Exception as exc:
                detail["issues"].append(f"JSON serialization failed: {exc}")
                serialization_ok = False

            # 8. Simulate MCP wrapping
            try:
                mcp_wrapped = _simulate_mcp_wrapper(result)
                detail["mcp_wrapped_ok"] = True
                detail["mcp_wrapped_content_type"] = type(mcp_wrapped["content"]).__name__
                detail["mcp_wrapped_structured_type"] = type(mcp_wrapped["structuredContent"]).__name__
                # Verify re-serialization of the MCP wrapper
                json.dumps(mcp_wrapped, ensure_ascii=False, default=str)
            except Exception as exc:
                detail["mcp_wrapped_ok"] = False
                detail["issues"].append(f"MCP wrapping failed: {exc}")
                mcp_shape_ok = False

            # Determine detail status
            if detail["issues"]:
                if any("failed" in i.lower() for i in detail["issues"]):
                    detail["status"] = "ERROR"
                else:
                    detail["status"] = "PARTIAL" if status != "ERROR" else "ERROR"
            else:
                detail["status"] = "OK" if status != "ERROR" else "ERROR"
                if status == "PARTIAL":
                    detail["status"] = "PARTIAL"

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

    # Overall MCP shape verdict
    if envelope_issues_total == 0 and serialization_ok and mcp_shape_ok:
        summary["mcp_shape_verdict"] = "PASS — envelope is safe to wrap with _mcp_result_content()"
    else:
        mcp_fails = []
        if envelope_issues_total > 0:
            mcp_fails.append(f"{envelope_issues_total} envelope key issues")
        if not serialization_ok:
            mcp_fails.append("JSON serialization failed")
        if not mcp_shape_ok:
            mcp_fails.append("MCP wrapping failed")
        summary["mcp_shape_verdict"] = f"ISSUES — {'; '.join(mcp_fails)}"

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return summary


if __name__ == "__main__":
    s = run()
    if s["failed"] > 0:
        sys.exit(1)
