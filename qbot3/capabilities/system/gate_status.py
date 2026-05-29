#!/usr/bin/env python3
"""Internal capability: gate_status — safe read-only gate diagnostics.

Production path:
  domena (qbot.cytr.us) -> Cloudflare -> nginx:20181 -> /gate/status
  -> qbot-qlab-server:8899 -> gate_hikconnect.py -> HikConnect API

SAFE: only reads /gate/status endpoint (config + last-success timestamp).
Never calls /gate/open, never sends unlock command, never authenticates to HikConnect.
dry_run=true is the only mode — this capability never performs real unlock.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from qbot3.capabilities.base import Capability, CapabilityDef, PROMOTION_ACTIVE, SAFETY_READ_ONLY


# Local endpoint (nginx -> qbot-qlab-server). Safe: only reads config, never unlocks.
GATE_STATUS_LOCAL = "http://127.0.0.1:8899/gate/status"
# Public domain endpoint (Cloudflare -> nginx:20181 -> qlab-server:8899).
GATE_STATUS_PUBLIC = "https://qbot.cytr.us/gate/status"


class GateStatusCapability(Capability):
    def manifest(self) -> CapabilityDef:
        return CapabilityDef(
            name="gate_status",
            description="Gate (HikConnect) configuration and last-success status. "
                       "Tylko odczyt — nie otwiera furtki. "
                       "Production path: qbot.cytr.us -> nginx -> qbot-qlab-server -> HikConnect. "
                       "Ngrok był historyczny/testowy, nie aktualny.",
            safety_class=SAFETY_READ_ONLY,
            capability_type="READ_ONLY_API",
            data_sources=[
                "http://127.0.0.1:8899/gate/status",
                "https://qbot.cytr.us/gate/status",
            ],
            promotion_state=PROMOTION_ACTIVE,
            inputs_schema={
                "dry_run": {"type": "boolean", "description": "always true — this capability never unlocks"}
            },
            output_schema={
                "type": "object",
                "properties": {
                    "service_ok": {"type": "boolean"},
                    "status": {"type": "object"},
                    "production_path": {"type": "string"},
                },
            },
            reason_existing_insufficient="No existing tool reads gate status from the separate qlab-server service",
        )

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Read /gate/status. Never calls /gate/open — pure dry-run."""
        result: dict[str, Any] = {
            "service_ok": False,
            "dry_run": True,
            "production_path": "qbot.cytr.us -> nginx:20181 -> qbot-qlab-server:8899 -> gate_hikconnect.py -> HikConnect API",
        }

        # Try local first, then public
        urls = [GATE_STATUS_LOCAL, GATE_STATUS_PUBLIC]
        response_data = None
        source_url = None
        for url in urls:
            try:
                r = httpx.get(url, timeout=5)
                if r.status_code == 200:
                    response_data = r.json()
                    source_url = url
                    break
            except Exception:
                continue

        if response_data:
            result["service_ok"] = True
            result["source"] = source_url
            result["status"] = {
                "mode": response_data.get("mode", "unknown"),
                "token_configured": response_data.get("tokenConfigured", False),
                "credentials_configured": response_data.get("hikconnectCredentialsConfigured", False),
                "device_configured": response_data.get("deviceConfigured", False),
                "rate_limit_sec": response_data.get("rateLimitSec"),
                "last_success_at_utc": response_data.get("lastSuccessAtUtc"),
                "last_success_age_sec": response_data.get("lastSuccessAgeSec"),
                "local_only": response_data.get("localOnly", False),
                "bridge_configured": response_data.get("legacyBridgeConfigured", False),
            }
        else:
            result["error"] = "gate/status unreachable from local and public endpoints"

        parts = ["GATE STATUS (dry-run, no unlock)"]
        if result.get("service_ok"):
            s = result["status"]
            parts.append(f"Mode: {s['mode']}")
            parts.append(f"Token: {'configured' if s['token_configured'] else 'MISSING'}")
            parts.append(f"Creds: {'configured' if s['credentials_configured'] else 'MISSING'}")
            parts.append(f"Device: {'configured' if s['device_configured'] else 'MISSING'}")
            ls = s.get("last_success_at_utc")
            parts.append(f"Last unlock: {ls if ls else 'never'}")
            parts.append(f"Rate limit: {s['rate_limit_sec']}s")
        else:
            parts.append(f"UNREACHABLE: {result.get('error')}")
        result["summary"] = " | ".join(parts)
        return {"status": "OK", "data": result}
