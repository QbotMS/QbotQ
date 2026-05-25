"""QBot report tools — daily report and ride report status/preview/send.

Read-only tools for status, config, preview, and restore planning.
Send operations default dry_run=true. Max 1 test message. No email without confirmed SMTP.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path("/opt/qbot/app")
_OUTGOING = _PROJECT_ROOT / "outgoing"
_DATA = _PROJECT_ROOT / "data"

SENT_FILE = _DATA / "daily_report_sent.json"
EXTERNAL_CACHE_FILE = _DATA / "daily_external_cache.json"
REPORTED_FILE = _DATA / "reported_activities.json"
WEEKLY_SENT_FILE = _DATA / "weekly_review_sent.json"
PREVIEW_DIR = _OUTGOING / "ride_report_previews"

MAX_PREVIEW_BYTES = 5000
MAX_SAFE_BYTES = 10000


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


def _load_json_safe(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _truncate_text(text: str, max_bytes: int = MAX_PREVIEW_BYTES) -> str:
    if not text:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated + "\n\n[... truncated]"


def _report_env_status() -> dict[str, Any]:
    names = [
        "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID",
        "GMAIL_USER", "GMAIL_APP_PASSWORD", "EMAIL_TO",
        "INTERVALS_ATHLETE_ID", "INTERVALS_API_KEY",
        "LOCATION_LAT", "LOCATION_LON", "LOCATION_NAME",
        "MCP_URL", "QGPT_API_KEY",
    ]
    presence = _env_presence(names)
    telegram_ok = presence.get("TELEGRAM_TOKEN") and presence.get("TELEGRAM_CHAT_ID")
    email_ok = (
        presence.get("GMAIL_USER")
        and presence.get("GMAIL_APP_PASSWORD")
        and presence.get("EMAIL_TO")
    )
    intervals_ok = presence.get("INTERVALS_ATHLETE_ID") and presence.get("INTERVALS_API_KEY")

    return {
        "telegram_configured": bool(telegram_ok),
        "email_configured": bool(email_ok),
        "intervals_configured": bool(intervals_ok),
        "smpt_requires_app_password": bool(presence.get("GMAIL_APP_PASSWORD")),
        "env_presence": presence,
        "missing": [n for n, p in presence.items() if not p],
    }


# ═══════════════════════════════════════════════════════════════════════
#  DAILY REPORT TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_daily_report_status(_args: dict | None = None) -> dict[str, Any]:
    """Check daily report infrastructure: data files, last sent date, channels configured."""
    env = _report_env_status()

    sent_exists = SENT_FILE.exists()
    cache_exists = EXTERNAL_CACHE_FILE.exists()

    sent_state: dict[str, Any] = {}
    if sent_exists:
        sent_state = _load_json_safe(SENT_FILE, {}) or {}

    cache_state: dict[str, Any] = {}
    cache_size = 0
    if cache_exists:
        try:
            cache_size = EXTERNAL_CACHE_FILE.stat().st_size
            cache_state = _load_json_safe(EXTERNAL_CACHE_FILE, {}) or {}
        except OSError:
            pass

    last_sent_date = sent_state.get("date") if isinstance(sent_state, dict) else None
    channels = sent_state.get("channels") if isinstance(sent_state, dict) else {}
    already_sent_today = last_sent_date == date.today().isoformat()

    cache_keys = list(cache_state.keys())[:15] if isinstance(cache_state, dict) else []
    cache_entry_count = len(cache_state) if isinstance(cache_state, dict) else 0

    report_deps_ok = (
        (_PROJECT_ROOT / "daily_report.py").exists()
        and (_PROJECT_ROOT / "qbot_report_status.py").exists()
        and (_PROJECT_ROOT / "qbot_readiness.py").exists()
        and (_PROJECT_ROOT / "qbot_coach.py").exists()
    )

    if env.get("telegram_configured") and env.get("intervals_configured"):
        status = "OK"
        notes = "Daily report infrastructure ready."
    elif env.get("telegram_configured") or env.get("intervals_configured"):
        status = "WARN"
        notes = "Partial daily report config — some channels or API credentials missing."
    else:
        status = "ERROR"
        notes = "No daily report channels or Intervals API configured."

    return {
        "tool": "qbot_daily_report_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "sent_file_exists": sent_exists,
        "sent_file_path": str(SENT_FILE.relative_to(_PROJECT_ROOT)) if sent_exists else None,
        "external_cache_exists": cache_exists,
        "external_cache_path": str(EXTERNAL_CACHE_FILE.relative_to(_PROJECT_ROOT)) if cache_exists else None,
        "external_cache_size_bytes": cache_size,
        "external_cache_entry_count": cache_entry_count,
        "external_cache_keys": cache_keys,
        "last_sent_date": last_sent_date,
        "already_sent_today": already_sent_today,
        "channels": channels,
        "telegram_configured": env.get("telegram_configured"),
        "email_configured": env.get("email_configured"),
        "intervals_configured": env.get("intervals_configured"),
        "report_deps_ok": report_deps_ok,
        "notes": notes,
    }


def _tool_qbot_daily_report_preview(_args: dict | None = None) -> dict[str, Any]:
    """Read and summarize latest daily report data: weather cache, Xert cache, activities summary.
    Does NOT generate a new report — only previews cached data.
    """
    env = _report_env_status()

    weather_data: dict[str, Any] = {}
    xert_data: dict[str, Any] = {}
    cache_summary: list[dict[str, Any]] = []

    if EXTERNAL_CACHE_FILE.exists():
        try:
            cache = _load_json_safe(EXTERNAL_CACHE_FILE, {}) or {}
            if isinstance(cache, dict):
                for key, value in cache.items():
                    entry: dict[str, Any] = {"key": key}
                    if isinstance(value, dict):
                        if value.get("cache_hit"):
                            entry["source"] = "cache"
                            entry["cached_at"] = value.get("cached_at")
                        elif value.get("error"):
                            entry["source"] = "error"
                            entry["error"] = str(value.get("error"))[:200]
                        else:
                            entry["source"] = "live"
                        entry["keys"] = [k for k in value.keys() if k not in ("cache_hit", "cache_reason", "cached_at")][:10]
                    else:
                        entry["source"] = "unknown"
                        entry["type"] = type(value).__name__
                    cache_summary.append(entry)
        except Exception as exc:
            cache_summary = [{"error": f"Failed to parse cache: {exc}"}]

    if EXTERNAL_CACHE_FILE.exists():
        cache = _load_json_safe(EXTERNAL_CACHE_FILE, {}) or {}
        if isinstance(cache, dict):
            weather_raw = cache.get("weather") or cache.get(str(cfg_get("LOCATION_NAME", "Warszawa"))) or {}
            if isinstance(weather_raw, dict) and "daily" in weather_raw:
                weather_data = weather_raw
            xert_raw = cache.get("xert_status") or {}
            if isinstance(xert_raw, dict) and "tp_ftp_watts" in xert_raw:
                xert_data = xert_raw

    sent_state = _load_json_safe(SENT_FILE, {}) or {} if SENT_FILE.exists() else {}
    today_sent = sent_state.get("date") == date.today().isoformat() if isinstance(sent_state, dict) else False

    can_generate = env.get("telegram_configured") and env.get("intervals_configured") and not today_sent

    return {
        "tool": "qbot_daily_report_preview",
        "status": "OK" if env.get("telegram_configured") else "WARN",
        "safety_class": "READ_ONLY",
        "weather_cache_available": bool(weather_data),
        "weather_keys": list(weather_data.keys())[:10] if weather_data else [],
        "xert_cache_available": bool(xert_data),
        "xert_tp_watts": xert_data.get("tp_ftp_watts") if xert_data else None,
        "xert_form_status": (xert_data.get("forma") or {}).get("status") if xert_data else None,
        "cache_summary": cache_summary,
        "today_sent": today_sent,
        "can_generate": can_generate,
        "telegram_configured": env.get("telegram_configured"),
        "email_configured": env.get("email_configured"),
        "notes": (
            "Cache data available for preview."
            if cache_summary else
            "No cache data found. Daily report has not been generated yet, or cache file is empty."
        ),
    }


def _tool_qbot_daily_report_send(_args: dict | None = None) -> dict[str, Any]:
    """Trigger daily report generation and sending.

    Args:
        dry_run: bool (default True) — when False, imports daily_report.py and sends.
        channel: str — "telegram", "email", or "auto" (both).

    Safety: dry_run true by default. Max 1 test message. No email without confirmed SMTP.
    """
    _args = _args or {}
    dry_run = bool(_args.get("dry_run", True))
    channel = str(_args.get("channel", "telegram")).lower()

    allowed_channels = {"telegram", "email", "auto"}
    if channel not in allowed_channels:
        return {
            "tool": "qbot_daily_report_send",
            "status": "BLOCKED_INVALID_CHANNEL",
            "safety_class": "WRITE_SAFE",
            "channel": channel,
            "allowed_channels": sorted(allowed_channels),
            "notes": f"Channel '{channel}' not in allowlist.",
        }

    env = _report_env_status()
    missing = env.get("missing", [])

    if not env.get("telegram_configured") and not env.get("email_configured"):
        return {
            "tool": "qbot_daily_report_send",
            "status": "BLOCKED_NO_CHANNELS",
            "safety_class": "WRITE_SAFE",
            "dry_run": dry_run,
            "channel": channel,
            "missing_config": missing,
            "notes": "No Telegram or Email channels configured.",
        }

    if not env.get("intervals_configured"):
        return {
            "tool": "qbot_daily_report_send",
            "status": "BLOCKED_NO_API",
            "safety_class": "WRITE_SAFE",
            "dry_run": dry_run,
            "channel": channel,
            "missing_config": missing,
            "notes": "Intervals.icu API not configured.",
        }

    sent_state = _load_json_safe(SENT_FILE, {}) or {} if SENT_FILE.exists() else {}
    today_sent = sent_state.get("date") == date.today().isoformat() if isinstance(sent_state, dict) else False
    channels_sent = sent_state.get("channels", {}) if isinstance(sent_state, dict) else {}

    if channel == "telegram" and channels_sent.get("telegram") == "sent":
        return {
            "tool": "qbot_daily_report_send",
            "status": "ALREADY_SENT",
            "safety_class": "WRITE_SAFE",
            "dry_run": dry_run,
            "channel": channel,
            "already_sent_today": True,
            "channels": channels_sent,
            "notes": "Telegram report already sent today.",
        }

    if channel == "email" and channels_sent.get("email") == "sent":
        return {
            "tool": "qbot_daily_report_send",
            "status": "ALREADY_SENT",
            "safety_class": "WRITE_SAFE",
            "dry_run": dry_run,
            "channel": channel,
            "already_sent_today": True,
            "channels": channels_sent,
            "notes": "Email report already sent today.",
        }

    channels_selected = []
    if channel in ("telegram", "auto"):
        if env.get("telegram_configured"):
            channels_selected.append("telegram")
    if channel in ("email", "auto"):
        if env.get("email_configured"):
            channels_selected.append("email")

    if not channels_selected:
        return {
            "tool": "qbot_daily_report_send",
            "status": "BLOCKED_CHANNEL_NOT_CONFIGURED",
            "safety_class": "WRITE_SAFE",
            "dry_run": dry_run,
            "channel": channel,
            "notes": f"Channel '{channel}' selected but not configured.",
        }

    if dry_run:
        preview_data = _tool_qbot_daily_report_preview()
        return {
            "tool": "qbot_daily_report_send",
            "status": "DRY_RUN",
            "safety_class": "WRITE_SAFE",
            "dry_run": True,
            "channel": channel,
            "channels_selected": channels_selected,
            "would_send_to": channels_selected,
            "telegram_configured": env.get("telegram_configured"),
            "email_configured": env.get("email_configured"),
            "today_sent": today_sent,
            "preview_cache_available": preview_data.get("weather_cache_available", False),
            "notes": (
                "Dry-run only. Set dry_run=false to generate and send the daily report. "
                "Max 1 test message per channel."
            ),
        }

    # Live send — run daily_report.py as subprocess
    daily_report_py = _PROJECT_ROOT / "daily_report.py"
    if not daily_report_py.exists():
        return {
            "tool": "qbot_daily_report_send",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "dry_run": False,
            "error": "daily_report.py not found",
            "notes": "daily_report.py missing from project root.",
        }

    venv_python = _PROJECT_ROOT / ".venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else "python3"

    try:
        result = subprocess.run(
            [python_bin, str(daily_report_py)],
            capture_output=True, text=True, timeout=120,
            cwd=str(_PROJECT_ROOT),
            env={**os.environ, "PYTHONPATH": str(_PROJECT_ROOT)},
        )
        stdout = result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout
        stderr = result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr
        ok = result.returncode == 0
    except subprocess.TimeoutExpired:
        return {
            "tool": "qbot_daily_report_send",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "dry_run": False,
            "error": "daily_report.py timed out after 120s",
            "notes": "Daily report generation timed out.",
        }
    except Exception as exc:
        return {
            "tool": "qbot_daily_report_send",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "dry_run": False,
            "error": str(exc),
            "notes": f"Failed to run daily_report.py: {exc}",
        }

    # re-read sent state after the run
    new_state = _load_json_safe(SENT_FILE, {}) or {} if SENT_FILE.exists() else {}
    new_channels = new_state.get("channels", {}) if isinstance(new_state, dict) else {}

    return {
        "tool": "qbot_daily_report_send",
        "status": "OK" if ok else "ERROR",
        "safety_class": "WRITE_SAFE",
        "dry_run": False,
        "channel": channel,
        "exit_code": result.returncode if not ok else 0,
        "channels_sent": new_channels,
        "stdout_tail": _truncate_text(stdout, 3000),
        "stderr_tail": _truncate_text(stderr, 1000) if stderr else None,
        "notes": "Daily report executed via subprocess." if ok else f"Daily report failed with exit code {result.returncode}.",
    }


# ═══════════════════════════════════════════════════════════════════════
#  RIDE REPORT TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_ride_report_status(_args: dict | None = None) -> dict[str, Any]:
    """Check ride report infrastructure: reported activities, preview HTML files, last activity."""
    env = _report_env_status()

    reported_exists = REPORTED_FILE.exists()
    reported: dict[str, Any] = {}
    reported_count = 0
    last_reported_id = None
    last_reported_name = None
    last_reported_date = None
    last_reported_status = None
    reported_entries: list[dict[str, Any]] = []

    if reported_exists:
        reported = _load_json_safe(REPORTED_FILE, {}) or {}
        if isinstance(reported, dict):
            reported_count = len(reported)
            sorted_items = sorted(reported.items(), key=lambda x: str(x[0]), reverse=True)
            reported_entries = [
                {"activity_id": aid, **({"status": v.get("status"), "name": v.get("name"), "date": v.get("date")} if isinstance(v, dict) else {"value": str(v)[:100]})}
                for aid, v in sorted_items[:20]
            ]
            for aid, v in sorted_items:
                if isinstance(v, dict) and v.get("status") in ("sent", "in_progress"):
                    last_reported_id = aid
                    last_reported_name = v.get("name")
                    last_reported_date = v.get("date")
                    last_reported_status = v.get("status")
                    break

    preview_files = _list_glob_files(PREVIEW_DIR, "*.html", max_files=20) if PREVIEW_DIR.exists() else []
    preview_count = len(preview_files)
    latest_preview = preview_files[0] if preview_files else None

    report_deps_ok = (
        (_PROJECT_ROOT / "ride_report.py").exists()
        and (_PROJECT_ROOT / "qbot_report_status.py").exists()
        and (_PROJECT_ROOT / "qbot_mcp_client.py").exists()
    )

    if env.get("telegram_configured") and env.get("intervals_configured"):
        status = "OK"
        notes = "Ride report infrastructure ready."
    elif env.get("telegram_configured") or env.get("intervals_configured"):
        status = "WARN"
        notes = "Partial ride report config."
    else:
        status = "ERROR"
        notes = "No ride report channels or Intervals API configured."

    return {
        "tool": "qbot_ride_report_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "reported_file_exists": reported_exists,
        "reported_file_path": str(REPORTED_FILE.relative_to(_PROJECT_ROOT)) if reported_exists else None,
        "reported_count": reported_count,
        "last_reported_activity_id": last_reported_id,
        "last_reported_activity_name": last_reported_name,
        "last_reported_date": last_reported_date,
        "last_reported_status": last_reported_status,
        "reported_entries": reported_entries[:10],
        "preview_dir": str(PREVIEW_DIR.relative_to(_PROJECT_ROOT)) if PREVIEW_DIR.exists() else None,
        "preview_count": preview_count,
        "latest_preview": latest_preview,
        "preview_files": [f["name"] for f in preview_files[:10]],
        "telegram_configured": env.get("telegram_configured"),
        "email_configured": env.get("email_configured"),
        "report_deps_ok": report_deps_ok,
        "notes": notes,
    }


def _tool_qbot_ride_report_latest(_args: dict | None = None) -> dict[str, Any]:
    """Show latest ride report HTML preview (truncated to safe length).

    Args:
        max_bytes: int (default 5000) — max bytes of HTML to return.
    """
    _args = _args or {}
    max_bytes = min(max(int(_args.get("max_bytes", MAX_PREVIEW_BYTES)), 100), 50000)

    if not PREVIEW_DIR.exists():
        return {
            "tool": "qbot_ride_report_latest",
            "status": "WARN",
            "safety_class": "READ_ONLY",
            "html_preview": None,
            "html_bytes": 0,
            "preview_file": None,
            "notes": "No ride report previews directory.",
        }

    html_files = sorted(PREVIEW_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not html_files:
        return {
            "tool": "qbot_ride_report_latest",
            "status": "WARN",
            "safety_class": "READ_ONLY",
            "html_preview": None,
            "html_bytes": 0,
            "preview_file": None,
            "notes": "No HTML preview files found.",
        }

    latest = html_files[0]
    try:
        raw = latest.read_text(encoding="utf-8", errors="ignore")
        size = len(raw.encode("utf-8"))
        preview = _truncate_text(raw, max_bytes)
    except Exception as exc:
        return {
            "tool": "qbot_ride_report_latest",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "preview_file": str(latest.relative_to(_PROJECT_ROOT)),
            "error": str(exc),
            "notes": "Failed to read preview file.",
        }

    return {
        "tool": "qbot_ride_report_latest",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "preview_file": str(latest.relative_to(_PROJECT_ROOT)),
        "file_size_bytes": latest.stat().st_size,
        "html_bytes": size,
        "html_preview": preview,
        "truncated": size > max_bytes,
        "mtime": datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat(),
        "notes": f"Latest ride report preview ({size} bytes)." + (" Truncated." if size > max_bytes else ""),
    }


def _tool_qbot_ride_report_preview(_args: dict | None = None) -> dict[str, Any]:
    """Show what would be in the next ride report: latest activity in Intervals, Xert status, weather.
    Read-only, does not generate or send.
    Uses ride_report module for data fetching (local import, no extra deps).
    """
    env = _report_env_status()

    if not env.get("intervals_configured"):
        return {
            "tool": "qbot_ride_report_preview",
            "status": "BLOCKED_NO_API",
            "safety_class": "READ_ONLY",
            "notes": "Intervals.icu API not configured. Cannot fetch activity data.",
        }

    _PROJECT_STR = str(_PROJECT_ROOT)
    try:
        import sys as _sys
        if _PROJECT_STR not in _sys.path:
            _sys.path.insert(0, _PROJECT_STR)
        import ride_report as _rr
    except ImportError:
        _rr = None

    today = date.today()
    latest_activity: dict[str, Any] = {}
    recent_activities_summary: list[dict[str, Any]] = []

    if _rr is not None:
        try:
            acts = _rr.icu_get(
                f"/athlete/{_rr.ATHLETE_ID}/activities",
                {"oldest": (today - timedelta(days=3)).isoformat(), "newest": today.isoformat(), "limit": 10},
            )
            if isinstance(acts, list):
                for a in acts:
                    recent_activities_summary.append({
                        "id": a.get("id"),
                        "name": a.get("name"),
                        "type": a.get("type"),
                        "date": str(a.get("start_date_local", ""))[:10],
                        "distance_m": a.get("distance"),
                    })
                    if not latest_activity and a.get("type") in ("Ride", "VirtualRide"):
                        latest_activity = a
        except Exception as exc:
            return {
                "tool": "qbot_ride_report_preview",
                "status": "ERROR",
                "safety_class": "READ_ONLY",
                "error": str(exc),
                "notes": f"Failed to fetch activities from Intervals.icu: {exc}",
            }
    else:
        # Fallback: use local data when ride_report not importable
        if REPORTED_FILE.exists():
            reported_map = _load_json_safe(REPORTED_FILE, {}) or {}
            if isinstance(reported_map, dict):
                for aid, v in sorted(reported_map.items(), key=lambda x: str(x[0]), reverse=True):
                    if isinstance(v, dict):
                        recent_activities_summary.append({
                            "id": aid,
                            "name": v.get("name", "?"),
                            "status": v.get("status"),
                            "date": v.get("date"),
                        })
        if PREVIEW_DIR.exists():
            for pf in sorted(PREVIEW_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
                aid_from_filename = pf.stem.lstrip("i")
                recent_activities_summary.append({
                    "id": aid_from_filename,
                    "name": pf.name,
                    "status": "preview_saved",
                    "date": datetime.fromtimestamp(pf.stat().st_mtime, tz=timezone.utc).isoformat(),
                })
                break  # just the latest one

    has_activity = bool(latest_activity)

    xert_available = False
    xert_tp = None
    xert_form_status = None
    try:
        xert_data = _load_json_safe(EXTERNAL_CACHE_FILE, {}) or {}
        if isinstance(xert_data, dict):
            xert_raw = xert_data.get("xert_status", {})
            if isinstance(xert_raw, dict) and xert_raw.get("tp_ftp_watts"):
                xert_available = True
                xert_tp = xert_raw.get("tp_ftp_watts")
                xert_form_status = (xert_raw.get("forma") or {}).get("status")
    except Exception:
        pass

    weather_available = False
    weather_condition = None
    try:
        weather_data = _load_json_safe(EXTERNAL_CACHE_FILE, {}) or {}
        if isinstance(weather_data, dict):
            _w = weather_data.get("weather:Warszawa:2d") or weather_data.get("weather")
            if isinstance(_w, dict) and _w.get("prognoza"):
                _wd = (_w.get("prognoza") or [{}])[0] if _w.get("prognoza") else {}
                weather_available = True
                weather_condition = _wd.get("warunki") or (_w.get("teraz") or {}).get("warunki")
    except Exception:
        pass

    already = False
    if has_activity:
        reported_map = _load_json_safe(REPORTED_FILE, {}) or {}
        aid = str(latest_activity.get("id", ""))
        if isinstance(reported_map, dict) and aid in reported_map:
            entry = reported_map.get(aid, {})
            already = isinstance(entry, dict) and entry.get("status") in ("sent", "in_progress")

    data_source = "live_api" if _rr is not None else "local_artifacts"

    return {
        "tool": "qbot_ride_report_preview",
        "status": "OK" if has_activity else "WARN",
        "safety_class": "READ_ONLY",
        "data_source": data_source,
        "latest_activity": {
            "id": latest_activity.get("id"),
            "name": latest_activity.get("name"),
            "type": latest_activity.get("type"),
            "date": str(latest_activity.get("start_date_local", ""))[:10],
            "distance_m": latest_activity.get("distance"),
            "moving_time_s": latest_activity.get("moving_time"),
            "avg_watts": latest_activity.get("icu_average_watts") or latest_activity.get("avg_power"),
            "avg_hr": latest_activity.get("average_heartrate"),
        } if has_activity else None,
        "recent_activities_summary": recent_activities_summary,
        "xert_available": xert_available,
        "xert_tp_watts": xert_tp,
        "xert_form_status": xert_form_status,
        "weather_cache_available": weather_available,
        "weather_condition": weather_condition,
        "already_reported": already,
        "telegram_configured": env.get("telegram_configured"),
        "email_configured": env.get("email_configured"),
        "can_send": has_activity and env.get("telegram_configured") and not already,
        "notes": (
            "Latest ride activity available for reporting."
            if has_activity and not already else
            "Activity already reported."
            if already else
            "No recent ride activities found."
        ),
    }


def _tool_qbot_ride_report_send(_args: dict | None = None) -> dict[str, Any]:
    """Trigger ride report generation and sending.

    Args:
        dry_run: bool (default True) — when False, generates and sends ride report.
        activity_id: str — "latest" (default) or specific activity ID.

    Safety: dry_run true by default. No email without confirmed SMTP.
    """
    _args = _args or {}
    dry_run = bool(_args.get("dry_run", True))
    activity_id = str(_args.get("activity_id", "latest"))

    env = _report_env_status()

    if not env.get("telegram_configured") and not env.get("email_configured"):
        return {
            "tool": "qbot_ride_report_send",
            "status": "BLOCKED_NO_CHANNELS",
            "safety_class": "WRITE_SAFE",
            "dry_run": dry_run,
            "activity_id": activity_id,
            "missing_config": env.get("missing", []),
            "notes": "No Telegram or Email channels configured.",
        }

    if not env.get("intervals_configured"):
        return {
            "tool": "qbot_ride_report_send",
            "status": "BLOCKED_NO_API",
            "safety_class": "WRITE_SAFE",
            "dry_run": dry_run,
            "activity_id": activity_id,
            "notes": "Intervals.icu API not configured.",
        }

    if dry_run:
        preview = _tool_qbot_ride_report_preview()

        already_reported = preview.get("already_reported", False)

        return {
            "tool": "qbot_ride_report_send",
            "status": "DRY_RUN",
            "safety_class": "WRITE_SAFE",
            "dry_run": True,
            "activity_id": activity_id,
            "would_process": not already_reported,
            "latest_activity_id": preview.get("latest_activity", {}).get("id") if preview.get("latest_activity") else None,
            "latest_activity_name": preview.get("latest_activity", {}).get("name") if preview.get("latest_activity") else None,
            "already_reported": already_reported,
            "telegram_configured": env.get("telegram_configured"),
            "email_configured": env.get("email_configured"),
            "notes": (
                "Dry-run only. Set dry_run=false to generate and send the ride report."
                if not already_reported else
                "Latest activity already reported. Dry-run only."
            ),
        }

    # Live send — run ride_report.py as subprocess
    ride_report_py = _PROJECT_ROOT / "ride_report.py"
    if not ride_report_py.exists():
        return {
            "tool": "qbot_ride_report_send",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "dry_run": False,
            "error": "ride_report.py not found",
            "notes": "ride_report.py missing from project root.",
        }

    venv_python = _PROJECT_ROOT / ".venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else "python3"

    if activity_id == "latest":
        try:
            import sys as _sys
            if str(_PROJECT_ROOT) not in _sys.path:
                _sys.path.insert(0, str(_PROJECT_ROOT))
            import ride_report as _rr
            new_acts = _rr.check_new_activities()
            if not new_acts:
                return {
                    "tool": "qbot_ride_report_send",
                    "status": "WARN",
                    "safety_class": "WRITE_SAFE",
                    "dry_run": False,
                    "activity_id": "latest",
                    "notes": "No new ride activities found.",
                }
            activity_id = str(new_acts[0]["id"])
            activity_name = new_acts[0].get("name", "Trening")
        except ImportError:
            return {
                "tool": "qbot_ride_report_send",
                "status": "WARN",
                "safety_class": "WRITE_SAFE",
                "dry_run": False,
                "activity_id": "latest",
                "notes": "Cannot resolve latest activity: ride_report not importable.",
            }
        except Exception as exc:
            return {
                "tool": "qbot_ride_report_send",
                "status": "ERROR",
                "safety_class": "WRITE_SAFE",
                "dry_run": False,
                "error": str(exc),
                "notes": f"Failed to find latest activity: {exc}",
            }
    else:
        activity_name = "Trening"

    try:
        result = subprocess.run(
            [python_bin, str(ride_report_py), activity_id, activity_name],
            capture_output=True, text=True, timeout=180,
            cwd=str(_PROJECT_ROOT),
            env={**os.environ, "PYTHONPATH": str(_PROJECT_ROOT)},
        )
        stdout = result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout
        stderr = result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr
        ok = result.returncode == 0
    except subprocess.TimeoutExpired:
        return {
            "tool": "qbot_ride_report_send",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "dry_run": False,
            "error": "ride_report.py timed out after 180s",
            "notes": "Ride report generation timed out.",
        }
    except Exception as exc:
        return {
            "tool": "qbot_ride_report_send",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "dry_run": False,
            "error": str(exc),
            "notes": f"Failed to run ride_report.py: {exc}",
        }

    preview_html = ""
    safe_id = str(activity_id).replace("/", "_")
    preview_path = PREVIEW_DIR / f"{safe_id}.html"
    if preview_path.exists():
        try:
            preview_html = _truncate_text(preview_path.read_text(encoding="utf-8", errors="ignore"), 2000)
        except Exception:
            pass

    return {
        "tool": "qbot_ride_report_send",
        "status": "OK" if ok else "ERROR",
        "safety_class": "WRITE_SAFE",
        "dry_run": False,
        "activity_id": activity_id,
        "activity_name": activity_name,
        "exit_code": result.returncode if not ok else 0,
        "channels_sent": {"telegram": "sent" if ok else "failed", "email": "sent" if ok else "failed"},
        "preview_text": preview_html[:1000] if preview_html else None,
        "stdout_tail": _truncate_text(stdout, 3000),
        "stderr_tail": _truncate_text(stderr, 1000) if stderr else None,
        "notes": f"Ride report executed via subprocess for activity {activity_id}." if ok else f"Ride report failed with exit code {result.returncode}.",
    }


# ═══════════════════════════════════════════════════════════════════════
#  REPORTS SCHEDULE & RESTORE PLAN
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_reports_schedule_status(_args: dict | None = None) -> dict[str, Any]:
    """Show crontab entries for reports, last daily/ride report times, next scheduled times."""
    now = datetime.now(timezone.utc)

    report_crontab_entries: list[str] = []
    all_crontab_entries: list[str] = []
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    all_crontab_entries.append(stripped)
                    lower = stripped.lower()
                    if any(kw in lower for kw in ("daily_report", "ride_report", "weekly_review", "report")):
                        report_crontab_entries.append(stripped)
    except Exception:
        pass

    last_daily_sent: str | None = None
    last_daily_channels: dict[str, str] = {}
    if SENT_FILE.exists():
        sent_state = _load_json_safe(SENT_FILE, {}) or {}
        if isinstance(sent_state, dict):
            last_daily_sent = sent_state.get("date")
            last_daily_channels = sent_state.get("channels", {})

    last_ride_reported: str | None = None
    last_ride_name: str | None = None
    if REPORTED_FILE.exists():
        reported = _load_json_safe(REPORTED_FILE, {}) or {}
        if isinstance(reported, dict):
            for aid, v in sorted(reported.items(), key=lambda x: str(x[0]), reverse=True):
                if isinstance(v, dict) and v.get("status") in ("sent",):
                    last_ride_reported = aid
                    last_ride_name = v.get("name")
                    break

    last_weekly_sent: str | None = None
    if WEEKLY_SENT_FILE.exists():
        ws_data = _load_json_safe(WEEKLY_SENT_FILE, {}) or {}
        if isinstance(ws_data, dict):
            last_weekly_sent = max(ws_data.keys(), key=lambda k: ws_data[k].get("sent_at", "")) if ws_data else None

    has_cron_for_reports = len(report_crontab_entries) > 0

    return {
        "tool": "qbot_reports_schedule_status",
        "status": "OK" if has_cron_for_reports else "WARN",
        "safety_class": "READ_ONLY",
        "check_time_utc": now.isoformat(),
        "report_crontab_entries": report_crontab_entries,
        "report_crontab_count": len(report_crontab_entries),
        "all_crontab_count": len(all_crontab_entries),
        "last_daily_report_date": last_daily_sent,
        "last_daily_channels": last_daily_channels,
        "last_ride_report_activity": last_ride_reported,
        "last_ride_report_name": last_ride_name,
        "last_weekly_review_key": last_weekly_sent,
        "has_report_cron": has_cron_for_reports,
        "notes": (
            "Report crontab entries found."
            if has_cron_for_reports else
            "No report crontab entries detected. Reports may not be scheduled. "
            "Daily report typically fires hourly 6:00-9:00; ride report every 30 min."
        ),
    }


def _tool_qbot_reports_restore_plan(_args: dict | None = None) -> dict[str, Any]:
    """Comprehensive restore plan for the reports subsystem."""
    env = _report_env_status()

    daily_status = _tool_qbot_daily_report_status()
    ride_status = _tool_qbot_ride_report_status()
    schedule_status = _tool_qbot_reports_schedule_status()

    mission_critical = ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "INTERVALS_ATHLETE_ID", "INTERVALS_API_KEY"]
    nice_to_have = ["GMAIL_USER", "GMAIL_APP_PASSWORD", "EMAIL_TO", "LOCATION_LAT", "LOCATION_LON", "LOCATION_NAME"]

    missing_critical = [n for n in mission_critical if n in env.get("missing", [])]
    missing_nice = [n for n in nice_to_have if n in env.get("missing", [])]

    telegram_ok = env.get("telegram_configured", False)
    email_ok = env.get("email_configured", False)
    intervals_ok = env.get("intervals_configured", False)

    daily_deps_ok = daily_status.get("report_deps_ok", False)
    ride_deps_ok = ride_status.get("report_deps_ok", False)
    has_cron = schedule_status.get("has_report_cron", False)

    if telegram_ok and intervals_ok and daily_deps_ok and ride_deps_ok:
        plan_status = "RESTORED" if has_cron else "PARTIAL"
    elif telegram_ok and intervals_ok:
        plan_status = "PARTIAL"
    elif telegram_ok or intervals_ok:
        plan_status = "PARTIAL"
    else:
        plan_status = "MISSING"

    next_steps: list[str] = []
    if missing_critical:
        next_steps.append(f"Set critical env vars: {', '.join(missing_critical)}")
    if missing_nice:
        next_steps.append(f"Set optional env vars for email: {', '.join(missing_nice)}")
    if not has_cron:
        next_steps.append("Restore crontab entries for daily report (hourly 6-9) and ride report (every 30 min)")
    if not daily_deps_ok:
        next_steps.append("Verify daily_report.py and supporting modules exist")
    if not ride_deps_ok:
        next_steps.append("Verify ride_report.py and supporting modules exist")
    if telegram_ok and intervals_ok and not has_cron:
        next_steps.append("Run qbot_daily_report_send with dry_run=false for first test")
    if not next_steps:
        next_steps.append("All report subsystems are healthy. No action needed.")

    return {
        "tool": "qbot_reports_restore_plan",
        "status": plan_status,
        "safety_class": "READ_ONLY",
        "telegram_configured": telegram_ok,
        "email_configured": email_ok,
        "intervals_configured": intervals_ok,
        "missing_critical_env": missing_critical,
        "missing_optional_env": missing_nice,
        "daily_report": {
            "sent_file_exists": daily_status.get("sent_file_exists"),
            "cache_exists": daily_status.get("external_cache_exists"),
            "last_sent": daily_status.get("last_sent_date"),
            "deps_ok": daily_deps_ok,
        },
        "ride_report": {
            "reported_file_exists": ride_status.get("reported_file_exists"),
            "preview_count": ride_status.get("preview_count"),
            "last_reported": ride_status.get("last_reported_activity_id"),
            "deps_ok": ride_deps_ok,
        },
        "schedule": {
            "has_cron": has_cron,
            "report_cron_count": schedule_status.get("report_crontab_count", 0),
            "last_daily": schedule_status.get("last_daily_report_date"),
            "last_ride": schedule_status.get("last_ride_report_activity"),
        },
        "safe_tests": [
            "qbot_daily_report_status",
            "qbot_daily_report_preview",
            "qbot_ride_report_status",
            "qbot_ride_report_latest",
            "qbot_ride_report_preview",
            "qbot_reports_schedule_status",
        ],
        "controlled_execution_needed": True,
        "send_requires_dry_run_false": [
            "qbot_daily_report_send (dry_run=false)",
            "qbot_ride_report_send (dry_run=false)",
        ],
        "blocked_without_smtp": [
            "Email channel requires GMAIL_USER + GMAIL_APP_PASSWORD",
            "No email send without confirmed SMTP",
        ],
        "next_steps": next_steps,
        "notes": (
            "Daily report generates from weather/Xert/Intervals data. "
            "Ride report generates per-activity HTML. "
            "Both send via Telegram (always) and Email (optional, requires SMTP). "
            "Max 1 test message per channel. No email without confirmed SMTP."
        ),
    }


# A minimal helper to get config without depending on qbot_config import succeeding
def cfg_get(name: str, default: str = "") -> str:
    try:
        from qbot_config import env as _cfg_env
        return _cfg_env(name, default)
    except ImportError:
        return os.getenv(name, default)
