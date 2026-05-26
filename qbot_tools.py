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
    try:
        from qbot_legacy_cutover_tools import _tool_qbot_legacy_cutover_status
        cutover = _tool_qbot_legacy_cutover_status()
        cutover_completed = bool(cutover.get("cutover_completed"))
    except Exception:
        cutover = {"status": "UNKNOWN"}
        cutover_completed = False

    services: list[dict[str, Any]] = []
    for svc in _SERVICES:
        entry = _service_status(svc)
        if svc == "q-bot.service" and cutover_completed:
            if entry.get("active_state") != "active" and entry.get("unit_file_state") in ("disabled", "masked", "static"):
                entry["status"] = "OK"
                entry["expected_after_cutover"] = True
                entry["note"] = "legacy service disabled after cutover"
        services.append(entry)

    return {
        "tool": "qbot_services_status",
        "cutover_completed": cutover_completed,
        "cutover_status": cutover,
        "services": services,
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

    try:
        rwgps_storage = api_db.rwgps_storage_overview()
    except Exception as exc:
        rwgps_storage = {"status": "ERROR", "error": str(exc)}

    return {
        "tool": "qbot_db_overview",
        "db_connected": True,
        **overview,
        "rwgps_storage": rwgps_storage,
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


def _tool_qbot_ride_readiness_status(_args: dict | None = None) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    def _safe_call(tool_name: str, func, args: dict | None = None, timeout_s: float = 5.0) -> dict[str, Any]:
        def _invoke():
            try:
                result = func(args) if args is not None else func()
            except Exception as exc:
                return {"tool": tool_name, "status": "ERROR", "error": str(exc)}
            if isinstance(result, dict):
                return result
            return {"tool": tool_name, "status": "ERROR", "error": "unexpected tool payload"}

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_invoke)
        try:
            return future.result(timeout=timeout_s)
        except TimeoutError:
            return {"tool": tool_name, "status": "ERROR", "error": f"{tool_name} timed out after {timeout_s:.1f}s"}
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    from qbot_operator_tools import _tool_qbot_readiness_report
    from qbot_ops_tools import _tool_qbot_operator_final_smoke_test
    from qbot_legacy_cutover_tools import _tool_qbot_legacy_cutover_status
    from qbot_mcp_adapter import _tool_qbot_mcp_status
    from qbot_telegram_tools import _tool_qbot_telegram_transport_status

    calls = {
        "readiness": ("qbot_readiness_report", _tool_qbot_readiness_report, None),
        "smoke": ("qbot_operator_final_smoke_test", _tool_qbot_operator_final_smoke_test, None),
        "takeover": ("qbot_legacy_cutover_status", _tool_qbot_legacy_cutover_status, None),
        "telegram": ("qbot_telegram_transport_status", _tool_qbot_telegram_transport_status, {"check_remote": False}),
        "mcp": ("qbot_mcp_status", _tool_qbot_mcp_status, {}),
    }
    results: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    blockers: list[str] = []
    pool = ThreadPoolExecutor(max_workers=len(calls))
    try:
        futures = {
            key: pool.submit(_safe_call, tool_name, func, args)
            for key, (tool_name, func, args) in calls.items()
        }
        for key, future in futures.items():
            try:
                results[key] = future.result(timeout=8.0)
            except TimeoutError:
                results[key] = {"tool": calls[key][0], "status": "ERROR", "error": f"{calls[key][0]} timed out"}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    readiness = results["readiness"]
    smoke = results["smoke"]
    takeover = results["takeover"]
    telegram = results["telegram"]
    mcp = results["mcp"]

    readiness_status = str(readiness.get("status", "UNKNOWN")).upper()
    smoke_status = str(smoke.get("status", "UNKNOWN")).upper()
    takeover_status = str(takeover.get("status", "UNKNOWN")).upper()
    takeover_percent_raw = takeover.get("takeover_readiness_percent", takeover.get("legacy_takeover_percent", 0))
    try:
        takeover_percent = int(takeover_percent_raw)
    except (ValueError, TypeError):
        takeover_percent = 0
    telegram_status = str(telegram.get("status", "UNKNOWN")).upper()
    mcp_status = str(mcp.get("status", "UNKNOWN")).upper()

    if readiness_status in {"ERROR", "NOT_READY"}:
        blockers.append("Qbot readiness report is not ready")
    elif readiness_status not in {"READY", "READY_WITH_WARNINGS"}:
        warnings.append(f"Qbot readiness status: {readiness_status}")

    if smoke_status == "FAIL":
        blockers.append("Final smoke test failed")

    if takeover_status == "ERROR":
        warnings.append("Legacy cutover status check failed")
    elif takeover_percent < 100 or not takeover.get("cutover_completed", False):
        warnings.append(f"Legacy takeover not fully complete: {takeover_percent}%")

    if telegram_status == "ERROR":
        warnings.append("Telegram transport status check failed")
    elif telegram_status != "OK":
        warnings.append(f"Telegram status: {telegram_status}")

    mcp_route_ok = bool(mcp.get("qbot_api_local_ok")) and bool(mcp.get("mcp_routes_enabled", True))
    mcp_public_ok = bool(mcp.get("public_mcp_reachable", True))
    if mcp_status == "ERROR" or not mcp_route_ok:
        blockers.append("MCP route is not healthy")
        mcp_effective = "ERROR"
    else:
        mcp_effective = "OK"

    qbot_core = readiness_status if readiness_status in {"READY", "READY_WITH_WARNINGS", "NOT_READY"} else (
        "READY" if smoke_status == "PASS" and not blockers else readiness_status
    )

    payload = {
        "status": "ok" if not blockers and not warnings else "warn" if not blockers else "error",
        "ready": not blockers,
        "source": "qbot",
        "service": "ride-readiness",
        "qbot_core": qbot_core,
        "legacy_takeover_percent": takeover_percent,
        "telegram": telegram_status if telegram_status in {"OK", "WARN", "ERROR"} else "WARN",
        "mcp": mcp_effective,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
        "blockers": blockers,
        "details": {
            "qbot_readiness_report": readiness,
            "qbot_operator_final_smoke_test": smoke,
            "qbot_legacy_cutover_status": takeover,
            "qbot_telegram_transport_status": telegram,
            "qbot_mcp_status": mcp,
        },
    }

    return {
        "tool": "qbot_ride_readiness_status",
        "status": "OK" if payload["ready"] and not warnings else "WARN" if payload["ready"] else "ERROR",
        "local_endpoint_available": True,
        "public_endpoint_expected": "https://qbot.cytr.us/ride-readiness",
        "payload_preview": payload,
        "warnings": warnings,
        "blockers": blockers,
        "ready": payload["ready"],
        "qext2_ready": True,
        "route": "/ride-readiness",
    }


# ── Project tools ───────────────────────────────────────────────────────

_PROJECT_ROOT = Path("/opt/qbot/app")
_SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules",
              ".pytest_cache", "outgoing", "logs"}


def _tool_qbot_project_tree(args: dict | None = None) -> dict[str, Any]:
    max_depth_raw = (args or {}).get("max_depth", 2)
    try:
        max_depth = int(max_depth_raw)
    except (ValueError, TypeError):
        return {"tool": "qbot_project_tree",
                "error": f"invalid max_depth: {max_depth_raw!r}"}
    if max_depth < 1:
        max_depth = 1
    if max_depth > 4:
        max_depth = 4

    def _walk(path: Path, depth: int) -> list[dict[str, Any]]:
        if depth > max_depth:
            return []
        entries: list[dict[str, Any]] = []
        try:
            children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            return [{"name": path.name, "type": "dir", "error": "permission denied"}]
        for child in children:
            if child.name in _SKIP_DIRS:
                continue
            if child.is_dir():
                subtree = _walk(child, depth + 1)
                entries.append({
                    "name": child.name,
                    "type": "dir",
                    "children": subtree,
                })
            else:
                try:
                    size = child.stat().st_size
                except OSError:
                    size = -1
                entries.append({
                    "name": child.name,
                    "type": "file",
                    "size_bytes": size,
                })
            if len(entries) >= 500:
                entries.append({"name": "...", "type": "truncated"})
                break
        return entries

    tree = _walk(_PROJECT_ROOT, 1)
    return {"tool": "qbot_project_tree", "root": str(_PROJECT_ROOT),
            "max_depth": max_depth, "entries": tree}


def _tool_qbot_project_files(_args: dict | None = None) -> dict[str, Any]:
    files = []
    for path in sorted(_PROJECT_ROOT.rglob("*")):
        if any(p in _SKIP_DIRS for p in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        rel = path.relative_to(_PROJECT_ROOT).as_posix()
        files.append({
            "path": rel,
            "size_bytes": st.st_size,
            "modified_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        })
        if len(files) >= 200:
            files.append({"path": "...", "size_bytes": -1,
                          "modified_at": "truncated"})
            break
    return {"tool": "qbot_project_files", "root": str(_PROJECT_ROOT),
            "count": len(files), "files": files}


def _tool_qbot_project_recent_commits(args: dict | None = None) -> dict[str, Any]:
    limit_raw = (args or {}).get("limit", 10)
    try:
        limit = int(limit_raw)
    except (ValueError, TypeError):
        return {"tool": "qbot_project_recent_commits",
                "error": f"invalid limit: {limit_raw!r}"}
    if limit < 1:
        limit = 1
    if limit > 30:
        limit = 30

    try:
        proc = subprocess.run(
            ["git", "--no-pager", "log", f"-{limit}", "--format=%h %s"],
            capture_output=True, text=True, timeout=5,
            cwd=str(_PROJECT_ROOT),
        )
    except Exception as exc:
        return {"tool": "qbot_project_recent_commits", "error": str(exc)}

    if proc.returncode != 0:
        return {"tool": "qbot_project_recent_commits",
                "error": proc.stderr.strip()}

    commits = [l.strip() for l in proc.stdout.strip().splitlines() if l]
    return {"tool": "qbot_project_recent_commits", "count": len(commits),
            "commits": commits}


def _tool_qbot_project_diff_summary(_args: dict | None = None) -> dict[str, Any]:
    def _git(cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "--no-pager"] + cmd,
            capture_output=True, text=True, timeout=5,
            cwd=str(_PROJECT_ROOT),
        )

    status_proc = _git(["status", "--short"])
    diff_stat = _git(["diff", "--stat"])
    diff_names = _git(["diff", "--name-only"])

    result: dict[str, Any] = {
        "tool": "qbot_project_diff_summary",
        "status_short": [l for l in status_proc.stdout.strip().splitlines() if l],
        "diff_stat": [l for l in diff_stat.stdout.strip().splitlines() if l],
        "diff_files": [l for l in diff_names.stdout.strip().splitlines() if l],
    }
    if status_proc.returncode != 0:
        result.setdefault("errors", []).append(f"status: {status_proc.stderr.strip()}")
    if diff_stat.returncode != 0:
        result.setdefault("errors", []).append(f"diff_stat: {diff_stat.stderr.strip()}")
    return result


def _tool_qbot_project_guard_check(_args: dict | None = None) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []

    result = _tool_qbot_project_diff_summary()
    diff_files = result.get("diff_files", [])
    status_lines = result.get("status_short", [])
    all_names = "\n".join(status_lines + diff_files).lower()

    if "qbot_qlab_server.py" in all_names:
        violations.append({"what": "qbot_qlab_server.py modified", "severity": "ERROR"})

    if ".env.example" in all_names:
        violations.append({"what": ".env.example modified", "severity": "WARN"})

    if "gate" in all_names or "hikconnect" in all_names:
        violations.append({"what": "Gate/HikConnect detected in changes", "severity": "ERROR"})

    gate_path = _PROJECT_ROOT / "gate_hikconnect.py"
    if gate_path.exists():
        violations.append({"what": "gate_hikconnect.py exists on disk", "severity": "ERROR"})

    api_listening = subprocess.run(
        ["ss", "-ltnp"], capture_output=True, text=True, timeout=5
    ).stdout
    if "0.0.0.0:8001" in api_listening:
        violations.append({"what": "API listening on 0.0.0.0", "severity": "ERROR"})

    git_result = _tool_qbot_git_status()
    if not git_result.get("clean", True):
        violations.append({"what": "repo has uncommitted changes", "severity": "WARN"})

    severities = [v["severity"] for v in violations]
    if "ERROR" in severities:
        status = "ERROR"
    elif "WARN" in severities:
        status = "WARN"
    else:
        status = "OK"

    return {
        "tool": "qbot_project_guard_check",
        "status": status,
        "violations": violations,
    }


def _tool_qbot_query(args: dict | None = None) -> dict[str, Any]:
    query = (args or {}).get("query", "")
    execute = (args or {}).get("execute", False) is True
    from qbot_query_processor import process_query
    result = process_query(query, execute)
    result["tool"] = "qbot_query"
    return result
