"""Operator pack tools — monitoring, diagnostics, readiness for Qbot API."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from qbot_tools import (
    _tool_qbot_api_self_check,
    _tool_qbot_db_overview,
    _tool_qbot_git_status,
    _tool_qbot_project_diff_summary,
    _tool_qbot_project_guard_check,
    _tool_qbot_project_recent_commits,
    _tool_qbot_recent_tool_calls,
    _tool_qbot_services_status,
    _tool_qbot_system_overview,
)

_MAX_ERROR_OUTPUT = 300


def _tool_qbot_error_summary(args: dict | None = None) -> dict[str, Any]:
    limit_raw = (args or {}).get("limit", 50)
    try:
        limit = int(limit_raw)
    except (ValueError, TypeError):
        return {
            "tool": "qbot_error_summary",
            "status": "error",
            "error": f"invalid limit: {limit_raw!r}, must be integer",
        }
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    try:
        import api_db
        rows = api_db.select_tool_calls(limit)
    except Exception as exc:
        return {
            "tool": "qbot_error_summary",
            "status": "error",
            "error": f"database query failed: {exc}",
        }

    total = len(rows)
    errors: list[dict[str, Any]] = []
    tools_with_errors: dict[str, int] = {}

    for r in rows:
        res = r.get("result")
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except Exception:
                res = None
        is_error = False
        error_text = None
        if isinstance(res, dict):
            if "error" in res:
                is_error = True
                error_text = str(res.get("error", ""))
            elif res.get("status") == "error":
                is_error = True
                error_text = res.get("reason", res.get("error", ""))
        if is_error:
            err_entry: dict[str, Any] = {
                "id": r["id"],
                "tool": r["tool"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "error": error_text[:_MAX_ERROR_OUTPUT] if error_text else "unknown error",
            }
            errors.append(err_entry)
            tools_with_errors[r["tool"]] = tools_with_errors.get(r["tool"], 0) + 1

    errors_count = len(errors)
    if total > 0:
        error_rate = round(errors_count / total * 100, 1)
    else:
        error_rate = 0.0

    if errors_count == 0:
        report_status = "OK"
    elif error_rate < 10:
        report_status = "WARN"
    else:
        report_status = "ERROR"

    recent = sorted(errors, key=lambda e: e["id"], reverse=True)[:20]

    return {
        "tool": "qbot_error_summary",
        "total_checked": total,
        "errors_count": errors_count,
        "error_rate": error_rate,
        "tools_with_errors": dict(sorted(tools_with_errors.items(), key=lambda x: -x[1])),
        "recent_errors": recent,
        "last_error_at": recent[0]["created_at"] if recent else None,
        "status": report_status,
    }


def _tool_qbot_tool_usage_summary(args: dict | None = None) -> dict[str, Any]:
    limit_raw = (args or {}).get("limit", 200)
    try:
        limit = int(limit_raw)
    except (ValueError, TypeError):
        return {
            "tool": "qbot_tool_usage_summary",
            "status": "error",
            "error": f"invalid limit: {limit_raw!r}, must be integer",
        }
    if limit < 1:
        limit = 1
    if limit > 1000:
        limit = 1000

    try:
        import api_db
        rows = api_db.select_tool_calls(limit)
    except Exception as exc:
        return {
            "tool": "qbot_tool_usage_summary",
            "status": "error",
            "error": f"database query failed: {exc}",
        }

    calls_by_tool: dict[str, int] = {}
    calls_by_status: dict[str, int] = {"ok": 0, "error": 0}

    for r in rows:
        tool = r.get("tool", "unknown")
        calls_by_tool[tool] = calls_by_tool.get(tool, 0) + 1
        res = r.get("result")
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except Exception:
                res = None
        if isinstance(res, dict) and ("error" in res or res.get("status") == "error"):
            calls_by_status["error"] += 1
        else:
            calls_by_status["ok"] += 1

    sorted_tools = sorted(calls_by_tool.items(), key=lambda x: -x[1])
    most_used = [{t: c} for t, c in sorted_tools[:10]]

    return {
        "tool": "qbot_tool_usage_summary",
        "total_checked": len(rows),
        "calls_by_tool": dict(sorted_tools),
        "calls_by_status": calls_by_status,
        "most_used_tools": most_used,
        "last_call_at": rows[0]["created_at"].isoformat() if rows and rows[0].get("created_at") else None,
        "status": "OK",
    }


def _tool_qbot_readiness_report(_args: dict | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    api_check = _tool_qbot_api_self_check()
    checks.append({"name": "api_self_check", "status": api_check.get("status", "UNKNOWN"), "detail": api_check})
    if api_check.get("status") == "ERROR":
        blockers.append("API self-check returned ERROR")

    for c in api_check.get("checks", []):
        if c["check"] == "db_connected" and c["status"] != "OK":
            blockers.append("Database disconnected")
        if c["check"] == "qbot-api.service" and c.get("status") == "ERROR":
            blockers.append("qbot-api.service is inactive or failed")

    guard = _tool_qbot_project_guard_check()
    checks.append({"name": "project_guard_check", "status": guard.get("status", "UNKNOWN"), "detail": guard})
    for v in guard.get("violations", []):
        if v["severity"] == "ERROR":
            blockers.append(f"Guard error: {v['what']}")
        elif v["severity"] == "WARN":
            warnings.append(f"Guard warning: {v['what']}")

    git_result = _tool_qbot_git_status()
    checks.append({"name": "git_status", "status": "OK" if git_result.get("clean") else "WARN", "detail": git_result})
    if not git_result.get("clean", True):
        warnings.append("Repository has uncommitted changes")

    db_overview = _tool_qbot_db_overview()
    db_connected = db_overview.get("db_connected", True)
    checks.append({"name": "db_overview", "status": "OK" if db_connected else "ERROR", "detail": db_overview})
    if not db_connected:
        blockers.append("Database disconnected")

    try:
        error_summary = _tool_qbot_error_summary({"limit": 50})
    except Exception as exc:
        error_summary = {"status": "error", "error": str(exc)}
    error_count = error_summary.get("errors_count", 0)
    error_rate = error_summary.get("error_rate", 0)
    checks.append({"name": "error_summary", "status": error_summary.get("status", "UNKNOWN"),
                   "detail": {"errors_count": error_count, "error_rate": error_rate}})
    if error_rate >= 50:
        blockers.append(f"High error rate: {error_rate}% ({error_count} errors)")
    elif error_rate > 0:
        warnings.append(f"Errors detected: {error_rate}% ({error_count} errors)")

    try:
        from qbot_ops_tools import _tool_qbot_test_error_classification
        test_cls = _tool_qbot_test_error_classification({"limit": 200})
    except Exception:
        test_cls = {"status": "error"}
    real_cand = test_cls.get("real_error_candidates", 0)
    checks.append({"name": "test_error_classification",
                   "status": "WARN" if real_cand > 0 else "OK",
                   "detail": {"real_error_candidates": real_cand}})
    if real_cand == 0 and error_count > 0:
        warnings.append(f"All {error_count} errors are expected test errors — no real issues")

    try:
        from qbot_ops_tools import _tool_qbot_backup_status
        backup = _tool_qbot_backup_status()
    except Exception:
        backup = {"status": "ERROR", "error": "backup check failed"}
    checks.append({"name": "backup_status", "status": backup.get("status", "UNKNOWN"),
                   "detail": backup})
    if backup.get("status") == "ERROR":
        blockers.append("Backup status check failed")
    elif backup.get("status") == "WARN":
        warnings.append("Backup not fully configured")

    svc_check = _tool_qbot_services_status()
    checks.append({"name": "services_status", "status": "OK", "detail": svc_check})
    for svc in svc_check.get("services", []):
        if svc.get("status") == "ERROR":
            warnings.append(f"Service {svc['name']} is {svc.get('active_state', 'unknown')}")

    if blockers:
        report_status = "NOT_READY"
        next_action = "Resolve blockers before working"
    elif warnings:
        report_status = "READY_WITH_WARNINGS"
        next_action = "System is ready but review warnings"
    else:
        report_status = "READY"
        next_action = "System is fully ready — proceed"

    return {
        "tool": "qbot_readiness_report",
        "status": report_status,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "recommended_next_action": next_action,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _tool_qbot_operator_snapshot(args: dict | None = None) -> dict[str, Any]:
    include_calls = (args or {}).get("include_recent_calls", True)
    if not isinstance(include_calls, bool):
        include_calls = bool(include_calls)
    include_logs = (args or {}).get("include_logs", False)
    if not isinstance(include_logs, bool):
        include_logs = bool(include_logs)
    include_backup = (args or {}).get("include_backup", True)
    if not isinstance(include_backup, bool):
        include_backup = bool(include_backup)

    recent_limit_raw = (args or {}).get("recent_limit", 20)
    try:
        recent_limit = int(recent_limit_raw)
    except (ValueError, TypeError):
        recent_limit = 20
    if recent_limit < 1:
        recent_limit = 1
    if recent_limit > 50:
        recent_limit = 50

    snapshot: dict[str, Any] = {
        "tool": "qbot_operator_snapshot",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        snapshot["api_self_check"] = _tool_qbot_api_self_check()
    except Exception as exc:
        snapshot["api_self_check"] = {"error": str(exc)}

    try:
        snapshot["readiness_report"] = _tool_qbot_readiness_report()
    except Exception as exc:
        snapshot["readiness_report"] = {"error": str(exc)}

    try:
        snapshot["system_overview"] = _tool_qbot_system_overview()
    except Exception as exc:
        snapshot["system_overview"] = {"error": str(exc)}

    try:
        snapshot["db_overview"] = _tool_qbot_db_overview()
    except Exception as exc:
        snapshot["db_overview"] = {"error": str(exc)}

    try:
        snapshot["git_status"] = _tool_qbot_git_status()
    except Exception as exc:
        snapshot["git_status"] = {"error": str(exc)}

    try:
        snapshot["guard_check"] = _tool_qbot_project_guard_check()
    except Exception as exc:
        snapshot["guard_check"] = {"error": str(exc)}

    try:
        snapshot["error_summary"] = _tool_qbot_error_summary({"limit": 50})
    except Exception as exc:
        snapshot["error_summary"] = {"error": str(exc)}

    if include_calls:
        try:
            snapshot["recent_tool_calls"] = _tool_qbot_recent_tool_calls({"limit": recent_limit})
        except Exception as exc:
            snapshot["recent_tool_calls"] = {"error": str(exc)}

    try:
        from qbot_ops_tools import _tool_qbot_test_error_classification
        snapshot["test_error_classification"] = _tool_qbot_test_error_classification({"limit": 200})
    except Exception as exc:
        snapshot["test_error_classification"] = {"error": str(exc)}

    if include_backup:
        try:
            from qbot_ops_tools import _tool_qbot_backup_status
            snapshot["backup_status"] = _tool_qbot_backup_status()
        except Exception as exc:
            snapshot["backup_status"] = {"error": str(exc)}

    if include_logs:
        try:
            from qbot_ops_tools import _tool_qbot_logs_overview
            snapshot["logs_overview"] = _tool_qbot_logs_overview({"lines": 30})
        except Exception as exc:
            snapshot["logs_overview"] = {"error": str(exc)}

    return snapshot


_OPERATOR_RUNBOOK_TOOLS: dict[str, list[str]] = {
    "safe_to_work": ["qbot_readiness_report", "qbot_project_guard_check", "qbot_git_status"],
    "full_diagnostic": ["qbot_readiness_report", "qbot_operator_snapshot", "qbot_error_summary"],
    "error_review": ["qbot_error_summary", "qbot_tool_usage_summary", "qbot_recent_tool_calls"],
    "project_review": ["qbot_git_status", "qbot_project_diff_summary", "qbot_project_recent_commits", "qbot_project_guard_check"],
    "api_review": ["qbot_api_self_check", "qbot_services_status", "qbot_db_overview", "qbot_tool_usage_summary"],
    "logs_review": ["qbot_logs_overview", "qbot_error_summary", "qbot_test_error_classification"],
    "backup_review": ["qbot_backup_status", "qbot_backup_plan", "qbot_create_backup_script_preview"],
    "maintenance": ["qbot_maintenance_report", "qbot_readiness_report", "qbot_project_guard_check"],
}

_ALLOWED_RUNBOOK_NAMES: set[str] = set(_OPERATOR_RUNBOOK_TOOLS.keys())


def _operator_dispatch(tool_name: str):
    mapping = {
        "qbot_readiness_report": _tool_qbot_readiness_report,
        "qbot_operator_snapshot": _tool_qbot_operator_snapshot,
        "qbot_error_summary": _tool_qbot_error_summary,
        "qbot_tool_usage_summary": _tool_qbot_tool_usage_summary,
        "qbot_project_guard_check": _tool_qbot_project_guard_check,
        "qbot_git_status": _tool_qbot_git_status,
        "qbot_project_diff_summary": _tool_qbot_project_diff_summary,
        "qbot_project_recent_commits": _tool_qbot_project_recent_commits,
        "qbot_api_self_check": _tool_qbot_api_self_check,
        "qbot_services_status": _tool_qbot_services_status,
        "qbot_db_overview": _tool_qbot_db_overview,
        "qbot_recent_tool_calls": _tool_qbot_recent_tool_calls,
    }
    func = mapping.get(tool_name)
    if func:
        return func
    try:
        from qbot_ops_tools import _get_ops_tool
        return _get_ops_tool(tool_name)
    except ImportError:
        return None


def _tool_qbot_operator_runbook(args: dict | None = None) -> dict[str, Any]:
    name = (args or {}).get("name", "")
    execute = (args or {}).get("execute", False) is True

    if name not in _ALLOWED_RUNBOOK_NAMES:
        return {
            "tool": "qbot_operator_runbook",
            "status": "error",
            "error": f"unknown runbook name: {name!r}",
            "allowed": sorted(_ALLOWED_RUNBOOK_NAMES),
            "execution_mode": "preview_only",
            "preview_only": True,
            "planned_tools": [],
            "executed_tools": [],
            "tool_results": None,
        }

    planned = _OPERATOR_RUNBOOK_TOOLS[name]

    if not execute:
        return {
            "tool": "qbot_operator_runbook",
            "runbook_name": name,
            "status": "ok",
            "execution_mode": "preview_only",
            "preview_only": True,
            "planned_tools": planned,
            "executed_tools": [],
            "tool_results": None,
            "limitations": [
                "Preview only; tools were not executed",
                "No arbitrary command execution",
                "Only allowlisted tools can appear in plan",
            ],
        }

    executed: list[str] = []
    results: dict[str, Any] = {}
    has_error = False
    has_ok = False

    for tool_name in planned:
        func = _operator_dispatch(tool_name)
        if func is None:
            has_error = True
            results[tool_name] = {"error": f"unknown tool: {tool_name}"}
            executed.append(tool_name)
            continue
        try:
            result = func({})
            if isinstance(result, dict) and result.get("status") in ("error", "ERROR", "NOT_READY"):
                has_error = True
            else:
                has_ok = True
            results[tool_name] = result
        except Exception as exc:
            has_error = True
            results[tool_name] = {"error": str(exc)}
        executed.append(tool_name)

    if has_error and has_ok:
        status = "partial"
    elif has_error:
        status = "error"
    else:
        status = "ok"

    return {
        "tool": "qbot_operator_runbook",
        "runbook_name": name,
        "status": status,
        "execution_mode": "multi_tool_execute",
        "preview_only": False,
        "planned_tools": planned,
        "executed_tools": executed,
        "tool_results": results,
        "limitations": [
            "Controlled multi-tool execution",
            "Only allowlisted tools were executed",
            "No arbitrary command execution",
        ],
    }
