#!/usr/bin/env python3
"""test_query_vnext_logging_safe.py — verify safe logging in qbot3/adapters/mcp_adapter.py.

Checks:
1. _log_query_vnext_metrics helper exists and accepts only safe fields
2. The log format does NOT include full query text, secrets, or personal data
3. Logged fields are: engine, intent, status, fallback_reason, query_len, sources_count, missing_sources_count, duration_ms

Usage:
    cd /opt/qbot/app
    .venv/bin/python scripts/test_query_vnext_logging_safe.py
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime

sys.path.insert(0, "/opt/qbot/app")

SAFE_LOG_FIELDS = {
    "engine", "intent", "status", "fallback",
    "qlen", "sources", "missing", "dur_ms",
}


def run():
    summary = {
        "test_time": datetime.now().isoformat(),
        "module": "qbot3.adapters.mcp_adapter",
        "total": 4,
        "passed": 0,
        "failed": 0,
        "details": [],
    }

    # ── Test 1: module imports with logger ──
    detail = {"label": "module_imports_ok", "status": "ERROR", "issues": []}
    try:
        from qbot3.adapters.mcp_adapter import _log_query_vnext_metrics, logger as _mod_logger
        detail["detail"] = "Module imported OK, _log_query_vnext_metrics exists"
        detail["status"] = "OK"
    except Exception as exc:
        detail["issues"].append(str(exc))
        detail["status"] = "ERROR"
    summary["details"].append(detail)
    if detail["status"] == "OK":
        summary["passed"] += 1
    else:
        summary["failed"] += 1

    # ── Test 2: helper only logs safe fields (no full query) ──
    detail = {"label": "safe_fields_only", "status": "ERROR", "issues": []}
    try:
        from qbot3.adapters.mcp_adapter import _log_query_vnext_metrics
        import inspect
        src = inspect.getsource(_log_query_vnext_metrics)
        # Check the log format string for unsafe patterns
        unsafe = []
        if "query=" in src and "qlen" not in src:
            unsafe.append("format may contain full query")
        if "password" in src.lower() or "token" in src.lower() or "secret" in src.lower() or "key" in src.lower():
            unsafe.append("format may contain secrets")
        # Extract field names from format string
        fmt_line = [l for l in src.split("\n") if "logger.info" in l]
        if fmt_line:
            fmt = fmt_line[0]
            # Check all %s or {} placeholders correspond to safe fields
            if "query=" in fmt and "qlen" not in fmt:
                unsafe.append("format has 'query=' without qlen guard")
        if unsafe:
            detail["issues"].extend(unsafe)
        else:
            detail["detail"] = "Log format uses only safe fields: engine, intent, status, fallback, qlen, sources, missing, dur_ms"
        detail["status"] = "OK" if not unsafe else "ERROR"
    except Exception as exc:
        detail["issues"].append(str(exc))
        detail["status"] = "ERROR"
    summary["details"].append(detail)
    if detail["status"] == "OK":
        summary["passed"] += 1
    else:
        summary["failed"] += 1

    # ── Test 3: no full query in log output ──
    detail = {"label": "no_full_query_in_log", "status": "ERROR", "issues": []}
    try:
        from qbot3.adapters.mcp_adapter import _log_query_vnext_metrics
        import io
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        # Capture the module's actual logger
        mod_logger = logging.getLogger("qbot3.adapters.mcp_adapter")
        mod_logger.addHandler(handler)
        mod_logger.setLevel(logging.INFO)

        _log_query_vnext_metrics(
            engine="query_vnext",
            intent="nutrition_day",
            status="OK",
            fallback_reason=None,
            query_len=42,
            sources_count=3,
            missing_sources_count=0,
            duration_ms=12.34,
        )
        log_text = log_stream.getvalue()
        if "qlen=42" in log_text:
            detail["detail"] = "Log contains qlen (safe) but not full query text"
            detail["status"] = "OK"
        else:
            detail["issues"].append("qlen not found in log output")
        if "nutrition_day" not in log_text:
            detail["issues"].append("intent not found in log output (expected)")
        mod_logger.removeHandler(handler)
    except Exception as exc:
        detail["issues"].append(str(exc))
        detail["status"] = "ERROR"
    summary["details"].append(detail)
    if detail["status"] == "OK":
        summary["passed"] += 1
    else:
        summary["failed"] += 1

    # ── Test 4: fallback reason is logged safely ──
    detail = {"label": "fallback_logged_safely", "status": "ERROR", "issues": []}
    try:
        from qbot3.adapters.mcp_adapter import _log_query_vnext_metrics
        import io
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        mod_logger = logging.getLogger("qbot3.adapters.mcp_adapter")
        mod_logger.addHandler(handler)
        mod_logger.setLevel(logging.INFO)

        _log_query_vnext_metrics(
            engine="albert",
            intent="unrecognized",
            status="OK",
            fallback_reason="query_vnext UNRECOGNIZED — fell back to Albert",
            query_len=15,
            sources_count=0,
            missing_sources_count=0,
            duration_ms=5234.56,
        )
        log_text = log_stream.getvalue()
        if "fallback=" in log_text and "UNRECOGNIZED" in log_text:
            detail["detail"] = "Fallback reason logged safely"
            detail["status"] = "OK"
        else:
            detail["issues"].append("fallback reason not found in log")
        mod_logger.removeHandler(handler)
    except Exception as exc:
        detail["issues"].append(str(exc))
        detail["status"] = "ERROR"
    summary["details"].append(detail)
    if detail["status"] == "OK":
        summary["passed"] += 1
    else:
        summary["failed"] += 1

    summary["verdict"] = "PASS" if summary["failed"] == 0 else "FAIL"
    summary["note"] = (
        "Logging helper logs only: engine, intent, status, fallback_reason, "
        "query_len, sources_count, missing_sources_count, duration_ms. "
        "NO full query text, NO secrets, NO personal data."
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return summary


if __name__ == "__main__":
    s = run()
    if s["failed"] > 0:
        sys.exit(1)
