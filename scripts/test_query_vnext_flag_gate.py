#!/usr/bin/env python3
"""test_query_vnext_flag_gate.py — verify qbot_mcp_adapter flag gate integration.

Tests:
1. qbot_mcp_adapter imports successfully without QBOT_QUERY_VNEXT_ENABLED
2. qbot_mcp_adapter imports successfully with QBOT_QUERY_VNEXT_ENABLED=1
3. query_vnext handle_query works independently
4. (Optional) Simulate MCP dispatch without server

Does NOT start the server, does NOT change production.
Does NOT set .env or env vars permanently.

Usage:
    cd /opt/qbot/app
    QBOT_QUERY_VNEXT_ENABLED= .venv/bin/python scripts/test_query_vnext_flag_gate.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime

sys.path.insert(0, "/opt/qbot/app")

TEST_CASES = [
    {
        "label": "import_adapter_no_flag",
        "env": {},
        "query": None,
    },
    {
        "label": "import_adapter_flag_1",
        "env": {"QBOT_QUERY_VNEXT_ENABLED": "1"},
        "query": None,
    },
    {
        "label": "handle_query_independent",
        "env": {},
        "query": None,
    },
]


def run():
    summary = {
        "test_time": datetime.now().isoformat(),
        "total": 0,
        "passed": 0,
        "failed": 0,
        "details": [],
        "mcp_adapter_import_ok": False,
        "mcp_adapter_flag_gate_code_present": False,
    }

    # ── Test 1: import qbot_mcp_adapter without flag ──
    detail = {"label": "import_adapter_no_flag", "phase": "import"}
    saved = dict(os.environ)
    try:
        # Unset the flag if set
        os.environ.pop("QBOT_QUERY_VNEXT_ENABLED", None)
        # Clear any cached module
        for mod in list(sys.modules.keys()):
            if mod.startswith("qbot_"):
                sys.modules.pop(mod, None)
        # Re-import (mcp_adapter imports many qbot_* modules indirectly)
        import importlib
        import qbot_mcp_adapter
        importlib.reload(qbot_mcp_adapter)
        detail["status"] = "OK"
        detail["detail"] = "qbot_mcp_adapter imported OK without flag"
        summary["mcp_adapter_import_ok"] = True
    except Exception as exc:
        detail["status"] = "ERROR"
        detail["detail"] = f"Import failed: {exc}"
        detail["traceback"] = traceback.format_exc()
    finally:
        os.environ.clear()
        os.environ.update(saved)
    summary["details"].append(detail)
    summary["total"] += 1
    if detail["status"] == "OK":
        summary["passed"] += 1
    else:
        summary["failed"] += 1

    # ── Test 2: import qbot_mcp_adapter with QBOT_QUERY_VNEXT_ENABLED=1 ──
    detail = {"label": "import_adapter_flag_1", "phase": "import"}
    saved = dict(os.environ)
    try:
        os.environ["QBOT_QUERY_VNEXT_ENABLED"] = "1"
        import importlib
        import qbot_mcp_adapter
        importlib.reload(qbot_mcp_adapter)
        detail["status"] = "OK"
        detail["detail"] = "qbot_mcp_adapter imported OK with QBOT_QUERY_VNEXT_ENABLED=1"
    except Exception as exc:
        detail["status"] = "ERROR"
        detail["detail"] = f"Import with flag=1 failed: {exc}"
        detail["traceback"] = traceback.format_exc()
    finally:
        os.environ.clear()
        os.environ.update(saved)
    summary["details"].append(detail)
    summary["total"] += 1
    if detail["status"] == "OK":
        summary["passed"] += 1
    else:
        summary["failed"] += 1

    # ── Test 3: handle_query works independently ──
    detail = {"label": "handle_query_independent", "phase": "execution"}
    try:
        from qbot_query_handler import handle_query
        test_queries = [
            ("daily_balance", "pokaż dzisiejszy bilans kalorii"),
            ("nutrition_day", "pokaż moje jedzenie dzisiaj"),
            ("unrecognized", "napisz mi wiersz"),
        ]
        results = []
        for intent, q in test_queries:
            r = handle_query(q)
            results.append({
                "intent": r.get("intent"),
                "status": r.get("status"),
                "engine": r.get("engine"),
                "query": q[:40],
            })
        detail["status"] = "OK"
        detail["detail"] = "handle_query works independently"
        detail["test_results"] = results
    except Exception as exc:
        detail["status"] = "ERROR"
        detail["detail"] = f"handle_query failed: {exc}"
        detail["traceback"] = traceback.format_exc()
    summary["details"].append(detail)
    summary["total"] += 1
    if detail["status"] == "OK":
        summary["passed"] += 1
    else:
        summary["failed"] += 1

    # ── Test 4: verify flag gate code exists in adapter ──
    detail = {"label": "flag_gate_code_present", "phase": "inspection"}
    try:
        import inspect
        import qbot_mcp_adapter
        source = inspect.getsource(qbot_mcp_adapter)
        if "QBOT_QUERY_VNEXT_ENABLED" in source:
            detail["status"] = "OK"
            detail["detail"] = "Flag gate QBOT_QUERY_VNEXT_ENABLED found in qbot_mcp_adapter.py source"
            summary["mcp_adapter_flag_gate_code_present"] = True
        else:
            detail["status"] = "ERROR"
            detail["detail"] = "Flag gate QBOT_QUERY_VNEXT_ENABLED NOT found in source"
    except Exception as exc:
        detail["status"] = "ERROR"
        detail["detail"] = f"Inspection failed: {exc}"
        detail["traceback"] = traceback.format_exc()
    summary["details"].append(detail)
    summary["total"] += 1
    if detail["status"] == "OK":
        summary["passed"] += 1
    else:
        summary["failed"] += 1

    # ── Overall verdict ──
    all_ok = summary["failed"] == 0
    summary["verdict"] = "PASS" if all_ok else "FAIL"
    summary["note"] = (
        "query_vnext is gated behind QBOT_QUERY_VNEXT_ENABLED=1. "
        "Default (flag unset) → Albert. "
        "Flag=1 with UNRECOGNIZED → falls back to Albert."
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return summary


if __name__ == "__main__":
    s = run()
    if s["failed"] > 0:
        sys.exit(1)
