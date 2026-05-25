"""Implementacje wszystkich narzędzi Q API."""
from __future__ import annotations

import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SERVICES = [
    "q-bot.service",
    "qbot-qlab-server.service",
    "qbot-api.service",
    "postgresql.service",
]

_GIT_REPO = Path("/opt/qbot/app")


def _service_status(svc: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["systemctl", "show", svc,
             "--property=ActiveState,SubState,LoadState,UnitFileState"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception as exc:
        return {"name": svc, "error": str(exc), "status": "ERROR"}

    props = {}
    for line in proc.stdout.strip().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k] = v

    active = props.get("ActiveState", "unknown")
    sub = props.get("SubState", "unknown")
    entry: dict[str, Any] = {
        "name": svc,
        "active_state": active,
        "sub_state": sub,
        "load_state": props.get("LoadState", "unknown"),
        "status": "OK" if active == "active" and sub in ("running", "exited")
        else "WARN" if active == "active"
        else "ERROR",
    }
    ufs = props.get("UnitFileState")
    if ufs is not None:
        entry["unit_file_state"] = ufs
    return entry


# ── Existing tools ──────────────────────────────────────────────────────

def _tool_qbot_status(_args: dict | None = None) -> dict[str, Any]:
    try:
        hostname = subprocess.run(
            ["hostname"], capture_output=True, text=True, timeout=2
        ).stdout.strip()
    except Exception:
        hostname = "unknown"
    return {
        "tool": "qbot_status",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": hostname,
        "python": platform.python_version(),
        "pid": os.getpid(),
    }


def _tool_qbot_services_status(_args: dict | None = None) -> dict[str, Any]:
    return {
        "tool": "qbot_services_status",
        "services": [_service_status(s) for s in _SERVICES],
    }


def _tool_qbot_recent_tool_calls(args: dict | None = None) -> dict[str, Any]:
    limit_raw = (args or {}).get("limit", 10)
    try:
        limit = int(limit_raw)
    except (ValueError, TypeError):
        return {
            "tool": "qbot_recent_tool_calls",
            "error": f"invalid limit: {limit_raw!r}, must be integer",
        }
    if limit < 1:
        return {"tool": "qbot_recent_tool_calls", "error": f"limit {limit} below minimum 1"}
    if limit > 50:
        return {"tool": "qbot_recent_tool_calls", "error": f"limit {limit} above maximum 50"}

    try:
        import api_db
        rows = api_db.select_tool_calls(limit)
    except Exception as exc:
        return {"tool": "qbot_recent_tool_calls", "error": f"query failed: {exc}"}

    entries = []
    for r in rows:
        entry = {
            "id": r["id"],
            "tool": r["tool"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        res = r.get("result")
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except Exception:
                pass
        entry["status"] = "ok" if not (isinstance(res, dict) and "error" in res) else "error"
        entries.append(entry)
    return {"tool": "qbot_recent_tool_calls", "count": len(entries), "calls": entries}


def _tool_qbot_git_status(_args: dict | None = None) -> dict[str, Any]:
    def _run(cmd: list[str]):
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=5,
            cwd=str(_GIT_REPO),
        )

    branch = "unknown"
    commit = "unknown"
    clean = False
    status_short: list[str] = []
    errors: list[str] = []

    proc = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if proc.returncode == 0:
        branch = proc.stdout.strip()
    else:
        errors.append(f"branch: {proc.stderr.strip()}")

    proc = _run(["git", "rev-parse", "HEAD"])
    if proc.returncode == 0:
        commit = proc.stdout.strip()[:12]
    else:
        errors.append(f"commit: {proc.stderr.strip()}")

    proc = _run(["git", "status", "--short"])
    if proc.returncode == 0:
        status_short = [l for l in proc.stdout.strip().splitlines() if l]
        clean = len(status_short) == 0
    else:
        errors.append(f"status: {proc.stderr.strip()}")

    result: dict[str, Any] = {
        "tool": "qbot_git_status",
        "branch": branch,
        "commit": commit,
        "clean": clean,
        "status_short": status_short,
    }
    if errors:
        result["errors"] = errors
    return result


# ── New tools ───────────────────────────────────────────────────────────

def _tool_qbot_api_tools_list(_args: dict | None = None) -> dict[str, Any]:
    from qbot_tool_registry import TOOLS_META

    items = []
    for name, meta in sorted(TOOLS_META.items()):
        items.append({
            "name": name,
            "description": meta["description"],
            "category": meta["category"],
            "safe": meta["safe"],
            "args_schema": meta["args_schema"],
        })
    return {"tool": "qbot_api_tools_list", "count": len(items), "tools": items}


def _tool_qbot_db_overview(_args: dict | None = None) -> dict[str, Any]:
    try:
        import api_db
    except Exception:
        return {"tool": "qbot_db_overview", "db_connected": False, "error": "api_db import failed"}

    try:
        overview = api_db.db_overview()
    except Exception as exc:
        return {"tool": "qbot_db_overview", "db_connected": False, "error": str(exc)}

    return {
        "tool": "qbot_db_overview",
        "db_connected": True,
        **overview,
    }


def _tool_qbot_system_overview(_args: dict | None = None) -> dict[str, Any]:
    def _out(cmd: list[str]) -> str:
        try:
            return subprocess.run(
                cmd, capture_output=True, text=True, timeout=5,
            ).stdout.strip()
        except Exception:
            return "unknown"

    def _read(path: str) -> str:
        try:
            return Path(path).read_text().strip()
        except Exception:
            return "unknown"

    hostname = _out(["hostname"])
    uptime_raw = _read("/proc/uptime")
    uptime_s = float(uptime_raw.split()[0]) if " " in uptime_raw else 0
    hours, rem = divmod(int(uptime_s), 3600)
    minutes = rem // 60
    uptime_str = f"{hours}h {minutes}m"

    loadavg = _read("/proc/loadavg").split()[:3] if _read("/proc/loadavg") != "unknown" else []

    disk = _out(["df", "-h", "/"])

    mem_total = "unknown"
    mem_used = "unknown"
    mem_pct = "unknown"
    mem_raw = _read("/proc/meminfo")
    if mem_raw != "unknown":
        mem_map = {}
        for line in mem_raw.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                mem_map[parts[0].rstrip(":")] = parts[1]
        total_kb = int(mem_map.get("MemTotal", 0))
        avail_kb = int(mem_map.get("MemAvailable", 0))
        if total_kb:
            used_kb = total_kb - avail_kb
            mem_total = f"{total_kb // 1024}M"
            mem_used = f"{used_kb // 1024}M"
            mem_pct = f"{used_kb * 100 // total_kb}%"

    services = [_service_status(s) for s in _SERVICES]

    return {
        "tool": "qbot_system_overview",
        "hostname": hostname,
        "uptime": uptime_str,
        "load_average": loadavg,
        "disk_root": disk,
        "memory": {
            "total": mem_total,
            "used": mem_used,
            "pct": mem_pct,
        },
        "services": services,
    }


def _tool_qbot_api_self_check(_args: dict | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # API alive
    checks.append({"check": "api_alive", "status": "OK"})

    # DB connected
    try:
        import api_db
        db_ok = api_db.ping()
    except Exception:
        db_ok = False
    checks.append({"check": "db_connected", "status": "OK" if db_ok else "ERROR"})

    # qbot-api.service
    svc_api = _service_status("qbot-api.service")
    checks.append({"check": "qbot-api.service", "status": svc_api["status"],
                   "detail": svc_api.get("active_state", "unknown")})

    # postgresql.service
    svc_pg = _service_status("postgresql.service")
    checks.append({"check": "postgresql.service", "status": svc_pg["status"],
                   "detail": svc_pg.get("active_state", "unknown")})

    # git clean
    git_result = _tool_qbot_git_status()
    git_clean = git_result.get("clean", False)
    git_errors = git_result.get("errors", [])
    checks.append({
        "check": "git_clean",
        "status": "OK" if git_clean else "WARN" if not git_errors else "ERROR",
        "detail": "clean" if git_clean else git_result.get("status_short", []),
    })

    # tools count
    from qbot_tool_registry import TOOLS
    tools_count = len(TOOLS)
    checks.append({"check": "available_tools_count", "status": "OK", "detail": tools_count})

    # recent calls count
    recent_count = 0
    if db_ok:
        try:
            recent_count = len(api_db.select_tool_calls(50))
        except Exception:
            pass
    checks.append({"check": "recent_tool_calls_count", "status": "OK", "detail": recent_count})

    # overall status
    statuses = [c["status"] for c in checks]
    if "ERROR" in statuses:
        overall = "ERROR"
    elif "WARN" in statuses:
        overall = "WARN"
    else:
        overall = "OK"

    return {
        "tool": "qbot_api_self_check",
        "status": overall,
        "checks": checks,
    }
