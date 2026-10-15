#!/usr/bin/env python3
"""Internal capability: hammerhead_sync_status (przepisane 15.10.2026).

Status AKTUALNEJ synchronizacji Hammerhead (Karoo) -> Garmin (jazdy wgrywane jako TACX):
program qbot-hammerhead-sync co 10 min, stan state/processed_hammerhead_activities.json,
log logs/hammerhead-garmin-sync.log, pliki outgoing/garmin_proxy.
Stary mechanizm per-profil (michal/user2/user3, state/michal_*.json) zakonczyl prace 26.07.2026 -- NIE czytac.
Logika w qbot_status_checks.hammerhead() (to samo zrodlo co SETUP > Polaczenia > Status).
Tylko odczyt.
"""
from __future__ import annotations

from typing import Any

from qbot3.capabilities.base import Capability, CapabilityDef, PROMOTION_ACTIVE, SAFETY_READ_ONLY_FILE


class HammerheadSyncStatusCapability(Capability):
    def manifest(self) -> CapabilityDef:
        return CapabilityDef(
            name="hammerhead_sync_status",
            description="Status synchronizacji Hammerhead (Karoo) -> Garmin (jazdy jako TACX): ostatnia przeslana jazda, ostatnie sprawdzenie, bledy. Tylko odczyt.",
            safety_class=SAFETY_READ_ONLY_FILE,
            capability_type="READ_ONLY_FILE",
            data_sources=["state/processed_hammerhead_activities.json", "logs/hammerhead-garmin-sync.log"],
            promotion_state=PROMOTION_ACTIVE,
            inputs_schema={},
            output_schema={"type": "object", "properties": {"state": {"type": "string"}, "text": {"type": "string"}}},
            reason_existing_insufficient="Albert nie widzi stanu programu synchronizacji (cron root).",
        )

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from qbot_status_checks import hammerhead
        r = hammerhead()
        data = dict(r, summary=r["text"])
        return {"status": "OK", "data": data, "summary": r["text"]}
