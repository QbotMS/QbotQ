#!/usr/bin/env python3
"""Internal capability: hammerhead_sync_status.

Checks Hammerhead->Garmin sync status: config, state file, cron, latest log.
SAFE: only reads files — never downloads, rewrites, or uploads.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from qbot3.capabilities.base import Capability, CapabilityDef, PROMOTION_ACTIVE, SAFETY_READ_ONLY


APP_DIR = Path("/opt/qbot/app")
STATE_FILE = APP_DIR / "state/michal_processed_hammerhead_activities.json"
LOG_FILE = APP_DIR / "logs/hammerhead-garmin-sync-michal.log"
PROFILE_ENV = APP_DIR / "config/profiles/michal.env"
HAMMERHEAD_TOKENS = APP_DIR / ".hammerhead_tokens/michal.json"
GARMIN_TOKENS = APP_DIR / ".garmin_tokens/michal/garmin_tokens.json"
OUTGOING_DIR = APP_DIR / "outgoing/michal"


class HammerheadSyncStatusCapability(Capability):
    def manifest(self) -> CapabilityDef:
        return CapabilityDef(
            name="hammerhead_sync_status",
            description="Hammerhead→Garmin sync pipeline status: config check, dedup state file, last log entries, outgoing files. Tylko odczyt — nie wykonuje transferu.",
            safety_class=SAFETY_READ_ONLY,
            capability_type="READ_ONLY_FILE",
            data_sources=["config/profiles/michal.env", "state/*_processed_hammerhead_activities.json", "logs/hammerhead-garmin-sync-*.log"],
            promotion_state=PROMOTION_ACTIVE,
            inputs_schema={},
            output_schema={
                "type": "object",
                "properties": {
                    "config_ok": {"type": "boolean"},
                    "details": {"type": "object"},
                },
            },
            reason_existing_insufficient="No existing tool reads the external hammerhead sync pipeline state",
        )

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"config_ok": False}

        # 1. Config check
        config_issues: list[str] = []
        if PROFILE_ENV.is_file():
            result["profile_env"] = str(PROFILE_ENV)
        else:
            config_issues.append("profile env missing")

        if HAMMERHEAD_TOKENS.is_file():
            result["hammerhead_tokens"] = "present"
        else:
            config_issues.append("hammerhead tokens missing")

        if GARMIN_TOKENS.is_file():
            result["garmin_tokens"] = "present"
        else:
            config_issues.append("garmin tokens missing")

        if OUTGOING_DIR.exists():
            originals = list((OUTGOING_DIR / "hammerhead_originals").glob("*.fit"))
            proxies = list((OUTGOING_DIR / "garmin_proxy").glob("*_garmin_proxy.fit"))
            reports = list((OUTGOING_DIR / "reports").glob("*.json"))
            result["outgoing"] = {
                "original_fits": len(originals),
                "proxy_fits": len(proxies),
                "reports": len(reports),
            }
        else:
            config_issues.append("outgoing dir missing")

        result["config_ok"] = len(config_issues) == 0
        result["config_issues"] = config_issues

        # 2. State file (dedup)
        state_info: dict[str, Any] = {"exists": STATE_FILE.is_file()}
        if STATE_FILE.is_file():
            try:
                state = json.loads(STATE_FILE.read_text())
                processed = state.get("processed", [])
                uploaded = [p for p in processed if p.get("status") == "uploaded"]
                failed = [p for p in processed if p.get("status") == "failed"]
                state_info["total_processed"] = len(processed)
                state_info["uploaded"] = len(uploaded)
                state_info["failed"] = len(failed)
                if uploaded:
                    state_info["last_uploaded_at"] = max(
                        (p.get("updatedAt", "") for p in uploaded), default=""
                    )
            except Exception as exc:
                state_info["error"] = str(exc)[:200]
        result["state"] = state_info

        # 3. Log tail
        log_info: dict[str, Any] = {"exists": LOG_FILE.is_file()}
        if LOG_FILE.is_file():
            try:
                lines = LOG_FILE.read_text().splitlines()
                log_info["total_lines"] = len(lines)
                tail = lines[-15:]
                log_info["tail"] = tail
                # Detect last status
                for line in reversed(tail):
                    if "uploaded" in line.lower() and "activity" in line.lower():
                        log_info["last_action"] = "upload"
                        break
                    if "dry-run" in line.lower():
                        log_info["last_action"] = "dry_run"
                        break
                    if "skipped" in line.lower():
                        log_info["last_action"] = "skipped"
                        break
                    if "failed" in line.lower():
                        log_info["last_action"] = "failed"
                        break
                    if "NoUnprocessed" in line or "no unprocessed" in line.lower():
                        log_info["last_action"] = "no_new_activities"
                        break
            except Exception as exc:
                log_info["error"] = str(exc)[:200]
        result["log"] = log_info

        # 4. Summary
        parts = []
        if result["config_ok"]:
            parts.append("Config OK")
        else:
            parts.append(f"Config issues: {', '.join(config_issues)}")
        s = result.get("state", {})
        parts.append(f"Uploaded: {s.get('uploaded', '?')}/{s.get('total_processed', '?')}")
        la = result.get("log", {}).get("last_action", "unknown")
        parts.append(f"Last action: {la}")
        result["summary"] = " | ".join(parts)
        return {"status": "OK", "data": result}
