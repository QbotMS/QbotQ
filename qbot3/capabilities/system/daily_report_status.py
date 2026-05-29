#!/usr/bin/env python3
"""Internal capability: daily_report_status.

Reads daily_report_sent.json and daily_report.log to report pipeline state.
READ_ONLY_FILE type — reads two local files, no side effects.
Promotion state: active (has tests, validated).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from qbot3.capabilities.base import Capability, CapabilityDef, PROMOTION_ACTIVE, SAFETY_READ_ONLY


_SENT_FILE = Path("/opt/qbot/app/data/daily_report_sent.json")
_LOG_FILE = Path("/opt/qbot/logs/daily_report.log")


class DailyReportStatusCapability(Capability):
    def manifest(self) -> CapabilityDef:
        return CapabilityDef(
            name="daily_report_status",
            description="Daily report pipeline status: pipeline stage, channel delivery, data source errors, legacy tool errors, sleep data wait status",
            safety_class=SAFETY_READ_ONLY,
            capability_type="READ_ONLY_FILE",
            data_sources=["daily_report_sent.json", "daily_report.log"],
            promotion_state=PROMOTION_ACTIVE,
            inputs_schema={},
            output_schema={
                "type": "object",
                "properties": {
                    "state": {"type": "object"},
                    "log_tail": {"type": "array"},
                    "recent_errors": {"type": "array"},
                    "legacy_tool_errors": {"type": "array"},
                    "waiting_for_sleep_data": {"type": "boolean"},
                    "summary": {"type": "string"},
                },
            },
            reason_existing_insufficient="No existing capability reads daily report pipeline state",
        )

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"date": date.today().isoformat()}

        try:
            if _SENT_FILE.is_file():
                state = json.loads(_SENT_FILE.read_text())
                result["state"] = {
                    "pipeline_stage": state.get("pipeline_stage", "unknown"),
                    "last_attempt_at": state.get("last_attempt_at", ""),
                    "data_sources": state.get("data_sources", {}),
                    "channels": state.get("channels", {}),
                    "last_error": state.get("last_error", ""),
                }
            else:
                result["state"] = {"pipeline_stage": "no_state_file"}
        except Exception as exc:
            result["state_error"] = str(exc)[:200]

        try:
            if _LOG_FILE.is_file():
                logs = _LOG_FILE.read_text().splitlines()
                recent = logs[-30:]
                errors = [l for l in recent if "mcp_call" in l or "error" in l.lower() or "Brak danych" in l]
                result["log_tail"] = recent[-10:]
                result["recent_errors"] = errors[-5:]
                waiting = any("czekam" in l for l in recent)
                legacy_tools = list(set(
                    l.split("mcp_call(")[1].split(")")[0] if "mcp_call(" in l else ""
                    for l in errors
                ))
                result["legacy_tool_errors"] = [t for t in legacy_tools if t]
                result["waiting_for_sleep_data"] = waiting
            else:
                result["log_error"] = "log file not found"
        except Exception as exc:
            result["log_error"] = str(exc)[:200]

        ch = result.get("state", {}).get("channels", {})
        result["summary"] = (
            f"Pipeline stage: {result.get('state', {}).get('pipeline_stage', 'unknown')}. "
            f"Telegram: {ch.get('telegram', 'not_attempted')}. "
            f"Email: {ch.get('email', 'not_attempted')}. "
            f"Legacy tool errors: {result.get('legacy_tool_errors', [])}. "
            f"Waiting for sleep: {result.get('waiting_for_sleep_data', False)}."
        )
        return {"status": "OK", "data": result}
