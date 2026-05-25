"""Legacy Q read-only capability wrappers — diagnostic status per capability."""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qbot_tools import _tool_qbot_api_self_check, _tool_qbot_project_guard_check

_PROJECT_ROOT: Path = Path("/opt/qbot/app")
_SKIP_DIRS: set[str] = {".git", ".venv", "__pycache__", ".pytest_cache", "logs", "outgoing", "backups", "node_modules"}
_SKIP_FILES: set[str] = {".env.local", ".env", ".garmin_tokens.json", ".garmin_session.pkl", ".hammerhead_tokens"}
_MAX_FILE: int = 300_000


def _file_excerpt(path: Path, keywords: list[str], max_len: int = 200) -> list[str]:
    """Return up to 5 short excerpts where keywords matched."""
    excerpts: list[str] = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")[:_MAX_FILE]
    except Exception:
        return excerpts
    for line in content.splitlines():
        ll = line.lower().strip()
        if any(k in ll for k in keywords) and len(excerpts) < 5:
            excerpts.append(line.strip()[:max_len])
    return excerpts


def _scan_symbols(path: Path, capability: str) -> list[str]:
    patterns: dict[str, list[str]] = {
        "export": ["def export", "def report", "def write", "def render", "export_report", "def generate", "to_csv", "to_json"],
        "garmin": ["def garmin", "def auth", "def upload", "def download", "def sync_garmin", "garmin_connect", "GARMIN"],
        "qlab": ["def route", "def endpoint", "@app", "fastapi", "qlab_server", "QLAB", "qbot_qlab"],
        "sync": ["def sync", "def poll", "def fetch", "def push", "def pull", "def import", "def schedule", "synchronize"],
    }
    kw_list = patterns.get(capability, [])
    return _file_excerpt(path, kw_list)


def _detect_capability_files(capability: str) -> list[dict[str, Any]]:
    kw_map: dict[str, list[str]] = {
        "export": ["export", "report", "csv", "json", "write", "render", "outgoing"],
        "garmin": ["garmin", "connect", "fit", "tcx", "gpx", "upload", "download"],
        "qlab": ["qlab", "qlab_server", "route", "endpoint", "fastapi", "uvicorn", "qbot_qlab"],
        "sync": ["sync", "schedule", "poll", "fetch", "push", "pull", "import"],
    }
    keywords = kw_map.get(capability, [])
    results: list[dict[str, Any]] = []
    try:
        for p in sorted(_PROJECT_ROOT.rglob("*")):
            if any(skip in p.parts for skip in _SKIP_DIRS):
                continue
            if p.name in _SKIP_FILES:
                continue
            if not p.is_file():
                continue
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            if sz > _MAX_FILE:
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")[:_MAX_FILE]
            except Exception:
                continue
            cl = content.lower()
            matched = [k for k in keywords if k in cl]
            if matched:
                rel = p.relative_to(_PROJECT_ROOT).as_posix()
                symbols = _scan_symbols(p, capability)
                results.append({"file": rel, "keywords_matched": matched, "symbols_detected": symbols})
    except Exception:
        pass
    return results


def _recent_log_hint(service: str, lines: int = 50) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["journalctl", "--no-pager", "-u", service, "-n", str(lines), "-q"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode != 0:
            return {"available": False, "error": proc.stderr.strip()[:200]}
        return {"available": True, "lines": len(proc.stdout.splitlines()), "last_line": proc.stdout.splitlines()[-1].strip()[:200] if proc.stdout.splitlines() else ""}
    except Exception as exc:
        return {"available": False, "error": str(exc)[:200]}


# ──────────── individual capability status tools ────────────────────────

def _build_capability_status(capability: str, extra_checks: dict[str, Any] | None = None) -> dict[str, Any]:
    files = _detect_capability_files(capability)
    svc_name = {"qlab": "qbot-qlab-server.service"}.get(capability, "q-bot.service")
    log_hint = _recent_log_hint(svc_name)

    readiness = "PARTIAL" if files else "UNKNOWN"
    if readiness != "UNKNOWN":
        readiness = "READY" if len(files) >= 5 else "PARTIAL"

    return {
        "tool": f"qbot_legacy_{capability}_status",
        "capability": capability,
        "detected_files": files,
        "detected_functions_or_symbols": len([f for f in files if f.get("symbols_detected")]),
        "related_logs_summary": log_hint,
        "config_presence": "detected" if any("config" in str(f.get("file", "")) for f in files) else "not detected",
        "external_dependency_hints": extra_checks or {},
        "readiness": readiness,
        "blockers": [],
        "warnings": [] if files else ["No files detected for this capability"],
        "safe_next_steps": [
            f"Review detected {len(files)} files for {capability} capability",
            "All diagnostics are read-only — no legacy code executed",
            "Proceed to Phase 2 (safe execution wrappers) only after operator review",
        ],
    }


def _tool_qbot_legacy_export_status(_args: dict | None = None) -> dict[str, Any]:
    return _build_capability_status("export")


def _tool_qbot_legacy_garmin_status(_args: dict | None = None) -> dict[str, Any]:
    return _build_capability_status("garmin")


def _tool_qbot_legacy_qlab_status(_args: dict | None = None) -> dict[str, Any]:
    status = _build_capability_status("qlab")
    try:
        proc = subprocess.run(
            ["systemctl", "show", "qbot-qlab-server.service",
             "--property=ActiveState,SubState"],
            capture_output=True, text=True, timeout=5,
        )
        for line in proc.stdout.splitlines():
            if "ActiveState=active" in line:
                status["warnings"].append("qbot-qlab-server.service is active — do not restart")
    except Exception:
        pass
    return status


def _tool_qbot_legacy_sync_status(_args: dict | None = None) -> dict[str, Any]:
    return _build_capability_status("sync")


# ──────────── capability_status dispatcher ──────────────────────────────

_ALLOWED_CAPS: dict[str, Any] = {
    "export": _tool_qbot_legacy_export_status,
    "garmin": _tool_qbot_legacy_garmin_status,
    "qlab": _tool_qbot_legacy_qlab_status,
    "sync": _tool_qbot_legacy_sync_status,
}


def _tool_qbot_legacy_capability_status(args: dict | None = None) -> dict[str, Any]:
    cap = (args or {}).get("capability", "")
    if cap not in _ALLOWED_CAPS:
        return {
            "tool": "qbot_legacy_capability_status",
            "status": "error",
            "error": f"unknown capability: {cap!r}",
            "allowed": sorted(_ALLOWED_CAPS.keys()),
        }
    result = _ALLOWED_CAPS[cap]({})
    result["tool"] = "qbot_legacy_capability_status"
    return result


# ──────────── readonly_wrapper_report ───────────────────────────────────

def _tool_qbot_legacy_readonly_wrapper_report(_args: dict | None = None) -> dict[str, Any]:
    caps_data: dict[str, Any] = {}
    readiness_map: dict[str, str] = {}
    blockers: list[str] = []
    warnings: list[str] = []

    for cap in ["export", "garmin", "qlab", "sync"]:
        try:
            caps_data[cap] = _ALLOWED_CAPS[cap]({})
        except Exception as exc:
            caps_data[cap] = {"readiness": "ERROR", "error": str(exc)}
        r = caps_data[cap].get("readiness", "UNKNOWN")
        readiness_map[cap] = r
        for w in caps_data[cap].get("warnings", []):
            if w not in warnings:
                warnings.append(f"{cap}: {w}")

    try:
        from qbot_legacy_inventory_tools import _tool_qbot_legacy_migration_plan
        mig = _tool_qbot_legacy_migration_plan()
    except Exception:
        mig = {"migration_readiness_percent": 85}

    ready_count = sum(1 for r in readiness_map.values() if r == "READY")
    partial_count = sum(1 for r in readiness_map.values() if r == "PARTIAL")
    unknown_count = sum(1 for r in readiness_map.values() if r == "UNKNOWN")

    takeover_pct = 40 + ready_count * 10 + partial_count * 5

    return {
        "tool": "qbot_legacy_readonly_wrapper_report",
        "status": "OK" if unknown_count == 0 else "WARN",
        "capabilities": {k: {"readiness": v, "files": len(caps_data.get(k, {}).get("detected_files", []))} for k, v in readiness_map.items()},
        "readiness_by_capability": readiness_map,
        "blockers": blockers,
        "warnings": warnings,
        "recommended_next_phase": "Phase 2: safe execution wrappers" if unknown_count == 0 else "Phase 1: complete read-only diagnostics",
        "takeover_readiness_percent": takeover_pct,
    }


# ──────────── wrapper_answer_context ────────────────────────────────────

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


def _tool_qbot_legacy_wrapper_answer_context(_args: dict | None = None) -> dict[str, Any]:
    try:
        raw = _tool_qbot_legacy_readonly_wrapper_report()
    except Exception as exc:
        return {"tool": "qbot_legacy_wrapper_answer_context", "status": "error", "error": str(exc)}
    return {
        "tool": "qbot_legacy_wrapper_answer_context",
        "safe_for_llm": True,
        "source": "qbot_legacy_readonly_wrapper_report",
        "context": _sanitize(raw),
        "suggested_answer_outline": ["1. Summarize 4 capability wrappers", "2. Note ready/partial/unknown statuses", "3. Recommend Phase 2 prerequisites", "4. Stay factual"],
        "llm_must_not": ["execute export", "sync data", "upload to Garmin", "restart qlab", "modify legacy code", "access secrets"],
        "limitations": ["Read-only diagnostic", "No legacy code executed", "No external network calls"],
    }


def _get_legacy_wrapper_tool(name: str):
    mapping: dict[str, Any] = {
        "qbot_legacy_export_status": _tool_qbot_legacy_export_status,
        "qbot_legacy_garmin_status": _tool_qbot_legacy_garmin_status,
        "qbot_legacy_qlab_status": _tool_qbot_legacy_qlab_status,
        "qbot_legacy_sync_status": _tool_qbot_legacy_sync_status,
        "qbot_legacy_capability_status": _tool_qbot_legacy_capability_status,
        "qbot_legacy_readonly_wrapper_report": _tool_qbot_legacy_readonly_wrapper_report,
        "qbot_legacy_wrapper_answer_context": _tool_qbot_legacy_wrapper_answer_context,
    }
    return mapping.get(name)
