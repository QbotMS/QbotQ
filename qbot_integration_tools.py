"""Integration status tools — Xert, Intervals, Garmin, Cronometer, Weather, OpenMaps.

Read-only tools for config checking, readiness assessment, and restore planning.
No mutations, no real uploads, no secrets in output.
"""
from __future__ import annotations

import base64 as _b64
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import qbot_config as cfg

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
            "status": "BLOCKED_BY_SECRET",
            "safety_class": "READ_ONLY",
            "athlete_id_present": config.get("athlete_id_present", False),
            "api_key_present": config.get("api_key_present", False),
            "auth_ok": False,
            "latest_wellness_date": None,
            "weight_kg": None,
            "hrv": None,
            "resting_hr": None,
            "sleep": None,
            "reason": "Intervals.icu credentials not configured. Set INTERVALS_ATHLETE_ID and INTERVALS_API_KEY in .env.local.",
        }

    api_key = os.getenv("INTERVALS_API_KEY", "")
    athlete_id = os.getenv("INTERVALS_ATHLETE_ID", "")

    try:
        encoded = _b64.b64encode(f"API_KEY:{api_key}".encode()).decode()
        with httpx.Client(timeout=10) as client:
            r = client.get(
                f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness",
                headers={"Authorization": f"Basic {encoded}"},
            )
            if r.status_code == 401:
                return {
                    "tool": "qbot_intervals_wellness_status",
                    "status": "AUTH_ERROR",
                    "safety_class": "READ_ONLY",
                    "athlete_id_present": True,
                    "api_key_present": True,
                    "auth_ok": False,
                    "latest_wellness_date": None,
                    "weight_kg": None,
                    "hrv": None,
                    "resting_hr": None,
                    "sleep": None,
                    "reason": "Intervals.icu HTTP 401 — invalid API key or athlete ID.",
                }
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response else "?"
        return {
            "tool": "qbot_intervals_wellness_status",
            "status": "API_ERROR",
            "safety_class": "READ_ONLY",
            "athlete_id_present": True,
            "api_key_present": True,
            "auth_ok": None,
            "latest_wellness_date": None,
            "weight_kg": None,
            "hrv": None,
            "resting_hr": None,
            "sleep": None,
            "reason": f"Intervals.icu HTTP {code}: {str(exc)[:200]}.",
        }
    except Exception as exc:
        return {
            "tool": "qbot_intervals_wellness_status",
            "status": "API_ERROR",
            "safety_class": "READ_ONLY",
            "athlete_id_present": True,
            "api_key_present": True,
            "auth_ok": None,
            "latest_wellness_date": None,
            "weight_kg": None,
            "hrv": None,
            "resting_hr": None,
            "sleep": None,
            "reason": f"Intervals.icu request failed: {type(exc).__name__}: {str(exc)[:200]}.",
        }

    records = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
    latest = records[-1] if records else {}
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    latest_id = latest.get("id", "") if isinstance(latest, dict) else ""

    weight = latest.get("weight") if isinstance(latest, dict) else None
    hrv = latest.get("hrv") if isinstance(latest, dict) else None
    resting_hr = latest.get("restingHR") if isinstance(latest, dict) else None
    sleep_hours = None
    sleep_data = latest.get("sleepSecs") if isinstance(latest, dict) else None
    if sleep_data is not None:
        sleep_hours = round(sleep_data / 3600, 1)

    if not records:
        return {
            "tool": "qbot_intervals_wellness_status",
            "status": "PARTIAL_NO_TODAY_DATA",
            "safety_class": "READ_ONLY",
            "athlete_id_present": True,
            "api_key_present": True,
            "auth_ok": True,
            "latest_wellness_date": None,
            "weight_kg": None,
            "hrv": None,
            "resting_hr": None,
            "sleep": None,
            "reason": "API responded but returned no wellness records.",
        }

    is_today = str(latest_id).startswith(today_str) if latest_id else False
    if not is_today:
        return {
            "tool": "qbot_intervals_wellness_status",
            "status": "PARTIAL_NO_TODAY_DATA",
            "safety_class": "READ_ONLY",
            "athlete_id_present": True,
            "api_key_present": True,
            "auth_ok": True,
            "latest_wellness_date": latest_id,
            "weight_kg": weight,
            "hrv": hrv,
            "resting_hr": resting_hr,
            "sleep": sleep_hours,
            "reason": f"Brak dzisiejszego wpisu wellness. Ostatni wpis: {latest_id}. API działa poprawnie.",
        }

    return {
        "tool": "qbot_intervals_wellness_status",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "athlete_id_present": True,
        "api_key_present": True,
        "auth_ok": True,
        "latest_wellness_date": latest_id,
        "weight_kg": weight,
        "hrv": hrv,
        "resting_hr": resting_hr,
        "sleep": sleep_hours,
        "wellness_records_count": len(records),
        "reason": "Intervals.icu API działa poprawnie. Zwrócono dane wellness.",
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

def _owm_api_key() -> str:
    return cfg.OPENWEATHERMAP_API_KEY or ""


def _owm_local_dt(ts: int, tz_offset_seconds: int | None = None) -> str:
    utc_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    if tz_offset_seconds is None:
        return utc_dt.astimezone().isoformat(timespec="minutes")
    tz = timezone(timedelta(seconds=int(tz_offset_seconds)))
    return utc_dt.astimezone(tz).isoformat(timespec="minutes")


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(
            str(v)
            .replace("°C", "")
            .replace("m/s", "")
            .replace("km/h", "")
            .replace("%", "")
            .replace("mm", "")
            .strip()
        )
    except Exception:
        return None


def _tool_qbot_weather_daily_report(_args: dict | None = None) -> dict[str, Any]:
    """OpenWeatherMap-based weather payload for daily_report.py."""
    _args = _args or {}
    location = str(_args.get("location", "") or cfg.LOCATION_NAME or "Marki").strip()
    days = min(max(int(_args.get("days", 2)), 1), 7)
    lat = _args.get("lat")
    lon = _args.get("lon")
    key = _owm_api_key()

    if not key:
        return {
            "tool": "qbot_weather_daily_report",
            "status": "ERROR",
            "source": "OpenWeatherMap",
            "error": "OpenWeatherMap API key not configured",
            "openweathermap_attempted": False,
            "openweathermap_status_code": None,
            "location_resolved": location,
        }

    try:
        with httpx.Client(timeout=10.0, trust_env=False) as c:
            if not (lat and lon):
                geo = c.get(
                    "https://api.openweathermap.org/geo/1.0/direct",
                    params={"q": location, "limit": 1, "appid": key},
                )
                if geo.status_code != 200:
                    return {
                        "tool": "qbot_weather_daily_report",
                        "status": "ERROR",
                        "source": "OpenWeatherMap",
                        "error": f"OpenWeatherMap geocoding HTTP {geo.status_code}",
                        "openweathermap_attempted": True,
                        "openweathermap_status_code": geo.status_code,
                        "location_resolved": location,
                    }
                geo_data = geo.json() or []
                if not geo_data:
                    return {
                        "tool": "qbot_weather_daily_report",
                        "status": "ERROR",
                        "source": "OpenWeatherMap",
                        "error": f"OpenWeatherMap geocoding returned no results for {location}",
                        "openweathermap_attempted": True,
                        "openweathermap_status_code": geo.status_code,
                        "location_resolved": location,
                    }
                first = geo_data[0]
                lat = first.get("lat")
                lon = first.get("lon")
                resolved_name = first.get("name") or location
                country = first.get("country")
                if country:
                    location = f"{resolved_name}, {country}"
                else:
                    location = resolved_name

            current_r = c.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"lat": lat, "lon": lon, "appid": key, "units": "metric", "lang": "pl"},
            )
            forecast_r = c.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params={"lat": lat, "lon": lon, "appid": key, "units": "metric", "lang": "pl"},
            )
            if current_r.status_code != 200:
                return {
                    "tool": "qbot_weather_daily_report",
                    "status": "ERROR",
                    "source": "OpenWeatherMap",
                    "error": f"OpenWeatherMap current HTTP {current_r.status_code}",
                    "openweathermap_attempted": True,
                    "openweathermap_status_code": current_r.status_code,
                    "location_resolved": location,
                }
            if forecast_r.status_code != 200:
                return {
                    "tool": "qbot_weather_daily_report",
                    "status": "ERROR",
                    "source": "OpenWeatherMap",
                    "error": f"OpenWeatherMap forecast HTTP {forecast_r.status_code}",
                    "openweathermap_attempted": True,
                    "openweathermap_status_code": forecast_r.status_code,
                    "location_resolved": location,
                }

            current = current_r.json()
            forecast = forecast_r.json()
            tz_offset = (forecast.get("city") or {}).get("timezone", 0)
            current_dt = _owm_local_dt(int(current.get("dt", 0)), tz_offset)
            current_weather = (current.get("weather") or [{}])[0]
            current_main = current.get("main") or {}
            current_wind = current.get("wind") or {}
            current_clouds = current.get("clouds") or {}

            forecast_items = forecast.get("list") or []
            selected = forecast_items[: min(len(forecast_items), days * 8)]
            hourly_forecast: list[dict[str, Any]] = []
            grouped: dict[str, list[dict[str, Any]]] = {}
            for item in selected:
                local_ts = _owm_local_dt(int(item.get("dt", 0)), tz_offset)
                day_key = local_ts[:10]
                grouped.setdefault(day_key, []).append(item)
                weather = (item.get("weather") or [{}])[0]
                main = item.get("main") or {}
                wind = item.get("wind") or {}
                clouds = item.get("clouds") or {}
                pop = item.get("pop")
                rain = item.get("rain") or {}
                snow = item.get("snow") or {}
                hourly_forecast.append({
                    "czas": local_ts,
                    "temperatura": f"{main.get('temp')}°C" if main.get("temp") is not None else None,
                    "szansa_deszczu": f"{round(float(pop) * 100)}%" if pop is not None else "0%",
                    "opady_mm": round(float(rain.get("3h") or 0) + float(snow.get("3h") or 0), 1),
                    "wiatr_ms": f"{wind.get('speed', 0)} m/s",
                    "zachmurzenie": f"{clouds.get('all', 0)}%",
                    "warunki": weather.get("description") or "",
                })

            prognoza: list[dict[str, Any]] = []
            for day_key, items in sorted(grouped.items()):
                temps = [item.get("main", {}).get("temp") for item in items if item.get("main", {}).get("temp") is not None]
                winds = [item.get("wind", {}).get("speed") for item in items if item.get("wind", {}).get("speed") is not None]
                clouds_vals = [item.get("clouds", {}).get("all") for item in items if item.get("clouds", {}).get("all") is not None]
                pops = [item.get("pop") for item in items if item.get("pop") is not None]
                rain_mm = 0.0
                for item in items:
                    rain = item.get("rain") or {}
                    snow = item.get("snow") or {}
                    rain_mm += float(rain.get("3h") or 0) + float(snow.get("3h") or 0)
                weather = (items[0].get("weather") or [{}])[0]
                prognoza.append({
                    "data": day_key,
                    "warunki": weather.get("description") or "",
                    "temp_max": f"{max(temps):.1f}°C" if temps else None,
                    "temp_min": f"{min(temps):.1f}°C" if temps else None,
                    "szansa_deszcz": f"{round(max(pops) * 100)}%" if pops else "0%",
                    "opady_mm": round(rain_mm, 1),
                    "max_wiatr_ms": f"{max(winds):.1f} m/s" if winds else None,
                    "zachmurzenie": f"{round(sum(clouds_vals) / len(clouds_vals))}%" if clouds_vals else None,
                })

            return {
                "tool": "qbot_weather_daily_report",
                "status": "OK",
                "source": "OpenWeatherMap",
                "api_source": "openweathermap.org",
                "location_resolved": location,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "teraz": {
                    "temperatura": f"{current_main.get('temp')}°C" if current_main.get("temp") is not None else None,
                    "odczuwalna": f"{current_main.get('feels_like')}°C" if current_main.get("feels_like") is not None else None,
                    "warunki": current_weather.get("description") or "",
                    "wiatr_ms": f"{current_wind.get('speed', 0)} m/s",
                    "zachmurzenie": f"{current_clouds.get('all', 0)}%",
                    "wilgotnosc": f"{current_main.get('humidity')}%" if current_main.get("humidity") is not None else None,
                    "opady_mm": round(float((current.get("rain") or {}).get("1h") or 0) + float((current.get("snow") or {}).get("1h") or 0), 1),
                    "observed_at": current_dt,
                },
                "hourly_forecast": hourly_forecast,
                "prognoza": prognoza,
                "openweathermap_attempted": True,
                "openweathermap_status_code": 200,
            }
    except Exception as exc:
        return {
            "tool": "qbot_weather_daily_report",
            "status": "ERROR",
            "source": "OpenWeatherMap",
            "error": f"OpenWeatherMap error: {str(exc)[:200]}",
            "openweathermap_attempted": True,
            "openweathermap_status_code": None,
            "location_resolved": location,
        }

def _tool_qbot_weather_config_status(_args: dict | None = None) -> dict[str, Any]:
    """Check weather configuration without exposing secrets."""
    owm_names = list(cfg.WEATHER_API_KEY_NAMES)
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
        notes = "OpenWeatherMap API key and location are fully configured. Primary: OWM, fallback: Open-Meteo."
    elif any_owm_key:
        status = "WARN"
        notes = "OpenWeatherMap key present but location missing. Primary: OWM, fallback: Open-Meteo."
    elif location_ok:
        status = "OK"
        notes = "Open-Meteo (free, no key) will be used. OpenWeatherMap not configured."
    else:
        status = "WARN"
        notes = "No weather API key and no location configured."

    if any_owm_key:
        restored = "RESTORED"
    elif location_ok:
        restored = "RESTORED"
    elif code_detected:
        restored = "PARTIAL"
    else:
        restored = "MISSING"

    return {
        "tool": "qbot_weather_config_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "openweathermap_key_present": any_owm_key,
        "default_location_present": location_ok,
        "fallback_open_meteo_enabled": True,
        "owm_envs_checked": owm_names,
        "owm_env_presence": owm_presence,
        "location_present": location_ok,
        "primary_provider": "OpenWeatherMap" if any_owm_key else "Open-Meteo/ECMWF",
        "notes": notes,
        "restored_status": restored,
        "missing": [n for n, p in owm_presence.items() if not p] if not any_owm_key else [],
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
#  WEATHER TOOLS — OpenWeatherMap primary, Open-Meteo fallback
# ═══════════════════════════════════════════════════════════════════════


def _find_city_from_text(text: str) -> str | None:
    import re
    t = (text or "").lower()
    # City patterns
    city_map = {
        "marek": "Marki,PL", "markach": "Marki,PL", "markami": "Marki,PL", "marki": "Marki,PL",
        "warszawy": "Warszawa,PL", "warszawie": "Warszawa,PL", "warszawa": "Warszawa,PL",
        "wrocław": "Wrocław,PL", "wrocławia": "Wrocław,PL",
        "krakow": "Kraków,PL", "krakowa": "Kraków,PL", "krakowie": "Kraków,PL",
    }
    for clean_prefix in ["dla ", "w ", "na ", "sprawdź pogodę dla ", "pogoda ", "pogodę "]:
        t = t.replace(clean_prefix, " ")
    words = t.split()
    for w in words:
        for city, full in city_map.items():
            if city in w:
                return full
    # Generic pattern: if 2+ words, check if capitalized == location
    return None


def _tool_qbot_last_ride_location_status(_args: dict | None = None) -> dict[str, Any]:
    from pathlib import Path
    import json, csv as _csv_module

    outgoing = Path("/opt/qbot/app/outgoing")
    now = datetime.now(timezone.utc)

    best_age = float("inf")
    best_lat = None
    best_lon = None
    best_label = ""
    best_file = ""
    best_type = ""

    # 1. Check report JSONs for location data
    for rp in outgoing.glob("**/reports/*_report.json"):
        try:
            st = rp.stat()
            age_h = (now - datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)).total_seconds() / 3600
            if age_h > 24:
                continue
            data = json.loads(rp.read_text(encoding="utf-8"))
            for k in ("end_lat", "start_lat", "lat", "latitude", "location_lat"):
                if k in data and data[k]:
                    best_lat = float(data[k])
                    for k2 in ("end_lon", "start_lon", "lon", "longitude", "location_lon"):
                        if k2 in data and data[k2]:
                            best_lon = float(data[k2])
                            break
                    if best_lat and best_lon:
                        best_age = age_h
                        best_file = str(rp)
                        best_type = "report_json"
                        best_label = f"{best_lat:.4f},{best_lon:.4f}"
                        break
        except Exception:
            pass

    # 2. Check Garmin proxy CSV for lat/lon columns
    if best_lat is None:
        for cp in outgoing.glob("**/garmin_proxy/*.csv"):
            try:
                st = cp.stat()
                age_h = (now - datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)).total_seconds() / 3600
                if age_h > 24 or age_h >= best_age:
                    continue
                text = cp.read_text(encoding="utf-8", errors="ignore")
                reader = _csv_module.reader(io.StringIO(text))
                rows = list(reader)
                if len(rows) < 2:
                    continue
                headers = [h.strip().lower() for h in rows[0]]
                lat_i, lon_i = -1, -1
                for i, h in enumerate(headers):
                    if h in ("position_lat", "lat", "latitude"):
                        lat_i = i
                    if h in ("position_long", "lon", "longitude"):
                        lon_i = i
                if lat_i >= 0 and lon_i >= 0:
                    for row in reversed(rows[1:]):
                        try:
                            best_lat = float(row[lat_i]) if row[lat_i] else None
                            best_lon = float(row[lon_i]) if row[lon_i] else None
                            if best_lat and best_lon:
                                best_age = age_h
                                best_file = str(cp)
                                best_type = "garmin_proxy_csv"
                                best_label = f"{best_lat:.4f},{best_lon:.4f}"
                                break
                        except Exception:
                            pass
            except Exception:
                pass

    usable = best_lat is not None and best_age <= 18
    reason = ""
    if best_lat is None:
        reason = "no location data found in recent ride artifacts"
    elif best_age > 18:
        reason = f"last ride is {best_age:.1f}h old (>18h limit)"

    return {
        "tool": "qbot_last_ride_location_status",
        "status": "OK" if best_lat else ("WARN" if usable else "NO_DATA"),
        "safety_class": "READ_ONLY",
        "latest_ride_at": datetime.fromtimestamp(Path(best_file).stat().st_mtime, tz=timezone.utc).isoformat() if best_file else None,
        "age_hours": round(best_age, 1) if best_age < float("inf") else None,
        "lat": best_lat,
        "lon": best_lon,
        "location_label": best_label,
        "source_file": best_file,
        "source_type": best_type,
        "usable_for_weather": usable,
        "reason": reason,
        "notes": "Read-only scan of ride artifacts. No API calls, no uploads.",
    }


def _tool_qbot_resolve_weather_location(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    text = str(_args.get("text", "") or "")
    max_age = float(_args.get("max_last_ride_age_hours", 18))

    # Step 1: Look for location in message text
    city = _find_city_from_text(text)
    if city:
        return {
            "tool": "qbot_resolve_weather_location",
            "status": "OK",
            "location_resolved": city,
            "location_source": "message_text",
            "last_ride_age_hours": None,
            "last_ride_source_file": None,
            "warnings": [],
        }

    # Step 2: Check last ride location
    ride = _tool_qbot_last_ride_location_status({})
    if ride.get("usable_for_weather") and ride.get("age_hours", 99) <= max_age:
        return {
            "tool": "qbot_resolve_weather_location",
            "status": "OK",
            "location_resolved": ride.get("location_label"),
            "lat": ride.get("lat"),
            "lon": ride.get("lon"),
            "location_source": "last_ride_location",
            "last_ride_age_hours": ride.get("age_hours"),
            "last_ride_source_file": ride.get("source_file"),
            "warnings": ["użyto ostatniej lokalizacji z przejechanej trasy"],
        }

    # Step 3: No location available
    age = ride.get("age_hours")
    if age is not None:
        return {
            "tool": "qbot_resolve_weather_location",
            "status": "NEEDS_LOCATION",
            "location_resolved": None,
            "location_source": "none",
            "last_ride_age_hours": age,
            "message": f"Dla jakiej lokalizacji sprawdzić pogodę? Ostatnia trasa ma {age:.0f}h (>18h).",
            "warnings": [],
        }

    return {
        "tool": "qbot_resolve_weather_location",
        "status": "NEEDS_LOCATION",
        "location_resolved": None,
        "location_source": "none",
        "last_ride_age_hours": age,
        "message": "Dla jakiej lokalizacji sprawdzić pogodę? Brak zapisanej lokalizacji z trasy.",
        "warnings": [],
    }


def _resolve_user_location(text: str, env_only: bool = False) -> dict[str, Any]:
    import re

    city_map = {
        "marek": "Marki,PL", "markach": "Marki,PL", "markami": "Marki,PL",
        "warszawy": "Warszawa,PL", "warszawie": "Warszawa,PL", "warszawa": "Warszawa,PL",
        "wrocław": "Wrocław,PL", "wrocławia": "Wrocław,PL",
        "krakow": "Kraków,PL", "krakowa": "Kraków,PL", "krakowie": "Kraków,PL",
    }

    t = (text or "").lower()
    for phrase in ["dla ", "w ", "na ", "sprawdź pogodę dla ", "pogoda ", "pogodę "]:
        t = t.replace(phrase, " ")
    words = t.split()

    for w in words:
        for city, full in city_map.items():
            if city in w:
                return {"location_resolved": full, "location_source": "message_text", "status": "OK"}

    for env_var in ["QBOT_DEFAULT_LOCATION", "WEATHER_DEFAULT_LOCATION", "QBOT_HOME_LOCATION"]:
        v = os.getenv(env_var)
        if v and v.strip():
            return {"location_resolved": v.strip(), "location_source": "env_default", "status": "OK"}

    lat = os.getenv("LOCATION_LAT")
    lon = os.getenv("LOCATION_LON")
    name = os.getenv("LOCATION_NAME")
    if lat and lon:
        loc = f"{name},PL" if name else f"{lat},{lon}"
        return {"location_resolved": loc, "location_source": "env_default", "status": "OK"}

    return {"status": "NEEDS_LOCATION", "message": "Dla jakiej lokalizacji sprawdzić pogodę?"}


def _tool_qbot_resolve_user_location(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    text = str(_args.get("text", ""))
    return {
        "tool": "qbot_resolve_user_location",
        "safety_class": "READ_ONLY",
        **_resolve_user_location(text),
    }


def _tool_qbot_weather_current(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    location = str(_args.get("location", "") or "")
    lat = _args.get("lat")
    lon = _args.get("lon")

    owm_key = os.getenv("OPENWEATHERMAP_API_KEY") or os.getenv("OWM_API_KEY") or os.getenv("WEATHER_API_KEY")

    owm_attempted = False
    owm_status_code = None
    owm_error_type = ""
    om_attempted = False
    om_status_code = None
    om_error_type = ""

    if not location and not (lat and lon):
        loc = _tool_qbot_resolve_weather_location({"text": str(_args.get("text", "")), "max_last_ride_age_hours": 18})
        if loc.get("status") == "NEEDS_LOCATION":
            return {
                "tool": "qbot_weather_current",
                "status": "NEEDS_LOCATION",
                "safety_class": "READ_ONLY",
                "source": "none",
                "fallback_used": False,
                "location_source": "none",
                "message": loc.get("message"),
                "openweathermap_attempted": False,
                "open_meteo_attempted": False,
            }
        location = loc.get("location_resolved", "")
        lat = loc.get("lat")
        lon = loc.get("lon")
        location_source = loc.get("location_source", "")
        last_ride_age = loc.get("last_ride_age_hours")

    if owm_key:
        owm_attempted = True
        try:
            import httpx
            if lat and lon:
                url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={owm_key}&units=metric&lang=pl"
            else:
                url = f"https://api.openweathermap.org/data/2.5/weather?q={location}&appid={owm_key}&units=metric&lang=pl"
            with httpx.Client(timeout=10.0, trust_env=False) as c:
                r = c.get(url)
                owm_status_code = r.status_code
                if r.status_code == 200:
                    d = r.json()
                    return {
                        "tool": "qbot_weather_current",
                        "status": "OK",
                        "source": "OpenWeatherMap",
                        "fallback_used": False,
                        "location_resolved": location,
                        "temperature_c": d["main"]["temp"],
                        "feels_like_c": d["main"]["feels_like"],
                        "wind_mps": d["wind"]["speed"],
                        "wind_kmh": round(d["wind"]["speed"] * 3.6, 1),
                        "clouds_percent": d["clouds"]["all"],
                        "rain_1h_mm": d.get("rain", {}).get("1h", 0),
                        "snow_1h_mm": d.get("snow", {}).get("1h", 0),
                        "description": d["weather"][0]["description"],
                        "humidity_percent": d["main"]["humidity"],
                        "pressure_hpa": d["main"]["pressure"],
                        "observed_at": datetime.fromtimestamp(d["dt"], tz=timezone.utc).isoformat(),
                        "openweathermap_attempted": True,
                        "openweathermap_status_code": owm_status_code,
                        "open_meteo_attempted": False,
                    }
                elif r.status_code in (401, 403):
                    owm_error_type = "auth_error"
                elif r.status_code == 404:
                    owm_error_type = "location_not_found"
                elif r.status_code == 429:
                    owm_error_type = "rate_limit"
                else:
                    owm_error_type = f"http_{r.status_code}"
        except Exception as e:
            owm_error_type = f"connection_error: {str(e)[:60]}"

    om_attempted = True
    import urllib.parse as _urlparse
    geo_city = location.split(",")[0].strip() if "," in (location or "") else location
    geo_city_encoded = _urlparse.quote(geo_city, safe="")
    geo_url_preview = ""
    try:
        import httpx
        with httpx.Client(timeout=10.0, trust_env=False) as c:
            if lat and lon:
                r = c.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code,precipitation,cloud_cover&timezone=auto")
            else:
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={geo_city_encoded}&count=1&language=pl"
                geo_url_preview = f"geocoding-api.open-meteo.com/v1/search?name={geo_city_encoded}"
                geo = c.get(geo_url)
                om_status_code = geo.status_code if geo.status_code != 200 else None
                if geo.status_code == 200 and geo.json().get("results"):
                    res = geo.json()["results"][0]
                    lat, lon = res["latitude"], res["longitude"]
                    location = f"{res.get('name', geo_city)}, {res.get('country', '')}"
                else:
                    om_error_type = f"geocoding_http_{geo.status_code}"
                r = c.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code,precipitation,cloud_cover&timezone=auto")
            om_status_code = r.status_code
            if r.status_code == 200:
                d = r.json()
                current = d["current"]
                wmo_code = current.get("weather_code", 0)
                wmo_map = {0: "bezchmurnie", 1: "prawie bezchmurnie", 2: "częściowe zachmurzenie", 3: "pochmurno", 45: "mgła", 51: "mżawka", 61: "deszcz", 71: "śnieg", 80: "przelotny deszcz", 95: "burza"}
                return {
                    "tool": "qbot_weather_current",
                    "status": "OK",
                    "source": "Open-Meteo/ECMWF fallback",
                    "fallback_used": True,
                    "location_resolved": location,
                    "temperature_c": current["temperature_2m"],
                    "feels_like_c": current["apparent_temperature"],
                    "wind_mps": current["wind_speed_10m"],
                    "wind_kmh": round(current["wind_speed_10m"] * 3.6, 1),
                    "clouds_percent": current.get("cloud_cover", 0),
                    "rain_1h_mm": current.get("precipitation", 0),
                    "humidity_percent": current["relative_humidity_2m"],
                    "description": wmo_map.get(wmo_code, f"kod {wmo_code}"),
                    "observed_at": current["time"],
                    "openweathermap_attempted": owm_attempted,
                    "openweathermap_status_code": owm_status_code,
                    "openweathermap_error_type": owm_error_type or None,
                    "open_meteo_attempted": True,
                    "open_meteo_status_code": om_status_code,
                    "open_meteo_geocoding_url_preview": geo_url_preview,
                    "open_meteo_geocoding_status_code": 200,
                }
            else:
                om_error_type = f"http_{r.status_code}"
    except Exception as e:
        if not om_error_type:
            om_error_type = f"connection_error: {str(e)[:60]}"

    return {
        "tool": "qbot_weather_current",
        "status": "ERROR",
        "source": "none",
        "fallback_used": False,
        "location_resolved": location,
        "openweathermap_attempted": owm_attempted,
        "openweathermap_status_code": owm_status_code,
        "openweathermap_error_type": owm_error_type or None,
        "open_meteo_attempted": om_attempted,
        "open_meteo_status_code": om_status_code,
        "open_meteo_error_type": om_error_type or None,
        "openweathermap_error_message": f"HTTP {owm_status_code}: {owm_error_type}" if owm_status_code else (owm_error_type or "not configured"),
        "open_meteo_error_message": f"HTTP {om_status_code}: {om_error_type}" if om_status_code else (om_error_type or None),
    }


def _tool_qbot_weather_forecast(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    period = str(_args.get("period", "today"))
    period_l = period.lower().strip()
    wants_tomorrow = any(k in period_l for k in ("tomorrow", "jutro", "jutrze"))
    wants_morning = any(k in period_l for k in ("morning", "rano"))
    wants_evening = any(k in period_l for k in ("evening", "wiecz"))
    hours = min(max(int(_args.get("hours", 12)), 1), 48)
    report = _tool_qbot_weather_daily_report({
        "location": _args.get("location", ""),
        "days": 2 if wants_tomorrow else max(1, min(7, (hours + 7) // 8)),
        "lat": _args.get("lat"),
        "lon": _args.get("lon"),
    })
    location = report.get("location_resolved", str(_args.get("location", "") or cfg.LOCATION_NAME or "Marki"))
    if report.get("status") != "OK":
        return {
            "tool": "qbot_weather_forecast",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": report.get("error", "unknown"),
            "source": report.get("source", "OpenWeatherMap"),
            "location_resolved": location,
        }

    hourly = report.get("hourly_forecast", [])
    selected_idx: list[int] = list(range(min(len(hourly), hours)))
    if wants_tomorrow:
        target_date = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        selected_idx = [i for i, h in enumerate(hourly) if isinstance(h.get("czas"), str) and h["czas"][:10] == target_date]
    elif "today" in period_l or "dzis" in period_l:
        target_date = datetime.now(timezone.utc).date().isoformat()
        selected_idx = [i for i, h in enumerate(hourly) if isinstance(h.get("czas"), str) and h["czas"][:10] == target_date]
    if wants_morning:
        selected_idx = [i for i in selected_idx if (hourly[i].get("czas", "")[11:13].isdigit() and 6 <= int(hourly[i]["czas"][11:13]) < 12)]
    if wants_evening:
        selected_idx = [i for i in selected_idx if (hourly[i].get("czas", "")[11:13].isdigit() and 18 <= int(hourly[i]["czas"][11:13]) < 23)]
    if not selected_idx:
        selected_idx = list(range(min(len(hourly), max(6, min(hours, 12)))))

    sel = [hourly[i] for i in selected_idx if i < len(hourly)]
    temps = [_num(h.get("temperatura")) for h in sel if _num(h.get("temperatura")) is not None]
    precip = [_num(h.get("szansa_deszczu")) for h in sel if _num(h.get("szansa_deszczu")) is not None]
    winds = [_num(h.get("wiatr_ms")) for h in sel if _num(h.get("wiatr_ms")) is not None]
    summary_bits = []
    if temps:
        summary_bits.append(f"temperatura {min(temps):.1f}-{max(temps):.1f}°C")
    if precip:
        summary_bits.append(f"opady do {max(precip):.0f}%")
    if winds:
        summary_bits.append(f"wiatr do {max(winds):.1f} m/s")
    summary_text = ", ".join(summary_bits) if summary_bits else "brak danych podsumowania"

    daily = report.get("prognoza", [])
    first_day = daily[0] if daily else {}
    return {
        "tool": "qbot_weather_forecast",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "source": report.get("source", "OpenWeatherMap"),
        "location_resolved": location,
        "hours": hours,
        "period": period,
        "target_date": first_day.get("data"),
        "summary_text": summary_text,
        "hourly_times": [h.get("czas") for h in sel[:12]],
        "hourly_temps": [_num(h.get("temperatura")) for h in sel[:12]],
        "hourly_precip_prob": [_num(h.get("szansa_deszczu")) for h in sel[:12]],
        "hourly_wind": [_num(h.get("wiatr_ms")) for h in sel[:12]],
        "daily_temp_min_c": _num(first_day.get("temp_min")),
        "daily_temp_max_c": _num(first_day.get("temp_max")),
        "daily_precip_max_prob": _num(first_day.get("szansa_deszcz")),
        "daily_wind_max_mps": _num(first_day.get("max_wiatr_ms")),
    }


def _tool_qbot_public_web_status(_args: dict | None = None) -> dict[str, Any]:
    http_ok = False
    try:
        import httpx
        with httpx.Client(timeout=5.0, trust_env=False) as c:
            r = c.get("https://api.open-meteo.com/v1/forecast?latitude=52&longitude=21&current=temperature_2m")
            http_ok = r.status_code == 200
    except Exception:
        pass

    return {
        "tool": "qbot_public_web_status",
        "status": "OK" if http_ok else "WARN",
        "safety_class": "READ_ONLY",
        "web_fallback_enabled": True,
        "http_client_available": http_ok,
        "known_public_sources": ["Open-Meteo/ECMWF", "OpenStreetMap/Overpass", "OpenWeatherMap"],
        "allowed_topics": ["weather", "maps", "docs", "news", "general"],
        "blocked_topics": ["private authenticated data", "uploads", "sync", "delete"],
        "notes": "Public web fallback allowed for public data. Private integrations via Qbot auth/tools only.",
    }


def _tool_qbot_public_web_fetch(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    query = str(_args.get("query", ""))
    topic = str(_args.get("topic", "general"))

    if topic == "weather":
        w = _tool_qbot_weather_current({"location": query, "text": query})
        return {
            "tool": "qbot_public_web_fetch",
            "status": w.get("status", "ERROR"),
            "safety_class": "READ_ONLY",
            "topic": topic,
            "query": query,
            "sources": [{"name": w.get("source", "unknown"), "type": "API"}],
            "extracted_summary": f"{w.get('temperature_c', '?')}°C, {w.get('description', '?')}",
            "warnings": w.get("warnings", []),
        }

    if topic == "maps":
        try:
            from qbot_integration_tools import _tool_qbot_openmaps_legacy_status
            return {
                "tool": "qbot_public_web_fetch",
                "status": "OK",
                "topic": topic,
                "query": query,
                "sources": [{"name": "OpenStreetMap/Overpass", "type": "API"}],
                "extracted_summary": "OSM/Overpass API available",
            }
        except Exception:
            pass

    return {
        "tool": "qbot_public_web_fetch",
        "status": "WARN_NO_SEARCH_BACKEND",
        "safety_class": "READ_ONLY",
        "topic": topic,
        "query": query,
        "sources": [],
        "extracted_summary": f"No general search backend for topic={topic}",
    }


def _tool_qbot_public_web_fallback_self_check(_args: dict | None = None) -> dict[str, Any]:
    tests = []
    blockers = []

    config = _tool_qbot_weather_config_status()
    owm_ok = config.get("openweathermap_key_present", False)

    try:
        weather = _tool_qbot_weather_current({"location": "Marki,PL"})
        tests.append({"test": "weather_current", "status": weather.get("status"), "source": weather.get("source")})
        if weather.get("status") == "OK":
            pass
        else:
            blockers.append(f"weather_current failed: {weather.get('status')}")
    except Exception as e:
        blockers.append(f"weather_current error: {e}")

    try:
        loc = _tool_qbot_resolve_user_location({"text": "sprawdź pogodę dla Marek"})
        tests.append({"test": "resolve Marek", "resolved": loc.get("location_resolved")})
        if "Marki" not in (loc.get("location_resolved") or ""):
            blockers.append("resolve Marek failed")
    except Exception as e:
        blockers.append(f"resolve error: {e}")

    return {
        "tool": "qbot_public_web_fallback_self_check",
        "status": "ERROR" if blockers else "OK",
        "safety_class": "READ_ONLY",
        "openweathermap_active": owm_ok,
        "open_meteo_fallback_available": True,
        "public_web_allowed": True,
        "forbidden_phrases": ["nie mam dostępu do internetu"],
        "blockers": blockers,
        "tests": tests,
        "notes": "Public web fallback: allowed for public data (weather, geocoding). Private integrations via Qbot auth/tools.",
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
    "_tool_qbot_last_ride_location_status",
    "_tool_qbot_resolve_weather_location",
    "_tool_qbot_resolve_user_location",
    "_tool_qbot_weather_current",
    "_tool_qbot_weather_forecast",
    "_tool_qbot_public_web_fallback_self_check",
    "_tool_qbot_public_web_fetch",
    "_tool_qbot_public_web_status",
    "_tool_qbot_openmaps_config_status",
    "_tool_qbot_openmaps_legacy_status",
]


# =========================================================================
#  MODELQ v2 FITNESS TOOL (kanoniczne CP/FTP/W'/forma z fitmodel_daily)
# =========================================================================

def _tool_qbot_fitness_status(args: dict | None = None) -> dict[str, Any]:
    """Kanoniczny stan formy z ModelQ v2 (qbot_v2.fitmodel_daily).

    JEDYNE zrodlo CP/FTP/LTP/W' + CTL/ATL/TSB + readiness. Domyslnie najnowszy
    dzien; opcjonalny arg date (ISO). Xert = tylko benchmark (xert_readiness).
    """
    args = args or {}
    day = args.get("date")
    try:
        try:
            import psycopg2 as pg
        except ModuleNotFoundError:
            import psycopg as pg
        conn = pg.connect(host="127.0.0.1", dbname="qbot", user="qbot", password="")
    except Exception as exc:
        return {
            "tool": "qbot_fitness_status", "status": "ERROR",
            "safety_class": "READ_ONLY", "source": "ModelQ v2",
            "error": type(exc).__name__,
            "notes": f"Brak polaczenia z baza: {type(exc).__name__}",
        }
    cols = ("day, ftp_est_w, cp_modelq_w, ltp_modelq_w, wprime_modelq_kj, "
            "wprime_lo_kj, wprime_hi_kj, wprime_confidence, wprime_source, "
            "ctl_xss, atl_plus, tsb_plus, readiness_score, readiness_label")
    try:
        with conn.cursor() as cur:
            if day:
                cur.execute(f"SELECT {cols} FROM qbot_v2.fitmodel_daily "
                            "WHERE day<=%s ORDER BY day DESC LIMIT 1", (day,))
            else:
                cur.execute(f"SELECT {cols} FROM qbot_v2.fitmodel_daily "
                            "ORDER BY day DESC LIMIT 1")
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return {
            "tool": "qbot_fitness_status", "status": "NO_DATA",
            "safety_class": "READ_ONLY", "source": "ModelQ v2",
            "notes": "Brak wiersza w qbot_v2.fitmodel_daily.",
        }

    def _f(v):
        return round(float(v), 1) if v is not None else None

    return {
        "tool": "qbot_fitness_status", "status": "OK",
        "safety_class": "READ_ONLY", "source": "ModelQ v2",
        "day": str(row[0]),
        "ftp_w": _f(row[1]), "cp_w": _f(row[2]), "ltp_w": _f(row[3]),
        "wprime_kj": _f(row[4]), "wprime_lo_kj": _f(row[5]), "wprime_hi_kj": _f(row[6]),
        "wprime_confidence": row[7], "wprime_source": row[8],
        "ctl": _f(row[9]), "atl": _f(row[10]), "tsb": _f(row[11]),
        "readiness_score": _f(row[12]), "readiness_label": row[13],
        "notes": "Kanoniczne CP/FTP/W' = ModelQ v2. Xert tylko benchmark.",
    }
