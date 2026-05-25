"""Operations pack v2 — service logs, backup, error classification, maintenance."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qbot_tools import _tool_qbot_api_self_check, _tool_qbot_git_status, _tool_qbot_project_guard_check

_ALLOWED_SERVICES: set[str] = {
    "qbot-api.service", "q-bot.service", "qbot-qlab-server.service", "postgresql",
}
_BACKUP_DIRS: list[Path] = [Path("/opt/qbot/backups"), Path("/var/backups/qbot")]
_BACKUP_EXTENSIONS: set[str] = {".sql", ".sql.gz", ".dump"}
_MAX_LINE_LENGTH: int = 1000

_ERROR_KW: list[str] = ["error", "failed", "traceback", "exception", "fatal"]
_WARN_KW: list[str] = ["warn", "warning"]


def _journalctl_runner(service: str, lines: int) -> subprocess.CompletedProcess:
    # Postgres journal is under 'postgresql' unit name, map for journalctl
    unit = "postgresql.service" if service == "postgresql" else service
    return subprocess.run(
        ["journalctl", "--no-pager", "-u", unit, "-n", str(lines), "-q"],
        capture_output=True, text=True, timeout=10,
    )


def _validate_lines(raw: object, default: int, min_val: int, max_val: int) -> int:
    try:
        val = int(raw)
    except (ValueError, TypeError):
        val = default
    return max(min_val, min(max_val, val))


# ──────────────────────────── service_logs ──────────────────────────────

def _tool_qbot_service_logs(args: dict | None = None) -> dict[str, Any]:
    service = (args or {}).get("service", "qbot-api.service")
    if service not in _ALLOWED_SERVICES:
        return {
            "tool": "qbot_service_logs",
            "status": "error",
            "error": f"service not allowed: {service!r}",
            "allowed": sorted(_ALLOWED_SERVICES),
        }
    lines_req = _validate_lines((args or {}).get("lines", 80), 80, 10, 300)

    try:
        proc = _journalctl_runner(service, lines_req)
    except Exception as exc:
        return {
            "tool": "qbot_service_logs",
            "service": service,
            "lines_requested": lines_req,
            "lines_returned": 0,
            "logs": [],
            "status": "ERROR",
            "error": str(exc),
        }

    if proc.returncode != 0:
        return {
            "tool": "qbot_service_logs",
            "service": service,
            "lines_requested": lines_req,
            "lines_returned": 0,
            "logs": [],
            "status": "ERROR",
            "error": proc.stderr.strip() or f"journalctl exit {proc.returncode}",
        }

    log_lines: list[str] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped:
            log_lines.append(stripped[:_MAX_LINE_LENGTH])

    return {
        "tool": "qbot_service_logs",
        "service": service,
        "lines_requested": lines_req,
        "lines_returned": len(log_lines),
        "logs": log_lines,
        "status": "OK",
    }


# ──────────────────────────── logs_overview ─────────────────────────────

def _tool_qbot_logs_overview(args: dict | None = None) -> dict[str, Any]:
    lines = _validate_lines((args or {}).get("lines", 40), 40, 10, 100)

    services: list[dict[str, Any]] = []
    for svc in sorted(_ALLOWED_SERVICES):
        entry: dict[str, Any] = {"service": svc}
        try:
            log_result = _tool_qbot_service_logs({"service": svc, "lines": lines})
        except Exception as exc:
            entry["status"] = "ERROR"
            entry["error"] = str(exc)
            entry["recent_error_like_lines_count"] = 0
            entry["recent_warning_like_lines_count"] = 0
            entry["last_lines_sample"] = []
            services.append(entry)
            continue

        entry["status"] = log_result.get("status", "UNKNOWN")
        entry["lines_returned"] = log_result.get("lines_returned", 0)

        err_count = 0
        warn_count = 0
        sample: list[str] = []
        for line in log_result.get("logs", []):
            ll = line.lower()
            if any(k in ll for k in _ERROR_KW):
                err_count += 1
            if any(k in ll for k in _WARN_KW):
                warn_count += 1
            if len(sample) < 10:
                sample.append(line[:200])

        entry["recent_error_like_lines_count"] = err_count
        entry["recent_warning_like_lines_count"] = warn_count
        entry["last_lines_sample"] = sample

        if entry.get("status") != "OK":
            entry["status"] = entry["status"]
        elif err_count > 0:
            entry["status"] = "WARN"
        else:
            entry["status"] = "OK"

        services.append(entry)

    statuses = [s["status"] for s in services]
    overall = "ERROR" if "ERROR" in statuses else "WARN" if "WARN" in statuses else "OK"

    return {
        "tool": "qbot_logs_overview",
        "lines_per_service": lines,
        "services": services,
        "status": overall,
    }


# ──────────────────────────── backup_status ─────────────────────────────

def _pg_dump_available() -> bool:
    try:
        return subprocess.run(
            ["which", "pg_dump"], capture_output=True, timeout=3
        ).returncode == 0
    except Exception:
        return False


def _tool_qbot_backup_status(_args: dict | None = None) -> dict[str, Any]:
    existing_dirs: list[str] = [str(d) for d in _BACKUP_DIRS if d.is_dir()]
    dirs_ok = len(existing_dirs) > 0

    pg_ok = _pg_dump_available()
    db_connected = False
    try:
        import api_db
        db_connected = api_db.ping()
    except Exception:
        pass

    latest: dict[str, Any] | None = None
    for d in _BACKUP_DIRS:
        if not d.is_dir():
            continue
        try:
            for f in sorted(d.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if f.is_file() and f.suffix in _BACKUP_EXTENSIONS or f.suffixes and f.name.endswith(tuple(_BACKUP_EXTENSIONS)):
                    st = f.stat()
                    latest = {
                        "path": str(f),
                        "name": f.name,
                        "size_bytes": st.st_size,
                        "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                    }
                    break
            if latest:
                break
        except PermissionError:
            pass

    age_hours: float | None = None
    if latest:
        try:
            mtime = datetime.fromisoformat(latest["modified_at"]).timestamp()
            age_hours = round((datetime.now(timezone.utc).timestamp() - mtime) / 3600, 1)
        except Exception:
            pass

    recommendations: list[str] = []
    if not dirs_ok:
        recommendations.append("Create backup directory: mkdir -p /opt/qbot/backups")
        status = "WARN"
    elif not latest:
        recommendations.append("No backup files found — run pg_dump manually or set up cron")
        status = "WARN"
    else:
        status = "OK"
        if age_hours is not None and age_hours > 168:
            recommendations.append(f"Latest backup is {age_hours}h old — consider running backup soon")
            status = "WARN"

    if not pg_ok:
        recommendations.append("pg_dump not found — install postgresql-client")
        status = "WARN"
    if not db_connected:
        recommendations.append("Database not reachable — check PostgreSQL service")
        status = "ERROR"

    return {
        "tool": "qbot_backup_status",
        "backup_dirs": existing_dirs,
        "latest_backup": latest,
        "latest_backup_age_hours": age_hours,
        "pg_dump_available": pg_ok,
        "db_connected": db_connected,
        "recommendations": recommendations,
        "status": status,
    }


# ──────────────────────────── backup_plan ───────────────────────────────

def _tool_qbot_backup_plan(_args: dict | None = None) -> dict[str, Any]:
    return {
        "tool": "qbot_backup_plan",
        "recommended_backup_dir": "/opt/qbot/backups",
        "recommended_filename_template": "qbot_backup_$(date +%Y%m%d_%H%M%S).sql.gz",
        "manual_commands": [
            "mkdir -p /opt/qbot/backups",
            "pg_dump -U qbot -h localhost qbot | gzip > /opt/qbot/backups/qbot_backup_$(date +%Y%m%d_%H%M%S).sql.gz",
            "chmod 600 /opt/qbot/backups/qbot_backup_*.sql.gz",
        ],
        "restore_commands": [
            "gunzip -c /opt/qbot/backups/qbot_backup_YYYYMMDD_HHMMSS.sql.gz | psql -U qbot -h localhost qbot",
        ],
        "systemd_timer_suggestion": {
            "description": "Run daily backup at 02:00",
            "unit": "qbot-backup.service",
            "timer": "qbot-backup.timer",
            "on_calendar": "*-*-* 02:00:00",
            "notes": "Create .service and .timer files in /etc/systemd/system/, then systemctl enable --now qbot-backup.timer",
        },
        "cron_suggestion": "0 2 * * * /opt/qbot/app/scripts/qbot_backup.sh 2>&1 | systemd-cat -t qbot-backup",
        "warnings": [
            "Passwords are read from env, never expose in scripts",
            "Keep at least 7 days of backups",
            "Store backups off-server as well (scp, rsync, rclone)",
        ],
    }


# ──────────────────────────── create_backup_script_preview ──────────────

def _tool_qbot_create_backup_script_preview(_args: dict | None = None) -> dict[str, Any]:
    script = r'''#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$(dirname "$SCRIPT_DIR")/.env.local"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

BACKUP_DIR="/opt/qbot/backups"
mkdir -p "$BACKUP_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
OUTFILE="${BACKUP_DIR}/qbot_backup_${TS}.sql.gz"

pg_dump -U "${PGUSER:-qbot}" -h "${PGHOST:-localhost}" "${PGDATABASE:-qbot}" \
    | gzip > "$OUTFILE"

chmod 600 "$OUTFILE"

echo "Backup created: $OUTFILE"

# Remove backups older than 14 days
find "$BACKUP_DIR" -name 'qbot_backup_*.sql.gz' -type f -mtime +14 -delete
echo "Cleaned up old backups (>14 days)"
'''

    return {
        "tool": "qbot_create_backup_script_preview",
        "target_path": "/opt/qbot/app/scripts/qbot_backup.sh",
        "script_content": script,
        "install_commands": [
            "mkdir -p /opt/qbot/app/scripts",
            "chmod +x /opt/qbot/app/scripts/qbot_backup.sh",
            "chown qbot:qbot /opt/qbot/app/scripts/qbot_backup.sh",
        ],
        "test_commands": [
            "/opt/qbot/app/scripts/qbot_backup.sh",
            "ls -la /opt/qbot/backups/",
        ],
        "warnings": [
            "This is a preview — the script has NOT been written to disk",
            "Passwords are read from .env.local, never exposed",
            "Test the backup manually before enabling cron/timer",
        ],
    }


# ──────────────────────────── test_error_classification ────────────────

_TEST_ERROR_PATTERNS: dict[str, list[str]] = {
    "expected_test_error": ["invalid", "out of range", "unknown intent",
                            "empty_query", "bad runbook name", "not in registry",
                            "must be integer", "above maximum", "below minimum"],
    "unknown_tool_test": ["unknown tool", "available"],
    "validation_test": ["invalid limit", "invalid max_depth", "invalid recent_limit",
                        "limit", "max_depth", "recent_limit"],
}
_TEST_TOOLS: set[str] = {"unknown", "qbot_query"}


def _classify_error(error_text: str, tool: str) -> str:
    et = str(error_text or "").lower()
    if tool in _TEST_TOOLS and any(k in et for k in _TEST_ERROR_PATTERNS["unknown_tool_test"]):
        return "unknown_tool_test"
    for pattern in _TEST_ERROR_PATTERNS["validation_test"]:
        if pattern in et and "above maximum" in et or "below minimum" in et or "invalid" in et:
            return "validation_test"
    if any(k in et for k in _TEST_ERROR_PATTERNS["expected_test_error"]):
        return "expected_test_error"
    return "real_error_candidate"


def _tool_qbot_test_error_classification(args: dict | None = None) -> dict[str, Any]:
    limit_raw = (args or {}).get("limit", 200)
    try:
        limit = int(limit_raw)
    except (ValueError, TypeError):
        return {
            "tool": "qbot_test_error_classification",
            "status": "error",
            "error": f"invalid limit: {limit_raw!r}, must be integer",
        }
    limit = max(1, min(1000, limit))

    try:
        import api_db
        rows = api_db.select_tool_calls(limit)
    except Exception as exc:
        return {
            "tool": "qbot_test_error_classification",
            "status": "error",
            "error": f"database query failed: {exc}",
        }

    expected_test: list[dict[str, Any]] = []
    real_candidates: list[dict[str, Any]] = []

    for r in rows:
        res = r.get("result")
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except Exception:
                res = None
        if not isinstance(res, dict):
            continue
        if "error" not in res and res.get("status") != "error":
            continue

        error_text = res.get("error", res.get("reason", ""))
        category = _classify_error(error_text, r["tool"])

        entry = {
            "id": r["id"],
            "tool": r["tool"],
            "error": str(error_text)[:300] if error_text else "unknown error",
            "category": category,
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }

        if category == "real_error_candidate":
            real_candidates.append(entry)
        else:
            expected_test.append(entry)

    total = len(expected_test) + len(real_candidates)
    if total == 0:
        status = "OK"
    elif len(real_candidates) == 0:
        status = "WARN"
    else:
        status = "ERROR"

    return {
        "tool": "qbot_test_error_classification",
        "total_errors_checked": total,
        "expected_test_errors": len(expected_test),
        "real_error_candidates": len(real_candidates),
        "real_error_candidate_samples": real_candidates[:10],
        "expected_test_error_categories": {
            "expected_test_error": len([e for e in expected_test if e["category"] == "expected_test_error"]),
            "unknown_tool_test": len([e for e in expected_test if e["category"] == "unknown_tool_test"]),
            "validation_test": len([e for e in expected_test if e["category"] == "validation_test"]),
        },
        "status": status,
    }


# ──────────────────────────── maintenance_report ────────────────────────

def _tool_qbot_maintenance_report(_args: dict | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    blockers: list[str] = []
    actions: list[str] = []

    from qbot_operator_tools import (
        _tool_qbot_error_summary,
        _tool_qbot_readiness_report,
        _tool_qbot_tool_usage_summary,
    )

    rr = _tool_qbot_readiness_report()
    checks.append({"name": "readiness_report", "status": "OK", "detail": rr.get("status")})
    if rr.get("status") == "NOT_READY":
        blockers.extend(rr.get("blockers", []))
    warnings.extend(rr.get("warnings", []))

    try:
        backup = _tool_qbot_backup_status()
    except Exception as exc:
        backup = {"status": "error", "error": str(exc)}
    checks.append({"name": "backup_status", "status": backup.get("status", "UNKNOWN"),
                   "detail": backup})
    if backup.get("status") in ("ERROR",):
        blockers.append("Backup check failed or missing")
    elif backup.get("status") in ("WARN",):
        warnings.append("Backup not fully configured")
    if not backup.get("latest_backup"):
        actions.append("Set up database backup (qbot_backup_plan for details)")

    try:
        logs = _tool_qbot_logs_overview({"lines": 30})
    except Exception as exc:
        logs = {"status": "error", "error": str(exc)}
    checks.append({"name": "logs_overview", "status": logs.get("status", "UNKNOWN"),
                   "detail": logs})

    try:
        err_sum = _tool_qbot_error_summary({"limit": 100})
    except Exception as exc:
        err_sum = {"status": "error", "error": str(exc)}
    error_count = err_sum.get("errors_count", 0)
    checks.append({"name": "error_summary", "status": err_sum.get("status", "UNKNOWN"),
                   "detail": {"errors_count": error_count}})

    test_cls_status = "OK"
    only_test_errors = False
    try:
        cls_result = _tool_qbot_test_error_classification({"limit": 500})
    except Exception as exc:
        cls_result = {"status": "error", "error": str(exc)}
    test_cls_status = cls_result.get("status", "UNKNOWN")
    real_candidates = cls_result.get("real_error_candidates", 0)
    if isinstance(real_candidates, int) and real_candidates == 0 and error_count > 0:
        only_test_errors = True
    checks.append({"name": "test_error_classification",
                   "status": test_cls_status,
                   "detail": {
                       "real_error_candidates": real_candidates,
                       "expected_test_errors": cls_result.get("expected_test_errors", 0),
                   }})

    try:
        tool_usage = _tool_qbot_tool_usage_summary({"limit": 200})
    except Exception as exc:
        tool_usage = {"status": "error", "error": str(exc)}
    checks.append({"name": "tool_usage_summary", "status": "OK", "detail": tool_usage})

    guard = _tool_qbot_project_guard_check()
    checks.append({"name": "project_guard_check", "status": guard.get("status", "UNKNOWN")})
    for v in guard.get("violations", []):
        if v["severity"] == "ERROR":
            blockers.append(f"Guard error: {v['what']}")
            actions.append(f"Fix: {v['what']}")
        elif v["severity"] == "WARN":
            warnings.append(f"Guard warning: {v['what']}")

    git_result = _tool_qbot_git_status()
    checks.append({"name": "git_status", "status": "OK" if git_result.get("clean") else "WARN"})
    if not git_result.get("clean", True):
        warnings.append("Repository has uncommitted changes")

    if blockers:
        overall = "ACTION_REQUIRED"
    elif warnings:
        overall = "WARN"
    else:
        overall = "OK"

    if overall == "ACTION_REQUIRED":
        actions.insert(0, "Resolve blockers before any other action")
    elif overall == "WARN":
        actions.insert(0, "Review warnings and schedule fixes")
    else:
        actions.insert(0, "All systems operational — no action required")

    summary = "All systems OK" if overall == "OK" else (
        "Issues detected — review maintenance checklist" if overall == "WARN"
        else "Critical issues require immediate attention"
    )

    return {
        "tool": "qbot_maintenance_report",
        "status": overall,
        "checks": checks,
        "warnings": warnings,
        "blockers": blockers,
        "suggested_actions": actions,
        "summary": summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────── cross-file dispatch ───────────────────────────────

def _get_ops_tool(name: str):
    mapping = {
        "qbot_service_logs": _tool_qbot_service_logs,
        "qbot_logs_overview": _tool_qbot_logs_overview,
        "qbot_backup_status": _tool_qbot_backup_status,
        "qbot_backup_plan": _tool_qbot_backup_plan,
        "qbot_create_backup_script_preview": _tool_qbot_create_backup_script_preview,
        "qbot_test_error_classification": _tool_qbot_test_error_classification,
        "qbot_maintenance_report": _tool_qbot_maintenance_report,
    }
    return mapping.get(name)
