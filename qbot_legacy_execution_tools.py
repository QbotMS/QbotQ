"""Legacy Q safe execution wrappers — dry-run, smoke checks, readiness reports."""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Any

from qbot_tools import _tool_qbot_project_guard_check

_QLAB_ENDPOINTS: list[str] = [
    "http://127.0.0.1:8899/health",
]


def _http_check(url: str, timeout: int = 3) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 2,
        )
        code = proc.stdout.strip()
        return {"url": url, "status_code": int(code) if code.isdigit() else 0, "reachable": proc.returncode == 0 and code != "000"}
    except Exception as exc:
        return {"url": url, "status_code": 0, "reachable": False, "error": str(exc)[:200]}


# ──────────── qbot_legacy_qlab_smoke_check ──────────────────────────────

def _tool_qbot_legacy_qlab_smoke_check(_args: dict | None = None) -> dict[str, Any]:
    svc: dict[str, Any] = {}
    try:
        proc = subprocess.run(
            ["systemctl", "show", "qbot-qlab-server.service",
             "--property=ActiveState,SubState"],
            capture_output=True, text=True, timeout=5,
        )
        for line in proc.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                svc[k] = v
    except Exception as exc:
        svc = {"error": str(exc)}

    endpoint_checks = [_http_check(url) for url in _QLAB_ENDPOINTS]
    reachable = len([e for e in endpoint_checks if e.get("reachable")])
    codes = [e.get("status_code", 0) for e in endpoint_checks]

    if svc.get("ActiveState") == "active" and reachable >= 1 and 200 in codes:
        status = "OK"
        next_steps = ["QLab server is active and responding — safe to proceed with shadow mode"]
    elif svc.get("ActiveState") == "active":
        status = "PARTIAL"
        next_steps = ["QLab server is active but some endpoints are unreachable — review configuration"]
    else:
        status = "WARN"
        next_steps = ["QLab server may not be running — check systemd status"]

    return {
        "tool": "qbot_legacy_qlab_smoke_check",
        "service_status": svc,
        "endpoint_checks": endpoint_checks,
        "status": status,
        "safe_next_steps": next_steps,
        "notes": "All checks are read-only; no data sent, no state modified",
    }


# ──────────── dry_run helpers ────────────────────────────────────────────

def _build_dry_run(capability: str) -> dict[str, Any]:
    from qbot_legacy_wrapper_tools import (
        _tool_qbot_legacy_export_status,
        _tool_qbot_legacy_garmin_status,
        _tool_qbot_legacy_sync_status,
    )
    dispatcher: dict[str, Any] = {
        "export": _tool_qbot_legacy_export_status,
        "garmin": _tool_qbot_legacy_garmin_status,
        "sync": _tool_qbot_legacy_sync_status,
    }
    wrapper = dispatcher.get(capability)
    wrapper_data = wrapper({}) if wrapper else {"detected_files": [], "readiness": "UNKNOWN"}

    files = wrapper_data.get("detected_files", [])
    symbols_count = wrapper_data.get("detected_functions_or_symbols", 0)
    readiness = wrapper_data.get("readiness", "UNKNOWN")

    blockers: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []

    if not files:
        blockers.append(f"No files detected for {capability} capability")
    if symbols_count == 0:
        warnings.append(f"No function symbols detected for {capability}")

    deps = {}
    try:
        from qbot_legacy_inventory_tools import _tool_qbot_legacy_dependency_inventory
        deps = _tool_qbot_legacy_dependency_inventory()
    except Exception:
        pass

    if readiness == "UNKNOWN":
        ready = "BLOCKED"
    elif readiness == "PARTIAL":
        ready = "PARTIAL"
    else:
        ready = "READY"

    return {
        "tool": f"qbot_legacy_{capability}_dry_run",
        "dry_run": True,
        "would_check": capability,
        f"detected_{capability}_paths_or_symbols": len(files),
        "external_dependency_hints": deps.get("external_services_detected", [])[:5] if deps else [],
        "missing_requirements": missing,
        "blockers": blockers,
        "warnings": warnings,
        "readiness_for_real_wrapper": ready,
        "status": "ERROR" if blockers else "WARN" if warnings else "OK",
    }


# ──────────── individual dry_run tools ───────────────────────────────────

def _tool_qbot_legacy_export_dry_run(_args: dict | None = None) -> dict[str, Any]:
    return _build_dry_run("export")


def _tool_qbot_legacy_sync_dry_run(_args: dict | None = None) -> dict[str, Any]:
    return _build_dry_run("sync")


def _tool_qbot_legacy_garmin_dry_run(_args: dict | None = None) -> dict[str, Any]:
    return _build_dry_run("garmin")


# ──────────── safe_execution_report ──────────────────────────────────────

def _tool_qbot_legacy_safe_execution_report(_args: dict | None = None) -> dict[str, Any]:
    qlab = _tool_qbot_legacy_qlab_smoke_check()
    export_dr = _tool_qbot_legacy_export_dry_run()
    sync_dr = _tool_qbot_legacy_sync_dry_run()
    garmin_dr = _tool_qbot_legacy_garmin_dry_run()

    wrappers = {
        "qlab_smoke": qlab.get("status", "UNKNOWN"),
        "export_dry_run": export_dr.get("readiness_for_real_wrapper", "UNKNOWN"),
        "sync_dry_run": sync_dr.get("readiness_for_real_wrapper", "UNKNOWN"),
        "garmin_dry_run": garmin_dr.get("readiness_for_real_wrapper", "UNKNOWN"),
    }

    blockers: list[str] = []
    warnings: list[str] = []
    for d in [export_dr, sync_dr, garmin_dr]:
        blockers.extend(d.get("blockers", []))
        warnings.extend(d.get("warnings", []))

    try:
        from qbot_legacy_wrapper_tools import _tool_qbot_legacy_readonly_wrapper_report
        wreport = _tool_qbot_legacy_readonly_wrapper_report()
    except Exception:
        wreport = {"takeover_readiness_percent": 80}

    guard = _tool_qbot_project_guard_check()
    gv = guard.get("violations", [])
    for v in gv:
        if v.get("severity") == "ERROR":
            blockers.append(f"Guard: {v.get('what')}")

    ready_count = sum(1 for v in wrappers.values() if v in ("OK", "READY"))
    shadow_ready = ready_count >= 3 and not blockers

    takeover = 85 if shadow_ready else wreport.get("takeover_readiness_percent", 80)

    return {
        "tool": "qbot_legacy_safe_execution_report",
        "phase": "Phase 2 safe execution wrappers",
        "status": "OK" if shadow_ready else "WARN",
        "wrappers": wrappers,
        "blockers": blockers,
        "warnings": warnings,
        "ready_for_shadow_mode": shadow_ready,
        "takeover_readiness_percent": takeover,
        "recommended_next_phase": "Phase 3: shadow mode (parallel execution)" if shadow_ready else "Resolve blockers before shadow mode",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ──────────── safe_execution_answer_context ─────────────────────────────

_SENSITIVE: set[str] = {"password", "secret", "token", "apikey", "api_key", "pgpassword", "env", "credential", "auth"}


def _sanitize(obj: Any, depth: int = 0) -> Any:
    if depth > 3:
        return "<truncated>"
    if isinstance(obj, dict):
        r: dict[str, Any] = {}
        for k, v in obj.items():
            if any(s in str(k).lower() for s in _SENSITIVE):
                r[k] = "<redacted>"
            elif isinstance(v, (dict, list)):
                r[k] = _sanitize(v, depth + 1)
            elif isinstance(v, str) and len(v) > 2000:
                r[k] = v[:2000] + "...<truncated>"
            else:
                r[k] = v
        return r
    if isinstance(obj, list):
        return [_sanitize(v, depth + 1) if isinstance(v, (dict, list)) else v[:500] + "...<truncated>" if isinstance(v, str) and len(v) > 500 else v for v in obj[:50]]
    return obj[:2000] + "...<truncated>" if isinstance(obj, str) and len(obj) > 2000 else obj


def _tool_qbot_legacy_safe_execution_answer_context(_args: dict | None = None) -> dict[str, Any]:
    try:
        raw = _tool_qbot_legacy_safe_execution_report()
    except Exception as exc:
        return {"tool": "qbot_legacy_safe_execution_answer_context", "status": "error", "error": str(exc)}
    return {
        "tool": "qbot_legacy_safe_execution_answer_context",
        "safe_for_llm": True,
        "source": "qbot_legacy_safe_execution_report",
        "context": _sanitize(raw),
        "suggested_answer_outline": ["1. Summarize safe execution wrapper results", "2. Note shadow mode readiness", "3. Highlight blockers", "4. Recommend next phase"],
        "llm_must_not": ["execute export/sync/garmin", "access tokens", "modify state", "restart services"],
        "limitations": ["Dry-run only", "No real execution", "Sanitized context"],
    }


def _get_legacy_execution_tool(name: str):
    mapping = {
        "qbot_legacy_qlab_smoke_check": _tool_qbot_legacy_qlab_smoke_check,
        "qbot_legacy_export_dry_run": _tool_qbot_legacy_export_dry_run,
        "qbot_legacy_sync_dry_run": _tool_qbot_legacy_sync_dry_run,
        "qbot_legacy_garmin_dry_run": _tool_qbot_legacy_garmin_dry_run,
        "qbot_legacy_safe_execution_report": _tool_qbot_legacy_safe_execution_report,
        "qbot_legacy_safe_execution_answer_context": _tool_qbot_legacy_safe_execution_answer_context,
    }
    return mapping.get(name)
