#!/usr/bin/env python3
"""Internal capability: withings_sync_status (15.10.2026).

Status synchronizacji Withings -> Garmin (waga, sklad ciala, cisnienie): program qbot-withings-sync (cron root),
stan state/processed_withings_measures.json, alarm state/withings_sync_alert_state.json (istnieje = ostatnia proba nieudana).
Logika w qbot_status_checks.withings() (to samo zrodlo co SETUP > Polaczenia > Status). Tylko odczyt.
"""
from __future__ import annotations

from typing import Any

from qbot3.capabilities.base import Capability, CapabilityDef, PROMOTION_ACTIVE, SAFETY_READ_ONLY_FILE


class WithingsSyncStatusCapability(Capability):
    def manifest(self) -> CapabilityDef:
        return CapabilityDef(
            name="withings_sync_status",
            description="Status synchronizacji Withings -> Garmin (waga, sklad ciala, cisnienie): ostatnio wyslane pomiary, alarm awarii. Tylko odczyt.",
            safety_class=SAFETY_READ_ONLY_FILE,
            capability_type="READ_ONLY_FILE",
            data_sources=["state/processed_withings_measures.json", "state/withings_sync_alert_state.json"],
            promotion_state=PROMOTION_ACTIVE,
            inputs_schema={},
            output_schema={"type": "object", "properties": {"state": {"type": "string"}, "text": {"type": "string"}}},
            reason_existing_insufficient="Albert nie widzi stanu programu synchronizacji Withings (cron root).",
        )

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from qbot_status_checks import withings
        r = withings()
        data = dict(r, summary=r["text"])
        return {"status": "OK", "data": data, "summary": r["text"]}
