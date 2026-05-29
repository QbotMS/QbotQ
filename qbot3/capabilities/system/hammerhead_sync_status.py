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

from qbot3.capabilities.base import Capability, CapabilityDef, PROMOTION_ACTIVE, SAFETY_READ_ONLY_FILE


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
            safety_class=SAFETY_READ_ONLY_FILE,
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

        try:
            if HAMMERHEAD_TOKENS.is_file():
                result["hammerhead_tokens"] = "present"
            else:
                config_issues.append("hammerhead tokens missing")
        except PermissionError:
            result["hammerhead_tokens"] = "restricted"
            config_issues.append("hammerhead tokens restricted (permission)")

        try:
            if GARMIN_TOKENS.is_file():
                result["garmin_tokens"] = "present"
            else:
                config_issues.append("garmin tokens missing")
        except PermissionError:
            result["garmin_tokens"] = "restricted"
            config_issues.append(f"garmin tokens restricted (permission) — path: {GARMIN_TOKENS.parent}")

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

        # 3. Log tail — auxiliary only, never overrides current state
        log_info: dict[str, Any] = {"exists": LOG_FILE.is_file()}
        if LOG_FILE.is_file():
            try:
                lines = LOG_FILE.read_text().splitlines()
                log_info["total_lines"] = len(lines)
                # Find last run line and its status
                previous_run_status = None
                previous_run_at = None
                previous_run_note = None
                for line in reversed(lines):
                    if "qbot-hammerhead-sync" in line and ("failed" in line or "done" in line):
                        previous_run_at = line[:25]  # timestamp
                        previous_run_note = line.strip()[:120]
                        if "failed" in line:
                            previous_run_status = "failed"
                        elif "done" in line:
                            previous_run_status = "done"
                        break
                log_info["previous_run_status"] = previous_run_status
                log_info["previous_run_at"] = previous_run_at
                log_info["previous_run_note"] = previous_run_note
                # Keep last few raw lines for debugging
                log_info["tail"] = lines[-5:] if len(lines) >= 5 else lines[:]
            except Exception as exc:
                log_info["error"] = str(exc)[:200]
        result["log"] = log_info

        # 4. Dry-run support and upload candidates
        result["dry_run_supported"] = True
        total_originals = len(list((OUTGOING_DIR / "hammerhead_originals").glob("*.fit"))) if OUTGOING_DIR.exists() else 0
        total_uploaded = result.get("state", {}).get("uploaded", 0)
        result["upload_candidates"] = max(0, total_originals - total_uploaded)

        # 5. Garmin DB sync status (cross-reference)
        garmin_db_status: dict[str, Any] = {"checked": False}
        try:
            import psycopg
            from psycopg.rows import dict_row
            import os
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=3,
            )
            cur = c.cursor()
            cur.execute("SELECT MAX(date) as last_date, MAX(imported_at) as last_sync FROM qbot_wellness_daily")
            row = cur.fetchone()
            if row and row.get("last_date"):
                garmin_db_status = {"checked": True, "last_garmin_data": str(row["last_date"]),
                                    "last_sync": str(row.get("last_sync", "")) if row.get("last_sync") else None}
            c.close()
        except Exception:
            garmin_db_status = {"checked": False, "error": "schema_incompatible"}
        result["garmin_db"] = garmin_db_status

        # 6. Overall health — derived from current state, not historical log
        s = result.get("state", {})
        total_processed = s.get("total_processed", 0)
        uploaded_count = s.get("uploaded", 0)
        failed_count = s.get("failed", 0)
        candidates = result.get("upload_candidates", 0)
        issues: list[str] = []
        if result.get("config_issues"):
            issues.append("config issues")
        if failed_count > 0:
            issues.append(f"{failed_count} failed")
        if candidates > 0:
            issues.append(f"{candidates} pending")
        health = "clean" if not issues else "; ".join(issues)

        # 7. Summary — state-first, log is auxiliary
        result["health"] = health
        parts = []
        if health == "clean":
            parts.append("State OK")
        else:
            parts.append(f"State: {health}")
        parts.append(f"Uploaded: {uploaded_count}/{total_processed}")
        parts.append(f"Candidates: {candidates}")
        parts.append(f"Failed: {failed_count}")
        parts.append(f"Dry-run: {'✅' if result.get('dry_run_supported') else '❌'}")

        # Log info is auxiliary, not primary
        log_prev = result.get("log", {})
        prev_status = log_prev.get("previous_run_status")
        prev_at = log_prev.get("previous_run_at")
        if prev_status:
            # Only show as warning if state also shows issues
            if health != "clean" and prev_status == "failed":
                parts.append(f"Previous run: FAILED at {prev_at[:19] if prev_at else '?'}")
            else:
                # Historical — not current
                parts.append(f"Previous run: {prev_status} ({prev_at[:19] if prev_at else '?'}, historical)")

        if garmin_db_status.get("last_garmin_data"):
            parts.append(f"Garmin DB: {garmin_db_status['last_garmin_data']}")

        result["summary"] = " | ".join(parts)
        return {"status": "OK", "data": result}
