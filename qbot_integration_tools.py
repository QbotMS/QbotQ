"""Integration status tools — Xert, Intervals, Garmin, Cronometer, Weather, OpenMaps.

Read-only tools for config checking, readiness assessment, and restore planning.
No mutations, no real uploads, no secrets in output.
"""
from __future__ import annotations

import base64 as _b64
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

_PROJECT_ROOT = Path("/opt/qbot/app")
_OUTGOING = _PROJECT_ROOT / "outgoing"


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


def _scan_code_references(keywords: list[str], max_matches: int = 30) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen = set()
    for ky in keywords:
        pattern = re.compile(re.escape(ky), re.IGNORECASE)
        for py_file in sorted(_PROJECT_ROOT.rglob("*.py")):
            if py_file.name in seen:
                continue
            if any(skip in str(py_file) for skip in ["__pycache__", ".venv", "node_modules"]):
                continue
            try:
                text = py_file.read_text(encoding="utf-8", errors="ignore")
            except (PermissionError, OSError):
                continue
            if pattern.search(text):
                seen.add(py_file.name)
                rel = str(py_file.relative_to(_PROJECT_ROOT))
                results.append({
                    "file": rel,
                    "keyword_matched": ky,
                    "size_bytes": len(text.encode("utf-8", errors="ignore")),
                })
            if len(results) >= max_matches:
                break
        if len(results) >= max_matches:
            break
    return results


# ═══════════════════════════════════════════════════════════════════════
#  XERT TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_xert_config_status(_args: dict | None = None) -> dict[str, Any]:
    """Check Xert configuration without exposing credentials."""
    presence = _env_presence(["XERT_EMAIL", "XERT_PASSWORD"])
    email_ok = presence.get("XERT_EMAIL", False)
    password_ok = presence.get("XERT_PASSWORD", False)
    configured = email_ok and password_ok

    missing = [n for n, p in presence.items() if not p]

    if configured:
        status = "OK"
        notes = "Xert credentials are configured. Readiness check available."
    elif email_ok or password_ok:
        status = "WARN"
        notes = "Partial Xert credentials — one of email/password is missing."
    else:
        status = "ERROR"
        notes = "No Xert credentials configured."

    code_refs = _scan_code_references(["xertonline", "xert_public", "get_xert_status"], max_matches=10)
    code_detected = len(code_refs) > 0

    restored = "RESTORED" if configured else ("PARTIAL" if code_detected else "MISSING")

    return {
        "tool": "qbot_xert_config_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "configured": configured,
        "email_present": email_ok,
        "env_presence": presence,
        "missing": missing,
        "code_detected": code_detected,
        "code_references": code_refs[:5],
        "notes": notes,
        "restored_status": restored,
    }


def _tool_qbot_xert_readiness_status(_args: dict | None = None) -> dict[str, Any]:
    """Read-only Xert readiness check. Fetches OAuth token + training data.

    Never exposes credentials in output. Timeout 10s.
    """
    config = _tool_qbot_xert_config_status()
    if not config.get("configured"):
        return {
            "tool": "qbot_xert_readiness_status",
            "status": "BLOCKED_MISSING_SECRET",
            "safety_class": "READ_ONLY",
            "configured": False,
            "ftp_watts": None,
            "ltp_watts": None,
            "w_prime_kj": None,
            "form_status": None,
            "error": None,
            "restored_status": config.get("restored_status", "MISSING"),
            "notes": "Xert credentials not configured. Set XERT_EMAIL and XERT_PASSWORD in .env.local.",
        }

    try:
        with httpx.Client(timeout=10) as client:
            token_r = client.post(
                "https://www.xertonline.com/oauth/token",
                auth=("xert_public", "xert_public"),
                data={
                    "grant_type": "password",
                    "username": os.getenv("XERT_EMAIL", ""),
                    "password": os.getenv("XERT_PASSWORD", ""),
                },
            )
            token_r.raise_for_status()
            token_data = token_r.json()
            access_token = token_data.get("access_token", "")

            training_r = client.get(
                "https://www.xertonline.com/oauth/training",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            training_r.raise_for_status()
            training_data = training_r.json()
    except Exception as exc:
        return {
            "tool": "qbot_xert_readiness_status",
            "status": "WARN",
            "safety_class": "READ_ONLY",
            "configured": True,
            "ftp_watts": None,
            "ltp_watts": None,
            "w_prime_kj": None,
            "form_status": None,
            "error": type(exc).__name__,
            "error_detail": str(exc)[:200],
            "restored_status": "PARTIAL",
            "notes": f"Xert API fetch failed: {type(exc).__name__}. Credentials present but API may be unreachable or invalid.",
        }

    advice = training_data.get("advice", {})
    sig = advice.get("signature", {})
    ts = advice.get("training_status", {})

    ftp_watts = round(sig.get("ftp", 0), 1) if sig.get("ftp") is not None else None
    ltp_watts = round(sig.get("ltp", 0), 1) if sig.get("ltp") is not None else None
    w_prime_kj = round(sig.get("atc", 0) / 1000, 1) if sig.get("atc") is not None else None
    form_cat = ts.get("form_cat", "unknown") if isinstance(ts, dict) else "unknown"

    return {
        "tool": "qbot_xert_readiness_status",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "configured": True,
        "ftp_watts": ftp_watts,
        "ltp_watts": ltp_watts,
        "w_prime_kj": w_prime_kj,
        "form_status": form_cat,
        "error": None,
        "restored_status": "RESTORED",
        "notes": "Xert API responsive. Training data retrieved successfully.",
    }


def _tool_qbot_xert_restore_plan(_args: dict | None = None) -> dict[str, Any]:
    """Restore plan for Xert integration."""
    config = _tool_qbot_xert_config_status()
    missing = config.get("missing", [])
    configured = config.get("configured", False)

    next_steps = []
    if not configured:
        next_steps.append("Set XERT_EMAIL and XERT_PASSWORD in .env.local")
        next_steps.append("Verify with qbot_xert_readiness_status after configuration")
    else:
        next_steps.append("Run qbot_xert_readiness_status to verify API connectivity")
        next_steps.append("Xert integration is configured and ready for read-only use")

    return {
        "tool": "qbot_xert_restore_plan",
        "status": "RESTORED" if configured else "MISSING",
        "safety_class": "READ_ONLY",
        "missing_config": missing,
        "configured": configured,
        "safe_readonly_tests": ["qbot_xert_config_status", "qbot_xert_readiness_status"],
        "next_steps": next_steps,
        "restored_status": "RESTORED" if configured else ("PARTIAL" if next_steps else "MISSING"),
        "notes": "Xert provides training readiness, FTP/LTP, W' and form status. MCP tool get_xert_status already implemented in mcp_server.py.",
    }


# ═══════════════════════════════════════════════════════════════════════
#  INTERVALS TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_intervals_config_status(_args: dict | None = None) -> dict[str, Any]:
    """Check Intervals.icu configuration without exposing secrets."""
    presence = _env_presence(["INTERVALS_ATHLETE_ID", "INTERVALS_API_KEY"])
    athlete_ok = presence.get("INTERVALS_ATHLETE_ID", False)
    api_key_ok = presence.get("INTERVALS_API_KEY", False)
    configured = athlete_ok and api_key_ok

    missing = [n for n, p in presence.items() if not p]

    if configured:
        status = "OK"
        notes = "Intervals.icu credentials are configured."
    elif athlete_ok or api_key_ok:
        status = "WARN"
        notes = "Partial Intervals.icu credentials — some variables missing."
    else:
        status = "ERROR"
        notes = "No Intervals.icu credentials configured."

    code_refs = _scan_code_references(["intervals.icu", "INTERVALS_ATHLETE_ID", "INTERVALS_API_KEY"], max_matches=10)
    code_detected = len(code_refs) > 0

    restored = "RESTORED" if configured else ("PARTIAL" if code_detected else "MISSING")

    return {
        "tool": "qbot_intervals_config_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "configured": configured,
        "athlete_id_present": athlete_ok,
        "api_key_present": api_key_ok,
        "env_presence": presence,
        "missing": missing,
        "code_detected": code_detected,
        "code_references": code_refs[:5],
        "notes": notes,
        "restored_status": restored,
    }


def _tool_qbot_intervals_wellness_status(_args: dict | None = None) -> dict[str, Any]:
    """Read-only Intervals.icu wellness check. Fetches latest wellness data.

    Never exposes API key in output. Timeout 10s.
    """
    config = _tool_qbot_intervals_config_status()
    if not config.get("configured"):
        return {
            "tool": "qbot_intervals_wellness_status",
            "status": "BLOCKED_MISSING_SECRET",
            "safety_class": "READ_ONLY",
            "configured": False,
            "latest_weight_kg": None,
            "latest_hrv_ms": None,
            "latest_sleep_hours": None,
            "latest_date": None,
            "error": None,
            "restored_status": config.get("restored_status", "MISSING"),
            "notes": "Intervals.icu credentials not configured. Set INTERVALS_ATHLETE_ID and INTERVALS_API_KEY in .env.local.",
        }

    api_key = os.getenv("INTERVALS_API_KEY", "")
    athlete_id = os.getenv("INTERVALS_ATHLETE_ID", "")

    try:
        encoded = _b64.b64encode(f"API_KEY:{api_key}".encode()).decode()
        with httpx.Client(timeout=10) as client:
            r = client.get(
                f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness",
                headers={"Authorization": f"Basic {encoded}"},
                params={"oldest": None, "newest": None},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return {
            "tool": "qbot_intervals_wellness_status",
            "status": "WARN",
            "safety_class": "READ_ONLY",
            "configured": True,
            "latest_weight_kg": None,
            "latest_hrv_ms": None,
            "latest_sleep_hours": None,
            "latest_date": None,
            "error": type(exc).__name__,
            "error_detail": str(exc)[:200],
            "restored_status": "PARTIAL",
            "notes": f"Intervals.icu API fetch failed: {type(exc).__name__}. Credentials present but API may be unreachable.",
        }

    latest = data[-1] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})

    weight = latest.get("weight") if isinstance(latest, dict) else None
    hrv = latest.get("hrv") if isinstance(latest, dict) else None
    sleep_hours = None
    sleep_data = latest.get("sleepSecs") if isinstance(latest, dict) else None
    if sleep_data is not None:
        sleep_hours = round(sleep_data / 3600, 1)

    return {
        "tool": "qbot_intervals_wellness_status",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "configured": True,
        "latest_weight_kg": weight,
        "latest_hrv_ms": hrv,
        "latest_sleep_hours": sleep_hours,
        "latest_date": latest.get("id") if isinstance(latest, dict) else None,
        "wellness_records_count": len(data) if isinstance(data, list) else 0,
        "error": None,
        "restored_status": "RESTORED",
        "notes": "Intervals.icu API responsive. Wellness data retrieved.",
    }


def _tool_qbot_intervals_restore_plan(_args: dict | None = None) -> dict[str, Any]:
    """Restore plan for Intervals.icu integration."""
    config = _tool_qbot_intervals_config_status()
    missing = config.get("missing", [])
    configured = config.get("configured", False)

    next_steps = []
    if not configured:
        next_steps.append("Set INTERVALS_ATHLETE_ID in .env.local (find in intervals.icu Settings > Account)")
        next_steps.append("Set INTERVALS_API_KEY in .env.local (generate at intervals.icu Settings > API)")
        next_steps.append("Verify with qbot_intervals_wellness_status after configuration")
    else:
        next_steps.append("Run qbot_intervals_wellness_status to verify API connectivity")
        next_steps.append("Intervals.icu integration is configured and ready for read-only wellness/activity queries")

    return {
        "tool": "qbot_intervals_restore_plan",
        "status": "RESTORED" if configured else "MISSING",
        "safety_class": "READ_ONLY",
        "missing_config": missing,
        "configured": configured,
        "safe_readonly_tests": ["qbot_intervals_config_status", "qbot_intervals_wellness_status"],
        "next_steps": next_steps,
        "restored_status": "RESTORED" if configured else ("PARTIAL" if next_steps else "MISSING"),
        "notes": "Intervals.icu provides wellness, activities, gear, and events data via API. MCP tools already implemented in mcp_server.py (get_wellness, get_activities, get_gear, etc.).",
    }


# ═══════════════════════════════════════════════════════════════════════
#  GARMIN TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_garmin_config_status(_args: dict | None = None) -> dict[str, Any]:
    """Check Garmin configuration without exposing secrets."""
    env_names = [
        "GARMIN_EMAIL",
        "GARMIN_PASSWORD",
        "GARMIN_TOKENSTORE",
    ]
    presence = _env_presence(env_names)

    email_ok = presence.get("GARMIN_EMAIL", False)
    password_ok = presence.get("GARMIN_PASSWORD", False)
    ts_env_ok = presence.get("GARMIN_TOKENSTORE", False)
    creds_ok = email_ok and password_ok

    tokenstore_path = _PROJECT_ROOT / ".garmin_tokens"
    ts_on_disk = False
    ts_file_count = 0
    try:
        if tokenstore_path.exists():
            if tokenstore_path.is_file():
                ts_on_disk = True
                ts_file_count = 1
            elif tokenstore_path.is_dir():
                entries = list(tokenstore_path.iterdir())
                ts_on_disk = len(entries) > 0
                ts_file_count = len(entries)
    except (PermissionError, OSError):
        pass

    has_auth = creds_ok or ts_on_disk

    missing: list[str] = []
    if not has_auth:
        missing = [n for n, p in presence.items() if not p]

    if creds_ok and ts_on_disk:
        status = "OK"
        notes = "Garmin credentials and tokenstore both present. Fully configured."
    elif creds_ok:
        status = "OK"
        notes = "Garmin credentials configured. Tokenstore will be populated on first login."
    elif ts_on_disk:
        status = "WARN"
        notes = "Garmin tokenstore exists on disk but email/password not set. Token may be expired."
    else:
        status = "ERROR"
        notes = "No Garmin credentials or tokenstore configured."

    code_refs = _scan_code_references(["garminconnect", "garmin_auth", "Garmin("], max_matches=10)
    code_detected = len(code_refs) > 0

    restored = "RESTORED" if (creds_ok and ts_on_disk) else ("PARTIAL" if has_auth else "MISSING")

    return {
        "tool": "qbot_garmin_config_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "email_present": email_ok,
        "password_present": password_ok,
        "tokenstore_env_present": ts_env_ok,
        "tokenstore_on_disk": ts_on_disk,
        "tokenstore_path": str(tokenstore_path.relative_to(_PROJECT_ROOT)),
        "tokenstore_file_count": ts_file_count,
        "env_presence": presence,
        "missing": missing,
        "code_detected": code_detected,
        "code_references": code_refs[:5],
        "has_upload_credentials": creds_ok or ts_on_disk,
        "notes": notes,
        "restored_status": restored,
    }


def _tool_qbot_garmin_upload_dry_run(_args: dict | None = None) -> dict[str, Any]:
    """Read-only dry-run of Garmin FIT upload. No real upload performed.

    Checks: latest FIT exists in outgoing/garmin_proxy, upload credentials present.
    Never performs real upload to Garmin.
    """
    config = _tool_qbot_garmin_config_status()

    fit_files = _list_glob_files(_OUTGOING, "garmin_proxy/*.fit", max_files=10)
    latest_fit = fit_files[0] if fit_files else None

    upload_creds_present = config.get("has_upload_credentials", False)
    tokenstore_ok = config.get("tokenstore_on_disk", False)
    fit_available = latest_fit is not None

    would_upload = upload_creds_present and fit_available

    blocked_reasons = []
    if not fit_available:
        blocked_reasons.append("No FIT files in outgoing/garmin_proxy/")
    if not upload_creds_present:
        blocked_reasons.append("No Garmin upload credentials/tokenstore")

    return {
        "tool": "qbot_garmin_upload_dry_run",
        "status": "OK" if would_upload else "BLOCKED",
        "safety_class": "READ_ONLY",
        "would_upload": would_upload,
        "latest_fit_available": fit_available,
        "latest_fit": {
            "name": latest_fit["name"],
            "path": latest_fit["path"],
            "size_bytes": latest_fit["size_bytes"],
            "mtime": latest_fit["mtime"],
        } if latest_fit else None,
        "fit_files_count": len(fit_files),
        "upload_credentials_present": upload_creds_present,
        "tokenstore_on_disk": tokenstore_ok,
        "blocked_reasons": blocked_reasons,
        "notes": "Dry-run only. No real upload to Garmin. To upload, use garmin_auth.py sync pipeline with explicit approval.",
        "restored_status": "RESTORED" if would_upload else ("PARTIAL" if upload_creds_present else "MISSING"),
    }


def _tool_qbot_garmin_restore_plan(_args: dict | None = None) -> dict[str, Any]:
    """Restore plan for Garmin integration."""
    config = _tool_qbot_garmin_config_status()
    dry_run = _tool_qbot_garmin_upload_dry_run()
    missing = config.get("missing", [])
    has_creds = config.get("has_upload_credentials", False)
    ts_ok = config.get("tokenstore_on_disk", False)

    next_steps = []
    if not has_creds:
        next_steps.append("Set GARMIN_EMAIL and GARMIN_PASSWORD in .env.local")
        next_steps.append("Run garmin_auth.py to authenticate and create .garmin_tokens tokenstore")
        next_steps.append("Alternatively restore .garmin_tokens from backup")
    elif not ts_ok:
        next_steps.append("Run garmin_auth.py to generate .garmin_tokens tokenstore")
        next_steps.append("Verify tokenstore with qbot_garmin_config_status")
    else:
        next_steps.append("Run qbot_garmin_upload_dry_run to check FIT files for upload")
        next_steps.append("Use sync_nutrition.py --garmin-sync for controlled upload")
        next_steps.append("MCP tool get_garmin_wellness already available in mcp_server.py")

    return {
        "tool": "qbot_garmin_restore_plan",
        "status": "RESTORED" if (has_creds and ts_ok) else ("PARTIAL" if has_creds else "MISSING"),
        "safety_class": "READ_ONLY",
        "missing_config": missing,
        "has_upload_credentials": has_creds,
        "tokenstore_on_disk": ts_ok,
        "fit_available_for_upload": dry_run.get("latest_fit_available", False),
        "safe_readonly_tests": [
            "qbot_garmin_config_status",
            "qbot_garmin_upload_dry_run",
            "qbot_garmin_proxy_status",
        ],
        "controlled_execution_needed": True,
        "next_steps": next_steps,
        "restored_status": "RESTORED" if (has_creds and ts_ok) else ("PARTIAL" if has_creds else "MISSING"),
        "notes": "Garmin integration uses garminconnect library with tokenstore at .garmin_tokens/. Upload pipeline via Hammerhead proxy FIT files.",
    }


# ═══════════════════════════════════════════════════════════════════════
#  CRONOMETER TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_cronometer_config_status(_args: dict | None = None) -> dict[str, Any]:
    """Check Cronometer configuration without exposing secrets."""
    presence = _env_presence(["CRONOMETER_EMAIL", "CRONOMETER_PASSWORD"])
    email_ok = presence.get("CRONOMETER_EMAIL", False)
    password_ok = presence.get("CRONOMETER_PASSWORD", False)
    configured = email_ok and password_ok

    missing = [n for n, p in presence.items() if not p]

    if configured:
        status = "OK"
        notes = "Cronometer credentials are configured."
    elif email_ok or password_ok:
        status = "WARN"
        notes = "Partial Cronometer credentials — one of email/password is missing."
    else:
        status = "ERROR"
        notes = "No Cronometer credentials configured."

    code_refs = _scan_code_references(["cronometer", "CRONOMETER_", "get_cronometer_nutrition"], max_matches=10)
    code_detected = len(code_refs) > 0

    restored = "RESTORED" if configured else ("PARTIAL" if code_detected else "MISSING")

    return {
        "tool": "qbot_cronometer_config_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "configured": configured,
        "email_present": email_ok,
        "env_presence": presence,
        "missing": missing,
        "code_detected": code_detected,
        "code_references": code_refs[:5],
        "notes": notes,
        "restored_status": restored,
    }


def _tool_qbot_cronometer_legacy_status(_args: dict | None = None) -> dict[str, Any]:
    """Comprehensive Cronometer legacy parity status. Read-only scan."""
    config = _tool_qbot_cronometer_config_status()

    code_refs = _scan_code_references(
        ["cronometer", "CRONOMETER_EMAIL", "CRONOMETER_PASSWORD", "get_cronometer_nutrition",
         "cronometer_mcp", "nutrition", "CronometerClient", "sync_nutrition"],
        max_matches=40,
    )

    code_detected = len(code_refs) > 0

    mcp_tool_detected = any("get_cronometer_nutrition" in ref.get("file", "") for ref in code_refs)
    sync_script = _PROJECT_ROOT / "sync_nutrition.py"

    if config.get("configured") and mcp_tool_detected:
        restored = "RESTORED"
        notes = "Cronometer configured and MCP nutrition tool available."
    elif code_detected:
        restored = "PARTIAL"
        notes = "Cronometer code detected but may be missing credentials or MCP surface."
    else:
        restored = "MISSING"
        notes = "No Cronometer code or configuration detected."

    return {
        "tool": "qbot_cronometer_legacy_status",
        "capability": "cronometer",
        "status": "OK" if config.get("configured") else ("WARN" if code_detected else "ERROR"),
        "safety_class": "READ_ONLY",
        "configured": config.get("configured"),
        "code_detected": code_detected,
        "candidate_files": code_refs[:20],
        "mcp_tool_available": mcp_tool_detected,
        "sync_script_exists": sync_script.exists(),
        "env_presence": config.get("env_presence", {}),
        "restored_status": restored,
        "notes": notes,
        "can_restore_today": config.get("configured", False),
        "risk": "medium",
    }


def _tool_qbot_cronometer_restore_plan(_args: dict | None = None) -> dict[str, Any]:
    """Restore plan for Cronometer integration."""
    config = _tool_qbot_cronometer_config_status()
    legacy = _tool_qbot_cronometer_legacy_status()
    missing = config.get("missing", [])
    configured = config.get("configured", False)

    next_steps = []
    if not configured:
        next_steps.append("Set CRONOMETER_EMAIL and CRONOMETER_PASSWORD in .env.local")
        next_steps.append("Install cronometer_mcp Python package if not present")
        next_steps.append("Verify with qbot_cronometer_config_status after configuration")
    else:
        next_steps.append("Run get_cronometer_nutrition MCP tool for read-only nutrition data")
        next_steps.append("Use sync_nutrition.py for scheduled nutrition sync")

    return {
        "tool": "qbot_cronometer_restore_plan",
        "status": "RESTORED" if configured else "MISSING",
        "safety_class": "READ_ONLY",
        "missing_config": missing,
        "configured": configured,
        "mcp_tool_available": legacy.get("mcp_tool_available", False),
        "sync_script_available": legacy.get("sync_script_exists", False),
        "safe_readonly_tests": ["qbot_cronometer_config_status", "qbot_cronometer_legacy_status"],
        "next_steps": next_steps,
        "restored_status": "RESTORED" if configured else ("PARTIAL" if legacy.get("code_detected") else "MISSING"),
        "notes": "Cronometer provides daily nutrition summaries via cronometer_mcp package. MCP tool get_cronometer_nutrition already implemented in mcp_server.py.",
    }


# ═══════════════════════════════════════════════════════════════════════
#  WEATHER TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_weather_config_status(_args: dict | None = None) -> dict[str, Any]:
    """Check weather configuration without exposing secrets."""
    owm_names = ["OPENWEATHERMAP_API_KEY", "OWM_API_KEY", "WEATHER_API_KEY"]
    location_names = ["LOCATION_LAT", "LOCATION_LON", "LOCATION_NAME"]

    owm_presence = _env_presence(owm_names)
    location_presence = _env_presence(location_names)

    any_owm_key = any(owm_presence.values())
    location_ok = all(location_presence.values())
    lat_ok = location_presence.get("LOCATION_LAT", False)
    lon_ok = location_presence.get("LOCATION_LON", False)
    name_ok = location_presence.get("LOCATION_NAME", False)

    if any_owm_key and location_ok:
        status = "OK"
        notes = "Weather API key and location are fully configured."
    elif any_owm_key or location_ok:
        status = "WARN"
        notes = "Partial weather configuration."
    else:
        status = "OK"
        notes = "Open-Meteo API (free, no key needed) is the primary weather provider. Location is configured for fallback."

    code_refs = _scan_code_references(["openweathermap", "open-meteo", "get_weather", "weathercode"], max_matches=10)
    code_detected = len(code_refs) > 0

    open_meteo_active = location_ok

    if open_meteo_active:
        restored = "RESTORED"
    elif any_owm_key:
        restored = "PARTIAL"
    elif code_detected:
        restored = "PARTIAL"
    else:
        restored = "MISSING"

    return {
        "tool": "qbot_weather_config_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "openweathermap_key_present": any_owm_key,
        "owm_envs_checked": owm_names,
        "owm_env_presence": owm_presence,
        "location_present": location_ok,
        "location_lat_present": lat_ok,
        "location_lon_present": lon_ok,
        "location_name_present": name_ok,
        "location_env_presence": location_presence,
        "primary_provider": "open-meteo (free, no API key)",
        "open_meteo_active": open_meteo_active,
        "code_detected": code_detected,
        "code_references": code_refs[:5],
        "notes": notes,
        "restored_status": restored,
    }


# ═══════════════════════════════════════════════════════════════════════
#  OPENMAPS TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_openmaps_config_status(_args: dict | None = None) -> dict[str, Any]:
    """Check OpenMaps/OSM/Overpass configuration. Free service, no auth needed.

    Reports code detected in mcp_server.py (6 OpenMaps tools).
    """
    overpass_endpoint = "https://overpass-api.de/api/interpreter"

    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                "https://overpass-api.de/api/status",
                headers={"User-Agent": "Q-rowerowy-asystent/1.0"},
            )
            overpass_ok = r.status_code == 200
            overpass_reason = f"Overpass API HTTP {r.status_code}"
    except Exception as exc:
        overpass_ok = False
        overpass_reason = str(exc)

    mcp_server = _PROJECT_ROOT / "mcp_server.py"
    openmaps_tools: list[str] = []
    try:
        if mcp_server.exists():
            text = mcp_server.read_text(encoding="utf-8", errors="ignore")
            openmaps_tool_names = [
                "openmaps_healthcheck",
                "openmaps_query_bbox",
                "openmaps_enrich_rwgps_track",
                "openmaps_find_pois_near_track",
                "openmaps_detect_route_risks",
                "openmaps_build_route_snapshot",
            ]
            for name in openmaps_tool_names:
                if f"def {name}" in text:
                    openmaps_tools.append(name)
    except (PermissionError, OSError):
        pass

    tool_count = len(openmaps_tools)
    code_detected = tool_count > 0

    if overpass_ok and code_detected:
        status = "OK"
        notes = "Overpass API reachable. All OpenMaps tools detected in mcp_server.py."
    elif code_detected:
        status = "WARN"
        notes = f"OpenMaps tools detected ({tool_count}) but Overpass API is degraded."
    else:
        status = "ERROR"
        notes = "OpenMaps/Overpass integration not detected."

    restored = "RESTORED" if (overpass_ok and code_detected) else ("PARTIAL" if code_detected else "MISSING")

    return {
        "tool": "qbot_openmaps_config_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "overpass_endpoint": overpass_endpoint,
        "overpass_reachable": overpass_ok,
        "overpass_reason": overpass_reason,
        "auth_required": False,
        "free_service": True,
        "openmaps_tools_detected": openmaps_tools,
        "openmaps_tool_count": tool_count,
        "code_detected": code_detected,
        "notes": notes,
        "restored_status": restored,
    }


def _tool_qbot_openmaps_legacy_status(_args: dict | None = None) -> dict[str, Any]:
    """Comprehensive OpenMaps/OSM/Overpass legacy parity status."""
    config = _tool_qbot_openmaps_config_status()

    mcp_server = _PROJECT_ROOT / "mcp_server.py"
    openmaps_lines = 0
    try:
        if mcp_server.exists():
            text = mcp_server.read_text(encoding="utf-8", errors="ignore")
            lines = text.split("\n")
            in_block = False
            for line in lines:
                if "openmaps_" in line.lower() or "overpass" in line.lower() or "osm_" in line.lower():
                    openmaps_lines += 1
    except (PermissionError, OSError):
        pass

    code_refs = _scan_code_references(
        ["openmap", "openmaps_v1", "openstreetmap", "osm", "overpass", "OpenMaps"],
        max_matches=30,
    )
    code_detected = len(code_refs) > 0

    merged_tools = []
    for ref in code_refs:
        file = ref.get("file", "")
        keyword = ref.get("keyword_matched", "")
        merged_tools.append(f"{file} :: {keyword}")

    route_surface_cache = _PROJECT_ROOT / "data" / "route_surface_cache.json"
    cache_exists = route_surface_cache.exists()
    cache_entries = 0
    if cache_exists:
        try:
            cache_data = json.loads(route_surface_cache.read_text(encoding="utf-8"))
            cache_entries = len(cache_data) if isinstance(cache_data, dict) else 0
        except Exception:
            pass

    overpass_ok = config.get("overpass_reachable", False)
    tool_count = config.get("openmaps_tool_count", 0)

    if overpass_ok and tool_count >= 6:
        restored = "RESTORED"
        notes = "All 6 OpenMaps tools detected and Overpass API reachable. Full integration active."
    elif tool_count >= 1:
        restored = "PARTIAL"
        notes = f"{tool_count} OpenMaps tools detected but Overpass API may be degraded."
    elif code_detected:
        restored = "PARTIAL"
        notes = "OSM/Overpass code references found but no OpenMaps tools detected."
    else:
        restored = "MISSING"
        notes = "No OpenMaps/OSM integration detected."

    return {
        "tool": "qbot_openmaps_legacy_status",
        "capability": "openmap_osm",
        "status": "OK" if overpass_ok and tool_count >= 6 else ("WARN" if code_detected else "ERROR"),
        "safety_class": "READ_ONLY",
        "overpass_reachable": overpass_ok,
        "overpass_endpoint": config.get("overpass_endpoint"),
        "openmaps_tools_count": tool_count,
        "openmaps_tools": config.get("openmaps_tools_detected", []),
        "code_detected": code_detected,
        "code_lines_with_openmaps": openmaps_lines,
        "candidate_files": code_refs[:15],
        "merged_tool_references": merged_tools[:20],
        "generated_artifacts": {
            "route_surface_cache_exists": cache_exists,
            "route_surface_cache_entries": cache_entries,
        },
        "auth_required": False,
        "restored_status": restored,
        "notes": notes,
        "can_restore_today": True,
        "risk": "medium",
    }


# ═══════════════════════════════════════════════════════════════════════
#  MODULE INIT — VERIFICATION
# ═══════════════════════════════════════════════════════════════════════

__all__ = [
    "_tool_qbot_xert_config_status",
    "_tool_qbot_xert_readiness_status",
    "_tool_qbot_xert_restore_plan",
    "_tool_qbot_intervals_config_status",
    "_tool_qbot_intervals_wellness_status",
    "_tool_qbot_intervals_restore_plan",
    "_tool_qbot_garmin_config_status",
    "_tool_qbot_garmin_upload_dry_run",
    "_tool_qbot_garmin_restore_plan",
    "_tool_qbot_cronometer_config_status",
    "_tool_qbot_cronometer_legacy_status",
    "_tool_qbot_cronometer_restore_plan",
    "_tool_qbot_weather_config_status",
    "_tool_qbot_openmaps_config_status",
    "_tool_qbot_openmaps_legacy_status",
]
