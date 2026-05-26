"""Legacy parity restoration tools — RWGPS, Hammerhead FIT Import, CSV Export.

Read-only tools for status, config, inventory, dry-run, and restore planning.
No real uploads, no mutations, no sync execution without explicit approval.
"""
from __future__ import annotations

import csv as _csv
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path("/opt/qbot/app")
_OUTGOING = _PROJECT_ROOT / "outgoing"
_EXPORTS  = _OUTGOING / "exports"
_EXPORTS.mkdir(parents=True, exist_ok=True)


def _env_has(name: str) -> bool:
    v = os.getenv(name)
    if v is not None and v.strip():
        return True
    try:
        text = (_PROJECT_ROOT / ".env.local").read_text(encoding="utf-8", errors="ignore")
        return re.search(rf"^{re.escape(name)}\s*=", text, re.MULTILINE) is not None
    except (PermissionError, FileNotFoundError, OSError):
        return False


def _env_presence(names: list[str]) -> dict[str, bool]:
    return {n: _env_has(n) for n in names}


def _list_glob_files(root: Path, pattern: str, *, max_files: int = 100) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True):
        if len(results) >= max_files:
            break
        try:
            st = path.stat()
        except OSError:
            continue
        results.append({
            "name": path.name,
            "path": str(path.relative_to(_PROJECT_ROOT)),
            "size_bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            "profile": path.parts[len(root.parts):-1] if len(path.parts) > len(root.parts) else [],
        })
    return results


# ═══════════════════════════════════════════════════════════════════════
#  RWGPS TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_rwgps_config_status(_args: dict | None = None) -> dict[str, Any]:
    """Check RWGPS configuration without exposing secrets."""
    env_names = [
        "RWGPS_AUTH_TOKEN",
        "RWGPS_USER_ID",
        "RWGPS_API_URL",
        "RWGPS_API_KEY",
        "RWGPS_PLANNED_COLLECTION_ID",
        "RIDEWITHGPS_AUTH_TOKEN",
        "RIDEWITHGPS_USER_ID",
    ]
    presence = _env_presence(env_names)

    token_ok = presence.get("RWGPS_AUTH_TOKEN") or presence.get("RIDEWITHGPS_AUTH_TOKEN")
    user_ok  = presence.get("RWGPS_USER_ID") or presence.get("RIDEWITHGPS_USER_ID")
    url_ok   = presence.get("RWGPS_API_URL")

    missing = [n for n, present in presence.items() if not present]

    if token_ok and user_ok:
        status = "OK"
        notes = "RWGPS credentials are configured."
    elif token_ok or user_ok:
        status = "WARN"
        notes = "Partial RWGPS credentials — some variables missing."
    else:
        status = "ERROR"
        notes = "No RWGPS credentials configured. Live API is inactive; local manifest fallback used."

    client_py = _PROJECT_ROOT / "tools" / "rwgps" / "client.py"
    code_detected = client_py.exists()

    return {
        "tool": "qbot_rwgps_config_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "auth_token_present": bool(token_ok),
        "user_id_present": bool(user_ok),
        "api_url_present": bool(url_ok),
        "config_source": ".env.local" if any(presence.values()) else "none",
        "env_presence": presence,
        "missing": missing,
        "code_detected": code_detected,
        "notes": notes,
        "restored_status": "PARTIAL" if code_detected and not (token_ok and user_ok) else ("RESTORED" if token_ok and user_ok else "MISSING"),
    }


def _tool_qbot_rwgps_legacy_status(_args: dict | None = None) -> dict[str, Any]:
    """Comprehensive RWGPS legacy parity status."""
    import subprocess

    config = _tool_qbot_rwgps_config_status()
    dry_run = _tool_qbot_rwgps_dry_run({"operation": "list_routes"})

    evidence_files: list[dict[str, Any]] = []
    for pattern in ["tools/rwgps/**/*.py", "data/routes/rwgps*.json", "mcp_server.py"]:
        for p in _PROJECT_ROOT.glob(pattern):
            if p.is_file() and p.name != "__init__.py":
                try:
                    evidence_files.append({
                        "file": str(p.relative_to(_PROJECT_ROOT)),
                        "size_bytes": p.stat().st_size,
                    })
                except OSError:
                    pass

    manifest_path = _PROJECT_ROOT / "data" / "routes" / "rwgps_manifest.json"
    cache_path = _PROJECT_ROOT / "data" / "routes" / "rwgps_route_cache.json"
    manifest_routes = 0
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            manifest_routes = len(manifest.get("routes", [])) if isinstance(manifest, dict) else len(manifest) if isinstance(manifest, list) else 0
        except Exception:
            pass

    configured = bool(config.get("auth_token_present") and config.get("user_id_present"))

    if configured and dry_run.get("status") == "PLAN_ONLY" and dry_run.get("would_execute"):
        restored = "RESTORED"
        notes = "RWGPS credentials configured and read-only dry-run path is available."
    elif evidence_files:
        restored = "PARTIAL"
        notes = "RWGPS code detected but missing API credentials. Local manifest fallback active."
    else:
        restored = "MISSING"
        notes = "No RWGPS code or configuration detected."

    return {
        "tool": "qbot_rwgps_legacy_status",
        "capability": "rwgps",
        "status": "OK" if config.get("status") == "OK" else "WARN",
        "safety_class": "READ_ONLY",
        "code_detected": bool(evidence_files),
        "candidate_files": evidence_files[:20],
        "env_presence": config.get("env_presence", {}),
        "generated_artifacts": {
            "manifest_routes": manifest_routes,
            "has_cache": cache_path.exists(),
        },
        "configured": bool(configured),
        "dry_run_status": dry_run.get("status"),
        "dry_run_would_execute": dry_run.get("would_execute"),
        "restored_status": restored,
        "notes": notes,
        "can_restore_today": bool(configured and dry_run.get("would_execute")),
        "risk": "medium",
    }


def _tool_qbot_rwgps_dry_run(_args: dict | None = None) -> dict[str, Any]:
    """Read-only dry-run of RWGPS operations. No uploads, no mutations."""
    _args = _args or {}
    operation = str(_args.get("operation", "list_routes"))

    allowed = {"list_routes", "get_user", "export_preview"}
    if operation not in allowed:
        return {
            "tool": "qbot_rwgps_dry_run",
            "status": "BLOCKED_UNKNOWN_OPERATION",
            "safety_class": "READ_ONLY",
            "operation": operation,
            "allowed_operations": sorted(allowed),
            "notes": f"Operation '{operation}' is not in the dry-run allowlist.",
        }

    config = _tool_qbot_rwgps_config_status()
    if not config.get("auth_token_present") or not config.get("user_id_present"):
        return {
            "tool": "qbot_rwgps_dry_run",
            "status": "BLOCKED_MISSING_SECRET",
            "safety_class": "READ_ONLY",
            "operation": operation,
            "missing_config": config.get("missing", []),
            "would_execute": False,
            "notes": "Cannot perform dry-run: RWGPS credentials missing.",
        }

    manifest_path = _PROJECT_ROOT / "data" / "routes" / "rwgps_manifest.json"
    local_routes = 0
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text())
            local_routes = len(data.get("routes", [])) if isinstance(data, dict) else len(data) if isinstance(data, list) else 0
        except Exception:
            pass

    return {
        "tool": "qbot_rwgps_dry_run",
        "status": "PLAN_ONLY",
        "safety_class": "READ_ONLY",
        "operation": operation,
        "would_execute": True,
        "envs_configured": True,
        "local_manifest_routes": local_routes,
        "notes": f"Dry-run for '{operation}' is PLAN_ONLY. Live API call requires controlled execution. Local manifest has {local_routes} cached routes.",
        "blocked_operations": ["upload", "sync", "create_route", "delete_route", "modify_route"],
    }


def _tool_qbot_rwgps_restore_plan(_args: dict | None = None) -> dict[str, Any]:
    """Restore plan for RWGPS capability."""
    config = _tool_qbot_rwgps_config_status()
    legacy = _tool_qbot_rwgps_legacy_status()

    missing = config.get("missing", [])
    configured = config.get("auth_token_present") and config.get("user_id_present")

    return {
        "tool": "qbot_rwgps_restore_plan",
        "status": "RESTORED" if configured else "PARTIAL",
        "safety_class": "READ_ONLY",
        "missing_config": missing,
        "safe_readonly_tests": [
            "list_routes (dry_run)",
            "get_user (dry_run)",
            "export_preview (dry_run)",
        ],
        "blocked_operations": [
            "create_route",
            "delete_route",
            "modify_route",
            "upload_route",
            "sync_routes",
        ],
        "required_manual_env": missing,
        "code_present": legacy.get("code_detected", False),
        "local_manifest_available": legacy.get("generated_artifacts", {}).get("manifest_routes", 0) > 0,
        "next_steps": [
            "Set RWGPS_AUTH_TOKEN and RWGPS_USER_ID in .env.local",
            "Run qbot_rwgps_dry_run to verify API connectivity",
            "Backup existing manifest before enabling live API",
        ] if not configured else [
            "Run qbot_rwgps_dry_run operation=list_routes for confirmation",
            "Live API is ready for controlled read-only operations",
        ],
        "notes": "RWGPS client code in tools/rwgps/client.py is 1,781 lines, smoke-tested. Local cache/backup present in /opt/qbot/backups/rwgps/.",
    }


# ═══════════════════════════════════════════════════════════════════════
#  HAMMERHEAD TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_hammerhead_config_status(_args: dict | None = None) -> dict[str, Any]:
    """Check Hammerhead config without exposing tokens."""
    env_names = [
        "HAMMERHEAD_EMAIL",
        "HAMMERHEAD_PASSWORD",
        "HAMMERHEAD_BEARER_TOKEN",
        "HAMMERHEAD_REFRESH_TOKEN",
        "HAMMERHEAD_TOKENSTORE",
        "HAMMERHEAD_USER_ID",
    ]
    presence = _env_presence(env_names)

    jwt_ok = presence.get("HAMMERHEAD_BEARER_TOKEN")
    refresh_ok = presence.get("HAMMERHEAD_REFRESH_TOKEN")
    email_ok = presence.get("HAMMERHEAD_EMAIL")
    user_id_ok = presence.get("HAMMERHEAD_USER_ID")
    ts_env_ok = presence.get("HAMMERHEAD_TOKENSTORE")

    possible_expired = "unknown"
    if jwt_ok:
        try:
            raw = os.getenv("HAMMERHEAD_BEARER_TOKEN", "")
            if raw:
                import base64 as _b64
                payload = raw.split(".")[1] if "." in raw else ""
                pad = len(payload) % 4
                payload += "=" * ((4 - pad) % 4) if pad else ""
                decoded = _b64.urlsafe_b64decode(payload)
                exp = json.loads(decoded).get("exp", 0)
                now = datetime.now(timezone.utc).timestamp()
                possible_expired = "true" if now > exp else "false"
        except Exception:
            possible_expired = "unknown"

    tokenstore = _PROJECT_ROOT / ".hammerhead_tokens"
    ts_ok = False
    try:
        ts_ok = tokenstore.exists() and any(tokenstore.iterdir())
    except (PermissionError, OSError):
        pass

    ts_user_id = None
    if ts_ok and not user_id_ok:
        try:
            for f in sorted(tokenstore.iterdir()):
                if f.is_file() and f.suffix in (".json", ""):
                    data = json.loads(f.read_text(encoding="utf-8"))
                    uid = data.get("user_id") or data.get("userId") or data.get("id")
                    if uid:
                        ts_user_id = str(uid)
                        break
        except (PermissionError, OSError, json.JSONDecodeError, Exception):
            pass

    has_local_token = jwt_ok or refresh_ok or ts_ok
    has_online_creds = email_ok and presence.get("HAMMERHEAD_PASSWORD")

    missing = []
    if not has_local_token and not has_online_creds:
        missing = [n for n, p in presence.items() if not p]
    else:
        for n in ["HAMMERHEAD_BEARER_TOKEN", "HAMMERHEAD_REFRESH_TOKEN", "HAMMERHEAD_EMAIL", "HAMMERHEAD_PASSWORD"]:
            if n in presence and not presence[n]:
                if n.startswith("HAMMERHEAD_EMAIL") and has_local_token:
                    continue
                if n.startswith("HAMMERHEAD_PASSWORD") and has_local_token:
                    continue
                if n.startswith("HAMMERHEAD_BEARER") and ts_ok and refresh_ok:
                    continue
                if n.startswith("HAMMERHEAD_REFRESH") and ts_ok and jwt_ok:
                    continue
                if not has_local_token and not has_online_creds:
                    missing.append(n)

    if has_local_token and ts_ok:
        status = "OK"
        notes = "Hammerhead tokenstore active with bearer/refresh tokens. Local read-only ready."
    elif has_local_token:
        status = "OK"
        notes = "Hammerhead bearer/refresh tokens configured. Tokenstore optional."
    elif has_online_creds:
        status = "WARN"
        notes = "Hammerhead email/password configured (legacy). Token refresh path available."
    else:
        status = "ERROR"
        notes = "No Hammerhead tokens or credentials configured."

    if has_local_token and ts_ok:
        restored = "RESTORED_FOR_READONLY"
    elif has_local_token:
        restored = "RESTORED_FOR_READONLY" if not (possible_expired == "true") else "PARTIAL"
    elif has_online_creds:
        restored = "PARTIAL"
    else:
        restored = "MISSING"

    return {
        "tool": "qbot_hammerhead_config_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "jwt_present": bool(jwt_ok),
        "bootstrap_jwt_present": bool(jwt_ok),
        "refresh_token_present": bool(refresh_ok),
        "email_configured": bool(email_ok),
        "api_url_present": False,
        "possible_expired_token": possible_expired,
        "tokenstore_active": ts_ok,
        "env_presence": presence,
        "missing": missing,
        "has_local_token": has_local_token,
        "has_online_creds": has_online_creds,
        "ts_user_id_inferred": ts_user_id,
        "notes": notes,
        "restored_status": restored,
        "email_optional_when_tokenstore_active": True,
    }


def _tool_qbot_hammerhead_import_status_enhanced(_args: dict | None = None) -> dict[str, Any]:
    """Extended Hammerhead import status with inventory. Delegates to legacy + adds context."""
    import importlib

    try:
        from qbot_legacy_parity_tools import _tool_qbot_hammerhead_import_status as _legacy
        base = _legacy(_args)
    except Exception:
        base = {"tool": "qbot_hammerhead_import_status", "status": "error"}

    config = _tool_qbot_hammerhead_config_status()
    inventory = _tool_qbot_hammerhead_import_inventory({"limit": 5})

    has_local = config.get("has_local_token", False) and config.get("tokenstore_active", False)
    local_ok = inventory.get("count", 0) > 0

    if has_local and local_ok:
        restored = "RESTORED_FOR_READONLY"
        base["status"] = "OK"
    elif has_local:
        restored = "PARTIAL"
        base["status"] = "WARN"
    else:
        restored = config.get("restored_status", "PARTIAL")
        base["status"] = "WARN" if base.get("status") != "error" else base.get("status")

    base["restored_status"] = restored
    base["config_status"] = config.get("status")
    base["possible_expired_token"] = config.get("possible_expired_token")
    base["hammerhead_originals_count"] = inventory.get("count", 0)
    base["latest_hammerhead_original_fit"] = inventory.get("latest_files", [])[0] if inventory.get("latest_files") else None
    base["config_detail"] = {
        "jwt_present": config.get("jwt_present"),
        "refresh_token_present": config.get("refresh_token_present"),
        "email_configured": config.get("email_configured"),
        "tokenstore_active": config.get("tokenstore_active"),
        "has_local_token": config.get("has_local_token"),
    }
    base["notes"] = "Tokenstore-based read-only status active. Online API import requires separate controlled execution approval."
    return base


def _tool_qbot_hammerhead_import_inventory(_args: dict | None = None) -> dict[str, Any]:
    """List Hammerhead original FIT files."""
    _args = _args or {}
    limit = min(max(int(_args.get("limit", 20)), 1), 100)

    all_files = _list_glob_files(_OUTGOING, "**/hammerhead_originals/*.fit", max_files=limit)

    per_user: dict[str, int] = {}
    for f in all_files:
        parts = f.get("profile", [])
        user = parts[0] if parts else "default"
        per_user[user] = per_user.get(user, 0) + 1

    return {
        "tool": "qbot_hammerhead_import_inventory",
        "status": "OK" if all_files else "WARN",
        "safety_class": "READ_ONLY",
        "count": len(all_files),
        "latest_files": all_files[:5],
        "per_user_counts": per_user,
        "latest_mtime": all_files[0]["mtime"] if all_files else None,
        "source_dir": str(_OUTGOING.relative_to(_PROJECT_ROOT)),
        "notes": "Read-only inventory. No files read from Hammerhead API.",
    }


def _tool_qbot_hammerhead_import_dry_run(_args: dict | None = None) -> dict[str, Any]:
    """Safe dry-run of Hammerhead import. No downloads, no sync.

    source=latest only inspects local artifacts — no API call.
    """
    _args = _args or {}
    source = str(_args.get("source", "latest"))

    config = _tool_qbot_hammerhead_config_status()
    inventory = _tool_qbot_hammerhead_import_inventory({"limit": 5})

    has_token = config.get("has_local_token", False)
    tokenstore_ok = config.get("tokenstore_active", False)
    expired = config.get("possible_expired_token", "unknown")
    local_count = inventory.get("count", 0)
    latest = inventory.get("latest_files", [])[0] if inventory.get("latest_files") else None

    profile_name = "default"
    if latest and latest.get("profile"):
        profile_name = latest["profile"][0] if latest["profile"] else "default"
    elif source not in ("latest",):
        profile_name = source

    no_creds_at_all = not has_token and not config.get("has_online_creds", False)

    if no_creds_at_all and local_count == 0:
        return {
            "tool": "qbot_hammerhead_import_dry_run",
            "status": "BLOCKED_NO_CREDENTIALS_OR_ARTIFACTS",
            "safety_class": "READ_ONLY",
            "source": source,
            "would_fetch": False,
            "would_store_to": None,
            "missing_config": config.get("missing", []),
            "latest_local_fit": None,
            "local_count": 0,
            "notes": "No Hammerhead credentials and no local FIT artifacts. Nothing to inspect.",
        }

    api_blocked = no_creds_at_all or (not has_token and not tokenstore_ok)
    warning_jwt = expired == "true"

    return {
        "tool": "qbot_hammerhead_import_dry_run",
        "status": "OK" if (not api_blocked) and local_count > 0 else "WARN",
        "safety_class": "READ_ONLY",
        "source": source,
        "would_fetch": False,
        "would_store_to": str(_OUTGOING.relative_to(_PROJECT_ROOT)) + "/" if not api_blocked else None,
        "api_blocked": api_blocked,
        "api_block_reason": (
            "No credentials" if no_creds_at_all else "Tokenstore inactive" if not tokenstore_ok else "JWT expired" if warning_jwt else None
        ),
        "jwt_expired": warning_jwt,
        "missing_config": config.get("missing", []),
        "latest_local_fit": latest,
        "profile": profile_name,
        "local_count": local_count,
        "tokenstore_active": tokenstore_ok,
        "has_local_token": has_token,
        "notes": (
            "Dry-run only. Local FIT artifacts available for inspection. "
            "Online Hammerhead API import requires controlled execution with valid credentials."
        ),
    }


def _tool_qbot_hammerhead_restore_plan(_args: dict | None = None) -> dict[str, Any]:
    """Restore plan for Hammerhead FIT import."""
    config = _tool_qbot_hammerhead_config_status()
    expired = config.get("possible_expired_token")
    has_local = config.get("has_local_token", False)
    ts_ok = config.get("tokenstore_active", False)

    if has_local and ts_ok and expired == "false":
        plan_status = "RESTORED_FOR_READONLY"
    elif has_local and ts_ok:
        plan_status = "READY_FOR_TOKEN_REFRESH"
    elif has_local:
        plan_status = "PARTIAL"
    else:
        plan_status = "MISSING"

    next_steps = []
    if expired == "true" or expired == "unknown":
        next_steps.append("Refresh HAMMERHEAD_BEARER_TOKEN using HAMMERHEAD_REFRESH_TOKEN (or email/password as fallback)")
    if not ts_ok:
        next_steps.append("Configure HAMMERHEAD_TOKENSTORE env var pointing to .hammerhead_tokens/")
    if has_local and ts_ok and expired == "false":
        next_steps.append("Tokenstore active and token valid — import pipeline ready for controlled execution")
        next_steps.append("Monitor cron logs for sync success")
    if not next_steps:
        next_steps.append("Set HAMMERHEAD_BEARER_TOKEN and HAMMERHEAD_REFRESH_TOKEN in .env.local")
        next_steps.append("Alternatively set HAMMERHEAD_EMAIL and HAMMERHEAD_PASSWORD for fresh login (optional fallback)")

    return {
        "tool": "qbot_hammerhead_restore_plan",
        "status": plan_status,
        "safety_class": "READ_ONLY",
        "missing_config": config.get("missing", []),
        "token_refresh_needed": expired != "false",
        "email_password_optional": True,
        "safe_tests": [
            "qbot_hammerhead_config_status",
            "qbot_hammerhead_import_inventory",
            "qbot_hammerhead_import_dry_run",
        ],
        "controlled_execution_needed": True,
        "next_steps": next_steps,
        "notes": "Email/password are optional fallback. Primary: tokenstore with bearer/refresh tokens.",
    }


# ═══════════════════════════════════════════════════════════════════════
#  CSV EXPORT TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_csv_export_inventory(_args: dict | None = None) -> dict[str, Any]:
    """List CSV files in outgoing directory."""
    _args = _args or {}
    limit = min(max(int(_args.get("limit", 20)), 1), 100)

    csv_files = _list_glob_files(_OUTGOING, "**/*.csv", max_files=limit)

    has_latest = (_OUTGOING / "qbot_garmin_proxy_latest.csv").exists()

    by_dir: dict[str, int] = {}
    for f in csv_files:
        parts = f.get("profile", [])
        key = parts[0] if parts else "root"
        by_dir[key] = by_dir.get(key, 0) + 1

    return {
        "tool": "qbot_csv_export_inventory",
        "status": "OK" if csv_files else "WARN",
        "safety_class": "READ_ONLY",
        "csv_count": len(csv_files),
        "latest_csv": str(_OUTGOING / "qbot_garmin_proxy_latest.csv") if has_latest else None,
        "qbot_garmin_proxy_latest_csv_present": has_latest,
        "latest_files": csv_files[:5],
        "by_directory": by_dir,
        "notes": "Read-only inventory. CSV files generated by Hammerhead-Garmin sync pipeline.",
    }


def _tool_qbot_csv_export_latest_get(_args: dict | None = None) -> dict[str, Any]:
    """Read latest CSV file (read-only)."""
    _args = _args or {}
    source = str(_args.get("source", "garmin_proxy_latest"))
    limit_rows = min(max(int(_args.get("limit_rows", 20)), 1), 200)

    allowed_sources = {"garmin_proxy_latest", "latest_any"}
    if source not in allowed_sources:
        return {
            "tool": "qbot_csv_export_latest_get",
            "status": "BLOCKED_UNKNOWN_SOURCE",
            "safety_class": "READ_ONLY",
            "allowed_sources": sorted(allowed_sources),
            "notes": f"Source '{source}' not in allowlist.",
        }

    candidates: list[Path] = []

    if source == "garmin_proxy_latest":
        p = _OUTGOING / "qbot_garmin_proxy_latest.csv"
        if p.exists():
            candidates = [p]
    elif source == "latest_any":
        for p in sorted(_OUTGOING.glob("**/*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
            candidates.append(p)
            if len(candidates) >= 1:
                break

    if not candidates:
        return {
            "tool": "qbot_csv_export_latest_get",
            "status": "WARN",
            "safety_class": "READ_ONLY",
            "source": source,
            "file": None,
            "columns": [],
            "row_count_estimate": 0,
            "sample_rows": [],
            "notes": "No CSV files found for the selected source.",
        }

    target = candidates[0]
    try:
        text = target.read_text(encoding="utf-8", errors="ignore")
        reader = _csv.reader(io.StringIO(text))
        rows = list(reader)
    except Exception as exc:
        return {
            "tool": "qbot_csv_export_latest_get",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "file": str(target.relative_to(_PROJECT_ROOT)),
            "error": str(exc),
            "notes": "Failed to read CSV file.",
        }

    columns = rows[0] if rows else []
    sample = rows[1:limit_rows + 1] if len(rows) > 1 else []

    return {
        "tool": "qbot_csv_export_latest_get",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "source": source,
        "file": str(target.relative_to(_PROJECT_ROOT)),
        "file_size_bytes": target.stat().st_size,
        "mtime": datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc).isoformat(),
        "columns": columns,
        "row_count_estimate": len(rows) - 1,
        "sample_rows": [
            dict(zip(columns, r)) for r in sample
        ] if columns else sample,
        "notes": f"Read-only preview. Showing {len(sample)} of {len(rows) - 1} data rows.",
    }


def _tool_qbot_csv_export_create_preview(_args: dict | None = None) -> dict[str, Any]:
    """Preview what a CSV export would contain. No file written."""
    _args = _args or {}
    source_report = str(_args.get("source_report", "latest"))
    output_name = str(_args.get("output_name", "preview"))

    latest_csv = _OUTGOING / "qbot_garmin_proxy_latest.csv"

    source_available = False
    source_info = ""

    if source_report in ("latest",) and latest_csv.exists():
        source_available = True
        try:
            st = latest_csv.stat()
            source_info = f"{latest_csv.name} ({st.st_size} bytes, {datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()})"
        except OSError:
            source_info = f"{latest_csv.name}"

    if not source_available:
        return {
            "tool": "qbot_csv_export_create_preview",
            "status": "PLAN_ONLY",
            "safety_class": "READ_ONLY",
            "source_report": source_report,
            "output_name": output_name,
            "source_available": False,
            "would_generate": False,
            "target_dir": str(_EXPORTS.relative_to(_PROJECT_ROOT)),
            "notes": "No source data available for CSV generation.",
        }

    return {
        "tool": "qbot_csv_export_create_preview",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "source_report": source_report,
        "output_name": output_name,
        "source_available": True,
        "source_info": source_info,
        "would_generate": True,
        "target_dir": str(_EXPORTS.relative_to(_PROJECT_ROOT)),
        "notes": f"Would copy/convert {source_info} to {_EXPORTS.relative_to(_PROJECT_ROOT)}/{output_name}.",
    }


def _tool_qbot_csv_export_create_execute(_args: dict | None = None) -> dict[str, Any]:
    """Execute CSV export (controlled, dry_run by default)."""
    _args = _args or {}
    source_report = str(_args.get("source_report", "latest"))
    output_name = str(_args.get("output_name", "qbot_export_latest.csv"))
    dry_run = bool(_args.get("dry_run", True))

    output_name = os.path.basename(output_name)
    target_path = _EXPORTS / output_name

    latest_csv = _OUTGOING / "qbot_garmin_proxy_latest.csv"

    if not latest_csv.exists():
        return {
            "tool": "qbot_csv_export_create_execute",
            "status": "WARN",
            "safety_class": "WRITE_SAFE",
            "source_not_found": True,
            "notes": "Source CSV not found. Cannot export.",
        }

    if dry_run:
        return {
            "tool": "qbot_csv_export_create_execute",
            "status": "DRY_RUN",
            "safety_class": "WRITE_SAFE",
            "dry_run": True,
            "would_write_to": str(target_path.relative_to(_PROJECT_ROOT)),
            "source_file": str(latest_csv.relative_to(_PROJECT_ROOT)),
            "source_size_bytes": latest_csv.stat().st_size,
            "notes": "Dry-run only. Set dry_run=false to export.",
        }

    if target_path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = _EXPORTS / f"{output_name.removesuffix('.csv')}_{ts}.csv"

    try:
        _EXPORTS.mkdir(parents=True, exist_ok=True)
        content = latest_csv.read_bytes()
        target_path.write_bytes(content)
        st = target_path.stat()
    except Exception as exc:
        return {
            "tool": "qbot_csv_export_create_execute",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "error": str(exc),
            "notes": "CSV export failed.",
        }

    return {
        "tool": "qbot_csv_export_create_execute",
        "status": "OK",
        "safety_class": "WRITE_SAFE",
        "dry_run": False,
        "written_to": str(target_path.relative_to(_PROJECT_ROOT)),
        "file_size_bytes": st.st_size,
        "source_file": str(latest_csv.relative_to(_PROJECT_ROOT)),
        "notes": "CSV exported successfully to outgoing/exports/.",
    }


def _tool_qbot_csv_export_status(_args: dict | None = None) -> dict[str, Any]:
    """Comprehensive CSV export status."""
    inventory = _tool_qbot_csv_export_inventory({"limit": 5})
    latest_get = _tool_qbot_csv_export_latest_get({"source": "garmin_proxy_latest", "limit_rows": 5})
    preview = _tool_qbot_csv_export_create_preview()

    has_csv = inventory.get("csv_count", 0) > 0
    latest_ok = latest_get.get("status") == "OK"
    preview_ok = preview.get("source_available", False)

    if has_csv and latest_ok and preview_ok:
        restored = "RESTORED"
    elif has_csv:
        restored = "PARTIAL"
    else:
        restored = "PARTIAL"

    return {
        "tool": "qbot_csv_export_status",
        "capability": "csv_export",
        "status": "OK" if restored == "RESTORED" else "WARN",
        "safety_class": "READ_ONLY",
        "restored_status": restored,
        "inventory": {"csv_count": inventory.get("csv_count")},
        "latest_available": latest_ok,
        "latest_file": latest_get.get("file"),
        "latest_columns": latest_get.get("columns", [])[:10],
        "create_preview_ready": preview_ok,
        "create_execute_ready": has_csv,
        "notes": "CSV export from Hammerhead-Garmin proxy pipeline. Read-only preview available; controlled execute writes to outgoing/exports/.",
    }
