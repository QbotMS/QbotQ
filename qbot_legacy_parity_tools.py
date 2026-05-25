"""Legacy parity audit tools — read-only scope expansion across all QBot services."""
from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

_PROJECT_ROOT: Path = Path("/opt/qbot/app")
_ARTIFACT_ROOT: Path = Path("/opt/qbot/artifacts")
_WORKSPACE_ROOT: Path = Path("/opt/qbot/workspace")
_SKIP_DIRS: set[str] = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "logs",
    "outgoing",
    "backups",
    "node_modules",
    ".aider",
    ".aider.tags.cache.v4",
    ".claude",
}
_SKIP_FILES: set[str] = {".env.local", ".env", ".garmin_tokens.json", ".garmin_session.pkl", ".hammerhead_tokens"}
_MAX_FILE_BYTES = 250_000
_MAX_EVIDENCE_PER_CAP = 6
_MAX_EXCERPTS_PER_FILE = 3

_SENSITIVE_KEYS: set[str] = {"password", "secret", "token", "apikey", "api_key", "pgpassword", "env", "credential", "auth"}


def _safe_read_text(path: Path) -> str:
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return ""
    except OSError:
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "\x00" in text:
            return ""
        return text
    except Exception:
        return ""


def _scan_files(keywords: list[str], roots: list[Path] | None = None) -> list[dict[str, Any]]:
    roots = roots or [_PROJECT_ROOT]
    hits: list[dict[str, Any]] = []
    lowered = [k.lower() for k in keywords if k]
    for root in roots:
        if not root.exists():
            continue
        try:
            candidates = sorted(root.rglob("*"))
        except Exception:
            continue
        for path in candidates:
            if any(skip in path.parts for skip in _SKIP_DIRS):
                continue
            if path.name in _SKIP_FILES or path.name.startswith(".aider") or path.name.startswith(".claude"):
                continue
            if not path.is_file():
                continue
            content = _safe_read_text(path)
            if not content:
                continue
            cl = content.lower()
            matched = [kw for kw in lowered if kw in cl]
            if not matched:
                continue
            excerpts: list[str] = []
            for line in content.splitlines():
                ll = line.lower()
                if any(kw in ll for kw in matched):
                    excerpts.append(line.strip()[:240])
                if len(excerpts) >= _MAX_EXCERPTS_PER_FILE:
                    break
            hits.append(
                {
                    "file": path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path),
                    "keywords_matched": matched,
                    "excerpts": excerpts,
                }
            )
            if len(hits) >= _MAX_EVIDENCE_PER_CAP:
                return hits
    return hits


def _env_presence(names: list[str]) -> dict[str, bool]:
    presence: dict[str, bool] = {}
    env_local = _PROJECT_ROOT / ".env.local"
    env_text = _safe_read_text(env_local)
    for name in names:
        present = bool(os.getenv(name))
        if not present and env_text:
            present = re.search(rf"^{re.escape(name)}\s*=", env_text, re.MULTILINE) is not None
        presence[name] = present
    return presence


def _systemd_unit_snapshot(unit: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["systemctl", "show", unit, "--property=ActiveState,SubState,LoadState,UnitFileState"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return {"unit": unit, "status": "ERROR", "error": str(exc)}

    props: dict[str, str] = {}
    for line in proc.stdout.strip().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k] = v
    active = props.get("ActiveState", "unknown")
    sub = props.get("SubState", "unknown")
    unit_file_state = props.get("UnitFileState", "unknown")
    return {
        "unit": unit,
        "active_state": active,
        "sub_state": sub,
        "load_state": props.get("LoadState", "unknown"),
        "unit_file_state": unit_file_state,
        "status": "OK" if active == "active" and sub in ("running", "exited") else "WARN" if active == "active" else "ERROR",
    }


def _systemd_inventory() -> dict[str, Any]:
    relevant_units = [
        "qbot-api.service",
        "q-bot.service",
        "qbot-qlab-server.service",
        "qbot-backup.service",
        "qbot-backup.timer",
        "qbot-mcp-bridge.service",
        "postgresql.service",
        "ngrok-qbot.service",
    ]
    snapshots = [_systemd_unit_snapshot(unit) for unit in relevant_units]

    cron_entries: list[str] = []
    try:
        proc = subprocess.run(["crontab", "-l", "-u", "qbot"], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    cron_entries.append(stripped)
    except Exception:
        pass

    return {
        "systemd_units": snapshots,
        "cron_entries": cron_entries,
        "timer_units": [u for u in snapshots if u["unit"].endswith(".timer")],
        "service_units": [u for u in snapshots if u["unit"].endswith(".service")],
    }


def _public_endpoint_snapshot() -> dict[str, Any]:
    base = os.getenv("QBOT_PUBLIC_BASE_URL", "https://qbot.cytr.us").rstrip("/")
    paths = ["/mcp/", "/telegram/webhook/badsecret", "/q", "/health"]
    results: dict[str, Any] = {}
    try:
        with httpx.Client(timeout=4.0, trust_env=False, follow_redirects=False) as client:
            for path in paths:
                url = f"{base}{path}"
                try:
                    resp = client.get(url)
                    results[path] = {
                        "url": url,
                        "reachable": True,
                        "status_code": resp.status_code,
                        "blocked": resp.status_code in (403, 404),
                        "public": resp.status_code != 404,
                    }
                except Exception as exc:
                    results[path] = {
                        "url": url,
                        "reachable": False,
                        "error": str(exc),
                        "blocked": False,
                        "public": False,
                    }
    except Exception as exc:
        results["error"] = str(exc)
    return results


def _service_state(unit: str) -> dict[str, Any]:
    snap = _systemd_unit_snapshot(unit)
    try:
        proc = subprocess.run(["systemctl", "is-enabled", unit], capture_output=True, text=True, timeout=3)
        snap["enabled_state"] = proc.stdout.strip() if proc.returncode == 0 else "unknown"
    except Exception:
        snap["enabled_state"] = "unknown"
    return snap


def _summarize_status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"RESTORED": 0, "PARTIAL": 0, "MISSING": 0, "BLOCKED_BY_POLICY": 0}
    for row in rows:
        status = str(row.get("new_qbot_status", "MISSING")).upper()
        if status not in counts:
            counts[status] = 0
        counts[status] += 1
    return counts


def _build_report_text(title: str, lines: list[str]) -> str:
    return "\n".join([title, *lines])


def _tool_qbot_weather_legacy_status(_args: dict | None = None) -> dict[str, Any]:
    evidence = _scan_files(
        [
            "openweathermap",
            "weather",
            "forecast",
            "pogoda",
            "weathercode",
            "open-meteo",
            "mcp_call(\"get_weather\"",
        ]
    )
    env_presence = _env_presence(["OPENWEATHERMAP_API_KEY", "WEATHER_API_KEY", "OWM_API_KEY"])
    current_status = "weather available via MCP get_weather (Open-Meteo); OpenWeatherMap integration is not present"
    status = "MISSING"
    if evidence and any("openweathermap" in kw for item in evidence for kw in item.get("keywords_matched", [])):
        status = "PARTIAL"
    return {
        "tool": "qbot_weather_legacy_status",
        "capability": "weather_openweathermap",
        "status": status,
        "safety_class": "READ_ONLY",
        "env_presence": env_presence,
        "candidate_files": evidence,
        "current_new_qbot_status": current_status,
        "proposed_tools": ["qbot_weather_status", "qbot_weather_current", "qbot_weather_forecast"],
        "can_restore_today": True,
        "risk": "medium",
        "notes": "Legacy OpenWeatherMap is not directly present; current weather path is read-only Open-Meteo via MCP.",
    }


def _tool_qbot_garage_legacy_status(_args: dict | None = None) -> dict[str, Any]:
    evidence = _scan_files(
        [
            "garage",
            "garaz",
            "garaż",
            "gate",
            "brama",
            "door",
            "relay",
            "switch",
            "mqtt",
            "zigbee",
            "hikconnect",
            "tuya",
            "shelly",
            "homeassistant",
            "ha_",
        ]
    )
    env_presence = _env_presence([
        "GATE_TOKEN",
        "GATE_DEVICE_SERIAL",
        "GATE_LOCK_CHANNEL",
        "GATE_LOCK_INDEX",
        "HIKCONNECT_ACCOUNT",
        "HIKCONNECT_PASSWORD",
        "MQTT_HOST",
        "ZIGBEE2MQTT_URL",
        "HOMEASSISTANT_URL",
    ])
    gate_refs = any(any(kw in item.get("keywords_matched", []) for kw in ["gate", "hikconnect"]) for item in evidence)
    home_refs = any(any(kw in item.get("keywords_matched", []) for kw in ["garage", "relay", "switch", "mqtt", "zigbee", "tuya", "shelly", "homeassistant", "ha_"]) for item in evidence)
    status = "BLOCKED_BY_POLICY" if gate_refs else "PARTIAL" if home_refs else "MISSING"
    return {
        "tool": "qbot_garage_legacy_status",
        "capability": "home_automation / garage_gate",
        "status": status,
        "safety_class": "CONTROLLED_ACTION",
        "env_presence": env_presence,
        "candidate_files": evidence,
        "current_new_qbot_status": "Garage data routing exists; gate/home automation control is intentionally blocked and not exposed as an execution tool.",
        "proposed_tools": [
            "qbot_garage_legacy_status",
            "qbot_home_automation_status",
            "qbot_gate_status",
        ],
        "can_restore_today": False,
        "risk": "high",
        "notes": "No remote opening/closing is implemented here. Any control path requires an explicit safety gate and operator approval.",
        "blocked_components": ["gate/hikconnect", "any remote open/close action"],
    }


def _tool_qbot_artifacts_legacy_status(_args: dict | None = None) -> dict[str, Any]:
    evidence = _scan_files(
        [
            "artifact",
            "artifacts",
            "container",
            "workspace",
            "outgoing",
            "generated",
            "uploads",
            "downloads",
            "qbot_artifacts",
        ],
        roots=[_PROJECT_ROOT, _ARTIFACT_ROOT, _WORKSPACE_ROOT],
    )
    filesystem_root_present = _ARTIFACT_ROOT.exists()
    filesystem_entries = 0
    if filesystem_root_present:
        try:
            filesystem_entries = sum(1 for p in _ARTIFACT_ROOT.rglob("*") if p.is_file())
        except Exception:
            filesystem_entries = 0

    sql_presence = bool(_scan_files(["CREATE TABLE IF NOT EXISTS qbot_artifacts", "INSERT INTO qbot_artifacts", "SELECT id, created_at, artifact_type, title, tags FROM qbot_artifacts"]))
    bridge_present = any(
        item.get("file") in {"mcp_server.py", "qbot_artifact_tools.py", "tools/rwgps/client.py"}
        for item in evidence
    ) and filesystem_root_present and sql_presence
    status = "PARTIAL" if filesystem_root_present and sql_presence else "MISSING"
    if bridge_present:
        status = "PARTIAL"
    return {
        "tool": "qbot_artifacts_legacy_status",
        "capability": "artifacts_container",
        "status": status,
        "filesystem_artifacts_root": str(_ARTIFACT_ROOT),
        "filesystem_artifacts_present": filesystem_root_present,
        "filesystem_artifacts_count": filesystem_entries,
        "sql_artifacts_table_present": sql_presence,
        "bridge_present": bridge_present,
        "candidate_files": evidence,
        "current_new_qbot_status": "Filesystem artifact root and PostgreSQL qbot_artifacts both exist, but there is no single generic filesystem↔SQL bridge tool.",
        "proposed_bridge_tools": [
            "qbot_artifacts_filesystem_inventory",
            "qbot_artifact_import_from_file_preview",
            "qbot_artifact_export_preview",
        ],
        "can_restore_today": True,
        "risk": "medium",
        "notes": "Current code has both filesystem artifacts and PostgreSQL artifacts; the gap is unified inventory/bridge behavior.",
    }


def _tool_qbot_external_integrations_report(_args: dict | None = None) -> dict[str, Any]:
    from qbot_mcp_adapter import _tool_qbot_mcp_status
    from qbot_telegram_tools import _tool_qbot_telegram_status

    sections: dict[str, Any] = {}
    sections["weather"] = _tool_qbot_weather_legacy_status()
    sections["garage_home_automation"] = _tool_qbot_garage_legacy_status()
    sections["artifacts_container"] = _tool_qbot_artifacts_legacy_status()
    sections["telegram"] = _tool_qbot_telegram_status()
    sections["mcp"] = _tool_qbot_mcp_status({})

    evidence = {
        "telegram": _scan_files(["telegram", "webhook", "chat_id", "allowed_chat_ids", "TELEGRAM_BOT_TOKEN"]),
        "email": _scan_files(["smtp", "gmail", "email", "mail", "send_message", "send_mail"]),
        "garmin": _scan_files(["garmin", "garmin_connect", "garmin_auth", "upload", "download"]),
        "rwgps": _scan_files(["rwgps", "ridewithgps", "openmap", "openmaps_v1", "track", "route"]),
        "maps": _scan_files(["openstreetmap", "osm", "overpass", "openmap"]),
        "webhooks": _scan_files(["webhook", "callback", "setWebhook", "deleteWebhook"]),
    }

    exposed = {
        "telegram": ["/telegram/webhook/", "/status", "/legacy", "/ready", "/smoke", "/backup", "/errors", "/takeover", "/ask"],
        "mcp": ["/mcp/", "/mcp/health", "/mcp/tools"],
    }

    summary_lines = [
        f"weather: {sections['weather'].get('status', 'UNKNOWN')}",
        f"garage/home automation: {sections['garage_home_automation'].get('status', 'UNKNOWN')}",
        f"artifacts/container: {sections['artifacts_container'].get('status', 'UNKNOWN')}",
        f"telegram: {sections['telegram'].get('status', 'UNKNOWN')}",
        f"mcp: {sections['mcp'].get('status', 'UNKNOWN')}",
    ]
    overall = "OK"
    if any(s in {"MISSING", "BLOCKED_BY_POLICY"} for s in [sections["weather"].get("status"), sections["garage_home_automation"].get("status"), sections["artifacts_container"].get("status")]):
        overall = "WARN"

    return {
        "tool": "qbot_external_integrations_report",
        "status": overall,
        "sections": sections,
        "evidence": evidence,
        "exposed_channels": exposed,
        "summary_text": _build_report_text("External integrations:", summary_lines),
        "notes": [
            "Read-only summary only.",
            "No secrets printed.",
            "Weather uses current MCP/Open-Meteo path; OpenWeatherMap legacy is missing.",
            "Garage/gate references are treated as controlled actions, not execution paths.",
        ],
    }


_CAPABILITY_SPECS: list[dict[str, Any]] = [
    {
        "legacy_capability": "qbot_core_api",
        "label": "Qbot core API",
        "keywords": ["qbot_api.py", "qbot_tools.py", "api_db.py", "qbot_tool_registry.py", "/health", "/q"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_status", "qbot_api_self_check", "qbot_db_overview", "qbot_services_status", "qbot_query"],
        "exposed_in_mcp": ["qbot.status"],
        "exposed_in_telegram": ["/status", "/ready", "/smoke", "/backup", "/errors", "/takeover", "/ask"],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "low",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Core FastAPI, DB, tool registry, and /q webhook dispatch are present.",
    },
    {
        "legacy_capability": "telegram_bot",
        "label": "Telegram bot",
        "keywords": ["qbot_telegram_tools.py", "qbot_telegram_client.py", "/telegram/webhook", "TELEGRAM_BOT_TOKEN"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_telegram_status", "qbot_telegram_webhook_plan", "qbot_telegram_set_webhook", "qbot_telegram_send_test", "qbot_public_endpoint_status"],
        "exposed_in_mcp": ["qbot.telegram_status"],
        "exposed_in_telegram": ["/status", "/legacy", "/ready", "/smoke", "/backup", "/errors", "/takeover", "/weather_status", "/garage_status", "/artifacts", "/integrations"],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "low",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Telegram webhook and command handling are restored; status output is cutover-aware.",
    },
    {
        "legacy_capability": "mcp_connector",
        "label": "ChatGPT MCP connector",
        "keywords": ["qbot_mcp_adapter.py", "/mcp/", "MCP_SHARED_SECRET", "QBOT_MCP_TOKEN"],
        "new_qbot_status": "PARTIAL",
        "new_qbot_tools": ["qbot_mcp_status", "qbot_mcp_tools_list", "qbot_mcp_call_preview"],
        "exposed_in_mcp": ["qbot.status", "qbot.readiness", "qbot.ask", "qbot.runbook", "qbot.context_bundle", "qbot.artifact_create", "qbot.artifact_list", "qbot.artifact_get", "qbot.tool_policy", "qbot.telegram_status", "qbot.weather_legacy_status", "qbot.garage_legacy_status", "qbot.artifacts_legacy_status", "qbot.external_integrations_report"],
        "exposed_in_telegram": [],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Public /mcp endpoint is present; adapter is read-only unless token-gated artifact writes are enabled.",
    },
    {
        "legacy_capability": "qlab",
        "label": "QLab",
        "keywords": ["qbot_qlab_server.py", "qbot-qlab-server.service", "qlab_exports", "qlab"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_legacy_qlab_status", "qbot_legacy_qlab_smoke_check"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": [],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Dedicated qbot-qlab-server unit and smoke check remain available.",
    },
    {
        "legacy_capability": "backup_restore",
        "label": "Backup / restore",
        "keywords": ["qbot-backup.service", "qbot-backup.timer", "restore_drill", "backup", "pg_dump"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_backup_status", "qbot_backup_timer_status", "qbot_restore_drill_status", "qbot_backup_plan", "qbot_create_backup_script_preview"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": ["/backup"],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Automated backup timer and restore drill are present.",
    },
    {
        "legacy_capability": "garmin_proxy",
        "label": "Garmin proxy",
        "keywords": ["garmin", "garmin_auth", "garmin_connect", "garmin_proxy", "fit_export", "qbot-hammerhead-sync"],
        "new_qbot_status": "PARTIAL",
        "new_qbot_tools": ["qbot_legacy_garmin_status", "qbot_legacy_garmin_dry_run", "qbot_legacy_capability_scan"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": [],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Legacy Garmin-related code and proxies exist, but full parity still depends on external auth and upload flows.",
    },
    {
        "legacy_capability": "garmin_upload",
        "label": "Garmin upload",
        "keywords": ["upload", "garmin", "garmin_connect", "fit", "tcx", "gpx"],
        "new_qbot_status": "PARTIAL",
        "new_qbot_tools": ["qbot_legacy_garmin_dry_run", "qbot_legacy_garmin_status"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": [],
        "safety_class": "CONTROLLED_ACTION",
        "missing_tools": ["qbot_garmin_upload_status", "qbot_garmin_upload_preview"],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Upload capability is represented indirectly; no new execution path is added here.",
    },
    {
        "legacy_capability": "fit_processing",
        "label": "FIT processing",
        "keywords": ["fit", "tcx", "TrainingCenterDatabase", "fit_export", "fit_parse"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_legacy_capability_scan", "qbot_legacy_dependency_inventory"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": [],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "low",
        "can_restore_today": True,
        "priority": "medium",
        "notes": "FIT/TCX processing code is present in the repo and exercised by tests.",
    },
    {
        "legacy_capability": "csv_export",
        "label": "CSV export",
        "keywords": ["csv", "export", "outgoing", "reports", "download"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_legacy_export_status", "qbot_legacy_export_dry_run", "qbot_legacy_safe_execution_report"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": [],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "low",
        "can_restore_today": True,
        "priority": "medium",
        "notes": "CSV-style export paths and report generation are present as legacy artifacts.",
    },
    {
        "legacy_capability": "json_reports",
        "label": "JSON reports",
        "keywords": ["json", "reports", "generated_at", "status_report", "operational_state"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_operator_final_smoke_test", "qbot_maintenance_report", "qbot_operator_snapshot"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": ["/status", "/legacy", "/ready", "/smoke", "/backup", "/errors", "/takeover"],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "low",
        "can_restore_today": True,
        "priority": "medium",
        "notes": "JSON report generation and operator summaries are already part of the new stack.",
    },
    {
        "legacy_capability": "hammerhead_import",
        "label": "Hammerhead import",
        "keywords": ["hammerhead", "karoo", "qbot-hammerhead-sync", "import"],
        "new_qbot_status": "PARTIAL",
        "new_qbot_tools": ["qbot_legacy_dependency_inventory", "qbot_legacy_capability_scan"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": [],
        "safety_class": "READ_ONLY",
        "missing_tools": ["qbot_hammerhead_import_status", "qbot_hammerhead_import_preview"],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Import logic exists as code and artifacts, but no dedicated read-only status surface was added before this audit.",
    },
    {
        "legacy_capability": "rwgps",
        "label": "RideWithGPS",
        "keywords": ["rwgps", "ridewithgps", "tools/rwgps/client.py", "route", "track"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_legacy_capability_scan", "qbot_legacy_dependency_inventory"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": [],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "high",
        "notes": "RWGPS client and artifact export surface are present in the workspace.",
    },
    {
        "legacy_capability": "openmap_osm",
        "label": "OpenMap / OSM",
        "keywords": ["openmap", "openmaps_v1", "openstreetmap", "osm", "overpass"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_legacy_capability_scan"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": [],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "medium",
        "notes": "OpenMap / OSM references exist in route tooling and artifact generation code.",
    },
    {
        "legacy_capability": "weather_openweathermap",
        "label": "Weather / OpenWeatherMap",
        "keywords": ["openweathermap", "weather", "forecast", "pogoda", "open-meteo"],
        "new_qbot_status": "MISSING",
        "new_qbot_tools": ["qbot_weather_legacy_status"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": ["/weather_status"],
        "safety_class": "READ_ONLY",
        "missing_tools": ["qbot_weather_status", "qbot_weather_current", "qbot_weather_forecast"],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Weather exists, but OpenWeatherMap-specific parity is absent; current path uses Open-Meteo instead.",
    },
    {
        "legacy_capability": "garage_gate",
        "label": "Garage / gate",
        "keywords": ["garage", "gate", "brama", "relay", "switch", "mqtt", "zigbee", "hikconnect", "tuya", "shelly", "homeassistant", "ha_"],
        "new_qbot_status": "BLOCKED_BY_POLICY",
        "new_qbot_tools": ["qbot_garage_legacy_status"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": ["/garage_status"],
        "safety_class": "CONTROLLED_ACTION",
        "missing_tools": ["qbot_home_automation_status", "qbot_gate_status"],
        "risk": "high",
        "can_restore_today": False,
        "priority": "high",
        "notes": "Legacy gate/home automation traces are detected, but execution remains blocked by policy and is not exposed.",
    },
    {
        "legacy_capability": "artifacts_container",
        "label": "Artifacts container",
        "keywords": ["artifact", "artifacts", "container", "workspace", "outgoing", "generated", "uploads", "downloads", "/opt/qbot/artifacts", "/opt/qbot/workspace", "qbot_artifacts"],
        "new_qbot_status": "PARTIAL",
        "new_qbot_tools": ["qbot_artifact_create", "qbot_artifact_list", "qbot_artifact_get", "qbot_workspace_write_file_preview", "qbot_artifacts_legacy_status"],
        "exposed_in_mcp": ["qbot.artifact_create", "qbot.artifact_list", "qbot.artifact_get"],
        "exposed_in_telegram": ["/artifacts"],
        "safety_class": "READ_ONLY",
        "missing_tools": ["qbot_artifacts_filesystem_inventory", "qbot_artifact_import_from_file_preview", "qbot_artifact_export_preview"],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Filesystem artifacts and PostgreSQL artifacts both exist, but the generic bridge/inventory surface is incomplete.",
    },
    {
        "legacy_capability": "filesystem_artifacts",
        "label": "Filesystem artifacts",
        "keywords": ["/opt/qbot/artifacts", "artifact_root", "list_qbot_artifacts", "save_qbot_artifact"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_artifact_list", "qbot_artifact_get", "qbot_workspace_write_file_preview"],
        "exposed_in_mcp": ["qbot.artifact_list", "qbot.artifact_get"],
        "exposed_in_telegram": ["/artifacts"],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "medium",
        "notes": "Filesystem artifact root is available and readable through the current workspace tooling.",
    },
    {
        "legacy_capability": "scheduled_jobs",
        "label": "Scheduled jobs",
        "keywords": ["cron", "timer", "scheduled", "daily", "periodic", "qbot-backup.timer", "crontab"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_backup_timer_status", "qbot_operator_final_smoke_test", "qbot_maintenance_report"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": ["/backup"],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "low",
        "can_restore_today": True,
        "priority": "medium",
        "notes": "Systemd timers and cron-backed jobs are present and readable.",
    },
    {
        "legacy_capability": "email_notifications",
        "label": "Email notifications",
        "keywords": ["smtp", "gmail", "email", "mail", "send_mail", "daily_report.py", "weekly_review.py", "ride_report.py"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_maintenance_report", "qbot_operator_final_smoke_test"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": [],
        "safety_class": "READ_ONLY",
        "missing_tools": ["qbot_email_status"],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "medium",
        "notes": "Mail sending paths are still present; there is no dedicated email status tool, but the delivery flow remains in place.",
    },
    {
        "legacy_capability": "public_endpoints",
        "label": "Public endpoints",
        "keywords": ["@app.get(\"/mcp/\"", "@app.post(\"/telegram/webhook", "@app.post(\"/q\")", "@app.get(\"/health\")"],
        "new_qbot_status": "RESTORED",
        "new_qbot_tools": ["qbot_public_endpoint_status", "qbot_mcp_status", "qbot_telegram_status"],
        "exposed_in_mcp": ["qbot.status", "qbot.readiness", "qbot.ask"],
        "exposed_in_telegram": ["/status", "/legacy", "/ready", "/smoke", "/backup", "/errors", "/takeover", "/weather_status", "/garage_status", "/artifacts", "/integrations"],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Public /mcp/ and /telegram/webhook/ are exposed; /q and /health remain blocked publicly.",
    },
    {
        "legacy_capability": "home_automation",
        "label": "Home automation",
        "keywords": ["homeassistant", "home assistant", "mqtt", "zigbee", "tuya", "shelly", "relay", "switch", "gate", "hikconnect"],
        "new_qbot_status": "BLOCKED_BY_POLICY",
        "new_qbot_tools": ["qbot_garage_legacy_status"],
        "exposed_in_mcp": [],
        "exposed_in_telegram": ["/garage_status"],
        "safety_class": "CONTROLLED_ACTION",
        "missing_tools": ["qbot_home_automation_status", "qbot_gate_status"],
        "risk": "high",
        "can_restore_today": False,
        "priority": "high",
        "notes": "Detected only as legacy capability; any actuation remains blocked and requires an explicit separate safety gate.",
    },
    {
        "legacy_capability": "external_api_integrations",
        "label": "External API integrations",
        "keywords": ["requests.get", "requests.post", "httpx", "webhook", "callback", "oauth", "openai", "deepseek", "telegram", "garmin", "rwgps", "openweathermap", "maps", "overpass"],
        "new_qbot_status": "PARTIAL",
        "new_qbot_tools": ["qbot_external_integrations_report", "qbot_telegram_status", "qbot_mcp_status", "qbot_weather_legacy_status", "qbot_artifacts_legacy_status", "qbot_garage_legacy_status"],
        "exposed_in_mcp": ["qbot.telegram_status", "qbot.weather_legacy_status", "qbot.artifacts_legacy_status", "qbot.garage_legacy_status", "qbot.external_integrations_report"],
        "exposed_in_telegram": ["/status", "/legacy", "/ready", "/smoke", "/backup", "/errors", "/takeover", "/weather_status", "/garage_status", "/artifacts", "/integrations"],
        "safety_class": "READ_ONLY",
        "missing_tools": [],
        "risk": "medium",
        "can_restore_today": True,
        "priority": "high",
        "notes": "Telegram, Garmin/RWGPS, weather, email, webhooks, and MCP are present; OpenWeatherMap and home automation remain incomplete or blocked.",
    },
]


def _build_matrix_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in _CAPABILITY_SPECS:
        evidence = _scan_files(spec.get("keywords", []))
        row = {
            "legacy_capability": spec["legacy_capability"],
            "old_qbot_evidence": evidence,
            "new_qbot_status": spec["new_qbot_status"],
            "new_qbot_tools": spec["new_qbot_tools"],
            "exposed_in_mcp": spec["exposed_in_mcp"],
            "exposed_in_telegram": spec["exposed_in_telegram"],
            "safety_class": spec["safety_class"],
            "missing_tools": spec["missing_tools"],
            "risk": spec["risk"],
            "can_restore_today": spec["can_restore_today"],
            "priority": spec["priority"],
            "notes": spec["notes"],
        }
        rows.append(row)
    return rows


def _tool_qbot_legacy_parity_matrix(_args: dict | None = None) -> dict[str, Any]:
    rows = _build_matrix_rows()
    counts = _summarize_status_counts(rows)
    restored = counts.get("RESTORED", 0)
    partial = counts.get("PARTIAL", 0)
    total = len(rows)
    parity_pct = round(((restored + partial * 0.5) / total * 100), 1) if total else 0.0
    return {
        "tool": "qbot_legacy_parity_matrix",
        "status": "OK" if counts.get("MISSING", 0) == 0 and counts.get("BLOCKED_BY_POLICY", 0) == 0 else "WARN",
        "total_capabilities": total,
        "status_counts": counts,
        "legacy_parity_percent": parity_pct,
        "rows": rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _tool_qbot_legacy_full_parity_audit(_args: dict | None = None) -> dict[str, Any]:
    matrix = _tool_qbot_legacy_parity_matrix()
    rows = matrix.get("rows", [])
    counts = matrix.get("status_counts", {})
    missing_services = [
        row["legacy_capability"]
        for row in rows
        if row.get("new_qbot_status") != "RESTORED"
    ]
    weather = next((row for row in rows if row["legacy_capability"] == "weather_openweathermap"), {})
    garage = next((row for row in rows if row["legacy_capability"] == "garage_gate"), {})
    artifacts = next((row for row in rows if row["legacy_capability"] == "artifacts_container"), {})
    garmin = next((row for row in rows if row["legacy_capability"] == "garmin_upload"), {})
    rwgps = next((row for row in rows if row["legacy_capability"] == "rwgps"), {})
    telegram = next((row for row in rows if row["legacy_capability"] == "telegram_bot"), {})
    mcp = next((row for row in rows if row["legacy_capability"] == "mcp_connector"), {})

    overall_status = "OK"
    if counts.get("MISSING", 0) or counts.get("BLOCKED_BY_POLICY", 0):
        overall_status = "WARN"

    return {
        "tool": "qbot_legacy_full_parity_audit",
        "status": overall_status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_capabilities": len(rows),
        "status_counts": counts,
        "legacy_parity_percent": matrix.get("legacy_parity_percent", 0.0),
        "capabilities": rows,
        "capability_summary": {
            "garage_gate": garage.get("new_qbot_status", "UNKNOWN"),
            "weather_openweathermap": weather.get("new_qbot_status", "UNKNOWN"),
            "artifacts_container": artifacts.get("new_qbot_status", "UNKNOWN"),
            "garmin_fit": {
                "garmin_upload": garmin.get("new_qbot_status", "UNKNOWN"),
                "fit_processing": next((row for row in rows if row["legacy_capability"] == "fit_processing"), {}).get("new_qbot_status", "UNKNOWN"),
            },
            "rwgps_openmap": {
                "rwgps": rwgps.get("new_qbot_status", "UNKNOWN"),
                "openmap_osm": next((row for row in rows if row["legacy_capability"] == "openmap_osm"), {}).get("new_qbot_status", "UNKNOWN"),
            },
            "telegram_mcp": {
                "telegram": telegram.get("new_qbot_status", "UNKNOWN"),
                "mcp": mcp.get("new_qbot_status", "UNKNOWN"),
            },
        },
        "missing_services_to_100": missing_services,
        "public_endpoint_inventory": _public_endpoint_snapshot(),
        "systemd_inventory": _systemd_inventory(),
        "summary_text": _build_report_text(
            "Qbot legacy parity audit:",
            [
                f"capabilities: {len(rows)}",
                f"counts: RESTORED={counts.get('RESTORED', 0)}, PARTIAL={counts.get('PARTIAL', 0)}, MISSING={counts.get('MISSING', 0)}, BLOCKED_BY_POLICY={counts.get('BLOCKED_BY_POLICY', 0)}",
                f"parity: {matrix.get('legacy_parity_percent', 0.0)}%",
                f"garage/gate: {garage.get('new_qbot_status', 'UNKNOWN')}",
                f"weather/OpenWeatherMap: {weather.get('new_qbot_status', 'UNKNOWN')}",
                f"artifacts/container: {artifacts.get('new_qbot_status', 'UNKNOWN')}",
            ],
        ),
        "notes": [
            "Read-only audit only; no legacy actions were executed.",
            "Gate/home automation is intentionally blocked by policy.",
            "OpenWeatherMap-specific parity is not present; current weather path is Open-Meteo-based.",
            "Artifacts exist in both filesystem and PostgreSQL forms, but the bridge is still partial.",
        ],
    }


def _get_legacy_parity_tool(name: str):
    mapping = {
        "qbot_weather_legacy_status": _tool_qbot_weather_legacy_status,
        "qbot_garage_legacy_status": _tool_qbot_garage_legacy_status,
        "qbot_artifacts_legacy_status": _tool_qbot_artifacts_legacy_status,
        "qbot_external_integrations_report": _tool_qbot_external_integrations_report,
        "qbot_legacy_parity_matrix": _tool_qbot_legacy_parity_matrix,
        "qbot_legacy_full_parity_audit": _tool_qbot_legacy_full_parity_audit,
    }
    return mapping.get(name)
