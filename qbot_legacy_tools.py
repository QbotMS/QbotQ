"""Legacy Q diagnostics — read-only integration with q-bot.service."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from typing import Any

from qbot_tools import (
    _tool_qbot_project_guard_check,
    _tool_qbot_services_status,
)

_LEGACY_SERVICE: str = "q-bot.service"
_MAX_LINE_LENGTH: int = 1000
_ERROR_KW: list[str] = ["error", "failed", "traceback", "exception", "fatal"]
_WARN_KW: list[str] = ["warn", "warning"]


def _validate_lines(raw: object, default: int, min_val: int, max_val: int) -> int:
    try:
        val = int(raw)
    except (ValueError, TypeError):
        val = default
    return max(min_val, min(max_val, val))


# ─────────────────────── qbot_legacy_status ─────────────────────────────

def _tool_qbot_legacy_status(_args: dict | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["systemctl", "show", _LEGACY_SERVICE,
             "--property=ActiveState,SubState,LoadState,UnitFileState"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception as exc:
        return {
            "tool": "qbot_legacy_status",
            "service_name": _LEGACY_SERVICE,
            "status": "ERROR",
            "reason": str(exc),
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
        }

    props = {}
    for line in proc.stdout.strip().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k] = v

    active = props.get("ActiveState", "unknown")
    sub = props.get("SubState", "unknown")

    if active == "active" and sub == "running":
        status = "OK"
        reason = f"{_LEGACY_SERVICE} is active and running"
    elif active == "active":
        status = "WARN"
        reason = f"{_LEGACY_SERVICE} is active but sub-state: {sub}"
    elif active == "failed":
        status = "ERROR"
        reason = f"{_LEGACY_SERVICE} has failed"
    else:
        status = "ERROR"
        reason = f"{_LEGACY_SERVICE} state: {active}"

    return {
        "tool": "qbot_legacy_status",
        "service_name": _LEGACY_SERVICE,
        "active_state": active,
        "sub_state": sub,
        "load_state": props.get("LoadState", "unknown"),
        "unit_file_state": props.get("UnitFileState", "unknown"),
        "status": status,
        "reason": reason,
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────── qbot_legacy_logs ───────────────────────────────

def _tool_qbot_legacy_logs(args: dict | None = None) -> dict[str, Any]:
    lines_req = _validate_lines((args or {}).get("lines", 120), 120, 20, 300)

    try:
        proc = subprocess.run(
            ["journalctl", "--no-pager", "-u", _LEGACY_SERVICE, "-n", str(lines_req), "-q"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as exc:
        return {
            "tool": "qbot_legacy_logs",
            "service": _LEGACY_SERVICE,
            "lines_requested": lines_req,
            "lines_returned": 0,
            "logs": [],
            "error_like_count": 0,
            "warning_like_count": 0,
            "status": "ERROR",
            "error": str(exc),
        }

    if proc.returncode != 0:
        return {
            "tool": "qbot_legacy_logs",
            "service": _LEGACY_SERVICE,
            "lines_requested": lines_req,
            "lines_returned": 0,
            "logs": [],
            "error_like_count": 0,
            "warning_like_count": 0,
            "status": "ERROR",
            "error": proc.stderr.strip() or f"journalctl exit {proc.returncode}",
        }

    log_lines: list[str] = []
    err_count = 0
    warn_count = 0

    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped:
            ll = stripped.lower()
            if any(k in ll for k in _ERROR_KW):
                err_count += 1
            if any(k in ll for k in _WARN_KW):
                warn_count += 1
            log_lines.append(stripped[:_MAX_LINE_LENGTH])

    if proc.returncode == 0 and err_count == 0:
        status = "OK"
    elif err_count > 0:
        status = "WARN"
    else:
        status = "OK"

    return {
        "tool": "qbot_legacy_logs",
        "service": _LEGACY_SERVICE,
        "lines_requested": lines_req,
        "lines_returned": len(log_lines),
        "error_like_count": err_count,
        "warning_like_count": warn_count,
        "logs": log_lines,
        "status": status,
    }


# ─────────────────────── qbot_legacy_error_summary ──────────────────────

def _tool_qbot_legacy_error_summary(args: dict | None = None) -> dict[str, Any]:
    lines_req = _validate_lines((args or {}).get("lines", 300), 300, 50, 1000)

    try:
        proc = subprocess.run(
            ["journalctl", "--no-pager", "-u", _LEGACY_SERVICE, "-n", str(lines_req), "-q"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as exc:
        return {
            "tool": "qbot_legacy_error_summary",
            "status": "ERROR",
            "error": str(exc),
        }

    if proc.returncode != 0:
        return {
            "tool": "qbot_legacy_error_summary",
            "status": "ERROR",
            "error": proc.stderr.strip() or f"journalctl exit {proc.returncode}",
        }

    error_lines: list[str] = []
    warn_lines: list[str] = []
    seen_errors: set[str] = set()
    seen_warns: set[str] = set()

    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        ll = stripped.lower()
        if any(k in ll for k in _ERROR_KW):
            key = stripped[:_MAX_LINE_LENGTH]
            if key not in seen_errors:
                seen_errors.add(key)
                error_lines.append(key)
        elif any(k in ll for k in _WARN_KW):
            key = stripped[:_MAX_LINE_LENGTH]
            if key not in seen_warns:
                seen_warns.add(key)
                warn_lines.append(key)

    err_count = len(error_lines)
    warn_count = len(warn_lines)

    if err_count == 0:
        status = "OK"
    elif err_count <= 5:
        status = "WARN"
    else:
        status = "ERROR"

    return {
        "tool": "qbot_legacy_error_summary",
        "checked_lines": len(proc.stdout.splitlines()),
        "errors_count": err_count,
        "warnings_count": warn_count,
        "recent_error_samples": error_lines[:10],
        "recent_warning_samples": warn_lines[:10],
        "status": status,
    }


# ─────────────────────── qbot_legacy_health_report ──────────────────────

def _tool_qbot_legacy_health_report(_args: dict | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    try:
        legacy_status = _tool_qbot_legacy_status()
    except Exception as exc:
        legacy_status = {"status": "ERROR", "error": str(exc)}
    checks.append({"name": "legacy_status", "status": legacy_status.get("status", "UNKNOWN"),
                   "detail": legacy_status})
    if legacy_status.get("status") == "ERROR":
        blockers.append(f"{_LEGACY_SERVICE} is not healthy: {legacy_status.get('reason', '')}")
        recommendations.append("Check q-bot.service: systemctl status q-bot.service")
    elif legacy_status.get("status") == "WARN":
        warnings.append(f"{_LEGACY_SERVICE} has warnings: {legacy_status.get('reason', '')}")

    try:
        legacy_errors = _tool_qbot_legacy_error_summary({"lines": 300})
    except Exception as exc:
        legacy_errors = {"status": "ERROR", "error": str(exc)}
    checks.append({"name": "legacy_error_summary", "status": legacy_errors.get("status", "UNKNOWN"),
                   "detail": {"errors": legacy_errors.get("errors_count", 0),
                              "warnings": legacy_errors.get("warnings_count", 0)}})
    if legacy_errors.get("status") == "ERROR":
        warnings.append(f"Legacy Q has significant errors: {legacy_errors.get('errors_count', 0)} error patterns")
        recommendations.append("Review qbot_legacy_error_summary for details")

    try:
        svc_check = _tool_qbot_services_status()
    except Exception as exc:
        svc_check = {"services": [], "error": str(exc)}
    checks.append({"name": "services_status", "status": "OK", "detail": svc_check})
    for svc in svc_check.get("services", []):
        if svc.get("name") == _LEGACY_SERVICE and svc.get("status") == "ERROR":
            warnings.append(f"{_LEGACY_SERVICE} service status shows error")

    try:
        guard = _tool_qbot_project_guard_check()
    except Exception as exc:
        guard = {"status": "ERROR", "error": str(exc)}
    checks.append({"name": "project_guard_check", "status": guard.get("status", "UNKNOWN"),
                   "detail": guard})
    for v in guard.get("violations", []):
        if v["severity"] == "ERROR":
            blockers.append(f"Guard error: {v['what']}")
        elif v["severity"] == "WARN":
            warnings.append(f"Guard warning: {v['what']}")

    if blockers:
        overall = "ERROR"
    elif warnings:
        overall = "WARN"
    else:
        overall = "OK"

    return {
        "tool": "qbot_legacy_health_report",
        "status": overall,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "recommendations": recommendations,
        "safe_next_actions": [
            "Review legacy Q status via qbot_legacy_status",
            "Check legacy Q logs via qbot_legacy_logs",
            "Run qbot_legacy_health_report for full diagnosis",
            "Use qbot_legacy_error_summary to analyze errors",
            "All diagnostics are read-only — no restarts or edits",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────── qbot_legacy_answer_context ─────────────────────────

_SENSITIVE_KEYS: set[str] = {"password", "secret", "token", "apikey", "api_key",
                               "pgpassword", "env", "credential", "auth"}
_MAX_DEPTH = 3


def _sanitize_legacy(obj: Any, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return "<truncated depth>"
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if any(s in kl for s in _SENSITIVE_KEYS):
                result[k] = "<redacted>"
            elif isinstance(v, (dict, list)):
                result[k] = _sanitize_legacy(v, depth + 1)
            elif isinstance(v, str) and len(v) > 2000:
                result[k] = v[:2000] + "...<truncated>"
            else:
                result[k] = v
        return result
    elif isinstance(obj, list):
        return [_sanitize_legacy(v, depth + 1) if isinstance(v, (dict, list))
                else (v[:500] + "...<truncated>" if isinstance(v, str) and len(v) > 500 else v)
                for v in obj[:50]]
    elif isinstance(obj, str) and len(obj) > 2000:
        return obj[:2000] + "...<truncated>"
    return obj


def _tool_qbot_legacy_answer_context(_args: dict | None = None) -> dict[str, Any]:
    try:
        raw = _tool_qbot_legacy_health_report()
    except Exception as exc:
        return {
            "tool": "qbot_legacy_answer_context",
            "status": "error",
            "error": f"failed to generate health report: {exc}",
        }

    return {
        "tool": "qbot_legacy_answer_context",
        "safe_for_llm": True,
        "source": "qbot_legacy_health_report",
        "context": _sanitize_legacy(raw),
        "suggested_answer_outline": [
            "1. Summarize legacy Q service status",
            "2. Note any error patterns from logs",
            "3. Highlight guard violations if any",
            "4. Recommend safe next actions (read-only diagnostics)",
            "5. Stay factual — do not invent information",
        ],
        "llm_must_not": [
            "restart q-bot.service",
            "edit legacy Q files",
            "restore or backup",
            "access secrets",
            "execute any command",
            "modify config",
        ],
        "limitations": [
            "Read-only diagnostics only",
            "No command execution",
            "No service modifications",
            "Context sanitized for LLM safety",
        ],
    }


def _get_legacy_tool(name: str):
    mapping = {
        "qbot_legacy_status": _tool_qbot_legacy_status,
        "qbot_legacy_logs": _tool_qbot_legacy_logs,
        "qbot_legacy_error_summary": _tool_qbot_legacy_error_summary,
        "qbot_legacy_health_report": _tool_qbot_legacy_health_report,
        "qbot_legacy_answer_context": _tool_qbot_legacy_answer_context,
    }
    return mapping.get(name)
