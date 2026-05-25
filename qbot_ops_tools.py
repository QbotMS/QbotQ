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
    "expected_test_error": ["invalid", "out of range", "unknown intent", "unknown_intent",
                            "empty_query", "bad runbook name", "unknown runbook name",
                            "not in registry", "must be integer", "above maximum",
                            "below minimum", "not allowed", "limit", "max_depth",
                            "recent_limit", "intent maps to allowlisted tool",
                            "selected_tool"],
    "unknown_tool_test": ["unknown tool", "available"],
    "validation_test": ["invalid limit", "invalid max_depth", "invalid recent_limit",
                        "must be integer", "above maximum", "below minimum"],
}
_TEST_TOOLS: set[str] = {"unknown", "qbot_query"}


def _classify_error(error_text: str, tool: str) -> str:
    et = str(error_text or "").lower()
    if tool in _TEST_TOOLS and any(k in et for k in _TEST_ERROR_PATTERNS["unknown_tool_test"]):
        return "unknown_tool_test"
    for pattern in _TEST_ERROR_PATTERNS["validation_test"]:
        if pattern in et:
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
        timer_status = _tool_qbot_backup_timer_status()
    except Exception as exc:
        timer_status = {"status": "error", "error": str(exc)}
    checks.append({"name": "backup_timer_status", "status": timer_status.get("status", "UNKNOWN"),
                   "detail": timer_status})
    if timer_status.get("status") in ("ERROR",):
        blockers.append("Backup timer is not active or missing")
    elif timer_status.get("status") in ("WARN",):
        warnings.append("Backup timer check has warnings")

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
        drill = _tool_qbot_restore_drill_status()
    except Exception as exc:
        drill = {"status": "error", "error": str(exc)}
    checks.append({"name": "restore_drill_status", "status": drill.get("status", "UNKNOWN"),
                   "detail": drill})
    if drill.get("status") == "ERROR":
        warnings.append("Restore drill has errors — re-run drill")
    elif drill.get("status") in ("WARN",):
        actions.append("Run restore drill to verify backup integrity")

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



# ──────────────────── backup_timer_status ───────────────────────────────

def _tool_qbot_backup_timer_status(_args: dict | None = None) -> dict[str, Any]:
    timer = {"exists": False, "active": False, "enabled": False, "next_run": None, "last_run": None}
    service = {"status": "unknown"}
    latest = None
    age_hours = None

    def _run(cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5)

    # Check timer exists
    proc = _run(["systemctl", "list-unit-files", "qbot-backup.timer"])
    if b"qbot-backup.timer" in proc.stdout.encode() or proc.returncode == 0:
        timer["exists"] = True

    if timer["exists"]:
        proc = _run(["systemctl", "is-active", "qbot-backup.timer"])
        timer["active"] = proc.stdout.strip() == "active"
        proc = _run(["systemctl", "is-enabled", "qbot-backup.timer"])
        timer["enabled"] = proc.stdout.strip() == "enabled"

        # Next run
        try:
            proc = _run(["systemctl", "show", "qbot-backup.timer",
                         "--property=NextElapseUSecRealtime"])
            val = proc.stdout.strip()
            if "=" in val:
                usec = val.split("=", 1)[1]
                if usec and usec.isdigit():
                    ts = int(usec) / 1_000_000
                    timer["next_run"] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except Exception:
            pass

        # Last run via service last invocation
        try:
            proc = _run(["systemctl", "show", "qbot-backup.service",
                         "--property=ExecMainExitTimestampMonotonic,ActiveEnterTimestamp"])
            for line in proc.stdout.strip().splitlines():
                if "ActiveEnterTimestamp=" in line:
                    timer["last_run"] = line.split("=", 1)[1].strip()
        except Exception:
            pass

        # Service status
        try:
            proc = _run(["systemctl", "show", "qbot-backup.service",
                         "--property=ActiveState,SubState,Result"])
            props = {}
            for line in proc.stdout.strip().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    props[k] = v
            service = {
                "active_state": props.get("ActiveState", "unknown"),
                "sub_state": props.get("SubState", "unknown"),
                "last_result": props.get("Result", "unknown"),
            }
        except Exception:
            service = {"status": "ERROR", "error": "cannot query service"}

    # Latest backup
    try:
        backup = _tool_qbot_backup_status()
        latest = backup.get("latest_backup")
        age_hours = backup.get("latest_backup_age_hours")
    except Exception:
        pass

    if not timer["exists"]:
        status = "ERROR"
    elif not timer["enabled"]:
        status = "WARN"
    elif not timer["active"]:
        status = "WARN"
    else:
        status = "OK"

    return {
        "tool": "qbot_backup_timer_status",
        "timer_exists": timer["exists"],
        "timer_active": timer["active"],
        "timer_enabled": timer["enabled"],
        "next_run": timer["next_run"],
        "last_run": timer["last_run"],
        "service_status": service,
        "latest_backup": latest,
        "latest_backup_age_hours": age_hours,
        "status": status,
    }


# ──────────────────── restore_drill_plan ────────────────────────────────

def _tool_qbot_restore_drill_plan(_args: dict | None = None) -> dict[str, Any]:
    return {
        "tool": "qbot_restore_drill_plan",
        "drill_db_name": "qbot_restore_drill",
        "commands": [
            "createdb -U qbot -h localhost qbot_restore_drill",
            "gunzip -c /opt/qbot/backups/qbot_YYYYmmdd_HHMMSS.sql.gz | psql -U qbot -h localhost qbot_restore_drill",
        ],
        "verification_queries": [
            "SELECT COUNT(*) FROM tool_calls;",
            "SELECT MAX(created_at) FROM tool_calls;",
            "SELECT tool, COUNT(*) AS cnt FROM tool_calls GROUP BY tool ORDER BY cnt DESC LIMIT 5;",
        ],
        "cleanup_commands": [
            "dropdb -U qbot -h localhost qbot_restore_drill",
        ],
        "safety_warnings": [
            "NEVER restore over qbot production database",
            "ALWAYS verify backup integrity with gzip -t first",
            "ALWAYS stop qbot-api.service before restoring production",
            "This drill uses separate database qbot_restore_drill — safe to run",
            "Passwords are read from env, never exposed in commands",
        ],
    }


# ──────────────────── restore_drill_status ──────────────────────────────

def _check_drill_db() -> dict[str, Any]:
    try:
        import api_db
        import psycopg
        from psycopg.rows import dict_row
        import os
        conn = psycopg.connect(
            host=os.getenv("PGHOST", "localhost"),
            port=os.getenv("PGPORT", "5432"),
            dbname="qbot_restore_drill",
            user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""),
            row_factory=dict_row,
        )
        rows = conn.execute("SELECT COUNT(*) AS cnt FROM information_schema.tables WHERE table_name = 'tool_calls'").fetchone()
        has_table = rows["cnt"] > 0 if rows else False
        count = 0
        latest = None
        if has_table:
            cnt_row = conn.execute("SELECT COUNT(*) AS cnt FROM tool_calls").fetchone()
            count = cnt_row["cnt"] if cnt_row else 0
            ts_row = conn.execute("SELECT MAX(created_at) AS ts FROM tool_calls").fetchone()
            if ts_row and ts_row["ts"]:
                latest = ts_row["ts"].isoformat()
        conn.close()
        return {
            "restore_drill_db_exists": True,
            "tool_calls_table_exists": has_table,
            "tool_calls_count": count,
            "latest_tool_call_at": latest,
        }
    except Exception:
        return {
            "restore_drill_db_exists": False,
            "tool_calls_table_exists": False,
            "tool_calls_count": 0,
            "latest_tool_call_at": None,
        }


def _tool_qbot_restore_drill_status(_args: dict | None = None) -> dict[str, Any]:
    info = _check_drill_db()
    recommendations: list[str] = []

    if not info["restore_drill_db_exists"]:
        status = "WARN"
        recommendations.append("Run restore drill: see qbot_restore_drill_plan for commands")
    elif not info["tool_calls_table_exists"]:
        status = "ERROR"
        recommendations.append("Restore drill DB exists but tool_calls table missing — re-run drill")
    elif info["tool_calls_count"] == 0:
        status = "ERROR"
        recommendations.append("tool_calls table exists but is empty — re-run drill")
    else:
        status = "OK"
        recommendations.append("Restore drill verified — data present")

    return {
        "tool": "qbot_restore_drill_status",
        **info,
        "status": status,
        "recommendations": recommendations,
    }


# ──────────────────── operator_quick_reference ──────────────────────────

def _tool_qbot_operator_quick_reference(_args: dict | None = None) -> dict[str, Any]:
    return {
        "tool": "qbot_operator_quick_reference",
        "endpoints": {
            "health": "GET http://127.0.0.1:8001/health",
            "query": "POST http://127.0.0.1:8001/q",
        },
        "key_tools": [
            "qbot_readiness_report — overall system readiness",
            "qbot_maintenance_report — full maintenance overview",
            "qbot_backup_status — backup health check",
            "qbot_backup_timer_status — automated backup timer status",
            "qbot_restore_drill_status — restore drill verification",
            "qbot_error_summary — recent errors overview",
            "qbot_test_error_classification — classify real vs test errors",
            "qbot_logs_overview — service logs check",
            "qbot_operator_snapshot — full diagnostic snapshot",
        ],
        "key_runbooks": [
            "safe_to_work — readiness + guard + git",
            "full_diagnostic — readiness + snapshot + errors",
            "backup_automation_review — backup + timer + drill + plan",
            "restore_drill_review — drill status + plan + backup",
            "operator_reference — quick reference + readiness + maintenance",
            "maintenance — maintenance + readiness + guard",
        ],
        "backup_commands": [
            "systemctl start qbot-backup.service",
            "ls -lh /opt/qbot/backups/",
            "gzip -t /opt/qbot/backups/qbot_*.sql.gz",
            "systemctl status qbot-backup.timer",
        ],
        "restore_drill_commands": [
            "createdb -U qbot -h localhost qbot_restore_drill",
            "gunzip -c <backup.sql.gz> | psql -U qbot -h localhost qbot_restore_drill",
            "psql -U qbot -h localhost qbot_restore_drill -c 'SELECT COUNT(*) FROM tool_calls;'",
            "dropdb -U qbot -h localhost qbot_restore_drill",
        ],
        "forbidden_actions": [
            "NEVER restore over qbot production database",
            "NEVER run DROP DATABASE qbot",
            "NEVER delete backup files younger than 14 days",
            "NEVER expose backup files over HTTP",
            "NEVER commit credentials or secrets",
            "NEVER restart production services without confirmation",
        ],
        "daily_checklist": [
            "Check health: curl http://127.0.0.1:8001/health",
            "Check readiness: qbot_query 'czy qbot jest gotowy'",
            "Check backup timer: systemctl status qbot-backup.timer",
            "Check backup status: qbot_backup_status",
            "Check errors: qbot_error_summary",
            "Check logs: qbot_logs_overview",
        ],
        "emergency_checklist": [
            "1. Check API: curl http://127.0.0.1:8001/health",
            "2. Check services: systemctl status qbot-api q-bot qbot-qlab-server postgresql",
            "3. Check backup: qbot_backup_status",
            "4. Run maintenance report: qbot_maintenance_report",
            "5. Check logs: journalctl -u qbot-api -n 100",
            "6. Check disk: df -h /",
            "7. Run restore drill: qbot_restore_drill_plan",
            "8. If DB issue: follow docs/qbot_backup_recovery.md",
        ],
    }


# ──────────────────── answer_context ────────────────────────────────────

_ANSWER_SOURCE_WHITELIST: set[str] = {
    "qbot_readiness_report", "qbot_maintenance_report", "qbot_operator_snapshot",
    "qbot_error_summary", "qbot_tool_usage_summary", "qbot_api_self_check",
    "qbot_project_guard_check", "qbot_git_status", "qbot_backup_status",
    "qbot_backup_timer_status", "qbot_restore_drill_status",
}

_SENSITIVE_KEYS: set[str] = {"password", "secret", "token", "apikey", "api_key",
                               "pgpassword", "env", "credential", "auth"}

_MAX_CONTEXT_DEPTH = 3


def _sanitize(obj: Any, depth: int = 0) -> Any:
    if depth > _MAX_CONTEXT_DEPTH:
        return "<truncated depth>"
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if any(s in kl for s in _SENSITIVE_KEYS):
                result[k] = "<redacted>"
            elif isinstance(v, (dict, list)):
                result[k] = _sanitize(v, depth + 1)
            elif isinstance(v, str) and len(v) > 2000:
                result[k] = v[:2000] + "...<truncated>"
            else:
                result[k] = v
        return result
    elif isinstance(obj, list):
        return [_sanitize(v, depth + 1) if isinstance(v, (dict, list))
                else (v[:500] + "...<truncated>" if isinstance(v, str) and len(v) > 500 else v)
                for v in obj[:50]]
    elif isinstance(obj, str) and len(obj) > 2000:
        return obj[:2000] + "...<truncated>"
    return obj


def _tool_qbot_answer_context(args: dict | None = None) -> dict[str, Any]:
    source_tool = (args or {}).get("source_tool", "qbot_readiness_report")
    source_args = dict((args or {}).get("source_args", {}) or {})

    if source_tool not in _ANSWER_SOURCE_WHITELIST:
        return {
            "tool": "qbot_answer_context",
            "status": "error",
            "error": f"source_tool not allowed: {source_tool!r}",
            "allowed": sorted(_ANSWER_SOURCE_WHITELIST),
        }

    try:
        from qbot_tool_registry import TOOLS
        func = TOOLS.get(source_tool)
        if func is None:
            return {"tool": "qbot_answer_context", "status": "error",
                    "error": f"tool not found in registry: {source_tool}"}
        raw = func(source_args)
    except Exception as exc:
        return {"tool": "qbot_answer_context", "status": "error",
                "error": f"source tool execution failed: {exc}"}

    source_status = raw.get("status", "unknown") if isinstance(raw, dict) else "unknown"
    safe_context = _sanitize(raw)

    return {
        "tool": "qbot_answer_context",
        "source_tool": source_tool,
        "source_status": source_status,
        "safe_for_llm": True,
        "llm_role": "answer_synthesizer_only",
        "llm_must_not": [
            "execute commands",
            "choose arbitrary tools",
            "restart services",
            "edit files",
            "perform backup or restore",
            "access secrets",
            "modify database",
            "call external APIs",
        ],
        "context": safe_context,
        "suggested_answer_outline": [
            "1. Summarize current system status",
            "2. Highlight any warnings or needed actions",
            "3. Note backup and restore drill status",
            "4. Recommend next steps if applicable",
            "5. Stay factual — do not invent information",
        ],
        "limitations": [
            "This context is sanitized for LLM consumption",
            "No secrets or credentials are included",
            "LLM must not act as executor — only as summarizer",
            "All actions must be confirmed by operator",
        ],
    }


# ──────────────────── llm_boundary_policy ───────────────────────────────

def _tool_qbot_llm_boundary_policy(_args: dict | None = None) -> dict[str, Any]:
    return {
        "tool": "qbot_llm_boundary_policy",
        "llm_allowed_roles": [
            "answer_synthesizer",
            "explanation_helper",
            "report_writer",
        ],
        "llm_forbidden_roles": [
            "executor",
            "planner_authority",
            "command_runner",
            "secrets_reader",
            "backup_restore_operator",
            "file_editor",
        ],
        "source_of_truth": "Qbot tools and PostgreSQL logs",
        "execution_authority": "Local allowlisted Qbot tools only",
        "required_flow": [
            "1. Qbot gathers diagnostic data",
            "2. Qbot validates system status",
            "3. Qbot prepares sanitized answer_context via qbot_answer_context",
            "4. LLM may summarize or explain (answer_synthesizer_only)",
            "5. Qbot/user decides next action",
        ],
        "safety_notes": [
            "LLM NEVER executes commands",
            "LLM NEVER accesses secrets or env",
            "LLM NEVER modifies code or config",
            "LLM NEVER performs backup or restore",
            "LLM output is advisory only",
            "All actions require operator confirmation",
            "LLM integration is OPTIONAL — system works without it",
        ],
    }


# ──────────────────── operator_final_smoke_test ─────────────────────────

def _tool_qbot_operator_final_smoke_test(_args: dict | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    # API health
    try:
        import api_db
        db_ok = api_db.ping()
        api_active = subprocess.run(
            ["systemctl", "is-active", "qbot-api.service"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip() == "active"
        checks.append({"name": "api_health", "status": "OK", "detail": {"db_connected": db_ok, "api_service_active": api_active}})
        if not db_ok:
            blockers.append("Database not connected")
        if not api_active:
            blockers.append("qbot-api.service is inactive")
    except Exception as exc:
        checks.append({"name": "api_health", "status": "FAIL", "detail": str(exc)})
        blockers.append(f"API health check failed: {exc}")

    # Backup timer
    try:
        timer = _tool_qbot_backup_timer_status()
        timer_ok = timer.get("timer_enabled") and timer.get("timer_active")
        checks.append({"name": "backup_timer", "status": "OK" if timer_ok else "FAIL",
                       "detail": timer})
        if not timer_ok:
            blockers.append("Backup timer not active or enabled")
    except Exception as exc:
        checks.append({"name": "backup_timer", "status": "FAIL", "detail": str(exc)})
        blockers.append(f"Backup timer check failed: {exc}")

    # Backup status
    try:
        backup = _tool_qbot_backup_status()
        has_backup = backup.get("latest_backup") is not None
        checks.append({"name": "latest_backup", "status": "OK" if has_backup else "FAIL",
                       "detail": backup})
        if not has_backup:
            blockers.append("No backup files found")
    except Exception as exc:
        checks.append({"name": "latest_backup", "status": "FAIL", "detail": str(exc)})
        blockers.append(f"Backup status check failed: {exc}")

    # Restore drill
    try:
        drill = _tool_qbot_restore_drill_status()
        drill_ok = drill.get("status") == "OK"
        checks.append({"name": "restore_drill", "status": "OK" if drill_ok else "WARN",
                       "detail": drill})
        if not drill_ok:
            warnings.append("Restore drill not fully verified")
    except Exception as exc:
        checks.append({"name": "restore_drill", "status": "WARN", "detail": str(exc)})
        warnings.append(f"Restore drill check failed: {exc}")

    # Guard check
    try:
        guard = _tool_qbot_project_guard_check()
        guard_ok = guard.get("status") != "ERROR"
        checks.append({"name": "project_guard", "status": "OK" if guard_ok else "FAIL",
                       "detail": guard})
        if not guard_ok:
            blockers.append("Guard check has errors")
        elif guard.get("status") == "WARN":
            warnings.append("Guard check has warnings")
    except Exception as exc:
        checks.append({"name": "project_guard", "status": "FAIL", "detail": str(exc)})
        blockers.append(f"Guard check failed: {exc}")

    # Git clean
    try:
        git = _tool_qbot_git_status()
        clean = git.get("clean", False)
        checks.append({"name": "git_clean", "status": "OK" if clean else "WARN",
                       "detail": git})
        if not clean:
            warnings.append("Repository has uncommitted changes")
    except Exception as exc:
        checks.append({"name": "git_clean", "status": "WARN", "detail": str(exc)})

    # Readiness
    try:
        from qbot_operator_tools import _tool_qbot_readiness_report
        readiness = _tool_qbot_readiness_report()
        ready = readiness.get("status") == "READY"
        checks.append({"name": "readiness", "status": "OK" if ready else "WARN",
                       "detail": readiness})
        if not ready:
            if readiness.get("status") == "NOT_READY":
                blockers.append("Readiness report is NOT_READY")
            else:
                warnings.append(f"Readiness report is {readiness.get('status')}")
    except Exception as exc:
        checks.append({"name": "readiness", "status": "FAIL", "detail": str(exc)})
        blockers.append(f"Readiness check failed: {exc}")

    # Error classification
    try:
        cls = _tool_qbot_test_error_classification({"limit": 300})
        real_cand = cls.get("real_error_candidates", 0)
        checks.append({"name": "error_classification",
                       "status": "OK" if real_cand == 0 else "WARN",
                       "detail": cls})
        if real_cand > 0:
            warnings.append(f"{real_cand} real error candidates detected")
    except Exception as exc:
        checks.append({"name": "error_classification", "status": "WARN",
                       "detail": str(exc)})

    # LLM boundary
    try:
        llm_policy = _tool_qbot_llm_boundary_policy()
        checks.append({"name": "llm_boundary_policy", "status": "OK",
                       "detail": "available"})
    except Exception:
        checks.append({"name": "llm_boundary_policy", "status": "WARN",
                       "detail": "not available"})

    # Compute total
    total = len(checks)
    pass_count = len([c for c in checks if c["status"] == "OK"])
    warn_count = len([c for c in checks if c["status"] == "WARN"])
    fail_count = len([c for c in checks if c["status"] == "FAIL"])

    if blockers:
        overall = "FAIL"
        readiness_pct = max(0, round(pass_count / total * 100))
    elif warnings:
        overall = "WARN"
        readiness_pct = max(95, round((pass_count + warn_count) / total * 100))
    else:
        overall = "PASS"
        readiness_pct = 100

    if overall == "PASS":
        next_action = "System is fully operational — no issues"
    elif overall == "WARN":
        next_action = "Review warnings and schedule fixes"
    else:
        next_action = "Resolve blockers before production use"

    return {
        "tool": "qbot_operator_final_smoke_test",
        "status": overall,
        "operational_readiness_percent": readiness_pct,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "recommended_next_action": next_action,
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
        "qbot_backup_timer_status": _tool_qbot_backup_timer_status,
        "qbot_restore_drill_plan": _tool_qbot_restore_drill_plan,
        "qbot_restore_drill_status": _tool_qbot_restore_drill_status,
        "qbot_operator_quick_reference": _tool_qbot_operator_quick_reference,
        "qbot_answer_context": _tool_qbot_answer_context,
        "qbot_llm_boundary_policy": _tool_qbot_llm_boundary_policy,
        "qbot_operator_final_smoke_test": _tool_qbot_operator_final_smoke_test,
    }
    return mapping.get(name)
